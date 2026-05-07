"""
Configuration analyzer - checks cluster and node configuration
"""

import re
import structlog
from typing import Any, Dict, List, Optional

from ..models import ClusterState, Recommendation, Severity
from ..utils import V5_0, version_at_least
from .base import BaseAnalyzer

logger = structlog.get_logger()

# Java versions <= 1.8 use the old "1.X" scheme; 9+ use "X.Y.Z". Match either.
_JAVA_VERSION_RE = re.compile(r"(?:1\.)?(\d{1,2})(?:[._]\d+)*")


def _parse_java_major(value: Any) -> Optional[int]:
    """Best-effort parse of a Java version string to its major number.

    Handles ``"1.8.0_392"`` → 8, ``"11.0.21"`` → 11, ``"17"`` → 17,
    ``"21.0.1+12"`` → 21. Returns None if the input doesn't look like a
    Java version.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    match = _JAVA_VERSION_RE.search(s)
    if not match:
        return None
    return int(match.group(1))


def _detect_java_major(node) -> Optional[int]:
    """Determine the Java major version a node is running, if known."""
    details = getattr(node, "Details", {}) or {}
    for key in (
        "comp_jvm_version",
        "comp_java_version",
        "comp_jvm_java.version",
        "comp_jvm_java.specification.version",
        "jvm_version",
    ):
        major = _parse_java_major(details.get(key))
        if major is not None:
            return major
    return None


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
                        "jvm_args": jvm_args,
                        "java_major": _detect_java_major(node),
                        "cassandra_version": node.Details.get("comp_releaseVersion") or node.Details.get("release_version"),
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
                        config["node"],
                        java_major=config.get("java_major"),
                        cassandra_version=config.get("cassandra_version"),
                    )
                    recommendations.extend(node_recommendations)
            
            return recommendations
        except Exception as e:
            logger.error(f"JVM settings analysis failed: {str(e)}")
            return []
    
    def _get_jvm_heap_recommendations(
        self,
        heap_size: int,
        gc_algorithm: str,
        system_memory: int,
        node_identifier: str,
        java_major: Optional[int] = None,
        cassandra_version: Optional[str] = None,
    ) -> List[Recommendation]:
        """Generate JVM heap recommendations"""
        recommendations = []
        is_5x = version_at_least(cassandra_version, V5_0)
        # Be conservative: if we don't know the JDK major, fall back to
        # behaviour that matches a modern (11+) deployment, since CMS is
        # already explicitly handled below and users on legacy JDK 8 will
        # also be flagged through the CMS branch.
        java_supports_shenandoah = java_major is None or java_major >= 11
        java_supports_zgc = java_major is None or java_major >= 11
        java_modern = java_major is None or java_major >= 17

        # On Cassandra 5.x, Java 17 is the recommended LTS. Flag clusters that
        # are still on Java 8 or 11 so operators consider upgrading.
        if is_5x and java_major is not None and java_major < 17:
            recommendations.append(
                self._create_recommendation(
                    title=f"Cassandra 5.x Running on Java {java_major}",
                    description=f"Node {node_identifier} runs Cassandra 5.x on Java {java_major}",
                    severity=Severity.INFO,
                    category="configuration",
                    impact="Cassandra 5.0 supports Java 11 and Java 17; Java 17 is the current LTS and unlocks ZGC for large heaps",
                    recommendation="Plan an upgrade to Java 17 (LTS) for new performance and GC options",
                    node=node_identifier,
                    java_major=java_major,
                    cassandra_version=cassandra_version,
                    config_location="JVM startup flags",
                )
            )
        
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
            # G1GC recommendations - suggest a low-pause alternative if the JDK supports one.
            if java_modern:
                alt_gc_text = "ZGC (recommended on Java 17+) or Shenandoah"
                alt_impact = "G1GC can have longer pause times than ZGC or Shenandoah, which are mature on Java 17+"
            elif java_supports_shenandoah:
                alt_gc_text = "Shenandoah GC"
                alt_impact = "G1GC can have longer pause times compared to Shenandoah"
            else:
                # Pre-JDK-11 — neither ZGC nor Shenandoah is generally available.
                alt_gc_text = None
                alt_impact = None

            if alt_gc_text:
                recommendations.append(
                    self._create_recommendation(
                        title=f"Consider {alt_gc_text} Instead of G1GC",
                        description=f"Node {node_identifier} uses G1GC" + (f" on Java {java_major}" if java_major else ""),
                        severity=Severity.INFO,
                        category="configuration",
                        impact=alt_impact,
                        recommendation=f"Consider migrating to {alt_gc_text} for lower and more predictable latencies",
                        node=node_identifier,
                        current_gc=gc_algorithm,
                        java_major=java_major,
                        config_location="JVM startup flags"
                    )
                )
            
            if heap_gb < 20:
                if java_modern:
                    fallback_advice = "Increase heap size to 20-31GB, or switch to ZGC / Shenandoah which handle smaller heaps better"
                elif java_supports_shenandoah:
                    fallback_advice = "Increase heap size to 20-31GB, or switch to Shenandoah GC (JDK 11+)"
                else:
                    fallback_advice = "Increase heap size to 20-31GB"
                recommendations.append(
                    self._create_recommendation(
                        title="Small Heap Size for G1GC",
                        description=f"Node {node_identifier} has G1GC heap of {heap_gb:.1f}GB but needs at least 20GB",
                        severity=Severity.WARNING,
                        category="configuration",
                        impact="G1GC performs poorly with small heaps",
                        recommendation=fallback_advice,
                        node=node_identifier,
                        current_heap_gb=heap_gb,
                        config_location="JVM startup flags"
                    )
                )
            
            # Check compressed OOPs limit (32GB)
            if heap_gb > 32:
                if java_modern:
                    large_heap_advice = "Decrease heap size to 31GB, or switch to ZGC / Shenandoah which handle large heaps without losing compressed OOPs"
                elif java_supports_shenandoah:
                    large_heap_advice = "Decrease heap size to 31GB, switch to Shenandoah GC (which handles large heaps better), or consider multiple smaller nodes"
                else:
                    large_heap_advice = "Decrease heap size to 31GB or consider multiple smaller nodes"
                recommendations.append(
                    self._create_recommendation(
                        title="Heap Size Above Compressed OOPs Limit",
                        description=f"Node {node_identifier} has G1GC heap of {heap_gb:.1f}GB, above 32GB compressed OOPs limit",
                        severity=Severity.WARNING,
                        category="configuration",
                        impact="Loss of compressed OOPs optimization, increased memory overhead",
                        recommendation=large_heap_advice,
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
            if java_major and java_major >= 17:
                # ZGC matured significantly in Java 17 (production-ready) and Java 21 (generational ZGC).
                recommendations.append(
                    self._create_recommendation(
                        title="ZGC Detected (Recommended on Java 17+)",
                        description=f"Node {node_identifier} uses ZGC on Java {java_major}",
                        severity=Severity.INFO,
                        category="configuration",
                        impact="ZGC delivers sub-millisecond pause times and scales to very large heaps; on Java 21 generational ZGC further reduces overhead",
                        recommendation="Monitor GC logs to ensure pause times meet SLAs; consider enabling generational ZGC (-XX:+ZGenerational) on Java 21",
                        node=node_identifier,
                        current_gc=gc_algorithm,
                        java_major=java_major,
                        config_location="JVM startup flags"
                    )
                )
            else:
                # On Java 11 ZGC is still experimental; Shenandoah is a safer choice.
                recommendations.append(
                    self._create_recommendation(
                        title="ZGC Detected",
                        description=f"Node {node_identifier} uses ZGC" + (f" on Java {java_major}" if java_major else ""),
                        severity=Severity.INFO,
                        category="configuration",
                        impact="ZGC was experimental before Java 15 and only became production-ready on Java 17",
                        recommendation="Upgrade to Java 17+ before relying on ZGC in production, or switch to Shenandoah GC",
                        node=node_identifier,
                        current_gc=gc_algorithm,
                        java_major=java_major,
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
        
        # Settings to compare across nodes. Each entry is (logical_name, kind)
        # where ``kind`` selects the unit-aware reader so we treat e.g.
        # ``compaction_throughput_mb_per_sec=64`` (4.x) and
        # ``compaction_throughput="64MiB/s"`` (5.x) as the same value.
        # ``"opaque"`` means compare the raw string verbatim.
        # Network-related addresses and interfaces are intentionally excluded
        # because they're expected to differ per node.
        logical_settings = [
            ("concurrent_reads", "opaque"),
            ("concurrent_writes", "opaque"),
            ("concurrent_compactors", "opaque"),
            ("compaction_throughput", "rate_mibps"),
            ("commitlog_sync", "opaque"),
            ("commitlog_sync_period", "duration_ms"),
            ("commitlog_sync_batch_window", "duration_ms"),
            ("endpoint_snitch", "opaque"),
            ("gc_warn_threshold", "duration_ms"),
            ("authenticator", "opaque"),
            ("authorizer", "opaque"),
            ("cluster_name", "opaque"),
            ("partitioner", "opaque"),
            ("commitlog_segment_size", "size_mib"),
            ("memtable_flush_writers", "opaque"),
            ("memtable_allocation_type", "opaque"),
            ("memtable_heap_space", "size_mib"),
            ("memtable_offheap_space", "size_mib"),
            ("disk_failure_policy", "opaque"),
            ("commit_failure_policy", "opaque"),
            ("key_cache_size", "size_mib"),
            ("row_cache_size", "size_mib"),
            ("num_tokens", "opaque"),
            ("hinted_handoff_enabled", "opaque"),
            ("max_hint_window", "duration_ms"),
            ("request_timeout", "duration_ms"),
            ("read_request_timeout", "duration_ms"),
            ("write_request_timeout", "duration_ms"),
            ("streaming_socket_timeout", "duration_ms"),
            ("phi_convict_threshold", "opaque"),
        ]

        def _read_logical(node, name: str, kind: str):
            """Return ``(canonical_value, display)``. ``canonical_value`` is the
            normalised value used for cross-node comparison; ``display`` is the
            string to surface to the user."""
            details = getattr(node, "Details", {}) or {}
            if kind == "duration_ms":
                v = self._get_duration_ms(node, name)
                return (v, f"{v} ms" if v is not None else None)
            if kind == "size_mib":
                v_bytes = self._get_size_bytes(node, name, legacy_suffix="in_mb", legacy_unit="MiB")
                if v_bytes is None:
                    return (None, None)
                return (v_bytes, f"{v_bytes / (1024 * 1024):.0f} MiB")
            if kind == "rate_mibps":
                v_bps = self._get_rate_bytes_per_sec(
                    node, name, legacy_suffix="mb_per_sec", legacy_unit="MiB/s"
                )
                if v_bps is None:
                    return (None, None)
                return (v_bps, f"{v_bps / (1024 * 1024):.0f} MiB/s")
            # Opaque: try the bare key, then the legacy ``_in_ms`` / ``_in_mb``
            # forms in case future renames slip through. Compare strings directly.
            for candidate in (name, f"{name}_in_ms", f"{name}_in_mb", f"{name}_mb_per_sec"):
                key = f"comp_{candidate}"
                if key in details and details[key] is not None:
                    raw = details[key]
                    return (raw, str(raw))
            return (None, None)

        # Build value map keyed by logical setting → canonical_value → list of (node, display)
        config_values: Dict[str, Dict[Any, List[str]]] = {}
        config_displays: Dict[str, Dict[Any, str]] = {}
        for node in cluster_state.nodes.values():
            if not hasattr(node, "Details") or not node.Details:
                continue
            node_label = self._get_node_identifier(node)
            for name, kind in logical_settings:
                canonical, display = _read_logical(node, name, kind)
                if canonical is None:
                    continue
                config_values.setdefault(name, {}).setdefault(canonical, []).append(node_label)
                config_displays.setdefault(name, {}).setdefault(canonical, display)

        # Check for mismatches
        difference_count = 0
        mismatches = []
        for logical_name, values in config_values.items():
            if len(values) > 1:
                value_list = [config_displays[logical_name][v] for v in values.keys()]
                recommendations.append(
                    self._create_recommendation(
                        title=f"Configuration Mismatch: {logical_name}",
                        description=f"Nodes have different values for {logical_name}: {value_list}",
                        severity=Severity.WARNING,
                        category="configuration",
                        impact="Inconsistent cluster behavior and unpredictable performance",
                        recommendation="Align this configuration setting across all nodes in cassandra.yaml",
                        config_key=logical_name,
                        values=value_list,
                        affected_nodes=list(values.values()),
                        config_location="cassandra.yaml"
                    )
                )
                difference_count += 1
                mismatches.append({
                    "setting": logical_name,
                    "values": {config_displays[logical_name][v]: nodes for v, nodes in values.items()},
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
                # commitlog_sync_batch_window_in_ms (4.x) → commitlog_sync_batch_window (5.x duration).
                sync_period = self._get_duration_ms(node, "commitlog_sync_batch_window")
                is_5x_node = version_at_least(
                    node.Details.get("comp_releaseVersion") or node.Details.get("release_version"),
                    V5_0,
                )
                setting_name = "commitlog_sync_batch_window" if is_5x_node else "commitlog_sync_batch_window_in_ms"
                if sync_period is not None and sync_period > 10:
                    recommendations.append(
                        self._create_recommendation(
                            title=f"High Commitlog Sync Window ({setting_name})",
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