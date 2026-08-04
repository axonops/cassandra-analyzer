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

    category = "configuration"
    default_recommendation_category = "configuration"

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
            self._reset_checks()
            recommendations = []
            details = {}

            # Analyze JVM settings
            recommendations.extend(self._analyze_jvm_settings(cluster_state))

            # Analyze Cassandra settings
            recommendations.extend(self._analyze_cassandra_settings(cluster_state))

            summary = {
                "recommendations_count": len(recommendations)
            }

            return {
                "recommendations": [r.dict() for r in recommendations],
                "summary": summary,
                "details": details,
                "checks": [c.model_dump() for c in self._checks],
            }
        except Exception as e:
            logger.error(f"Configuration analysis failed: {str(e)}")
            return {
                "error": f"Configuration analysis failed: {str(e)}",
                "recommendations": [],
                "checks": [c.model_dump() for c in self._checks],
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

                    # Extract heap size from comp_jvm_heap_heapMaxSize (bytes)
                    heap_size_bytes = None
                    heap_size_str = None
                    raw_heap = node.Details.get("comp_jvm_heap_heapMaxSize")
                    if raw_heap is not None:
                        try:
                            heap_size_bytes = int(raw_heap)
                            heap_gb = heap_size_bytes / (1024 ** 3)
                            heap_size_str = f"{heap_gb:.1f}G"
                        except (ValueError, TypeError):
                            pass

                    # Extract GC algorithm - ensure we're checking the string properly
                    jvm_args_str = str(node.Details.get("comp_jvm_input arguments", ""))

                    gc_algorithm = "unknown"
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
                        "jvm_args": jvm_args_str,
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
            heap_consistency_rec = None
            if not heap_sizes:
                self._record_check(
                    "config.jvm.heap.consistency",
                    "All nodes report the same JVM heap size",
                    "comp_jvm_heap_heapMaxSize",
                    "no_data",
                    skipped_reason="no node reported a heap size",
                )
            elif len(set(heap_sizes)) > 1:
                heap_variations = {}
                for config in jvm_configs:
                    if config["heap_size_str"]:
                        if config["heap_size_str"] not in heap_variations:
                            heap_variations[config["heap_size_str"]] = []
                        heap_variations[config["heap_size_str"]].append(config["node"])

                heap_consistency_rec = self._create_recommendation(
                    check_id="config.jvm.heap.consistency",
                    title="Inconsistent JVM Heap Sizes",
                    description=f"Found {len(heap_variations)} different heap sizes across nodes: {list(heap_variations.keys())}",
                    severity=Severity.WARNING,
                    category="configuration",
                    impact="Unpredictable performance across nodes",
                    recommendation="Align JVM heap settings across all nodes for consistent behavior",
                    heap_variations=heap_variations,
                    config_location="JVM startup flags",
                )
                recommendations.append(heap_consistency_rec)
                self._record_check(
                    "config.jvm.heap.consistency",
                    "All nodes report the same JVM heap size",
                    "comp_jvm_heap_heapMaxSize",
                    "fail",
                    recommendation_id=heap_consistency_rec.id,
                    distinct_sizes=list(heap_variations.keys()),
                )
            else:
                self._record_check(
                    "config.jvm.heap.consistency",
                    "All nodes report the same JVM heap size",
                    "comp_jvm_heap_heapMaxSize",
                    "pass",
                )

            # Check for GC algorithm consistency
            if not gc_algorithms:
                self._record_check(
                    "config.jvm.gc.consistency",
                    "All nodes use the same GC algorithm",
                    "comp_jvm_input arguments",
                    "no_data",
                    skipped_reason="no node reported a recognised GC algorithm flag",
                )
            elif len(set(gc_algorithms)) > 1:
                gc_variations = {}
                for config in jvm_configs:
                    gc_algo = config["gc_algorithm"]
                    if gc_algo not in gc_variations:
                        gc_variations[gc_algo] = []
                    gc_variations[gc_algo].append(config["node"])

                gc_details = []
                for gc_algo, nodes in gc_variations.items():
                    gc_details.append(f"{gc_algo}: {len(nodes)} nodes")

                gc_consistency_rec = self._create_recommendation(
                    check_id="config.jvm.gc.consistency",
                    title="Inconsistent GC Algorithms",
                    description=f"Found {len(gc_variations)} different GC algorithms across nodes: {', '.join(gc_details)}",
                    severity=Severity.WARNING,
                    category="configuration",
                    impact="Different performance characteristics across nodes",
                    recommendation="Use the same GC algorithm on all nodes",
                    gc_variations=gc_variations,
                    gc_algorithms=list(gc_variations.keys()),
                    config_location="JVM startup flags",
                )
                recommendations.append(gc_consistency_rec)
                self._record_check(
                    "config.jvm.gc.consistency",
                    "All nodes use the same GC algorithm",
                    "comp_jvm_input arguments",
                    "fail",
                    recommendation_id=gc_consistency_rec.id,
                    distinct_algorithms=list(gc_variations.keys()),
                )
            else:
                self._record_check(
                    "config.jvm.gc.consistency",
                    "All nodes use the same GC algorithm",
                    "comp_jvm_input arguments",
                    "pass",
                )

            # Analyze individual node JVM configurations
            heap_alloc_recs: List[Recommendation] = []
            gc_algo_recs: List[Recommendation] = []
            java_version_recs: List[Recommendation] = []
            jvm_per_node_evaluated = False

            for config in jvm_configs:
                if config["heap_size_bytes"] and config["system_memory_bytes"]:
                    jvm_per_node_evaluated = True
                    node_recommendations = self._get_jvm_heap_recommendations(
                        config["heap_size_bytes"],
                        config["gc_algorithm"],
                        config["system_memory_bytes"],
                        config["node"],
                        node_id=config["node_id"],
                        java_major=config.get("java_major"),
                        cassandra_version=config.get("cassandra_version"),
                    )
                    for r in node_recommendations:
                        if r.id == "config.jvm.heap.allocation":
                            heap_alloc_recs.append(r)
                        elif r.id == "config.jvm.gc.algorithm":
                            gc_algo_recs.append(r)
                        elif r.id == "config.jvm.java_version":
                            java_version_recs.append(r)
                        recommendations.append(r)

            self._record_jvm_aggregate(
                "config.jvm.heap.allocation",
                "Heap is sized 25-50% of system memory and within compressed-OOPs limits",
                "comp_jvm_heap_heapMaxSize + host_virtualmem_Total",
                jvm_per_node_evaluated,
                heap_alloc_recs,
            )
            self._record_jvm_aggregate(
                "config.jvm.gc.algorithm",
                "GC algorithm is appropriate for the JDK and heap size",
                "comp_jvm_input arguments + comp_jvm_heap_heapMaxSize",
                jvm_per_node_evaluated,
                gc_algo_recs,
            )
            self._record_jvm_aggregate(
                "config.jvm.java_version",
                "Java major version is appropriate for the Cassandra release",
                "comp_jvm_version + comp_releaseVersion",
                jvm_per_node_evaluated,
                java_version_recs,
            )

            return recommendations
        except Exception as e:
            logger.error(f"JVM settings analysis failed: {str(e)}")
            return []

    def _record_jvm_aggregate(
            self,
            check_id: str,
            description: str,
            data_source: str,
            evaluated: bool,
            recs: List[Recommendation],
    ) -> None:
        """Emit a single aggregated Check entry for a per-node JVM check."""
        if not evaluated:
            self._record_check(
                check_id, description, data_source, "no_data",
                skipped_reason="no node provided both heap and system memory data",
            )
        elif recs:
            # Filter to "fail-shaped" findings — INFO-only positive feedback like
            # "Shenandoah GC Detected (Recommended)" should still count as a pass.
            failing = [r for r in recs if r.severity != Severity.INFO or "recommended" not in (r.title or "").lower()]
            if failing:
                self._record_check(
                    check_id, description, data_source, "fail",
                    affected_count=len(failing),
                )
            else:
                self._record_check(check_id, description, data_source, "pass")
        else:
            self._record_check(check_id, description, data_source, "pass")

    def _get_jvm_heap_recommendations(
            self,
            heap_size: int,
            gc_algorithm: str,
            system_memory: int,
            node_identifier: str,
            node_id: Optional[str] = None,
            java_major: Optional[int] = None,
            cassandra_version: Optional[str] = None,
    ) -> List[Recommendation]:
        """Generate JVM heap recommendations.

        ``node_identifier`` is the human-readable ``hostname/ip`` label used in
        description text; ``node_id`` is the node's host UUID and is what
        populates ``affected_resources.nodes`` (kept consistent with every
        other check, which scopes findings by UUID).
        """
        recommendations = []
        is_5x = version_at_least(cassandra_version, V5_0)
        # Be conservative: if we don't know the JDK major, fall back to
        # behaviour that matches a modern (11+) deployment, since CMS is
        # already explicitly handled below and users on legacy JDK 8 will
        # also be flagged through the CMS branch.
        java_supports_shenandoah = java_major is None or java_major >= 11
        # On Cassandra 5.x with JDK 17 we recommend Shenandoah exclusively and
        # do *not* suggest G1GC as an alternative. (Cassandra 5.0 does not yet
        # support JDK 21, which would unlock generational ZGC; until then
        # Shenandoah is the recommended low-pause collector on this stack.)
        shenandoah_only = bool(is_5x and java_major is not None and java_major >= 17)

        # On Cassandra 5.x, Java 17 is the recommended LTS. Flag clusters that
        # are still on Java 8 or 11 so operators consider upgrading.
        if is_5x and java_major is not None and java_major < 17:
            recommendations.append(
                self._create_recommendation(
                    check_id="config.jvm.java_version",
                    title=f"Cassandra 5.x Running on Java {java_major}",
                    description=f"Node {node_identifier} runs Cassandra 5.x on Java {java_major}",
                    severity=Severity.INFO,
                    category="configuration",
                    impact="Cassandra 5.0 supports Java 11 and Java 17; Java 17 is the current LTS and is required for the latest Shenandoah improvements",
                    recommendation="Plan an upgrade to Java 17 (LTS) for new performance and GC options",
                    node_id=node_id,
                    java_major=java_major,
                    cassandra_version=cassandra_version,
                    config_location="JVM startup flags",
                )
            )

        # Convert bytes to more readable units
        heap_gb = heap_size / (1024 ** 3) if heap_size else 0
        system_gb = system_memory / (1024 ** 3) if system_memory else 0

        # Calculate heap percentage of system memory
        heap_percentage = (heap_gb / system_gb * 100) if system_gb > 0 else 0

        # Check heap size relative to system memory (should be 25-50% for Cassandra)
        if heap_percentage > 60:
            recommendations.append(
                self._create_recommendation(
                    check_id="config.jvm.heap.allocation",
                    title="Excessive Heap Allocation",
                    description=f"Node {node_identifier} allocates {heap_percentage:.1f}% of system memory ({heap_gb:.1f}GB of {system_gb:.1f}GB) to heap",
                    severity=Severity.WARNING,
                    category="configuration",
                    impact="Insufficient memory for page cache and system operations",
                    recommendation="Reduce heap to 25-50% of system memory for optimal performance",
                    node_id=node_id,
                    current_heap_gb=heap_gb,
                    system_memory_gb=system_gb,
                    heap_percentage=heap_percentage,
                    config_location="JVM startup flags"
                )
            )
        elif heap_percentage < 20 and system_gb > 32:
            recommendations.append(
                self._create_recommendation(
                    check_id="config.jvm.heap.allocation",
                    title="Underutilized Memory for Heap",
                    description=f"Node {node_identifier} only uses {heap_percentage:.1f}% of system memory ({heap_gb:.1f}GB of {system_gb:.1f}GB) for heap",
                    severity=Severity.INFO,
                    category="configuration",
                    impact="May not be fully utilizing available memory for Cassandra",
                    recommendation="Consider increasing heap size if experiencing GC pressure",
                    node_id=node_id,
                    current_heap_gb=heap_gb,
                    system_memory_gb=system_gb,
                    heap_percentage=heap_percentage,
                    config_location="JVM startup flags"
                )
            )

        if gc_algorithm.upper() in ["CMS", "CONCURRENT_MARK_SWEEP"]:
            # CMS is deprecated in Java 9+. Push operators to G1GC, or to
            # Shenandoah on the stacks where it's the right default.
            if shenandoah_only:
                cms_recommendation = "Migrate to Shenandoah GC (recommended on Cassandra 5.x + JDK 17)"
            elif java_supports_shenandoah:
                cms_recommendation = "Migrate to G1GC, or to Shenandoah GC (requires JDK 11+) for low-pause behaviour"
            else:
                cms_recommendation = "Migrate to G1GC"
            recommendations.append(
                self._create_recommendation(
                    check_id="config.jvm.gc.algorithm",
                    title="Deprecated CMS Garbage Collector",
                    description=f"Node {node_identifier} uses CMS GC which is deprecated",
                    severity=Severity.WARNING,
                    category="configuration",
                    impact="CMS is deprecated and will be removed in future Java versions",
                    recommendation=cms_recommendation,
                    node_id=node_id,
                    current_gc=gc_algorithm,
                    config_location="JVM startup flags"
                )
            )

        elif gc_algorithm.upper() in ["G1", "G1GC"]:
            # G1GC recommendations - suggest a low-pause alternative if the JDK supports one.
            # ZGC is intentionally NOT recommended for Cassandra workloads.
            if java_supports_shenandoah:
                alt_gc_text = "Shenandoah GC"
                if shenandoah_only:
                    alt_impact = (
                        "Cassandra 5.x on JDK 17 should use Shenandoah for low-pause performance; "
                        "G1GC has longer pause times and is not recommended on this stack"
                    )
                    alt_severity = Severity.WARNING
                    alt_recommendation = "Migrate to Shenandoah GC (recommended on Cassandra 5.x + JDK 17)"
                else:
                    alt_impact = "G1GC can have longer pause times compared to Shenandoah"
                    alt_severity = Severity.INFO
                    alt_recommendation = f"Consider migrating to {alt_gc_text} for lower and more predictable latencies"
            else:
                # Pre-JDK-11 — Shenandoah is not generally available.
                alt_gc_text = None
                alt_impact = None
                alt_severity = Severity.INFO
                alt_recommendation = None

            if alt_gc_text:
                recommendations.append(
                    self._create_recommendation(
                        check_id="config.jvm.gc.algorithm",
                        title=f"Consider {alt_gc_text} Instead of G1GC",
                        description=f"Node {node_identifier} uses G1GC" + (f" on Java {java_major}" if java_major else ""),
                        severity=alt_severity,
                        category="configuration",
                        impact=alt_impact,
                        recommendation=alt_recommendation,
                        node_id=node_id,
                        current_gc=gc_algorithm,
                        java_major=java_major,
                        config_location="JVM startup flags"
                    )
                )

            # Check compressed OOPs limit (>31GB risks losing compressed OOPs)
            if heap_gb >= 31:
                if shenandoah_only:
                    large_heap_advice = "Migrate to Shenandoah GC (recommended on Cassandra 5.x + JDK 17), which handles large heaps without losing compressed OOPs"
                elif java_supports_shenandoah:
                    large_heap_advice = "Decrease heap size to 31GB or below, switch to Shenandoah GC (which handles large heaps better), or consider multiple smaller nodes"
                else:
                    large_heap_advice = "Decrease heap size to 31GB or below, or consider multiple smaller nodes"
                recommendations.append(
                    self._create_recommendation(
                        check_id="config.jvm.heap.allocation",
                        title="Heap Size Above Compressed OOPs Limit",
                        description=f"Node {node_identifier} has G1GC heap of {heap_gb:.1f}GB, above 31GB compressed OOPs limit",
                        severity=Severity.WARNING,
                        category="configuration",
                        impact="Loss of compressed OOPs optimization, increased memory overhead",
                        recommendation=large_heap_advice,
                        node_id=node_id,
                        current_heap_gb=heap_gb,
                        config_location="JVM startup flags"
                    )
                )

            # G1GC specific tuning recommendations
            # On Cassandra 5.x + JDK 17, the operator should be moving off
            # G1GC entirely, so skip the positive finding in that case to
            # avoid contradictory advice.
            if heap_gb <= 31 and not shenandoah_only:
                recommendations.append(
                    self._create_recommendation(
                        check_id="config.jvm.heap.allocation",
                        title="G1GC Heap Size Within Compressed OOPs Range",
                        description=f"Node {node_identifier} has G1GC heap of {heap_gb:.1f}GB, within the compressed OOPs limit",
                        severity=Severity.INFO,
                        category="configuration",
                        impact="Good heap size for G1GC performance",
                        recommendation="Monitor GC logs to ensure pause times meet SLAs",
                        node_id=node_id,
                        current_heap_gb=heap_gb,
                        config_location="JVM startup flags"
                    )
                )

        elif gc_algorithm.upper() == "SHENANDOAHGC":
            # Shenandoah is recommended - just provide positive feedback
            recommendations.append(
                self._create_recommendation(
                    check_id="config.jvm.gc.algorithm",
                    title="Shenandoah GC Detected (Recommended)",
                    description=f"Node {node_identifier} uses Shenandoah GC for low-latency performance",
                    severity=Severity.INFO,
                    category="configuration",
                    impact="Excellent choice for low and predictable pause times",
                    recommendation="Monitor GC logs to ensure pause times meet SLAs",
                    node_id=node_id,
                    current_gc=gc_algorithm,
                    config_location="JVM startup flags"
                )
            )

            # Shenandoah handles large heaps well, but still check basics
            if heap_percentage > 60:
                recommendations.append(
                    self._create_recommendation(
                        check_id="config.jvm.heap.allocation",
                        title="Excessive Heap Allocation with Shenandoah",
                        description=f"Node {node_identifier} allocates {heap_percentage:.1f}% of system memory ({heap_gb:.1f}GB of {system_gb:.1f}GB) to heap",
                        severity=Severity.WARNING,
                        category="configuration",
                        impact="Insufficient memory for page cache and system operations",
                        recommendation="Even with Shenandoah, reduce heap to 25-50% of system memory",
                        node_id=node_id,
                        current_heap_gb=heap_gb,
                        system_memory_gb=system_gb,
                        heap_percentage=heap_percentage,
                        config_location="JVM startup flags"
                    )
                )

        elif gc_algorithm.upper() == "ZGC":
            # Non-generational ZGC (the only flavour available on JDK 17) is
            # not recommended for Cassandra: on write-heavy workloads its
            # single-generation design produces excessive allocation pressure
            # and throughput regressions. Generational ZGC addresses this but
            # requires JDK 21+, which Cassandra 5.0 does not yet support, so
            # ZGC is currently not a viable option for Cassandra clusters.
            recommendations.append(
                self._create_recommendation(
                    check_id="config.jvm.gc.algorithm",
                    title="ZGC Detected (Not Recommended for Cassandra)",
                    description=f"Node {node_identifier} uses ZGC" + (f" on Java {java_major}" if java_major else ""),
                    severity=Severity.WARNING,
                    category="configuration",
                    impact=(
                        "Non-generational ZGC (JDK 17) is not recommended for Cassandra workloads. "
                        "Only Generational ZGC is recommended, and it requires JDK 21+, "
                        "which Cassandra 5.0 does not yet support."
                    ),
                    recommendation=(
                        "Migrate to Shenandoah GC (recommended on Cassandra 5.x + JDK 17)"
                        if shenandoah_only
                        else "Migrate to G1GC, or to Shenandoah GC (JDK 11+) for low-latency performance"
                    ),
                    node_id=node_id,
                    current_gc=gc_algorithm,
                    java_major=java_major,
                    config_location="JVM startup flags"
                )
            )

        elif gc_algorithm == "unknown":
            recommendations.append(
                self._create_recommendation(
                    check_id="config.jvm.gc.algorithm",
                    title="Unable to Determine GC Algorithm",
                    description=f"Could not determine GC algorithm for node {node_identifier}",
                    severity=Severity.INFO,
                    category="configuration",
                    impact="Cannot provide GC-specific recommendations",
                    recommendation="Verify JVM arguments are properly configured",
                    node_id=node_id,
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
            self._record_check(
                "config.consistency.cassandra_yaml",
                "Cassandra.yaml settings are uniform across nodes",
                "comp_* (cassandra.yaml inventory)",
                "skipped",
                skipped_reason=f"only {len(cluster_state.nodes)} node(s) available — comparison needs ≥2",
            )
            recommendations.append(
                self._create_recommendation(
                    check_id="config.consistency.cassandra_yaml",
                    title="Insufficient Nodes for Configuration Comparison",
                    description="Less than two nodes available for configuration comparison",
                    severity=Severity.WARNING,
                    category="configuration",
                    impact="Unable to detect configuration inconsistencies",
                    recommendation="Ensure all nodes provide configuration data",
                    node_count=len(cluster_state.nodes),
                    config_location="cassandra.yaml",
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
        # Parallel map holding host UUIDs (rather than the hostname/ip labels in
        # ``config_values``) so ``affected_resources.nodes`` is scoped by UUID,
        # consistent with every other check.
        config_node_ids: Dict[str, Dict[Any, List[str]]] = {}
        for node in cluster_state.nodes.values():
            if not hasattr(node, "Details") or not node.Details:
                continue
            node_label = self._get_node_identifier(node)
            for name, kind in logical_settings:
                canonical, display = _read_logical(node, name, kind)
                if canonical is None:
                    continue
                config_values.setdefault(name, {}).setdefault(canonical, []).append(node_label)
                config_node_ids.setdefault(name, {}).setdefault(canonical, []).append(node.host_id)
                config_displays.setdefault(name, {}).setdefault(canonical, display)

        # Check for mismatches
        difference_count = 0
        mismatches = []
        for logical_name, values in config_values.items():
            if len(values) > 1:
                value_list = [config_displays[logical_name][v] for v in values.keys()]
                recommendations.append(
                    self._create_recommendation(
                        check_id="config.consistency.cassandra_yaml",
                        title=f"Configuration Mismatch: {logical_name}",
                        description=f"Nodes have different values for {logical_name}: {value_list}",
                        severity=Severity.WARNING,
                        category="configuration",
                        impact="Inconsistent cluster behavior and unpredictable performance",
                        recommendation="Align this configuration setting across all nodes in cassandra.yaml",
                        config_key=logical_name,
                        values=value_list,
                        affected_nodes=[
                            host_id
                            for host_ids in config_node_ids[logical_name].values()
                            for host_id in host_ids
                        ],
                        config_location="cassandra.yaml",
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
                    check_id="config.consistency.cassandra_yaml",
                    title="Multiple Configuration Mismatches Detected",
                    description=f"Found {difference_count} configuration differences across cluster nodes",
                    severity=Severity.WARNING,
                    category="configuration",
                    impact="Inconsistent performance characteristics across nodes",
                    recommendation="Review and align all configuration settings across nodes",
                    mismatch_count=difference_count,
                    mismatches=mismatches,
                    config_location="cassandra.yaml",
                )
            )
            self._record_check(
                "config.consistency.cassandra_yaml",
                "Cassandra.yaml settings are uniform across nodes",
                "comp_* (cassandra.yaml inventory)",
                "fail",
                mismatch_count=difference_count,
                mismatched_keys=[m["setting"] for m in mismatches],
            )
        else:
            self._record_check(
                "config.consistency.cassandra_yaml",
                "Cassandra.yaml settings are uniform across nodes",
                "comp_* (cassandra.yaml inventory)",
                "pass",
            )

        return recommendations

    def _analyze_specific_configurations(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze specific configuration settings for best practices"""
        recommendations = []

        disk_policy_seen = False
        disk_policy_fail: List[str] = []
        commitlog_seen = False
        commitlog_fail: List[str] = []

        for node in cluster_state.nodes.values():
            if not hasattr(node, 'Details') or not node.Details:
                continue
            # Authentication checks are handled by SecurityAnalyzer to avoid duplication.

            disk_policy = node.Details.get("comp_disk_failure_policy")
            if disk_policy is not None:
                disk_policy_seen = True
                if disk_policy == "ignore":
                    disk_policy_fail.append(node.host_id)
                    recommendations.append(
                        self._create_recommendation(
                            check_id="config.cassandra.disk_failure_policy",
                            title="Risky Disk Failure Policy (disk_failure_policy)",
                            description=f"Disk failure policy is set to 'ignore' on node {self._get_node_identifier(node)}",
                            severity=Severity.WARNING,
                            category="configuration",
                            impact="Data corruption risk if disk failures are ignored",
                            recommendation="Consider using 'stop' or 'best_effort' policy in cassandra.yaml",
                            node_id=node.host_id,
                            node=self._get_node_identifier(node),
                            current_policy=disk_policy,
                            config_location="cassandra.yaml",
                        )
                    )

            commitlog_sync = node.Details.get("comp_commitlog_sync")
            if commitlog_sync is not None:
                commitlog_seen = True
                if commitlog_sync == "batch":
                    sync_period = self._get_duration_ms(node, "commitlog_sync_batch_window")
                    is_5x_node = version_at_least(
                        node.Details.get("comp_releaseVersion") or node.Details.get("release_version"),
                        V5_0,
                    )
                    setting_name = "commitlog_sync_batch_window" if is_5x_node else "commitlog_sync_batch_window_in_ms"
                    if sync_period is not None and sync_period > 10:
                        commitlog_fail.append(node.host_id)
                        recommendations.append(
                            self._create_recommendation(
                                check_id="config.cassandra.commitlog_sync_batch_window",
                                title=f"High Commitlog Sync Window ({setting_name})",
                                description=f"Commitlog sync window is {sync_period}ms on node {self._get_node_identifier(node)}",
                                severity=Severity.WARNING,
                                category="configuration",
                                impact="Potential data loss on failure",
                                recommendation="Consider reducing sync window or using periodic sync in cassandra.yaml",
                                node_id=node.host_id,
                                node=self._get_node_identifier(node),
                                sync_window_ms=sync_period,
                                config_location="cassandra.yaml",
                            )
                        )

        if not disk_policy_seen:
            self._record_check(
                "config.cassandra.disk_failure_policy",
                "disk_failure_policy is not set to 'ignore'",
                "comp_disk_failure_policy",
                "no_data",
                skipped_reason="comp_disk_failure_policy not reported by any node",
            )
        elif disk_policy_fail:
            self._record_check(
                "config.cassandra.disk_failure_policy",
                "disk_failure_policy is not set to 'ignore'",
                "comp_disk_failure_policy",
                "fail",
                affected_nodes=disk_policy_fail,
            )
        else:
            self._record_check(
                "config.cassandra.disk_failure_policy",
                "disk_failure_policy is not set to 'ignore'",
                "comp_disk_failure_policy",
                "pass",
            )

        if not commitlog_seen:
            self._record_check(
                "config.cassandra.commitlog_sync_batch_window",
                "commitlog_sync_batch_window is within recommended bounds",
                "comp_commitlog_sync + comp_commitlog_sync_batch_window",
                "no_data",
                skipped_reason="comp_commitlog_sync not reported by any node",
            )
        elif commitlog_fail:
            self._record_check(
                "config.cassandra.commitlog_sync_batch_window",
                "commitlog_sync_batch_window is within recommended bounds",
                "comp_commitlog_sync + comp_commitlog_sync_batch_window",
                "fail",
                affected_nodes=commitlog_fail,
            )
        else:
            self._record_check(
                "config.cassandra.commitlog_sync_batch_window",
                "commitlog_sync_batch_window is within recommended bounds",
                "comp_commitlog_sync + comp_commitlog_sync_batch_window",
                "pass",
            )

        return recommendations
