"""
Infrastructure analyzer - checks hardware, OS, and deployment aspects
"""

from typing import Dict, Any, List
from ..models import ClusterState, Recommendation, Severity
from .base import BaseAnalyzer


class InfrastructureAnalyzer(BaseAnalyzer):
    """Analyzes infrastructure aspects of the cluster"""
    
    def _get_node_identifier(self, node) -> str:
        """Get a human-readable node identifier in hostname/ipaddress format"""
        hostname = node.Details.get("host_Hostname", "unknown")
        listen_address = node.Details.get("comp_listen_address", "unknown")
        return f"{hostname}/{listen_address}"
    
    def analyze(self, cluster_state: ClusterState) -> Dict[str, Any]:
        """Analyze infrastructure"""
        recommendations = []
        summary = {}
        details = {}
        
        # Analyze node configuration
        recommendations.extend(self._analyze_nodes(cluster_state))
        
        # Analyze resource usage
        recommendations.extend(self._analyze_resource_usage(cluster_state))
        
        # Analyze cluster topology
        recommendations.extend(self._analyze_topology(cluster_state))
        
        # Analyze storage configuration
        recommendations.extend(self._analyze_storage_configuration(cluster_state))
        
        # Analyze virtual nodes configuration
        recommendations.extend(self._analyze_vnodes_configuration(cluster_state))
        
        # Analyze swap configuration
        recommendations.extend(self._analyze_swap_configuration(cluster_state))
        
        # Analyze system configuration
        recommendations.extend(self._analyze_system_configuration(cluster_state))
        
        # Create summary
        summary = {
            "total_nodes": cluster_state.get_total_nodes(),
            "active_nodes": cluster_state.get_active_nodes(),
            "datacenters": cluster_state.get_datacenters(),
            "recommendations_count": len(recommendations)
        }
        
        return {
            "recommendations": [r.dict() for r in recommendations],
            "summary": summary,
            "details": details
        }
    
    def _analyze_nodes(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze node configuration and health"""
        recommendations = []
        
        # Check for insufficient nodes
        total_nodes = cluster_state.get_total_nodes()
        if total_nodes < 3:
            recommendations.append(
                self._create_recommendation(
                    title="Insufficient Node Count",
                    description=f"Cluster has only {total_nodes} nodes. For production workloads, a minimum of 3 nodes is recommended.",
                    severity=Severity.WARNING,
                    category="infrastructure",
                    impact="Reduced availability and potential data loss risk",
                    recommendation="Add additional nodes to achieve at least 3 nodes per datacenter",
                    total_nodes=total_nodes,
                    component="Cluster Topology"
                )
            )
        
        # Check for down nodes
        active_nodes = cluster_state.get_active_nodes()
        if active_nodes < total_nodes:
            down_nodes = total_nodes - active_nodes
            recommendations.append(
                self._create_recommendation(
                    title="Nodes Down",
                    description=f"{down_nodes} out of {total_nodes} nodes are down",
                    severity=Severity.CRITICAL,
                    category="infrastructure",
                    impact="Reduced cluster capacity and availability",
                    recommendation="Investigate and restore down nodes",
                    down_nodes=down_nodes,
                    total_nodes=total_nodes,
                    component="Cluster Health"
                )
            )
        
        return recommendations
    
    def _analyze_resource_usage(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze CPU, memory, and disk usage"""
        recommendations = []
        
        # Check CPU usage
        avg_cpu = self._get_metric_average(cluster_state.metrics, "cpu_usage")
        if avg_cpu > self.thresholds.cpu_usage_warn:
            severity = Severity.CRITICAL if avg_cpu > 90 else Severity.WARNING
            recommendations.append(
                self._create_recommendation(
                    title="High CPU Usage",
                    description=f"Average CPU usage is {avg_cpu:.1f}%",
                    severity=severity,
                    category="infrastructure",
                    impact="Performance degradation and increased latency",
                    recommendation="Scale cluster or optimize workload",
                    cpu_usage=avg_cpu,
                    component="CPU"
                )
            )
        
        # Check memory usage (now as percentage)
        avg_memory_percent = self._get_metric_average(cluster_state.metrics, "memory_usage_percent")
        if avg_memory_percent > self.thresholds.memory_usage_warn:
            recommendations.append(
                self._create_recommendation(
                    title="High Memory Usage",
                    description=f"Memory usage is {avg_memory_percent:.1f}%",
                    severity=Severity.WARNING,
                    category="infrastructure",
                    impact="Risk of OOM errors and node failures",
                    recommendation="Monitor memory usage and consider adding more memory",
                    memory_usage_percent=avg_memory_percent,
                    component="Memory"
                )
            )
        
        # Check disk usage
        max_disk_usage = self._get_metric_max(cluster_state.metrics, "disk_usage_percent")
        if max_disk_usage > self.thresholds.disk_usage_warn:
            severity = Severity.CRITICAL if max_disk_usage > 90 else Severity.WARNING
            recommendations.append(
                self._create_recommendation(
                    title="High Disk Usage",
                    description=f"Disk usage is {max_disk_usage:.1f}%",
                    severity=severity,
                    category="infrastructure",
                    impact="Risk of running out of disk space",
                    recommendation="Add disk space or clean up data",
                    disk_usage_percent=max_disk_usage,
                    component="Storage"
                )
            )
        
        return recommendations
    
    def _analyze_topology(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze cluster topology and distribution"""
        recommendations = []
        
        # Check datacenter distribution
        nodes_by_dc = cluster_state.get_nodes_by_dc()
        datacenters = cluster_state.get_datacenters()
        
        if len(datacenters) == 1:
            recommendations.append(
                self._create_recommendation(
                    title="Single Datacenter Deployment",
                    description="Cluster is deployed in a single datacenter",
                    severity=Severity.INFO,
                    category="infrastructure",
                    impact="No protection against datacenter-level failures",
                    recommendation="Consider multi-datacenter deployment for high availability",
                    datacenters=datacenters,
                    component="Datacenter Topology"
                )
            )
        else:
            # Analyze distribution across datacenters
            # Group nodes by datacenter and rack
            from collections import defaultdict
            dc_rack_nodes = defaultdict(lambda: defaultdict(list))
            
            for dc, nodes in nodes_by_dc.items():
                for node in nodes:
                    rack = node.rack if node.rack else 'default'
                    dc_rack_nodes[dc][rack].append(node)
            
            # Calculate node counts and check for significant imbalances
            node_counts = [len(nodes) for nodes in nodes_by_dc.values()]
            min_nodes = min(node_counts)
            max_nodes = max(node_counts)
            
            # Only warn about significant imbalances:
            # - More than 2x difference in node count
            # - Or more than 10 nodes difference
            if max_nodes > min_nodes * 2 or (max_nodes - min_nodes) > 10:
                dc_distribution = {dc: len(nodes) for dc, nodes in nodes_by_dc.items()}
                
                # Build detailed rack information
                rack_info = []
                for dc, racks in dc_rack_nodes.items():
                    num_racks = len(racks)
                    nodes_per_rack = [len(nodes) for nodes in racks.values()]
                    rack_balance = "balanced" if max(nodes_per_rack) - min(nodes_per_rack) <= 1 else "unbalanced"
                    rack_info.append(f"{dc}: {num_racks} racks ({rack_balance})")
                
                recommendations.append(
                    self._create_recommendation(
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
                        recommended_value="Balanced distribution based on RF and rack topology"
                    )
                )
        
        # Analyze rack configuration
        # Group all nodes by datacenter and rack regardless of DC count
        from collections import defaultdict
        dc_rack_nodes = defaultdict(lambda: defaultdict(list))
        
        for node in cluster_state.nodes.values():
            dc = node.DC if node.DC else 'default'
            rack = node.rack if node.rack else 'default'
            dc_rack_nodes[dc][rack].append(node)
        
        # Check rack configuration for each datacenter
        for dc, racks in dc_rack_nodes.items():
            num_racks = len(racks)
            total_nodes_in_dc = sum(len(nodes) for nodes in racks.values())
            
            # Get the typical replication factor from keyspaces
            # We'll look at non-system keyspaces to determine RF
            typical_rf = 3  # Default assumption
            for ks_name, ks in cluster_state.keyspaces.items():
                if not ks_name.startswith('system'):
                    # Try to extract RF from replication strategy
                    if hasattr(ks, 'strategy_options') and isinstance(ks.strategy_options, dict):
                        if 'replication_factor' in ks.strategy_options:
                            try:
                                typical_rf = int(ks.strategy_options['replication_factor'])
                                break
                            except (ValueError, TypeError):
                                pass
                        elif dc in ks.strategy_options:
                            try:
                                typical_rf = int(ks.strategy_options[dc])
                                break
                            except (ValueError, TypeError):
                                pass
            
            # Check if rack configuration is optimal
            if num_racks == 1 or all(rack == 'default' for rack in racks.keys()):
                # No rack awareness configured
                if total_nodes_in_dc >= typical_rf:
                    recommendations.append(
                        self._create_recommendation(
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
                            config_location="cassandra-rackdc.properties"
                        )
                    )
            elif num_racks != typical_rf:
                # Suboptimal rack count
                if num_racks < typical_rf:
                    impact = "Cannot guarantee data availability when an entire rack is down for maintenance"
                    severity = Severity.WARNING
                else:
                    impact = "More racks than RF may lead to uneven data distribution"
                    severity = Severity.INFO
                
                recommendations.append(
                    self._create_recommendation(
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
                        config_location="cassandra-rackdc.properties"
                    )
                )
            
            # Check rack balance
            if num_racks > 1:
                nodes_per_rack = [len(nodes) for nodes in racks.values()]
                min_nodes_per_rack = min(nodes_per_rack)
                max_nodes_per_rack = max(nodes_per_rack)
                
                if max_nodes_per_rack - min_nodes_per_rack > 1:
                    rack_distribution = {rack: len(nodes) for rack, nodes in racks.items()}
                    recommendations.append(
                        self._create_recommendation(
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
                            config_location="cassandra-topology.properties"
                        )
                    )
        
        return recommendations
    
    def _analyze_storage_configuration(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze storage configuration based on AxonOps disk data"""
        recommendations = []
        
        for node in cluster_state.nodes.values():
            # Check filesystem types from host_disk_*_fstype
            root_fstype = node.Details.get("host_disk_/_fstype")
            data_fstype = node.Details.get("host_disk_/srv/cassandra_fstype")
            
            # Recommend XFS for data directories
            if data_fstype and data_fstype != "xfs":
                recommendations.append(
                    self._create_recommendation(
                        title=f"Suboptimal Data Filesystem: {data_fstype}",
                        description=f"Node {self._get_node_identifier(node)} uses {data_fstype} for data directory",
                        severity=Severity.WARNING,
                        category="infrastructure",
                        impact="Potential performance degradation with non-XFS filesystem",
                        recommendation="Consider using XFS filesystem for Cassandra data directories",
                        node_id=node.host_id,
                        current_fstype=data_fstype,
                        component="Storage"
                    )
                )
            
            # Check disk usage levels
            root_total = node.Details.get("host_disk_/_Total")
            root_used = node.Details.get("host_disk_/_Used")
            data_total = node.Details.get("host_disk_/srv/cassandra_Total")
            data_used = node.Details.get("host_disk_/srv/cassandra_Used")
            
            # Calculate usage percentages
            if root_total and root_used:
                try:
                    root_usage_pct = (int(root_used) / int(root_total)) * 100
                    if root_usage_pct > 90:
                        recommendations.append(
                            self._create_recommendation(
                                title="High Root Disk Usage",
                                description=f"Node {self._get_node_identifier(node)} root disk is {root_usage_pct:.1f}% full",
                                severity=Severity.CRITICAL,
                                category="infrastructure",
                                impact="Risk of system instability",
                                recommendation="Free up root disk space immediately",
                                node_id=node.host_id,
                                usage_percent=root_usage_pct,
                                component="Storage"
                            )
                        )
                    elif root_usage_pct > 80:
                        recommendations.append(
                            self._create_recommendation(
                                title="Moderate Root Disk Usage",
                                description=f"Node {self._get_node_identifier(node)} root disk is {root_usage_pct:.1f}% full",
                                severity=Severity.WARNING,
                                category="infrastructure",
                                impact="Approaching disk space limits",
                                recommendation="Monitor and clean up root disk space",
                                node_id=node.host_id,
                                usage_percent=root_usage_pct,
                                component="Storage"
                            )
                        )
                except (ValueError, TypeError):
                    pass
            
            if data_total and data_used:
                try:
                    data_usage_pct = (int(data_used) / int(data_total)) * 100
                    if data_usage_pct > 85:
                        recommendations.append(
                            self._create_recommendation(
                                title="High Data Disk Usage",
                                description=f"Node {self._get_node_identifier(node)} data disk is {data_usage_pct:.1f}% full",
                                severity=Severity.CRITICAL,
                                category="infrastructure",
                                impact="Risk of write failures and compaction issues",
                                recommendation="Add disk capacity or run cleanup operations",
                                node_id=node.host_id,
                                usage_percent=data_usage_pct,
                                component="Storage"
                            )
                        )
                    elif data_usage_pct > 70:
                        recommendations.append(
                            self._create_recommendation(
                                title="Moderate Data Disk Usage",
                                description=f"Node {self._get_node_identifier(node)} data disk is {data_usage_pct:.1f}% full",
                                severity=Severity.WARNING,
                                category="infrastructure",
                                impact="Approaching storage capacity limits",
                                recommendation="Plan for additional storage capacity",
                                node_id=node.host_id,
                                usage_percent=data_usage_pct,
                                component="Storage"
                            )
                        )
                except (ValueError, TypeError):
                    pass
        
        return recommendations
    
    def _analyze_vnodes_configuration(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze virtual nodes configuration"""
        recommendations = []
        
        vnodes_configs = {}
        for node in cluster_state.nodes.values():
            num_tokens = node.Details.get("comp_num_tokens")
            if num_tokens:
                if num_tokens not in vnodes_configs:
                    vnodes_configs[num_tokens] = []
                vnodes_configs[num_tokens].append(node.host_id)
        
        # Check for vnodes consistency
        if len(vnodes_configs) > 1:
            recommendations.append(
                self._create_recommendation(
                    title="Inconsistent VNodes Configuration",
                    description=f"Different num_tokens values across cluster: {list(vnodes_configs.keys())}",
                    severity=Severity.CRITICAL,
                    category="infrastructure",
                    impact="Uneven data distribution and operational complexity",
                    recommendation="Ensure all nodes have the same num_tokens value",
                    vnodes_configs=vnodes_configs,
                    component="Virtual Nodes"
                )
            )
        
        # Check for recommended vnodes values
        for num_tokens, nodes in vnodes_configs.items():
            try:
                tokens_val = int(num_tokens)
                # Skip if tokens_val is 1 (not using vnodes)
                if tokens_val == 1:
                    continue
                    
                # Check thresholds: >48 is critical, >32 is warning
                if tokens_val > 48:
                    severity = Severity.CRITICAL
                    impact = "Excessive virtual nodes cause operational overhead and slower repairs"
                    recommendation = "Reduce num_tokens to 32 or less for better operational efficiency"
                elif tokens_val > 32:
                    severity = Severity.WARNING
                    impact = "High vnode count may impact repair and streaming performance"
                    recommendation = "Consider reducing num_tokens to 32 or less"
                else:
                    # 32 or less is acceptable, skip
                    continue
                    
                recommendations.append(
                    self._create_recommendation(
                        title=f"High VNodes Count: {tokens_val}",
                        description=f"Nodes have {tokens_val} virtual nodes (num_tokens)",
                        severity=severity,
                        category="infrastructure",
                        impact=impact,
                        recommendation=recommendation,
                        current_value=f"{tokens_val} vnodes",
                        num_tokens=tokens_val,
                        affected_nodes=nodes,
                        component="Virtual Nodes"
                    )
                )
            except (ValueError, TypeError):
                pass
        
        return recommendations
    
    def _analyze_swap_configuration(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze swap configuration"""
        recommendations = []
        
        for node in cluster_state.nodes.values():
            # Check swappiness setting
            swappiness = node.Details.get("host_sysctl_vm.swappiness")
            if swappiness:
                try:
                    swappiness_val = int(swappiness)
                    if swappiness_val > 1:
                        recommendations.append(
                            self._create_recommendation(
                                title="High VM Swappiness Setting",
                                description=f"Node {self._get_node_identifier(node)} has vm.swappiness={swappiness_val}",
                                severity=Severity.WARNING,
                                category="infrastructure",
                                impact="Cassandra may swap to disk causing severe performance degradation",
                                recommendation="Set vm.swappiness=1 in /etc/sysctl.conf or /etc/sysctl.d/ and run 'sysctl -p'",
                                current_value=f"vm.swappiness={swappiness_val}",
                                node_id=node.host_id,
                                current_swappiness=swappiness_val,
                                component="Memory",
                                recommended_value="vm.swappiness=1",
                                config_location="/etc/sysctl.conf or /etc/sysctl.d/"
                            )
                        )
                except (ValueError, TypeError):
                    pass
            
            # Check swap usage
            swap_free = node.Details.get("host_swapmem_Free")
            swap_total = node.Details.get("host_swapmem_Total")
            if swap_total and swap_free:
                try:
                    total_val = int(swap_total)
                    free_val = int(swap_free)
                    if total_val > 0:
                        swap_used_pct = ((total_val - free_val) / total_val) * 100
                        if swap_used_pct > 5:
                            recommendations.append(
                                self._create_recommendation(
                                    title="Swap Usage Detected",
                                    description=f"Node {self._get_node_identifier(node)} is using {swap_used_pct:.1f}% of swap space",
                                    severity=Severity.CRITICAL,
                                    category="infrastructure",
                                    impact="Severe performance degradation when Cassandra swaps",
                                    recommendation="Disable swap or ensure sufficient memory to avoid swapping",
                                    node_id=node.host_id,
                                    swap_usage_percent=swap_used_pct,
                                    component="Memory"
                                )
                            )
                        
                        # Recommend disabling swap entirely
                        if total_val > 1024 * 1024:  # More than 1MB swap configured
                            recommendations.append(
                                self._create_recommendation(
                                    title="Swap Enabled",
                                    description=f"Node {self._get_node_identifier(node)} has {total_val/1024/1024:.0f}MB swap configured",
                                    severity=Severity.WARNING,
                                    category="infrastructure",
                                    impact="Potential for performance issues if swap is used",
                                    recommendation="Consider disabling swap entirely for Cassandra nodes",
                                    current_value=f"{total_val/1024/1024:.0f}MB swap",
                                    node_id=node.host_id,
                                    swap_size_mb=total_val/1024/1024,
                                    component="Memory",
                                    recommended_value="0MB swap"
                                )
                            )
                except (ValueError, TypeError):
                    pass
        
        return recommendations
    
    def _analyze_system_configuration(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze system configuration parameters"""
        recommendations = []
        
        for node in cluster_state.nodes.values():
            # Check vm.max_map_count (should be >= 1048575 for Cassandra)
            max_map_count = node.Details.get("host_sysctl_vm.max_map_count")
            if max_map_count:
                try:
                    max_map_val = int(max_map_count)
                    if max_map_val < 1048575:
                        recommendations.append(
                            self._create_recommendation(
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
                                config_location="/etc/sysctl.conf or /etc/sysctl.d/"
                            )
                        )
                except (ValueError, TypeError):
                    pass
            
            # Check other important kernel parameters available in AxonOps
            important_sysctls = {
                "net.core.rmem_max": {"min_value": 16777216, "description": "socket receive buffer", "component": "Network"},
                "net.core.wmem_max": {"min_value": 16777216, "description": "socket send buffer", "component": "Network"},
                "net.core.netdev_max_backlog": {"min_value": 5000, "description": "network device backlog", "component": "Network"},
            }
            
            for sysctl_name, config in important_sysctls.items():
                sysctl_key = f"host_sysctl_{sysctl_name}"
                current_value = node.Details.get(sysctl_key)
                if current_value:
                    try:
                        current_val = int(current_value)
                        if current_val < config["min_value"]:
                            recommendations.append(
                                self._create_recommendation(
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
                                    config_location="/etc/sysctl.conf or /etc/sysctl.d/"
                                )
                            )
                    except (ValueError, TypeError):
                        pass
        
        return recommendations