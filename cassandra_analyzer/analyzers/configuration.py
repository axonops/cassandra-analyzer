"""
Configuration analyzer - checks cluster and node configuration
"""

import structlog
from typing import Dict, Any, List
from ..models import ClusterState, Recommendation, Severity
from .base import BaseAnalyzer

logger = structlog.get_logger()


class ConfigurationAnalyzer(BaseAnalyzer):
    """Analyzes configuration aspects of the cluster"""
    
    def _get_node_identifier(self, node) -> str:
        """Get a user-friendly node identifier (hostname/ip format)"""
        if not hasattr(node, 'Details') or not node.Details:
            return node.host_id
        
        hostname = node.Details.get('host_Hostname', 'unknown')
        ip_address = node.Details.get('comp_listen_address', 'unknown')
        
        return f"{hostname}/{ip_address}"
    
    def analyze(self, cluster_state: ClusterState) -> Dict[str, Any]:
        """Analyze configuration"""
        try:
            recommendations = []
            summary = {}
            details = {}
            
            # Analyze JVM settings
            recommendations.extend(self._analyze_jvm_settings(cluster_state))
            
            # Analyze Cassandra settings
            recommendations.extend(self._analyze_cassandra_settings(cluster_state))
            
            # Create summary
            summary = {
                "recommendations_count": len(recommendations)
            }
            
            return {
                "recommendations": [r.dict() for r in recommendations],
                "summary": summary,
                "details": details
            }
        except Exception as e:
            logger.error(f"Configuration analysis failed: {str(e)}")
            return {
                "error": f"Configuration analysis failed: {str(e)}",
                "recommendations": []
            }
    
    def _analyze_jvm_settings(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze JVM configuration across nodes """
        recommendations = []
        
        try:
            # Extract JVM settings from node details
            jvm_configs = []
            heap_sizes = []
            gc_algorithms = []
            
            for node in cluster_state.nodes.values():
                try:
                    if not hasattr(node, 'Details') or not node.Details:
                        continue
                    
                    # Parse JVM settings from comp_jvm_input arguments
                    jvm_args = node.Details.get("comp_jvm_input arguments", "")
                    
                    # Extract heap size from -Xmx parameter
                    heap_size_bytes = None
                    heap_size_str = None
                    import re
                    heap_match = re.search(r'-Xmx(\d+)([GMK])', jvm_args)
                    if heap_match:
                        size = int(heap_match.group(1))
                        unit = heap_match.group(2)
                        heap_size_str = f"{size}{unit}"
                        
                        # Convert to bytes
                        if unit == 'G':
                            heap_size_bytes = size * 1024 * 1024 * 1024
                        elif unit == 'M':
                            heap_size_bytes = size * 1024 * 1024
                        elif unit == 'K':
                            heap_size_bytes = size * 1024
                    
                    # Extract GC algorithm - ensure we're checking the string properly
                    gc_algorithm = "unknown"
                    jvm_args_str = str(jvm_args)  # Ensure it's a string
                    
                    if "-XX:+UseG1GC" in jvm_args_str:
                        gc_algorithm = "G1GC"
                    elif "-XX:+UseConcMarkSweepGC" in jvm_args_str or "-XX:+UseCMS" in jvm_args_str:
                        gc_algorithm = "CMS"
                    elif "-XX:+UseParallelGC" in jvm_args_str:
                        gc_algorithm = "ParallelGC"
                    elif "-XX:+UseZGC" in jvm_args_str:
                        gc_algorithm = "ZGC"
                    elif "-XX:+UseShenandoahGC" in jvm_args_str:
                        gc_algorithm = "ShenandoahGC"
                        logger.warning(f"Detected ShenandoahGC for node {self._get_node_identifier(node)} - please verify this is correct")
                    
                    # Get system memory from host_virtualmem_Total
                    system_memory_bytes = None
                    system_memory_str = node.Details.get("host_virtualmem_Total")
                    if system_memory_str:
                        try:
                            system_memory_bytes = int(system_memory_str)
                        except (ValueError, TypeError):
                            pass
                    
                    jvm_configs.append({
                        "node": self._get_node_identifier(node),
                        "node_id": node.host_id,
                        "heap_size_bytes": heap_size_bytes,
                        "heap_size_str": heap_size_str,
                        "gc_algorithm": gc_algorithm,
                        "system_memory_bytes": system_memory_bytes,
                        "jvm_args": jvm_args
                    })
                    
                    if heap_size_bytes:
                        heap_sizes.append(heap_size_bytes)
                    if gc_algorithm != "unknown":
                        gc_algorithms.append(gc_algorithm)
                        logger.debug(f"Node {self._get_node_identifier(node)} detected GC: {gc_algorithm}")
                    
                except Exception as e:
                    logger.warning(f"Error processing JVM settings for node {self._get_node_identifier(node)}: {str(e)}")
            
            # Check for JVM heap size consistency
            if heap_sizes and len(set(heap_sizes)) > 1:
                heap_variations = {}
                for config in jvm_configs:
                    if config["heap_size_str"]:
                        if config["heap_size_str"] not in heap_variations:
                            heap_variations[config["heap_size_str"]] = []
                        heap_variations[config["heap_size_str"]].append(config["node"])
                
                recommendations.append(
                    self._create_recommendation(
                        title="Inconsistent JVM Heap Sizes",
                        description=f"Found {len(heap_variations)} different heap sizes across nodes: {list(heap_variations.keys())}",
                        severity=Severity.WARNING,
                        category="configuration",
                        impact="Unpredictable performance across nodes",
                        recommendation="Align JVM heap settings across all nodes for consistent behavior",
                        heap_variations=heap_variations,
                        config_location="JVM startup flags"
                    )
                )
            
            # Check for GC algorithm consistency
            if gc_algorithms and len(set(gc_algorithms)) > 1:
                gc_variations = {}
                for config in jvm_configs:
                    gc_algo = config["gc_algorithm"]
                    if gc_algo not in gc_variations:
                        gc_variations[gc_algo] = []
                    gc_variations[gc_algo].append(config["node"])
                
                # Create a more detailed description showing which nodes have which GC
                gc_details = []
                for gc_algo, nodes in gc_variations.items():
                    gc_details.append(f"{gc_algo}: {len(nodes)} nodes")
                
                recommendations.append(
                    self._create_recommendation(
                        title="Inconsistent GC Algorithms",
                        description=f"Found {len(gc_variations)} different GC algorithms across nodes: {', '.join(gc_details)}",
                        severity=Severity.WARNING,
                        category="configuration",
                        impact="Different performance characteristics across nodes",
                        recommendation="Use the same GC algorithm on all nodes",
                        gc_variations=gc_variations,
                        gc_algorithms=list(gc_variations.keys()),
                        config_location="JVM startup flags"
                    )
                )
            
            # Analyze individual node JVM configurations
            for config in jvm_configs:
                if config["heap_size_bytes"] and config["system_memory_bytes"]:
                    node_recommendations = self._get_jvm_heap_recommendations(
                        config["heap_size_bytes"],
                        config["gc_algorithm"],
                        config["system_memory_bytes"],
                        config["node"]
                    )
                    recommendations.extend(node_recommendations)
            
            return recommendations
        except Exception as e:
            logger.error(f"JVM settings analysis failed: {str(e)}")
            return []
    
    def _get_jvm_heap_recommendations(self, heap_size: int, gc_algorithm: str, system_memory: int, node_identifier: str) -> List[Recommendation]:
        """Generate JVM heap recommendations"""
        recommendations = []
        
        # Convert bytes to more readable units
        heap_gb = heap_size / (1024**3) if heap_size else 0
        system_gb = system_memory / (1024**3) if system_memory else 0
        
        # Calculate heap percentage of system memory
        heap_percentage = (heap_gb / system_gb * 100) if system_gb > 0 else 0
        
        # Check heap size relative to system memory (should be 25-50% for Cassandra)
        if heap_percentage > 60:
            recommendations.append(
                self._create_recommendation(
                    title="Excessive Heap Allocation",
                    description=f"Node {node_identifier} allocates {heap_percentage:.1f}% of system memory ({heap_gb:.1f}GB of {system_gb:.1f}GB) to heap",
                    severity=Severity.WARNING,
                    category="configuration",
                    impact="Insufficient memory for page cache and system operations",
                    recommendation="Reduce heap to 25-50% of system memory for optimal performance",
                    node=node_identifier,
                    current_heap_gb=heap_gb,
                    system_memory_gb=system_gb,
                    heap_percentage=heap_percentage,
                    config_location="JVM startup flags"
                )
            )
        elif heap_percentage < 20 and system_gb > 32:
            recommendations.append(
                self._create_recommendation(
                    title="Underutilized Memory for Heap",
                    description=f"Node {node_identifier} only uses {heap_percentage:.1f}% of system memory ({heap_gb:.1f}GB of {system_gb:.1f}GB) for heap",
                    severity=Severity.INFO,
                    category="configuration",
                    impact="May not be fully utilizing available memory for Cassandra",
                    recommendation="Consider increasing heap size if experiencing GC pressure",
                    node=node_identifier,
                    current_heap_gb=heap_gb,
                    system_memory_gb=system_gb,
                    heap_percentage=heap_percentage,
                    config_location="JVM startup flags"
                )
            )
        
        if gc_algorithm.upper() in ["CMS", "CONCURRENT_MARK_SWEEP"]:
            # CMS is deprecated in Java 9+
            recommendations.append(
                self._create_recommendation(
                    title="Deprecated CMS Garbage Collector",
                    description=f"Node {node_identifier} uses CMS GC which is deprecated",
                    severity=Severity.WARNING,
                    category="configuration",
                    impact="CMS is deprecated and will be removed in future Java versions",
                    recommendation="Migrate to Shenandoah GC (requires JDK 11+) for low-latency performance, or G1GC as an alternative",
                    node=node_identifier,
                    current_gc=gc_algorithm,
                    config_location="JVM startup flags"
                )
            )
            
            # CMS specific heap recommendations
            if heap_gb < 8 and system_gb >= 30:
                recommendations.append(
                    self._create_recommendation(
                        title="Small Heap Size for Available Memory (CMS)",
                        description=f"Node {node_identifier} has heap size {heap_gb:.1f}GB with {system_gb:.1f}GB RAM available",
                        severity=Severity.WARNING,
                        category="configuration",
                        impact="Underutilized system memory",
                        recommendation="Consider allocating 12-16GB heap size for CMS",
                        node=node_identifier,
                        current_heap_gb=heap_gb,
                        available_memory_gb=system_gb,
                        config_location="JVM startup flags"
                    )
                )
        
        elif gc_algorithm.upper() in ["G1", "G1GC"]:
            # G1GC recommendations - suggest Shenandoah as better alternative
            recommendations.append(
                self._create_recommendation(
                    title="Consider Shenandoah GC Instead of G1GC",
                    description=f"Node {node_identifier} uses G1GC",
                    severity=Severity.INFO,
                    category="configuration",
                    impact="G1GC can have longer pause times compared to Shenandoah",
                    recommendation="Consider migrating to Shenandoah GC (requires JDK 11+) for lower and more predictable latencies",
                    node=node_identifier,
                    current_gc=gc_algorithm,
                    config_location="JVM startup flags"
                )
            )
            
            if heap_gb < 20:
                recommendations.append(
                    self._create_recommendation(
                        title="Small Heap Size for G1GC",
                        description=f"Node {node_identifier} has G1GC heap of {heap_gb:.1f}GB but needs at least 20GB",
                        severity=Severity.WARNING,
                        category="configuration",
                        impact="G1GC performs poorly with small heaps",
                        recommendation="Increase heap size to 20-31GB or switch to Shenandoah GC (JDK 11+)",
                        node=node_identifier,
                        current_heap_gb=heap_gb,
                        config_location="JVM startup flags"
                    )
                )
            
            # Check compressed OOPs limit (32GB)
            if heap_gb > 32:
                recommendations.append(
                    self._create_recommendation(
                        title="Heap Size Above Compressed OOPs Limit",
                        description=f"Node {node_identifier} has G1GC heap of {heap_gb:.1f}GB, above 32GB compressed OOPs limit",
                        severity=Severity.WARNING,
                        category="configuration",
                        impact="Loss of compressed OOPs optimization, increased memory overhead",
                        recommendation="Decrease heap size to 31GB, switch to Shenandoah GC (which handles large heaps better), or consider multiple smaller nodes",
                        node=node_identifier,
                        current_heap_gb=heap_gb,
                        config_location="JVM startup flags"
                    )
                )
            
            # G1GC specific tuning recommendations
            if 20 <= heap_gb <= 31:
                # This is the sweet spot for G1GC, but we can still provide tuning guidance
                recommendations.append(
                    self._create_recommendation(
                        title="G1GC Heap Size Optimal",
                        description=f"Node {node_identifier} has G1GC heap of {heap_gb:.1f}GB which is in the optimal range",
                        severity=Severity.INFO,
                        category="configuration",
                        impact="Good heap size for G1GC performance",
                        recommendation="Monitor GC logs to ensure pause times meet SLAs",
                        node=node_identifier,
                        current_heap_gb=heap_gb,
                        config_location="JVM startup flags"
                    )
                )
        
        elif gc_algorithm.upper() == "SHENANDOAHGC":
            # Shenandoah is recommended - just provide positive feedback
            recommendations.append(
                self._create_recommendation(
                    title="Shenandoah GC Detected (Recommended)",
                    description=f"Node {node_identifier} uses Shenandoah GC for low-latency performance",
                    severity=Severity.INFO,
                    category="configuration",
                    impact="Excellent choice for low and predictable pause times",
                    recommendation="Monitor GC logs to ensure pause times meet SLAs",
                    node=node_identifier,
                    current_gc=gc_algorithm,
                    config_location="JVM startup flags"
                )
            )
            
            # Shenandoah handles large heaps well, but still check basics
            if heap_percentage > 60:
                recommendations.append(
                    self._create_recommendation(
                        title="Excessive Heap Allocation with Shenandoah",
                        description=f"Node {node_identifier} allocates {heap_percentage:.1f}% of system memory ({heap_gb:.1f}GB of {system_gb:.1f}GB) to heap",
                        severity=Severity.WARNING,
                        category="configuration",
                        impact="Insufficient memory for page cache and system operations",
                        recommendation="Even with Shenandoah, reduce heap to 25-50% of system memory",
                        node=node_identifier,
                        current_heap_gb=heap_gb,
                        system_memory_gb=system_gb,
                        heap_percentage=heap_percentage,
                        config_location="JVM startup flags"
                    )
                )
        
        elif gc_algorithm.upper() == "ZGC":
            # ZGC is also a good low-latency collector
            recommendations.append(
                self._create_recommendation(
                    title="ZGC Detected",
                    description=f"Node {node_identifier} uses ZGC for low-latency performance",
                    severity=Severity.INFO,
                    category="configuration",
                    impact="Good choice for low pause times, though Shenandoah may offer better throughput for Cassandra",
                    recommendation="Consider Shenandoah GC as an alternative for potentially better throughput with similar low latency",
                    node=node_identifier,
                    current_gc=gc_algorithm,
                    config_location="JVM startup flags"
                )
            )
        
        elif gc_algorithm == "unknown":
            recommendations.append(
                self._create_recommendation(
                    title="Unable to Determine GC Algorithm",
                    description=f"Could not determine GC algorithm for node {node_identifier}",
                    severity=Severity.INFO,
                    category="configuration",
                    impact="Cannot provide GC-specific recommendations",
                    recommendation="Verify JVM arguments are properly configured",
                    node=node_identifier,
                    config_location="JVM startup flags"
                )
            )
        
        return recommendations
    
    def _analyze_cassandra_settings(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze Cassandra configurations"""
        recommendations = []
        
        logger.debug(f"Starting Cassandra settings analysis with {len(cluster_state.nodes)} nodes")
        
        try:
            # Check for configuration mismatches across nodes (based on ConfigurationMismatches.kt)
            logger.debug("Analyzing configuration mismatches...")
            mismatch_recs = self._analyze_configuration_mismatches(cluster_state)
            logger.debug(f"Configuration mismatch analysis returned {len(mismatch_recs)} recommendations")
            recommendations.extend(mismatch_recs)
            
            # Check specific settings
            logger.debug("Analyzing specific configurations...")
            specific_recs = self._analyze_specific_configurations(cluster_state)
            logger.debug(f"Specific configuration analysis returned {len(specific_recs)} recommendations")
            recommendations.extend(specific_recs)
        except Exception as e:
            import traceback
            logger.error(
                "Cassandra settings analysis failed",
                error=str(e),
                error_type=type(e).__name__,
                traceback=traceback.format_exc(),
                exc_info=True
            )
            # Re-raise to see full traceback in logs
            raise
        
        return recommendations
    
    def _analyze_configuration_mismatches(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Detect configuration mismatches"""
        recommendations = []
        
        if len(cluster_state.nodes) < 2:
            recommendations.append(
                self._create_recommendation(
                    title="Insufficient Nodes for Configuration Comparison",
                    description="Less than two nodes available for configuration comparison",
                    severity=Severity.WARNING,
                    category="configuration",
                    impact="Unable to detect configuration inconsistencies",
                    recommendation="Ensure all nodes provide configuration data",
                    node_count=len(cluster_state.nodes),
                    config_location="cassandra.yaml"
                )
            )
            return recommendations
        
        # Extract configuration from node details
        config_values = {}
        nodes_with_configs = []
        
        # Important configuration keys to check
        # Note: Network-related addresses and interfaces are excluded as they should be different per node
        important_configs = [
            "comp_concurrent_reads",
            "comp_concurrent_writes", 
            "comp_concurrent_compactors",
            "comp_compaction_throughput_mb_per_sec",
            "comp_commitlog_sync",
            "comp_commitlog_sync_period_in_ms",
            "comp_commitlog_sync_batch_window_in_ms",
            "comp_endpoint_snitch",
            "comp_gc_warn_threshold_in_ms",
            "comp_authenticator",
            "comp_authorizer",
            # "comp_listen_address",  # Excluded - should be different per node
            # "comp_broadcast_address",  # Excluded - should be different per node
            # "comp_listen_interface",  # Excluded - should be different per node
            # "comp_rpc_address",  # Excluded - should be different per node
            # "comp_rpc_interface",  # Excluded - should be different per node
            # "comp_broadcast_rpc_address",  # Excluded - should be different per node
            "comp_cluster_name",
            "comp_partitioner",
            "comp_commitlog_segment_size_in_mb",
            "comp_memtable_flush_writers",
            "comp_memtable_allocation_type",
            "comp_disk_failure_policy",
            "comp_commit_failure_policy",
            "comp_key_cache_size_in_mb",
            "comp_row_cache_size_in_mb",
            "comp_num_tokens",
            "comp_hinted_handoff_enabled",
            "comp_max_hint_window_in_ms",
            "comp_request_timeout_in_ms",
            "comp_read_request_timeout_in_ms",
            "comp_write_request_timeout_in_ms",
            "comp_streaming_socket_timeout_in_ms",
            "comp_phi_convict_threshold"
        ]
        
        for node in cluster_state.nodes.values():
            node_configs = {}
            if not hasattr(node, 'Details') or not node.Details:
                continue
            for config_key in important_configs:
                if config_key in node.Details:
                    node_configs[config_key] = node.Details[config_key]
            
            if node_configs:
                nodes_with_configs.append((self._get_node_identifier(node), node_configs))
                
                for config_key, value in node_configs.items():
                    if config_key not in config_values:
                        config_values[config_key] = {}
                    if value not in config_values[config_key]:
                        config_values[config_key][value] = []
                    config_values[config_key][value].append(self._get_node_identifier(node))
        
        # Check for mismatches
        difference_count = 0
        mismatches = []
        for config_key, values in config_values.items():
            if len(values) > 1:
                # Remove comp_ prefix for user-facing display
                display_key = config_key.replace('comp_', '')
                recommendations.append(
                    self._create_recommendation(
                        title=f"Configuration Mismatch: {display_key}",
                        description=f"Nodes have different values for {display_key}: {list(values.keys())}",
                        severity=Severity.WARNING,
                        category="configuration",
                        impact="Inconsistent cluster behavior and unpredictable performance",
                        recommendation="Align this configuration setting across all nodes in cassandra.yaml",
                        config_key=display_key,
                        values=list(values.keys()),
                        affected_nodes=list(values.values()),
                        config_location="cassandra.yaml"
                    )
                )
                difference_count += 1
                # Collect mismatches for the summary recommendation
                mismatches.append({
                    "setting": display_key,
                    "values": values
                })
        
        if difference_count > 0:
            recommendations.append(
                self._create_recommendation(
                    title="Multiple Configuration Mismatches Detected",
                    description=f"Found {difference_count} configuration differences across cluster nodes",
                    severity=Severity.WARNING,
                    category="configuration",
                    impact="Inconsistent performance characteristics across nodes",
                    recommendation="Review and align all configuration settings across nodes",
                    mismatch_count=difference_count,
                    mismatches=mismatches,
                    config_location="cassandra.yaml"
                )
            )
        
        return recommendations
    
    def _analyze_specific_configurations(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze specific configuration settings for best practices"""
        recommendations = []
        
        for node in cluster_state.nodes.values():
            if not hasattr(node, 'Details') or not node.Details:
                continue
            # Authentication checks are handled by SecurityAnalyzer to avoid duplication
            # Skip authentication checks here
            
            # Check disk failure policy
            disk_policy = node.Details.get("comp_disk_failure_policy")
            if disk_policy == "ignore":
                recommendations.append(
                    self._create_recommendation(
                        title="Risky Disk Failure Policy (disk_failure_policy)",
                        description=f"Disk failure policy is set to 'ignore' on node {self._get_node_identifier(node)}",
                        severity=Severity.WARNING,
                        category="configuration",
                        impact="Data corruption risk if disk failures are ignored",
                        recommendation="Consider using 'stop' or 'best_effort' policy in cassandra.yaml",
                        node_id=node.host_id,  # Keep original host_id for reference
                        node=self._get_node_identifier(node),
                        current_policy=disk_policy,
                        config_location="cassandra.yaml"
                    )
                )
            
            # Check commitlog sync
            commitlog_sync = node.Details.get("comp_commitlog_sync")
            if commitlog_sync == "batch":
                sync_period = node.Details.get("comp_commitlog_sync_batch_window_in_ms", 0)
                if sync_period > 10:
                    recommendations.append(
                        self._create_recommendation(
                            title="High Commitlog Sync Window (commitlog_sync_batch_window_in_ms)",
                            description=f"Commitlog sync window is {sync_period}ms on node {self._get_node_identifier(node)}",
                            severity=Severity.WARNING,
                            category="configuration",
                            impact="Potential data loss on failure",
                            recommendation="Consider reducing sync window or using periodic sync in cassandra.yaml",
                            node_id=node.host_id,  # Keep original host_id for reference
                            node=self._get_node_identifier(node),
                            sync_window_ms=sync_period,
                            config_location="cassandra.yaml"
                        )
                    )
        
        return recommendations