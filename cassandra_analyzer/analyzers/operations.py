"""
Operations analyzer - checks operational health and performance
"""

from typing import Dict, Any, List
from ..models import ClusterState, Recommendation, Severity
from .base import BaseAnalyzer
from ..utils.gc_metric_selector import GCMetricSelector


class OperationsAnalyzer(BaseAnalyzer):
    """Analyzes operational aspects of the cluster"""
    
    def analyze(self, cluster_state: ClusterState) -> Dict[str, Any]:
        """Analyze operational health"""
        recommendations = []
        summary = {}
        details = {}
        
        # Analyze dropped messages
        recommendations.extend(self._analyze_dropped_messages(cluster_state))
        
        # Analyze GC performance
        recommendations.extend(self._analyze_gc_performance(cluster_state))
        
        # Analyze compactions
        recommendations.extend(self._analyze_compactions(cluster_state))
        
        # Analyze thread pools
        recommendations.extend(self._analyze_thread_pools(cluster_state))
        
        # Create summary
        summary = {
            "recommendations_count": len(recommendations),
            "critical_issues": sum(1 for r in recommendations if r.severity == Severity.CRITICAL),
            "warnings": sum(1 for r in recommendations if r.severity == Severity.WARNING)
        }
        
        return {
            "recommendations": [r.dict() for r in recommendations],
            "summary": summary,
            "details": details
        }
    
    def _analyze_dropped_messages(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze dropped messages by type"""
        recommendations = []
        
        # Check each type of dropped message
        dropped_types = {
            "dropped_mutations": {
                "title": "Dropped Mutations",
                "impact": "Write requests being dropped, potential data loss",
                "recommendation": "Check for overloaded nodes, increase write capacity"
            },
            "dropped_mutation_responses": {
                "title": "Dropped Mutation Responses", 
                "impact": "Write acknowledgments being dropped, client timeouts",
                "recommendation": "Check network and coordinator load"
            },
            "dropped_reads": {
                "title": "Dropped Read Requests",
                "impact": "Read requests being dropped, query failures",
                "recommendation": "Check read thread pools and increase read capacity"
            },
            "dropped_hints": {
                "title": "Dropped Hints",
                "impact": "Hints being dropped, eventual consistency issues",
                "recommendation": "Check hint storage capacity and delivery rate"
            },
            "dropped_hint_responses": {
                "title": "Dropped Hint Responses",
                "impact": "Hint acknowledgments dropped, hint replay issues", 
                "recommendation": "Check hint handoff settings and network"
            }
        }
        
        # Track total dropped messages across all types
        total_dropped = 0
        critical_drops = []
        warning_drops = []
        
        for metric_name, drop_info in dropped_types.items():
            dropped_count = self._get_metric_average(cluster_state.metrics, metric_name)
            
            if dropped_count > 0:
                total_dropped += dropped_count
                
                # Determine severity based on count
                if dropped_count > 100:  # More than 100/sec is critical
                    severity = Severity.CRITICAL
                    critical_drops.append((drop_info["title"], dropped_count))
                elif dropped_count > 10:  # More than 10/sec is warning
                    severity = Severity.WARNING
                    warning_drops.append((drop_info["title"], dropped_count))
                else:
                    continue  # Skip info level for now
                
                recommendations.append(
                    self._create_recommendation(
                        title=f"{drop_info['title']} Detected",
                        description=f"{drop_info['title']}: {dropped_count:.1f} messages/sec",
                        severity=severity,
                        category="operations",
                        impact=drop_info["impact"],
                        recommendation=drop_info["recommendation"],
                        dropped_count=dropped_count,
                        metric_type=metric_name
                    )
                )
        
        # Add overall summary if multiple types are dropping
        if len(critical_drops) + len(warning_drops) > 2:
            recommendations.append(
                self._create_recommendation(
                    title="Multiple Message Types Being Dropped",
                    description=f"Total dropped messages across all types: {total_dropped:.0f}/sec",
                    severity=Severity.CRITICAL if critical_drops else Severity.WARNING,
                    category="operations",
                    impact="System is under severe stress, multiple subsystems affected",
                    recommendation="Immediate action required: scale cluster, reduce load, or tune performance",
                    total_dropped=total_dropped,
                    critical_types=[t[0] for t in critical_drops],
                    warning_types=[t[0] for t in warning_drops]
                )
            )
        
        # Also check the general dropped messages metric for backward compatibility
        general_dropped = self._get_metric_average(cluster_state.metrics, "dropped_messages")
        if general_dropped > self.thresholds.dropped_messages_critical and not recommendations:
            recommendations.append(
                self._create_recommendation(
                    title="Critical Dropped Messages",
                    description=f"High rate of dropped messages: {general_dropped:.0f}",
                    severity=Severity.CRITICAL,
                    category="operations",
                    impact="Data loss and client request failures",
                    recommendation="Investigate network issues, tune thread pools, or scale cluster",
                    dropped_messages=general_dropped
                )
            )
        
        return recommendations
    
    def _analyze_gc_performance(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze garbage collection performance"""
        recommendations = []
        
        # Detect GC type from nodes data to select appropriate metrics
        gc_types = set()
        node_gc_info = {}
        
        if hasattr(cluster_state, 'nodes_data') and cluster_state.nodes_data:
            for node in cluster_state.nodes_data:
                jvm_args = node.get('comp_jvm_input arguments', '')
                gc_type = GCMetricSelector.detect_gc_type(jvm_args)
                gc_types.add(gc_type)
                node_gc_info[node.get('host_Hostname', 'Unknown')] = gc_type
        
        # Check if we have mixed GC types
        if len(gc_types) > 1:
            gc_summary = ", ".join([f"{host}: {gc}" for host, gc in node_gc_info.items()])
            recommendations.append(
                self._create_recommendation(
                    title="Inconsistent GC Algorithms",
                    description=f"Different GC algorithms detected across nodes",
                    severity=Severity.WARNING,
                    category="operations",
                    impact="Inconsistent performance characteristics across nodes",
                    recommendation="Standardize GC algorithm across all nodes",
                    gc_types=list(gc_types),
                    node_gc_info=node_gc_info
                )
            )
        
        # Use the most common GC type for metric selection
        if gc_types:
            most_common_gc = max(gc_types, key=lambda x: list(node_gc_info.values()).count(x))
            
            # Add GC-specific recommendations
            if hasattr(cluster_state, 'nodes_data') and cluster_state.nodes_data:
                # Get heap size from first node for recommendations
                first_node = cluster_state.nodes_data[0]
                jvm_args = first_node.get('comp_jvm_input arguments', '')
                import re
                heap_match = re.search(r'-Xmx(\d+)([GMK])', jvm_args)
                if heap_match:
                    size = int(heap_match.group(1))
                    unit = heap_match.group(2)
                    heap_gb = size if unit == 'G' else size/1024 if unit == 'M' else 0
                    
                    gc_recs = GCMetricSelector.get_gc_recommendations(most_common_gc, heap_gb)
                    for rec in gc_recs:
                        recommendations.append(
                            self._create_recommendation(
                                title=f"GC Configuration Advisory ({most_common_gc})",
                                description=rec,
                                severity=Severity.INFO,
                                category="operations",
                                impact="Sub-optimal GC performance",
                                recommendation="Review GC configuration based on heap size and workload",
                                gc_type=most_common_gc,
                                heap_size_gb=heap_gb
                            )
                        )
        
        # Check young generation GC
        avg_gc_young = self._get_metric_average(cluster_state.metrics, "gc_young_rate")
        
        # Check old generation GC (Note: AxonOps only provides Young Gen metrics for G1)
        # For G1GC, most of the GC activity is in Young Generation
        # Old generation collections are rare and handled by mixed collections
        avg_gc_old = 0  # Not available in AxonOps metrics
        
        # Combined GC analysis (values are already in milliseconds from rate calculation)
        # For G1GC, this is primarily Young Generation time
        total_gc_time = avg_gc_young
        
        if total_gc_time > self.thresholds.gc_pause_critical_ms:
            recommendations.append(
                self._create_recommendation(
                    title="Critical GC Pause Times",
                    description=f"GC pause times are critically high: {total_gc_time:.1f}ms average (Young Generation)",
                    severity=Severity.CRITICAL,
                    category="operations",
                    impact="Severe performance impact and potential timeouts",
                    recommendation="Tune JVM heap settings, review GC algorithm, or add nodes",
                    gc_pause_ms=total_gc_time,
                    gc_young_ms=avg_gc_young
                )
            )
        elif total_gc_time > self.thresholds.gc_pause_warn_ms:
            recommendations.append(
                self._create_recommendation(
                    title="Elevated GC Pause Times",
                    description=f"GC pause times are elevated: {total_gc_time:.1f}ms average",
                    severity=Severity.WARNING,
                    category="operations",
                    impact="Performance degradation and increased latency",
                    recommendation="Review heap sizing and consider GC tuning",
                    gc_pause_ms=total_gc_time
                )
            )
        
        return recommendations
    
    def _analyze_compactions(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze compaction performance"""
        recommendations = []
        
        pending_compactions = self._get_metric_average(cluster_state.metrics, "pending_compactions")
        
        if pending_compactions > self.thresholds.pending_compactions_critical:
            recommendations.append(
                self._create_recommendation(
                    title="Critical Compaction Backlog",
                    description=f"High number of pending compactions: {pending_compactions:.0f}",
                    severity=Severity.CRITICAL,
                    category="operations",
                    impact="Read performance degradation and disk space bloat",
                    recommendation="Increase compaction throughput or add nodes",
                    pending_compactions=pending_compactions
                )
            )
        elif pending_compactions > self.thresholds.pending_compactions_warn:
            recommendations.append(
                self._create_recommendation(
                    title="Elevated Compaction Backlog",
                    description=f"Elevated number of pending compactions: {pending_compactions:.0f}",
                    severity=Severity.WARNING,
                    category="operations",
                    impact="Potential read performance impact",
                    recommendation="Monitor compaction throughput and consider tuning",
                    pending_compactions=pending_compactions
                )
            )
        
        return recommendations
    
    def _analyze_thread_pools(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze thread pool health"""
        recommendations = []
        
        # Check for blocked/pending tasks
        blocked_tasks = self._get_metric_max(cluster_state.metrics, "thread_pool_blocked")
        
        if blocked_tasks > self.thresholds.blocked_tasks_warn:
            recommendations.append(
                self._create_recommendation(
                    title="Blocked Thread Pool Tasks",
                    description=f"Thread pools have pending/blocked tasks: {blocked_tasks:.0f}",
                    severity=Severity.WARNING,
                    category="operations",
                    impact="Request queuing and increased latency",
                    recommendation="Review thread pool sizing and system resources",
                    blocked_tasks=blocked_tasks
                )
            )
        
        # Check hints
        hints_in_progress = self._get_metric_average(cluster_state.metrics, "hints_in_progress")
        if hints_in_progress > 0:
            recommendations.append(
                self._create_recommendation(
                    title="Hints in Progress",
                    description=f"Cluster has {hints_in_progress:.0f} hints in progress",
                    severity=Severity.INFO,
                    category="operations",
                    impact="Indicates nodes are catching up with missed writes",
                    recommendation="Monitor hint delivery and ensure nodes are healthy",
                    hints_in_progress=hints_in_progress
                )
            )
        
        return recommendations