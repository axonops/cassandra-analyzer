"""
Infrastructure analyzer - checks hardware, OS, and deployment aspects
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional

from ..models import ClusterState, Recommendation, Severity
from .base import BaseAnalyzer


class InfrastructureAnalyzer(BaseAnalyzer):
    """Analyzes infrastructure aspects of the cluster"""

    category = "infrastructure"
    # Most infrastructure findings (down nodes, rack misconfiguration, single-DC
    # clusters) are reliability concerns. Call sites that emit capacity-shaped
    # findings (disk usage, CPU/memory pressure) override this with
    # ``recommendation_category="capacity"``.
    default_recommendation_category = "reliability"

    def _get_node_identifier(self, node) -> str:
        """Get a human-readable node identifier in hostname/ipaddress format"""
        hostname = node.Details.get("host_Hostname", "unknown")
        listen_address = node.Details.get("comp_listen_address", "unknown")
        return f"{hostname}/{listen_address}"

    def analyze(self, cluster_state: ClusterState) -> Dict[str, Any]:
        """Analyze infrastructure"""
        self._reset_checks()
        recommendations: List[Recommendation] = []
        details: Dict[str, Any] = {}

        recommendations.extend(self._analyze_nodes(cluster_state))
        recommendations.extend(self._analyze_resource_usage(cluster_state))
        recommendations.extend(self._analyze_topology(cluster_state))
        recommendations.extend(self._analyze_storage_configuration(cluster_state))
        recommendations.extend(self._analyze_vnodes_configuration(cluster_state))
        recommendations.extend(self._analyze_swap_configuration(cluster_state))
        recommendations.extend(self._analyze_system_configuration(cluster_state))

        summary = {
            "total_nodes": cluster_state.get_total_nodes(),
            "active_nodes": cluster_state.get_active_nodes(),
            "datacenters": cluster_state.get_datacenters(),
            "recommendations_count": len(recommendations),
        }

        return {
            "recommendations": [r.dict() for r in recommendations],
            "summary": summary,
            "details": details,
            "checks": [c.model_dump() for c in self._checks],
        }

    # ------------------------------------------------------------------ helpers

    def _record_pass_or_fail(
        self,
        check_id: str,
        description: str,
        data_source: str,
        rec: Optional[Recommendation],
        **context: Any,
    ) -> None:
        """Record fail (with rec id) when a recommendation was created, else pass."""
        if rec is None:
            self._record_check(check_id, description, data_source, "pass", **context)
        else:
            self._record_check(
                check_id, description, data_source, "fail",
                recommendation_id=rec.id, **context,
            )

    # ------------------------------------------------------------------ checks

    def _analyze_nodes(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze node configuration and health"""
        recommendations: List[Recommendation] = []

        total_nodes = cluster_state.get_total_nodes()
        active_nodes = cluster_state.get_active_nodes()

        rec: Optional[Recommendation] = None
        if total_nodes < 3:
            rec = self._create_recommendation(
                check_id="infra.nodes.count",
                title="Insufficient Node Count",
                description=f"Cluster has only {total_nodes} nodes. For production workloads, a minimum of 3 nodes is recommended.",
                severity=Severity.WARNING,
                category="infrastructure",
                impact="Reduced availability and potential data loss risk",
                recommendation="Add additional nodes to achieve at least 3 nodes per datacenter",
                total_nodes=total_nodes,
                component="Cluster Topology",
            )
            recommendations.append(rec)
        self._record_pass_or_fail(
            "infra.nodes.count",
            "Cluster has at least 3 nodes",
            "cluster.nodes",
            rec,
            total_nodes=total_nodes,
        )

        rec = None
        if active_nodes < total_nodes:
            down_nodes = total_nodes - active_nodes
            rec = self._create_recommendation(
                check_id="infra.nodes.health",
                title="Nodes Down",
                description=f"{down_nodes} out of {total_nodes} nodes are down",
                severity=Severity.CRITICAL,
                category="infrastructure",
                impact="Reduced cluster capacity and availability",
                recommendation="Investigate and restore down nodes",
                down_nodes=down_nodes,
                total_nodes=total_nodes,
                component="Cluster Health",
            )
            recommendations.append(rec)
        self._record_pass_or_fail(
            "infra.nodes.health",
            "All cluster nodes are reporting active",
            "cluster.nodes.status",
            rec,
            active_nodes=active_nodes,
            total_nodes=total_nodes,
        )

        return recommendations

    def _analyze_resource_usage(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze CPU, memory, and disk usage"""
        recommendations: List[Recommendation] = []

        # CPU
        avg_cpu = self._get_metric_average(cluster_state.metrics, "cpu_usage")
        if not cluster_state.metrics.get("cpu_usage"):
            self._record_check(
                "infra.cpu.usage",
                "Cluster-wide CPU usage is below the warn threshold",
                "metrics.cpu_usage",
                "no_data",
                skipped_reason="cpu_usage metric returned no samples",
            )
        else:
            rec: Optional[Recommendation] = None
            if avg_cpu > self.thresholds.cpu_usage_warn:
                severity = Severity.CRITICAL if avg_cpu > 90 else Severity.WARNING
                rec = self._create_recommendation(
                    check_id="infra.cpu.usage",
                    title="High CPU Usage",
                    description=f"Average CPU usage is {avg_cpu:.1f}%",
                    severity=severity,
                    category="infrastructure",
                    impact="Performance degradation and increased latency",
                    recommendation="Scale cluster or optimize workload",
                    cpu_usage=avg_cpu,
                    component="CPU",
                )
                recommendations.append(rec)
            self._record_pass_or_fail(
                "infra.cpu.usage",
                "Cluster-wide CPU usage is below the warn threshold",
                "metrics.cpu_usage",
                rec,
                avg_cpu=avg_cpu,
                threshold=self.thresholds.cpu_usage_warn,
            )

        # Memory
        avg_memory_percent = self._get_metric_average(cluster_state.metrics, "memory_usage_percent")
        if not cluster_state.metrics.get("memory_usage_percent"):
            self._record_check(
                "infra.memory.usage",
                "Cluster-wide memory usage is below the warn threshold",
                "metrics.memory_usage_percent",
                "no_data",
                skipped_reason="memory_usage_percent metric returned no samples",
            )
        else:
            rec = None
            if avg_memory_percent > self.thresholds.memory_usage_warn:
                rec = self._create_recommendation(
                    check_id="infra.memory.usage",
                    title="High Memory Usage",
                    description=f"Memory usage is {avg_memory_percent:.1f}%",
                    severity=Severity.WARNING,
                    category="infrastructure",
                    impact="Risk of OOM errors and node failures",
                    recommendation="Monitor memory usage and consider adding more memory",
                    memory_usage_percent=avg_memory_percent,
                    component="Memory",
                )
                recommendations.append(rec)
            self._record_pass_or_fail(
                "infra.memory.usage",
                "Cluster-wide memory usage is below the warn threshold",
                "metrics.memory_usage_percent",
                rec,
                avg_memory_percent=avg_memory_percent,
                threshold=self.thresholds.memory_usage_warn,
            )

        # Disk
        max_disk_usage = self._get_metric_max(cluster_state.metrics, "disk_usage_percent")
        if not cluster_state.metrics.get("disk_usage_percent"):
            self._record_check(
                "infra.disk.usage",
                "Per-node disk usage is below the warn threshold",
                "metrics.disk_usage_percent",
                "no_data",
                skipped_reason="disk_usage_percent metric returned no samples",
            )
        else:
            rec = None
            if max_disk_usage > self.thresholds.disk_usage_warn:
                severity = Severity.CRITICAL if max_disk_usage > 90 else Severity.WARNING
                rec = self._create_recommendation(
                    check_id="infra.disk.usage",
                    title="High Disk Usage",
                    description=f"Disk usage is {max_disk_usage:.1f}%",
                    severity=severity,
                    category="infrastructure",
                    impact="Risk of running out of disk space",
                    recommendation="Add disk space or clean up data",
                    disk_usage_percent=max_disk_usage,
                    component="Storage",
                )
                recommendations.append(rec)
            self._record_pass_or_fail(
                "infra.disk.usage",
                "Per-node disk usage is below the warn threshold",
                "metrics.disk_usage_percent",
                rec,
                max_disk_usage=max_disk_usage,
                threshold=self.thresholds.disk_usage_warn,
            )

        return recommendations

    def _analyze_topology(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze cluster topology and distribution"""
        recommendations: List[Recommendation] = []

        nodes_by_dc = cluster_state.get_nodes_by_dc()
        datacenters = cluster_state.get_datacenters()

        # DC count
        rec: Optional[Recommendation] = None
        if len(datacenters) == 1:
            rec = self._create_recommendation(
                check_id="infra.topology.dc.count",
                title="Single Datacenter Deployment",
                description="Cluster is deployed in a single datacenter",
                severity=Severity.INFO,
                category="infrastructure",
                impact="No protection against datacenter-level failures",
                recommendation="Consider multi-datacenter deployment for high availability",
                datacenters=datacenters,
                component="Datacenter Topology",
            )
            recommendations.append(rec)
        self._record_pass_or_fail(
            "infra.topology.dc.count",
            "Cluster spans more than one datacenter",
            "cluster.nodes.dc",
            rec,
            datacenters=datacenters,
        )

        # DC balance — only meaningful with multiple DCs
        if len(datacenters) > 1:
            dc_rack_nodes = defaultdict(lambda: defaultdict(list))
            for dc, nodes in nodes_by_dc.items():
                for node in nodes:
                    rack = node.rack if node.rack else "default"
                    dc_rack_nodes[dc][rack].append(node)

            node_counts = [len(nodes) for nodes in nodes_by_dc.values()]
            min_nodes = min(node_counts)
            max_nodes = max(node_counts)

            rec = None
            if max_nodes > min_nodes * 2 or (max_nodes - min_nodes) > 10:
                dc_distribution = {dc: len(nodes) for dc, nodes in nodes_by_dc.items()}

                rack_info = []
                for dc, racks in dc_rack_nodes.items():
                    num_racks = len(racks)
                    nodes_per_rack = [len(nodes) for nodes in racks.values()]
                    rack_balance = (
                        "balanced"
                        if max(nodes_per_rack) - min(nodes_per_rack) <= 1
                        else "unbalanced"
                    )
                    rack_info.append(f"{dc}: {num_racks} racks ({rack_balance})")

                rec = self._create_recommendation(
                    check_id="infra.topology.dc.balance",
                    title="Unbalanced Datacenter Distribution",
                    description=f"Significant variance in node count across datacenters (min: {min_nodes}, max: {max_nodes})",
                    severity=Severity.WARNING,
                    category="infrastructure",
                    impact="May lead to uneven workload distribution and potential data availability issues",
                    recommendation="Consider the replication factor and rack topology when planning node distribution. Each DC should have nodes as multiples of its rack count",
                    current_value=f"DC distribution: {dc_distribution}",
                    datacenter_distribution=dc_distribution,
                    rack_distribution="; ".join(rack_info),
                    min_nodes=min_nodes,
                    max_nodes=max_nodes,
                    component="Datacenter Topology",
                    recommended_value="Balanced distribution based on RF and rack topology",
                )
                recommendations.append(rec)
            self._record_pass_or_fail(
                "infra.topology.dc.balance",
                "Node counts across datacenters are within balance tolerance",
                "cluster.nodes.dc",
                rec,
                min_nodes=min_nodes,
                max_nodes=max_nodes,
            )
        else:
            self._record_check(
                "infra.topology.dc.balance",
                "Node counts across datacenters are within balance tolerance",
                "cluster.nodes.dc",
                "skipped",
                skipped_reason="single-DC cluster — DC balance check not applicable",
            )

        # Rack configuration
        dc_rack_nodes = defaultdict(lambda: defaultdict(list))
        for node in cluster_state.nodes.values():
            dc = node.DC if node.DC else "default"
            rack = node.rack if node.rack else "default"
            dc_rack_nodes[dc][rack].append(node)

        rack_config_recs: List[Recommendation] = []
        rack_count_recs: List[Recommendation] = []
        rack_balance_recs: List[Recommendation] = []

        for dc, racks in dc_rack_nodes.items():
            num_racks = len(racks)
            total_nodes_in_dc = sum(len(nodes) for nodes in racks.values())

            typical_rf = 3
            for ks_name, ks in cluster_state.keyspaces.items():
                if not ks_name.startswith("system"):
                    if hasattr(ks, "strategy_options") and isinstance(ks.strategy_options, dict):
                        if "replication_factor" in ks.strategy_options:
                            try:
                                typical_rf = int(ks.strategy_options["replication_factor"])
                                break
                            except (ValueError, TypeError):
                                pass
                        elif dc in ks.strategy_options:
                            try:
                                typical_rf = int(ks.strategy_options[dc])
                                break
                            except (ValueError, TypeError):
                                pass

            if num_racks == 1 or all(rack == "default" for rack in racks.keys()):
                if total_nodes_in_dc >= typical_rf:
                    rec = self._create_recommendation(
                        check_id="infra.topology.rack.config",
                        title=f"No Rack Configuration in {dc}",
                        description=f"Datacenter {dc} has {total_nodes_in_dc} nodes but no rack configuration",
                        severity=Severity.WARNING,
                        category="infrastructure",
                        impact="Cannot perform rack-aware maintenance. Entire datacenter must be considered a failure domain",
                        recommendation=f"Configure {typical_rf} racks (equal to RF={typical_rf}) to allow maintenance of entire racks",
                        current_value=f"{num_racks} rack(s)",
                        datacenter=dc,
                        node_count=total_nodes_in_dc,
                        typical_rf=typical_rf,
                        component="Rack Topology",
                        recommended_value=f"{typical_rf} racks",
                        config_location="cassandra-rackdc.properties",
                    )
                    recommendations.append(rec)
                    rack_config_recs.append(rec)
            elif num_racks != typical_rf:
                if num_racks < typical_rf:
                    impact = "Cannot guarantee data availability when an entire rack is down for maintenance"
                    severity = Severity.WARNING
                else:
                    impact = "More racks than RF may lead to uneven data distribution"
                    severity = Severity.INFO

                rec = self._create_recommendation(
                    check_id="infra.topology.rack.count",
                    title=f"Suboptimal Rack Count in {dc}",
                    description=f"Datacenter {dc} has {num_racks} racks but RF is {typical_rf}",
                    severity=severity,
                    category="infrastructure",
                    impact=impact,
                    recommendation=f"Configure exactly {typical_rf} racks to match RF for optimal fault tolerance",
                    current_value=f"{num_racks} racks",
                    datacenter=dc,
                    rack_count=num_racks,
                    typical_rf=typical_rf,
                    component="Rack Topology",
                    recommended_value=f"{typical_rf} racks",
                    config_location="cassandra-rackdc.properties",
                )
                recommendations.append(rec)
                rack_count_recs.append(rec)

            if num_racks > 1:
                nodes_per_rack = [len(nodes) for nodes in racks.values()]
                min_nodes_per_rack = min(nodes_per_rack)
                max_nodes_per_rack = max(nodes_per_rack)
                if max_nodes_per_rack - min_nodes_per_rack > 1:
                    rack_distribution = {rack: len(nodes) for rack, nodes in racks.items()}
                    rec = self._create_recommendation(
                        check_id="infra.topology.rack.balance",
                        title=f"Unbalanced Rack Distribution in {dc}",
                        description=f"Datacenter {dc} has uneven node distribution across racks",
                        severity=Severity.WARNING,
                        category="infrastructure",
                        impact="Uneven workload distribution and potential hotspots",
                        recommendation="Balance nodes evenly across racks",
                        current_value=f"Rack distribution: {rack_distribution}",
                        datacenter=dc,
                        rack_distribution=rack_distribution,
                        min_nodes_per_rack=min_nodes_per_rack,
                        max_nodes_per_rack=max_nodes_per_rack,
                        component="Rack Topology",
                        config_location="cassandra-topology.properties",
                    )
                    recommendations.append(rec)
                    rack_balance_recs.append(rec)

        # Aggregate per-DC findings into one Check per check_id.
        if rack_config_recs:
            self._record_check(
                "infra.topology.rack.config",
                "Each DC has rack configuration set",
                "cluster.nodes.rack",
                "fail",
                affected_dcs=[r.context.get("datacenter") for r in rack_config_recs],
            )
        else:
            self._record_check(
                "infra.topology.rack.config",
                "Each DC has rack configuration set",
                "cluster.nodes.rack",
                "pass",
            )

        if rack_count_recs:
            self._record_check(
                "infra.topology.rack.count",
                "Per-DC rack count matches the typical replication factor",
                "cluster.nodes.rack",
                "fail",
                affected_dcs=[r.context.get("datacenter") for r in rack_count_recs],
            )
        else:
            self._record_check(
                "infra.topology.rack.count",
                "Per-DC rack count matches the typical replication factor",
                "cluster.nodes.rack",
                "pass",
            )

        if rack_balance_recs:
            self._record_check(
                "infra.topology.rack.balance",
                "Nodes are balanced across racks within each DC",
                "cluster.nodes.rack",
                "fail",
                affected_dcs=[r.context.get("datacenter") for r in rack_balance_recs],
            )
        else:
            self._record_check(
                "infra.topology.rack.balance",
                "Nodes are balanced across racks within each DC",
                "cluster.nodes.rack",
                "pass",
            )

        return recommendations

    def _analyze_storage_configuration(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze storage configuration based on AxonOps disk data"""
        recommendations: List[Recommendation] = []

        fstype_data_seen = False
        fstype_fail_nodes: List[str] = []
        root_usage_seen = False
        root_usage_fail_nodes: List[str] = []
        data_usage_seen = False
        data_usage_fail_nodes: List[str] = []

        for node in cluster_state.nodes.values():
            data_fstype = node.Details.get("host_disk_/srv/cassandra_fstype")

            if data_fstype:
                fstype_data_seen = True
                if data_fstype != "xfs":
                    fstype_fail_nodes.append(node.host_id)
                    recommendations.append(
                        self._create_recommendation(
                            check_id="infra.storage.fs.data",
                            title=f"Suboptimal Data Filesystem: {data_fstype}",
                            description=f"Node {self._get_node_identifier(node)} uses {data_fstype} for data directory",
                            severity=Severity.WARNING,
                            category="infrastructure",
                            impact="Potential performance degradation with non-XFS filesystem",
                            recommendation="Consider using XFS filesystem for Cassandra data directories",
                            node_id=node.host_id,
                            current_fstype=data_fstype,
                            component="Storage",
                        )
                    )

            root_total = node.Details.get("host_disk_/_Total")
            root_used = node.Details.get("host_disk_/_Used")
            data_total = node.Details.get("host_disk_/srv/cassandra_Total")
            data_used = node.Details.get("host_disk_/srv/cassandra_Used")

            if root_total and root_used:
                try:
                    root_usage_pct = (int(root_used) / int(root_total)) * 100
                    root_usage_seen = True
                    if root_usage_pct > 90:
                        root_usage_fail_nodes.append(node.host_id)
                        recommendations.append(
                            self._create_recommendation(
                                check_id="infra.storage.disk.root_usage",
                                title="High Root Disk Usage",
                                description=f"Node {self._get_node_identifier(node)} root disk is {root_usage_pct:.1f}% full",
                                severity=Severity.CRITICAL,
                                category="infrastructure",
                                impact="Risk of system instability",
                                recommendation="Free up root disk space immediately",
                                node_id=node.host_id,
                                usage_percent=root_usage_pct,
                                component="Storage",
                            )
                        )
                    elif root_usage_pct > 80:
                        root_usage_fail_nodes.append(node.host_id)
                        recommendations.append(
                            self._create_recommendation(
                                check_id="infra.storage.disk.root_usage",
                                title="Moderate Root Disk Usage",
                                description=f"Node {self._get_node_identifier(node)} root disk is {root_usage_pct:.1f}% full",
                                severity=Severity.WARNING,
                                category="infrastructure",
                                impact="Approaching disk space limits",
                                recommendation="Monitor and clean up root disk space",
                                node_id=node.host_id,
                                usage_percent=root_usage_pct,
                                component="Storage",
                            )
                        )
                except (ValueError, TypeError):
                    pass

            if data_total and data_used:
                try:
                    data_usage_pct = (int(data_used) / int(data_total)) * 100
                    data_usage_seen = True
                    if data_usage_pct > 85:
                        data_usage_fail_nodes.append(node.host_id)
                        recommendations.append(
                            self._create_recommendation(
                                check_id="infra.storage.disk.data_usage",
                                title="High Data Disk Usage",
                                description=f"Node {self._get_node_identifier(node)} data disk is {data_usage_pct:.1f}% full",
                                severity=Severity.CRITICAL,
                                category="infrastructure",
                                impact="Risk of write failures and compaction issues",
                                recommendation="Add disk capacity or run cleanup operations",
                                node_id=node.host_id,
                                usage_percent=data_usage_pct,
                                component="Storage",
                            )
                        )
                    elif data_usage_pct > 70:
                        data_usage_fail_nodes.append(node.host_id)
                        recommendations.append(
                            self._create_recommendation(
                                check_id="infra.storage.disk.data_usage",
                                title="Moderate Data Disk Usage",
                                description=f"Node {self._get_node_identifier(node)} data disk is {data_usage_pct:.1f}% full",
                                severity=Severity.WARNING,
                                category="infrastructure",
                                impact="Approaching storage capacity limits",
                                recommendation="Plan for additional storage capacity",
                                node_id=node.host_id,
                                usage_percent=data_usage_pct,
                                component="Storage",
                            )
                        )
                except (ValueError, TypeError):
                    pass

        if not fstype_data_seen:
            self._record_check(
                "infra.storage.fs.data",
                "Data directory uses XFS filesystem",
                "host_disk_*/_fstype",
                "no_data",
                skipped_reason="host_disk_/srv/cassandra_fstype not reported by any node",
            )
        elif fstype_fail_nodes:
            self._record_check(
                "infra.storage.fs.data",
                "Data directory uses XFS filesystem",
                "host_disk_*/_fstype",
                "fail",
                affected_nodes=fstype_fail_nodes,
            )
        else:
            self._record_check(
                "infra.storage.fs.data",
                "Data directory uses XFS filesystem",
                "host_disk_*/_fstype",
                "pass",
            )

        if not root_usage_seen:
            self._record_check(
                "infra.storage.disk.root_usage",
                "Root disk usage is below the warn threshold",
                "host_disk_/_Total / host_disk_/_Used",
                "no_data",
                skipped_reason="root disk usage not reported by any node",
            )
        elif root_usage_fail_nodes:
            self._record_check(
                "infra.storage.disk.root_usage",
                "Root disk usage is below the warn threshold",
                "host_disk_/_Total / host_disk_/_Used",
                "fail",
                affected_nodes=root_usage_fail_nodes,
            )
        else:
            self._record_check(
                "infra.storage.disk.root_usage",
                "Root disk usage is below the warn threshold",
                "host_disk_/_Total / host_disk_/_Used",
                "pass",
            )

        if not data_usage_seen:
            self._record_check(
                "infra.storage.disk.data_usage",
                "Data directory disk usage is below the warn threshold",
                "host_disk_/srv/cassandra_Total / _Used",
                "no_data",
                skipped_reason="data directory disk usage not reported by any node",
            )
        elif data_usage_fail_nodes:
            self._record_check(
                "infra.storage.disk.data_usage",
                "Data directory disk usage is below the warn threshold",
                "host_disk_/srv/cassandra_Total / _Used",
                "fail",
                affected_nodes=data_usage_fail_nodes,
            )
        else:
            self._record_check(
                "infra.storage.disk.data_usage",
                "Data directory disk usage is below the warn threshold",
                "host_disk_/srv/cassandra_Total / _Used",
                "pass",
            )

        return recommendations

    def _analyze_vnodes_configuration(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze virtual nodes configuration"""
        recommendations: List[Recommendation] = []

        vnodes_configs: Dict[str, List[str]] = {}
        for node in cluster_state.nodes.values():
            num_tokens = node.Details.get("comp_num_tokens")
            if num_tokens:
                vnodes_configs.setdefault(num_tokens, []).append(node.host_id)

        if not vnodes_configs:
            self._record_check(
                "infra.vnodes.consistency",
                "All nodes report a consistent num_tokens value",
                "comp_num_tokens",
                "no_data",
                skipped_reason="comp_num_tokens not reported by any node",
            )
            self._record_check(
                "infra.vnodes.count",
                "num_tokens is within the recommended range (≤32)",
                "comp_num_tokens",
                "no_data",
                skipped_reason="comp_num_tokens not reported by any node",
            )
            return recommendations

        rec: Optional[Recommendation] = None
        if len(vnodes_configs) > 1:
            rec = self._create_recommendation(
                check_id="infra.vnodes.consistency",
                title="Inconsistent VNodes Configuration",
                description=f"Different num_tokens values across cluster: {list(vnodes_configs.keys())}",
                severity=Severity.CRITICAL,
                category="infrastructure",
                impact="Uneven data distribution and operational complexity",
                recommendation="Ensure all nodes have the same num_tokens value",
                vnodes_configs=vnodes_configs,
                component="Virtual Nodes",
            )
            recommendations.append(rec)
        self._record_pass_or_fail(
            "infra.vnodes.consistency",
            "All nodes report a consistent num_tokens value",
            "comp_num_tokens",
            rec,
            distinct_values=list(vnodes_configs.keys()),
        )

        count_fail = False
        for num_tokens, nodes in vnodes_configs.items():
            try:
                tokens_val = int(num_tokens)
                if tokens_val == 1:
                    continue
                if tokens_val > 48:
                    severity = Severity.CRITICAL
                    impact = "Excessive virtual nodes cause operational overhead and slower repairs"
                    recommendation = "Reduce num_tokens to 32 or less for better operational efficiency"
                elif tokens_val > 32:
                    severity = Severity.WARNING
                    impact = "High vnode count may impact repair and streaming performance"
                    recommendation = "Consider reducing num_tokens to 32 or less"
                else:
                    continue
                count_fail = True
                recommendations.append(
                    self._create_recommendation(
                        check_id="infra.vnodes.count",
                        title=f"High VNodes Count: {tokens_val}",
                        description=f"Nodes have {tokens_val} virtual nodes (num_tokens)",
                        severity=severity,
                        category="infrastructure",
                        impact=impact,
                        recommendation=recommendation,
                        current_value=f"{tokens_val} vnodes",
                        num_tokens=tokens_val,
                        affected_nodes=nodes,
                        component="Virtual Nodes",
                    )
                )
            except (ValueError, TypeError):
                pass
        self._record_check(
            "infra.vnodes.count",
            "num_tokens is within the recommended range (≤32)",
            "comp_num_tokens",
            "fail" if count_fail else "pass",
        )

        return recommendations

    def _analyze_swap_configuration(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze swap configuration"""
        recommendations: List[Recommendation] = []

        swappiness_seen = False
        swappiness_fail: List[str] = []
        swap_usage_seen = False
        swap_usage_fail: List[str] = []
        swap_enabled_seen = False
        swap_enabled_fail: List[str] = []

        for node in cluster_state.nodes.values():
            swappiness = node.Details.get("host_sysctl_vm.swappiness")
            if swappiness is not None:
                try:
                    swappiness_val = int(swappiness)
                    swappiness_seen = True
                    if swappiness_val > 1:
                        swappiness_fail.append(node.host_id)
                        recommendations.append(
                            self._create_recommendation(
                                check_id="infra.swap.swappiness",
                                title="High vm.swappiness Setting",
                                description=f"Node {self._get_node_identifier(node)} has vm.swappiness={swappiness_val}",
                                severity=Severity.WARNING,
                                category="infrastructure",
                                impact="Cassandra may swap to disk causing severe performance degradation",
                                recommendation="Set vm.swappiness=1 in /etc/sysctl.conf or /etc/sysctl.d/ and run 'sysctl -p'",
                                current_value=str(swappiness_val),
                                node_id=node.host_id,
                                current_swappiness=swappiness_val,
                                component="Memory",
                                recommended_value="1",
                                config_location="/etc/sysctl.conf or /etc/sysctl.d/",
                            )
                        )
                except (ValueError, TypeError):
                    pass

            swap_free = node.Details.get("host_swapmem_Free")
            swap_total = node.Details.get("host_swapmem_Total")
            if swap_total and swap_free:
                try:
                    total_val = int(swap_total)
                    free_val = int(swap_free)
                    swap_usage_seen = True
                    if total_val > 0:
                        swap_used_pct = ((total_val - free_val) / total_val) * 100
                        if swap_used_pct > 5:
                            swap_usage_fail.append(node.host_id)
                            recommendations.append(
                                self._create_recommendation(
                                    check_id="infra.swap.usage",
                                    title="Swap Usage Detected",
                                    description=f"Node {self._get_node_identifier(node)} is using {swap_used_pct:.1f}% of swap space",
                                    severity=Severity.CRITICAL,
                                    category="infrastructure",
                                    impact="Severe performance degradation when Cassandra swaps",
                                    recommendation="Disable swap or ensure sufficient memory to avoid swapping",
                                    node_id=node.host_id,
                                    swap_usage_percent=swap_used_pct,
                                    component="Memory",
                                )
                            )

                        swap_enabled_seen = True
                        if total_val > 1024 * 1024:
                            swap_enabled_fail.append(node.host_id)
                            recommendations.append(
                                self._create_recommendation(
                                    check_id="infra.swap.enabled",
                                    title="Swap Enabled",
                                    description=f"Node {self._get_node_identifier(node)} has {total_val/1024/1024:.0f}MB swap configured",
                                    severity=Severity.WARNING,
                                    category="infrastructure",
                                    impact="Potential for performance issues if swap is used",
                                    recommendation="Consider disabling swap entirely for Cassandra nodes",
                                    current_value=f"{total_val/1024/1024:.0f}MB swap",
                                    node_id=node.host_id,
                                    swap_size_mb=total_val / 1024 / 1024,
                                    component="Memory",
                                    recommended_value="0MB swap",
                                )
                            )
                except (ValueError, TypeError):
                    pass

        for check_id, description, source, seen, fails in (
            (
                "infra.swap.swappiness",
                "vm.swappiness ≤ 1",
                "host_sysctl_vm.swappiness",
                swappiness_seen,
                swappiness_fail,
            ),
            (
                "infra.swap.usage",
                "Active swap usage is below 5%",
                "host_swapmem_Free / host_swapmem_Total",
                swap_usage_seen,
                swap_usage_fail,
            ),
            (
                "infra.swap.enabled",
                "Swap is disabled (no swap configured)",
                "host_swapmem_Total",
                swap_enabled_seen,
                swap_enabled_fail,
            ),
        ):
            if not seen:
                self._record_check(
                    check_id, description, source, "no_data",
                    skipped_reason=f"{source} not reported by any node",
                )
            elif fails:
                self._record_check(
                    check_id, description, source, "fail",
                    affected_nodes=fails,
                )
            else:
                self._record_check(check_id, description, source, "pass")

        return recommendations

    def _analyze_system_configuration(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze system configuration parameters"""
        recommendations: List[Recommendation] = []

        max_map_seen = False
        max_map_fail: List[str] = []

        sysctl_state: Dict[str, Dict[str, Any]] = {
            "net.core.rmem_max": {"min_value": 16777216, "description": "socket receive buffer", "component": "Network", "seen": False, "fail": []},
            "net.core.wmem_max": {"min_value": 16777216, "description": "socket send buffer", "component": "Network", "seen": False, "fail": []},
            "net.core.netdev_max_backlog": {"min_value": 5000, "description": "network device backlog", "component": "Network", "seen": False, "fail": []},
        }

        for node in cluster_state.nodes.values():
            max_map_count = node.Details.get("host_sysctl_vm.max_map_count")
            if max_map_count is not None:
                try:
                    max_map_val = int(max_map_count)
                    max_map_seen = True
                    if max_map_val < 1048575:
                        max_map_fail.append(node.host_id)
                        recommendations.append(
                            self._create_recommendation(
                                check_id="infra.system.max_map_count",
                                title="Low vm.max_map_count Setting",
                                description=f"Node {self._get_node_identifier(node)} has vm.max_map_count={max_map_val}",
                                severity=Severity.CRITICAL,
                                category="infrastructure",
                                impact="Cassandra may fail to start or experience memory mapping issues",
                                recommendation="Set vm.max_map_count=1048575 in /etc/sysctl.conf or /etc/sysctl.d/ and run 'sysctl -p'",
                                node_id=node.host_id,
                                current_value=str(max_map_val),
                                recommended_value=1048575,
                                component="Memory",
                                config_location="/etc/sysctl.conf or /etc/sysctl.d/",
                            )
                        )
                except (ValueError, TypeError):
                    pass

            for sysctl_name, config in sysctl_state.items():
                sysctl_key = f"host_sysctl_{sysctl_name}"
                current_value = node.Details.get(sysctl_key)
                if current_value is None:
                    continue
                try:
                    current_val = int(current_value)
                    config["seen"] = True
                    if current_val < config["min_value"]:
                        config["fail"].append(node.host_id)
                        recommendations.append(
                            self._create_recommendation(
                                check_id=f"infra.system.sysctl.{sysctl_name.replace('.', '_')}",
                                title=f"Low {sysctl_name} Setting",
                                description=f"Node {self._get_node_identifier(node)} has {sysctl_name}={current_val}",
                                severity=Severity.WARNING,
                                category="infrastructure",
                                impact=f"Suboptimal {config['description']} configuration",
                                recommendation=f"Set {sysctl_name}={config['min_value']} in /etc/sysctl.conf or /etc/sysctl.d/ and run 'sysctl -p'",
                                node_id=node.host_id,
                                current_value=str(current_val),
                                sysctl_value=current_val,
                                recommended_value=config["min_value"],
                                component=config["component"],
                                config_location="/etc/sysctl.conf or /etc/sysctl.d/",
                            )
                        )
                except (ValueError, TypeError):
                    pass

        if not max_map_seen:
            self._record_check(
                "infra.system.max_map_count",
                "vm.max_map_count meets the Cassandra minimum (1048575)",
                "host_sysctl_vm.max_map_count",
                "no_data",
                skipped_reason="host_sysctl_vm.max_map_count not reported by any node",
            )
        elif max_map_fail:
            self._record_check(
                "infra.system.max_map_count",
                "vm.max_map_count meets the Cassandra minimum (1048575)",
                "host_sysctl_vm.max_map_count",
                "fail",
                affected_nodes=max_map_fail,
            )
        else:
            self._record_check(
                "infra.system.max_map_count",
                "vm.max_map_count meets the Cassandra minimum (1048575)",
                "host_sysctl_vm.max_map_count",
                "pass",
            )

        for sysctl_name, config in sysctl_state.items():
            cid = f"infra.system.sysctl.{sysctl_name.replace('.', '_')}"
            if not config["seen"]:
                self._record_check(
                    cid,
                    f"{sysctl_name} ≥ {config['min_value']}",
                    f"host_sysctl_{sysctl_name}",
                    "no_data",
                    skipped_reason=f"host_sysctl_{sysctl_name} not reported by any node",
                )
            elif config["fail"]:
                self._record_check(
                    cid,
                    f"{sysctl_name} ≥ {config['min_value']}",
                    f"host_sysctl_{sysctl_name}",
                    "fail",
                    affected_nodes=config["fail"],
                )
            else:
                self._record_check(
                    cid,
                    f"{sysctl_name} ≥ {config['min_value']}",
                    f"host_sysctl_{sysctl_name}",
                    "pass",
                )

        return recommendations
