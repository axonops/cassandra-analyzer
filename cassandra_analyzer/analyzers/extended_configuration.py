"""
Extended configuration analyzers implementing additional configuration checks
"""

from typing import Dict, Any, List, Optional
import structlog
from ..models import ClusterState, Recommendation, Severity
from .base import BaseAnalyzer

logger = structlog.get_logger()


class ExtendedConfigurationAnalyzer(BaseAnalyzer):
    """Extended configuration analyzer implementing additional checks"""
    
    def _get_node_identifier(self, node) -> str:
        """Get a human-readable node identifier in hostname/ipaddress format"""
        hostname = node.Details.get("host_Hostname", "unknown")
        listen_address = node.Details.get("comp_listen_address", "unknown")
        return f"{hostname}/{listen_address}"
    
    def analyze(self, cluster_state: ClusterState) -> Dict[str, Any]:
        """Analyze extended configuration settings"""
        recommendations = []
        summary = {}
        details = {}
        
        # Compaction settings analysis
        recommendations.extend(self._analyze_compaction_settings(cluster_state))
        
        # Disk failure policy analysis
        recommendations.extend(self._analyze_disk_failure_policy(cluster_state))
        
        # Memtable storage analysis
        recommendations.extend(self._analyze_memtable_settings(cluster_state))
        
        # Snitch configuration analysis
        recommendations.extend(self._analyze_snitch_configuration(cluster_state))
        
        # Seeds configuration analysis
        recommendations.extend(self._analyze_seeds_configuration(cluster_state))
        
        # Streaming settings analysis
        recommendations.extend(self._analyze_streaming_settings(cluster_state))
        
        # Version analysis
        recommendations.extend(self._analyze_version_consistency(cluster_state))
        
        # Thread pool settings analysis (concurrent_reads/writes)
        recommendations.extend(self._analyze_thread_pool_settings(cluster_state))
        
        # Authentication cache settings analysis
        recommendations.extend(self._analyze_auth_cache_settings(cluster_state))
        
        # Create summary
        summary = {
            "recommendations_count": len(recommendations),
            "extended_checks_performed": 9
        }
        
        return {
            "recommendations": [r.dict() for r in recommendations],
            "summary": summary,
            "details": details
        }
    
    def _analyze_compaction_settings(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze compaction configuration settings"""
        recommendations = []
        
        for node in cluster_state.nodes.values():
            # Check compaction throughput
            throughput = node.Details.get("comp_compaction_throughput_mb_per_sec", 16)
            concurrent_compactors = node.Details.get("comp_concurrent_compactors", 2)
            
            try:
                throughput_val = int(throughput)
                compactors_val = int(concurrent_compactors)
                
                # Calculate throughput per compactor
                if compactors_val > 0:
                    throughput_per_compactor = throughput_val / compactors_val
                    
                    # When throughput is at default AND results in low per-compactor throughput,
                    # create a single combined recommendation
                    if throughput_val == 16 and throughput_per_compactor < 8:
                        recommendations.append(
                            self._create_recommendation(
                                title="Conservative Compaction Throughput with High Concurrency (compaction_throughput_mb_per_sec, concurrent_compactors)",
                                description=f"Node {self._get_node_identifier(node)} uses default 16 MB/s throughput with {compactors_val} compactors, resulting in only {throughput_per_compactor:.1f} MB/s per compactor",
                                severity=Severity.WARNING,
                                category="configuration",
                                impact="Default throughput spread across many compactors may cause compaction to lag behind writes",
                                recommendation="Increase compaction_throughput_mb_per_sec to 64 MB/s or reduce concurrent_compactors in cassandra.yaml",
                                current_value=f"compaction_throughput_mb_per_sec={throughput_val} MB/s, concurrent_compactors={compactors_val}",
                                node_id=node.host_id,
                                compaction_throughput_mb_per_sec=throughput_val,
                                concurrent_compactors=compactors_val,
                                recommended_value="64 MB/s throughput or fewer compactors",
                                config_location="cassandra.yaml"
                            )
                        )
                    # Only create low throughput per compactor warning if NOT at default
                    elif throughput_val != 16 and throughput_per_compactor < 8:
                        recommendations.append(
                            self._create_recommendation(
                                title="Low Compaction Throughput Per Compactor (compaction_throughput_mb_per_sec, concurrent_compactors)",
                                description=f"Node {self._get_node_identifier(node)} has {throughput_per_compactor:.1f} MB/s per compactor",
                                severity=Severity.WARNING,
                                category="configuration",
                                impact="Compaction may lag behind writes causing read performance issues",
                                recommendation="Increase compaction_throughput_mb_per_sec or reduce concurrent_compactors in cassandra.yaml",
                                current_value=f"compaction_throughput_mb_per_sec={throughput_val} MB/s, concurrent_compactors={compactors_val}",
                                node_id=node.host_id,
                                compaction_throughput_mb_per_sec=throughput_val,
                                concurrent_compactors=compactors_val,
                                recommended_value="≥8 MB/s per compactor",
                                config_location="cassandra.yaml"
                            )
                        )
                    # Only create conservative throughput warning if throughput per compactor is OK
                    elif throughput_val == 16 and throughput_per_compactor >= 8:
                        recommendations.append(
                            self._create_recommendation(
                                title="Conservative Compaction Throughput (compaction_throughput_mb_per_sec)",
                                description=f"Node {self._get_node_identifier(node)} uses default 16 MB/s compaction throughput",
                                severity=Severity.INFO,
                                category="configuration",
                                impact="May not utilize available I/O capacity for compaction",
                                recommendation="Consider increasing compaction_throughput_mb_per_sec to 64 MB/s for modern hardware in cassandra.yaml",
                                current_value="compaction_throughput_mb_per_sec=16 MB/s",
                                node_id=node.host_id,
                                compaction_throughput_mb_per_sec=throughput_val,
                                recommended_value="64 MB/s",
                                config_location="cassandra.yaml"
                            )
                        )
                
                # Check for unthrottled compaction
                if throughput_val == 0:
                    recommendations.append(
                        self._create_recommendation(
                            title="Unthrottled Compaction (compaction_throughput_mb_per_sec)",
                            description=f"Node {self._get_node_identifier(node)} has unlimited compaction throughput",
                            severity=Severity.WARNING,
                            category="configuration",
                            impact="May overwhelm I/O and affect read/write performance",
                            recommendation="Set reasonable compaction throughput limit in cassandra.yaml",
                            current_value="compaction_throughput_mb_per_sec=0 MB/s (unlimited)",
                            node_id=node.host_id,
                            compaction_throughput_mb_per_sec=throughput_val,
                            recommended_value="64-128 MB/s",
                            config_location="cassandra.yaml"
                        )
                    )
                
                # Check for unusually high values
                if throughput_val > 200:
                    recommendations.append(
                        self._create_recommendation(
                            title="Very High Compaction Throughput (compaction_throughput_mb_per_sec)",
                            description=f"Node {self._get_node_identifier(node)} has {throughput_val} MB/s compaction throughput",
                            severity=Severity.WARNING,
                            category="configuration",
                            impact="May overwhelm I/O bandwidth",
                            recommendation="Verify this setting is appropriate for your hardware in cassandra.yaml",
                            current_value=f"compaction_throughput_mb_per_sec={throughput_val} MB/s",
                            node_id=node.host_id,
                            compaction_throughput_mb_per_sec=throughput_val,
                            config_location="cassandra.yaml"
                        )
                    )
                
            except (ValueError, TypeError):
                # Handle non-numeric values
                pass
        
        return recommendations
    
    def _analyze_disk_failure_policy(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze disk failure policy configuration"""
        recommendations = []
        
        disk_policies = {}
        commit_policies = {}
        
        for node in cluster_state.nodes.values():
            disk_policy = node.Details.get("comp_disk_failure_policy", "stop")
            commit_policy = node.Details.get("comp_commit_failure_policy", "stop")
            
            if disk_policy not in disk_policies:
                disk_policies[disk_policy] = []
            disk_policies[disk_policy].append(node.host_id)
            
            if commit_policy not in commit_policies:
                commit_policies[commit_policy] = []
            commit_policies[commit_policy].append(node.host_id)
        
        # Check for best practice policies
        for policy, nodes in disk_policies.items():
            if policy not in ["stop", "die"]:
                recommendations.append(
                    self._create_recommendation(
                        title=f"Suboptimal Disk Failure Policy: {policy} (disk_failure_policy)",
                        description=f"Nodes using disk_failure_policy '{policy}': {nodes}",
                        severity=Severity.WARNING,
                        category="configuration",
                        impact="May not handle disk failures appropriately",
                        recommendation="Use 'stop' with auto-restart or 'die' for better monitoring in cassandra.yaml",
                        policy=policy,
                        affected_nodes=nodes,
                        config_location="cassandra.yaml"
                    )
                )
        
        # Check for policy consistency
        if len(disk_policies) > 1:
            recommendations.append(
                self._create_recommendation(
                    title="Inconsistent Disk Failure Policies (disk_failure_policy)",
                    description=f"Different disk failure policies across nodes: {list(disk_policies.keys())}",
                    severity=Severity.WARNING,
                    category="configuration",
                    impact="Inconsistent failure handling behavior",
                    recommendation="Standardize disk failure policy across all nodes in cassandra.yaml",
                    policies=list(disk_policies.keys()),
                    config_location="cassandra.yaml"
                )
            )
        
        return recommendations
    
    def _analyze_memtable_settings(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze memtable storage configuration"""
        recommendations = []
        
        for node in cluster_state.nodes.values():
            allocation_type = node.Details.get("comp_memtable_allocation_type", "heap_buffers")
            
            if allocation_type == "heap_buffers":
                # Check if version supports offheap_objects
                version = node.Details.get("comp_cassandra_version", "")
                if self._supports_offheap_objects(version):
                    recommendations.append(
                        self._create_recommendation(
                            title="Suboptimal Memtable Allocation Type (memtable_allocation_type)",
                            description=f"Node {self._get_node_identifier(node)} uses heap_buffers instead of offheap_objects",
                            severity=Severity.INFO,
                            category="configuration",
                            impact="Higher GC pressure and potential performance degradation",
                            recommendation="Consider using offheap_objects for better performance in cassandra.yaml",
                            current_value="memtable_allocation_type=heap_buffers",
                            node_id=node.host_id,
                            memtable_allocation_type=allocation_type,
                            recommended_value="offheap_objects",
                            config_location="cassandra.yaml"
                        )
                    )
            
            # Check memtable flush writers
            flush_writers = node.Details.get("comp_memtable_flush_writers")
            if flush_writers is not None:
                try:
                    flush_writers_val = int(flush_writers)
                    
                    # Calculate actual flush writers
                    if flush_writers_val == 0:
                        # When 0, uses min(8, num_cores / 2)
                        cpu_count = int(node.Details.get("host_CPU_ProcessorCount", 1))
                        actual_flush_writers = min(8, max(1, cpu_count // 2))
                    else:
                        actual_flush_writers = flush_writers_val
                    
                    # Only warn if the actual value is less than 2
                    if actual_flush_writers < 2:
                        recommendations.append(
                            self._create_recommendation(
                                title="Low Memtable Flush Writers (memtable_flush_writers)",
                                description=f"Node {self._get_node_identifier(node)} has only {actual_flush_writers} memtable flush writer",
                                severity=Severity.WARNING,
                                category="configuration",
                                impact="May bottleneck memtable flushing",
                                recommendation="Consider increasing to at least 2 flush writers in cassandra.yaml",
                                current_value=f"memtable_flush_writers={flush_writers_val} (actual: {actual_flush_writers})",
                                node_id=node.host_id,
                                memtable_flush_writers=actual_flush_writers,
                                recommended_value="≥2",
                                config_location="cassandra.yaml"
                            )
                        )
                except (ValueError, TypeError):
                    pass
        
        return recommendations
    
    def _analyze_snitch_configuration(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze endpoint snitch configuration"""
        recommendations = []
        
        problematic_snitches = [
            "SimpleSnitch",
            "PropertyFileSnitch", 
            "DseSimpleSnitch"
        ]
        
        for node in cluster_state.nodes.values():
            snitch = node.Details.get("comp_endpoint_snitch", "SimpleSnitch")
            
            if snitch in problematic_snitches:
                recommendations.append(
                    self._create_recommendation(
                        title=f"Problematic Endpoint Snitch: {snitch} (endpoint_snitch)",
                        description=f"Node {self._get_node_identifier(node)} uses {snitch}",
                        severity=Severity.WARNING,
                        category="configuration",
                        impact="Poor network topology awareness and performance",
                        recommendation="Use GossipingPropertyFileSnitch for better topology awareness in cassandra.yaml",
                        current_value=f"endpoint_snitch={snitch}",
                        node_id=node.host_id,
                        endpoint_snitch=snitch,
                        recommended_value="GossipingPropertyFileSnitch",
                        config_location="cassandra.yaml"
                    )
                )
        
        return recommendations
    
    def _analyze_seeds_configuration(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze seed node configuration"""
        recommendations = []
        
        # Extract seed configurations from nodes
        seed_lists = {}
        datacenter_nodes = {}
        
        for node in cluster_state.nodes.values():
            # Group nodes by datacenter
            dc = node.DC
            if dc not in datacenter_nodes:
                datacenter_nodes[dc] = []
            datacenter_nodes[dc].append(node.host_id)
            
            # Extract seed list (this would need to parse the seed_provider config)
            # For now, we'll check if seed config exists
            seed_provider = node.Details.get("comp_seed_provider")
            if seed_provider:
                seed_key = str(seed_provider)
                if seed_key not in seed_lists:
                    seed_lists[seed_key] = []
                seed_lists[seed_key].append(node.host_id)
        
        # Check seed consistency
        if len(seed_lists) > 1:
            recommendations.append(
                self._create_recommendation(
                    title="Inconsistent Seed Lists (seed_provider)",
                    description=f"Found {len(seed_lists)} different seed configurations",
                    severity=Severity.WARNING,
                    category="configuration",
                    impact="May complicate future node additions or replacements",
                    recommendation="Ensure all nodes have identical seed lists",
                    current_value=f"{len(seed_lists)} different configurations",
                    config_location="cassandra.yaml"
                )
            )
        
        # Check seed count per datacenter (should be at least 2)
        # Count actual seeds per DC
        seeds_per_dc = {}
        all_seeds = set()
        
        # First, extract all seed hostnames from any node's seed_provider
        for node in cluster_state.nodes.values():
            seed_provider = node.Details.get("comp_seed_provider", "")
            if seed_provider:
                # Parse seed provider string to extract seed hostnames
                # Format: "org.apache.cassandra.locator.SimpleSeedProvider{seeds=host1,host2,host3}"
                import re
                seeds_match = re.search(r'seeds=([^}]+)', seed_provider)
                if seeds_match:
                    seeds_str = seeds_match.group(1)
                    # Split by comma and clean up
                    seed_hostnames = [s.strip() for s in seeds_str.split(',')]
                    all_seeds.update(seed_hostnames)
                    
                    # Check for non-existent seed hostnames
                    # Collect all node hostnames in the cluster
                    node_hostnames = set()
                    for cluster_node in cluster_state.nodes.values():
                        node_hostname = cluster_node.Details.get("host_Hostname", "")
                        if node_hostname:
                            node_hostnames.add(node_hostname)
                    
                    # Check which seeds don't exist in the cluster
                    non_existent_seeds = []
                    for seed in seed_hostnames:
                        # Remove port if present
                        seed_host = seed.split(':')[0] if ':' in seed else seed
                        
                        # Check if this seed hostname exists in the cluster
                        if seed_host not in node_hostnames:
                            non_existent_seeds.append(seed)
                    
                    # Create recommendation for non-existent seeds
                    if non_existent_seeds:
                        recommendations.append(
                            self._create_recommendation(
                                title="Non-existent Seed Hostnames",
                                description=f"Found {len(non_existent_seeds)} seed hostname(s) that don't exist in the cluster",
                                severity=Severity.CRITICAL,
                                category="configuration",
                                impact="Seeds are unreachable, preventing proper cluster formation and gossip propagation",
                                recommendation="Update seed list to use correct hostnames that exist in the cluster",
                                current_value=f"Invalid seeds: {', '.join(non_existent_seeds[:3])}{'...' if len(non_existent_seeds) > 3 else ''}",
                                non_existent_seeds=non_existent_seeds,
                                config_location="cassandra.yaml"
                            )
                        )
                    
                    break  # All nodes should have the same seed list
        
        # Now count seeds per DC by matching hostnames
        for node in cluster_state.nodes.values():
            dc = node.DC
            if dc not in seeds_per_dc:
                seeds_per_dc[dc] = 0
            
            # Check if this node is a seed by hostname
            node_hostname = node.Details.get("host_Hostname", "")
            if node_hostname:
                # Check for exact match first
                if node_hostname in all_seeds:
                    seeds_per_dc[dc] += 1
                else:
                    # Check if any seed matches this node's hostname pattern
                    # This handles cases where seed domains might be misconfigured
                    for seed in all_seeds:
                        # Extract the base hostname part (before first dot)
                        node_base = node_hostname.split('.')[0] if '.' in node_hostname else node_hostname
                        seed_base = seed.split('.')[0] if '.' in seed else seed
                        # If the base hostnames match, count it as a seed
                        if node_base == seed_base:
                            seeds_per_dc[dc] += 1
                            break
        
        # Now check if each DC has adequate seeds
        for dc, nodes in datacenter_nodes.items():
            seed_count = seeds_per_dc.get(dc, 0)
            if len(nodes) >= 3 and seed_count < 2:
                recommendations.append(
                    self._create_recommendation(
                        title=f"Insufficient Seeds in Datacenter {dc}",
                        description=f"Datacenter {dc} has only {seed_count} seed node(s)",
                        severity=Severity.WARNING,
                        category="configuration",
                        impact="Inadequate seed nodes may affect cluster discovery and gossip",
                        recommendation="Ensure at least 2 seeds per datacenter",
                        current_value=f"{seed_count} seeds",
                        datacenter=dc,
                        node_count=len(nodes),
                        seed_count=seed_count,
                        recommended_value="≥2 seeds",
                        config_location="cassandra.yaml"
                    )
                )
        
        return recommendations
    
    def _analyze_streaming_settings(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze data streaming configuration"""
        recommendations = []
        
        for node in cluster_state.nodes.values():
            # Check streaming throughput
            throughput = node.Details.get("comp_stream_throughput_outbound_megabits_per_sec", 200)
            timeout = node.Details.get("comp_streaming_socket_timeout_in_ms", 86400000)
            
            try:
                throughput_val = int(throughput)
                timeout_val = int(timeout)
                
                # Recommend keeping defaults unless there's a specific reason
                if throughput_val != 200:
                    recommendations.append(
                        self._create_recommendation(
                            title="Non-Default Streaming Throughput (stream_throughput_outbound_megabits_per_sec)",
                            description=f"Node {self._get_node_identifier(node)} has {throughput_val} Mb/s streaming throughput",
                            severity=Severity.INFO,
                            category="configuration",
                            impact="May affect repair and bootstrap performance",
                            recommendation="Default 200 Mb/s is usually optimal unless network capacity differs in cassandra.yaml",
                            current_value=f"stream_throughput_outbound_megabits_per_sec={throughput_val} Mb/s",
                            node_id=node.host_id,
                            stream_throughput_outbound_megabits_per_sec=throughput_val,
                            recommended_value="200 Mb/s",
                            config_location="cassandra.yaml"
                        )
                    )
                
                # Check timeout (should be 24 hours = 86400000ms)
                if timeout_val != 86400000:
                    recommendations.append(
                        self._create_recommendation(
                            title="Non-Default Streaming Timeout (streaming_socket_timeout_in_ms)",
                            description=f"Node {self._get_node_identifier(node)} has {timeout_val/1000/60/60:.1f} hour timeout",
                            severity=Severity.INFO,
                            category="configuration",
                            impact="May affect long-running streaming operations",
                            recommendation="Default 24 hour timeout is usually appropriate in cassandra.yaml",
                            current_value=f"streaming_socket_timeout_in_ms={timeout_val} ms ({timeout_val/1000/60/60:.1f} hours)",
                            node_id=node.host_id,
                            streaming_socket_timeout_in_ms=timeout_val,
                            recommended_value="86400000 ms (24 hours)",
                            config_location="cassandra.yaml"
                        )
                    )
                
            except (ValueError, TypeError):
                pass
        
        return recommendations
    
    def _analyze_version_consistency(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze Cassandra version consistency and support status"""
        recommendations = []
        
        versions = {}
        for node in cluster_state.nodes.values():
            version = node.Details.get("comp_cassandra_version", "unknown")
            if version not in versions:
                versions[version] = []
            versions[version].append(node.host_id)
        
        # Check version consistency
        if len(versions) > 1:
            recommendations.append(
                self._create_recommendation(
                    title="Inconsistent Cassandra Versions",
                    description=f"Multiple versions detected: {list(versions.keys())}",
                    severity=Severity.CRITICAL,
                    category="configuration",
                    impact="Mixed versions can cause compatibility issues",
                    recommendation="Upgrade all nodes to the same version",
                    versions=list(versions.keys()),
                    config_location="cassandra.yaml"
                )
            )
        
        # Check for unsupported versions
        for version, nodes in versions.items():
            if version != "unknown":
                if self._is_version_unsupported(version):
                    recommendations.append(
                        self._create_recommendation(
                            title=f"Unsupported Cassandra Version: {version}",
                            description=f"Nodes running unsupported version {version}: {nodes}",
                            severity=Severity.CRITICAL,
                            category="configuration",
                            impact="Security vulnerabilities and lack of support",
                            recommendation="Upgrade to Cassandra 4.x or latest supported version",
                            version=version,
                            affected_nodes=nodes,
                            config_location="cassandra.yaml"
                        )
                    )
        
        return recommendations
    
    def _supports_offheap_objects(self, version: str) -> bool:
        """Check if Cassandra version supports offheap_objects"""
        # Simplified version check - offheap_objects available in 2.1+
        try:
            if version and version != "unknown":
                major_version = float(version.split('.')[0] + '.' + version.split('.')[1])
                return major_version >= 2.1
        except (ValueError, IndexError):
            pass
        return True  # Default to True if version can't be parsed
    
    def _is_version_unsupported(self, version: str) -> bool:
        """Check if Cassandra version is unsupported"""
        # Simplified check - versions below 3.0 are generally unsupported
        try:
            if version and version != "unknown":
                major_version = float(version.split('.')[0] + '.' + version.split('.')[1])
                return major_version < 3.0
        except (ValueError, IndexError):
            pass
        return False  # Default to False if version can't be parsed
    
    def _analyze_thread_pool_settings(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze thread pool settings (concurrent_reads/writes) based on CPU count"""
        recommendations = []
        
        for node in cluster_state.nodes.values():
            # Get CPU count from host_cpu_CPU (last CPU ID, so add 1 for actual count)
            cpu_count = None
            
            # Primary method: use host_cpu_CPU parameter
            host_cpu = node.Details.get("host_cpu_CPU")
            if host_cpu is not None and host_cpu != "-1":
                try:
                    # host_cpu_CPU is the last CPU ID, so actual count is ID + 1
                    cpu_count = int(host_cpu) + 1
                except (ValueError, TypeError):
                    pass
            
            # Fallback: Try to get CPU count from JVM available processors
            if cpu_count is None:
                jvm_processors = node.Details.get("comp_jvm_cassandra.available_processors")
                if jvm_processors and jvm_processors != "-1":
                    try:
                        cpu_count = int(jvm_processors)
                    except (ValueError, TypeError):
                        pass
            
            # Get concurrent settings
            concurrent_reads = node.Details.get("comp_concurrent_reads")
            concurrent_writes = node.Details.get("comp_concurrent_writes")
            concurrent_counter_writes = node.Details.get("comp_concurrent_counter_writes")
            concurrent_materialized_view_writes = node.Details.get("comp_concurrent_materialized_view_writes")
            native_transport_max_threads = node.Details.get("comp_native_transport_max_threads")
            
            # Analyze concurrent_reads
            if concurrent_reads and cpu_count:
                try:
                    reads_val = int(concurrent_reads)
                    
                    # Recommended: 16 * num_cores per user requirement
                    recommended_reads = 16 * cpu_count
                    
                    # Check if using default value (32) when more cores are available
                    if reads_val == 32 and cpu_count > 2:
                        recommendations.append(
                            self._create_recommendation(
                                title="Default Concurrent Reads Not Leveraging CPU Cores (concurrent_reads)",
                                description=f"Node {self._get_node_identifier(node)} uses default concurrent_reads=32 with {cpu_count} CPU cores",
                                severity=Severity.WARNING,
                                category="configuration",
                                impact="CPU cores are not being fully leveraged for read operations",
                                recommendation=f"Increase concurrent_reads to {recommended_reads} (16x CPU count) in cassandra.yaml",
                                current_value=f"concurrent_reads={reads_val}",
                                node_id=node.host_id,
                                concurrent_reads=reads_val,
                                cpu_count=cpu_count,
                                recommended_value=f"{recommended_reads} (16x CPU count)",
                                config_location="cassandra.yaml"
                            )
                        )
                    elif reads_val < recommended_reads:
                        recommendations.append(
                            self._create_recommendation(
                                title="Low Concurrent Reads Setting (concurrent_reads)",
                                description=f"Node {self._get_node_identifier(node)} has concurrent_reads={reads_val} with {cpu_count} CPU cores",
                                severity=Severity.WARNING,
                                category="configuration",
                                impact="May not fully utilize available CPU resources for read operations",
                                recommendation=f"Increase concurrent_reads to {recommended_reads} (16x CPU count) in cassandra.yaml",
                                current_value=f"concurrent_reads={reads_val}",
                                node_id=node.host_id,
                                concurrent_reads=reads_val,
                                cpu_count=cpu_count,
                                recommended_value=f"{recommended_reads} (16x CPU count)",
                                config_location="cassandra.yaml"
                            )
                        )
                except (ValueError, TypeError):
                    pass
            
            # Analyze concurrent_writes
            if concurrent_writes and cpu_count:
                try:
                    writes_val = int(concurrent_writes)
                    
                    # Recommended: 16 * num_cores per user requirement
                    recommended_writes = 16 * cpu_count
                    
                    # Check if using default value (32) when more cores are available
                    if writes_val == 32 and cpu_count > 2:
                        recommendations.append(
                            self._create_recommendation(
                                title="Default Concurrent Writes Not Leveraging CPU Cores (concurrent_writes)",
                                description=f"Node {self._get_node_identifier(node)} uses default concurrent_writes=32 with {cpu_count} CPU cores",
                                severity=Severity.WARNING,
                                category="configuration",
                                impact="CPU cores are not being fully leveraged for write operations",
                                recommendation=f"Increase concurrent_writes to {recommended_writes} (16x CPU count) in cassandra.yaml",
                                current_value=f"concurrent_writes={writes_val}",
                                node_id=node.host_id,
                                concurrent_writes=writes_val,
                                cpu_count=cpu_count,
                                recommended_value=f"{recommended_writes} (16x CPU count)",
                                config_location="cassandra.yaml"
                            )
                        )
                    elif writes_val < recommended_writes:
                        recommendations.append(
                            self._create_recommendation(
                                title="Low Concurrent Writes Setting (concurrent_writes)",
                                description=f"Node {self._get_node_identifier(node)} has concurrent_writes={writes_val} with {cpu_count} CPU cores",
                                severity=Severity.WARNING,
                                category="configuration",
                                impact="May not fully utilize available CPU resources for write operations",
                                recommendation=f"Increase concurrent_writes to {recommended_writes} (16x CPU count) in cassandra.yaml",
                                current_value=f"concurrent_writes={writes_val}",
                                node_id=node.host_id,
                                concurrent_writes=writes_val,
                                cpu_count=cpu_count,
                                recommended_value=f"{recommended_writes} (16x CPU count)",
                                config_location="cassandra.yaml"
                            )
                        )
                except (ValueError, TypeError):
                    pass
            
            # Analyze native_transport_max_threads
            if cpu_count and native_transport_max_threads and native_transport_max_threads != "-1":
                try:
                    # Get current concurrent operation values
                    reads_val = int(concurrent_reads) if concurrent_reads else 32
                    writes_val = int(concurrent_writes) if concurrent_writes else 32
                    counter_writes_val = int(concurrent_counter_writes) if concurrent_counter_writes else 32
                    mv_writes_val = int(concurrent_materialized_view_writes) if concurrent_materialized_view_writes else 32
                    
                    # Calculate RECOMMENDED values for concurrent operations
                    recommended_reads = 16 * cpu_count  # As per user requirement
                    recommended_writes = 16 * cpu_count  # As per user requirement
                    recommended_counter_writes = 16 * cpu_count  # Same as writes
                    recommended_mv_writes = 32  # Keep default for MV writes
                    
                    # Calculate recommended native_transport_max_threads
                    # Should be sum of all RECOMMENDED concurrent operations
                    recommended_native_threads = recommended_reads + recommended_writes + recommended_counter_writes + recommended_mv_writes
                    
                    native_threads_val = int(native_transport_max_threads)
                    
                    if native_threads_val < recommended_native_threads:
                        recommendations.append(
                            self._create_recommendation(
                                title="Low Native Transport Max Threads (native_transport_max_threads)",
                                description=f"Node {self._get_node_identifier(node)} has native_transport_max_threads={native_threads_val}, should be at least {recommended_native_threads}",
                                severity=Severity.WARNING,
                                category="configuration",
                                impact="May limit concurrent client operations and cause thread pool saturation",
                                recommendation=f"Increase native_transport_max_threads to {recommended_native_threads} (sum of concurrent_reads + concurrent_writes + concurrent_counter_writes + concurrent_materialized_view_writes) in cassandra.yaml",
                                current_value=f"native_transport_max_threads={native_threads_val}",
                                node_id=node.host_id,
                                native_transport_max_threads=native_threads_val,
                                concurrent_reads=reads_val,
                                concurrent_writes=writes_val,
                                concurrent_counter_writes=counter_writes_val,
                                concurrent_materialized_view_writes=mv_writes_val,
                                recommended_value=f"{recommended_native_threads}",
                                config_location="cassandra.yaml"
                            )
                        )
                except (ValueError, TypeError):
                    pass
            
            # Check if we couldn't determine CPU count but have thread pool settings
            if cpu_count is None and (concurrent_reads or concurrent_writes):
                recommendations.append(
                    self._create_recommendation(
                        title="Unable to Determine CPU Count for Thread Pool Analysis",
                        description=f"Cannot analyze thread pool settings optimally for node {self._get_node_identifier(node)}",
                        severity=Severity.INFO,
                        category="configuration",
                        impact="Cannot provide CPU-based recommendations for thread pool sizing",
                        recommendation="Check that host_cpu_CPU parameter is available in node metrics",
                        node_id=node.host_id,
                        config_location="cassandra.yaml"
                    )
                )
        
        return recommendations
    
    def _analyze_auth_cache_settings(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze authentication cache settings for performance"""
        recommendations = []
        
        # Recommended values for production (in milliseconds)
        recommended_settings = {
            "roles_validity": (120000, "120s"),  # 120 seconds
            "roles_update_interval": (10000, "10s"),  # 10 seconds
            "permissions_validity": (60000, "60s"),  # 60 seconds
            "permissions_update_interval": (10000, "10s"),  # 10 seconds
            "credentials_validity": (120000, "120s"),  # 120 seconds
            "credentials_update_interval": (10000, "10s")  # 10 seconds
        }
        
        for node in cluster_state.nodes.values():
            # Check each authentication cache setting
            for setting_name, (recommended_ms, recommended_str) in recommended_settings.items():
                # Note: The API provides these without _in_ms suffix
                param_name = f"comp_{setting_name}"
                setting_value = node.Details.get(param_name)
                
                if setting_value is not None:
                    try:
                        value_ms = int(setting_value)
                        
                        # Check if using default 2 seconds (2000ms) or any value less than recommended
                        if value_ms == 2000:
                            recommendations.append(
                                self._create_recommendation(
                                    title=f"Default Authentication Cache Setting ({setting_name})",
                                    description=f"Node {self._get_node_identifier(node)} uses default {setting_name}=2s which can impact query performance",
                                    severity=Severity.WARNING,
                                    category="configuration",
                                    impact="Frequent authentication cache refreshes can cause performance overhead and impact query latency",
                                    recommendation=f"Increase {setting_name} to {recommended_str} for production workloads in cassandra.yaml",
                                    current_value=f"{setting_name}=2s (2000ms)",
                                    node_id=node.host_id,
                                    **{setting_name: value_ms},
                                    recommended_value=f"{recommended_str} ({recommended_ms}ms)",
                                    config_location="cassandra.yaml"
                                )
                            )
                        elif value_ms < recommended_ms:
                            recommendations.append(
                                self._create_recommendation(
                                    title=f"Low Authentication Cache Setting ({setting_name})",
                                    description=f"Node {self._get_node_identifier(node)} has {setting_name}={value_ms}ms ({value_ms/1000}s)",
                                    severity=Severity.WARNING,
                                    category="configuration",
                                    impact="Frequent authentication cache refreshes can cause performance overhead",
                                    recommendation=f"Increase {setting_name} to {recommended_str} for better performance in cassandra.yaml",
                                    current_value=f"{setting_name}={value_ms}ms ({value_ms/1000}s)",
                                    node_id=node.host_id,
                                    **{setting_name: value_ms},
                                    recommended_value=f"{recommended_str} ({recommended_ms}ms)",
                                    config_location="cassandra.yaml"
                                )
                            )
                        elif value_ms > 3600000:  # More than 1 hour
                            # Very high cache validity can be a security risk
                            recommendations.append(
                                self._create_recommendation(
                                    title=f"High Authentication Cache Setting ({setting_name})",
                                    description=f"Node {self._get_node_identifier(node)} has {setting_name}={value_ms}ms ({value_ms/1000/60:.1f} minutes)",
                                    severity=Severity.INFO,
                                    category="configuration",
                                    impact="Long cache validity periods may delay permission/role changes from taking effect",
                                    recommendation=f"Consider reducing {setting_name} to {recommended_str} for better security/performance balance in cassandra.yaml",
                                    current_value=f"{setting_name}={value_ms}ms ({value_ms/1000/60:.1f} minutes)",
                                    node_id=node.host_id,
                                    **{setting_name: value_ms},
                                    recommended_value=f"{recommended_str} ({recommended_ms}ms)",
                                    config_location="cassandra.yaml"
                                )
                            )
                    except (ValueError, TypeError):
                        pass
        
        return recommendations