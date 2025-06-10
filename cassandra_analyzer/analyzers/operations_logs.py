"""
Operations log analyzer - analyzes operational issues from Cassandra logs
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import re
from collections import defaultdict
from ..models import ClusterState, Recommendation, Severity
from .base import BaseAnalyzer


class OperationsLogAnalyzer(BaseAnalyzer):
    """Analyzes operational issues from Cassandra logs via AxonOps histogram API"""
    
    def analyze(self, cluster_state: ClusterState) -> Dict[str, Any]:
        """Analyze operational logs"""
        recommendations = []
        summary = {}
        details = {}
        
        # Analyze prepared statements discards
        recommendations.extend(self._analyze_prepared_statements(cluster_state))
        
        # Analyze batch warnings
        recommendations.extend(self._analyze_batches(cluster_state))
        
        # Analyze tombstone warnings
        recommendations.extend(self._analyze_tombstone_warnings(cluster_state))
        
        # Analyze aggregation queries
        recommendations.extend(self._analyze_aggregation_queries(cluster_state))
        
        # Analyze GC pauses
        recommendations.extend(self._analyze_gc_pauses(cluster_state))
        
        # Analyze gossip pauses
        recommendations.extend(self._analyze_gossip_pauses(cluster_state))
        
        # Create summary
        summary = {
            "recommendations_count": len(recommendations),
            "log_analysis_performed": True
        }
        
        return {
            "recommendations": [r.dict() for r in recommendations],
            "summary": summary,
            "details": details
        }
    
    def _analyze_prepared_statements(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze prepared statement discards from logs"""
        recommendations = []
        
        # Get histogram data for prepared statement warnings
        histogram_data = cluster_state.log_events.get("prepared_statements", {})
        
        if not histogram_data or not isinstance(histogram_data, dict):
            return recommendations
        
        # Extract total count from metadata
        total_count = 0
        if "metadata" in histogram_data:
            total_count = int(histogram_data["metadata"].get("_count", 0))
        
        if total_count == 0:
            return recommendations
        
        # Analyze histogram data to understand time patterns
        histogram = histogram_data.get("histogram", [])
        if histogram:
            # Calculate time range from histogram
            timestamps = [point[0] for point in histogram]
            if timestamps:
                start_ts = min(timestamps)
                end_ts = max(timestamps)
                time_range_hours = max((end_ts - start_ts) / (1000 * 3600), 1)  # Convert ms to hours
                
                # Calculate rate
                discards_per_hour = total_count / time_range_hours
                
                # Find peak activity
                max_count = max(point[1] for point in histogram) if histogram else 0
                
                if discards_per_hour > 100:  # High rate threshold
                    recommendations.append(
                        self._create_recommendation(
                            title="High Prepared Statement Discard Rate",
                            description=f"Cluster is discarding {discards_per_hour:.1f} prepared statements per hour ({total_count} total)",
                            severity=Severity.CRITICAL,
                            category="operations",
                            impact="Application performance degradation due to statement re-preparation",
                            recommendation="Increase prepared_statement_cache_size_mb or optimize statement usage",
                            total_count=total_count,
                            hourly_rate=discards_per_hour,
                            discards_per_hour=discards_per_hour,
                            total_discards=total_count,
                            peak_count=max_count
                        )
                    )
                elif discards_per_hour > 50:  # Moderate rate
                    recommendations.append(
                        self._create_recommendation(
                            title="Moderate Prepared Statement Discards",
                            description=f"Cluster is discarding {discards_per_hour:.1f} prepared statements per hour ({total_count} total)",
                            severity=Severity.WARNING,
                            category="operations",
                            impact="Potential performance impact from statement re-preparation",
                            recommendation="Monitor prepared statement cache usage and consider increasing cache size",
                            total_count=total_count,
                            hourly_rate=discards_per_hour,
                            discards_per_hour=discards_per_hour,
                            total_discards=total_count
                        )
                    )
        elif total_count > 0:
            # No histogram data but we have a count
            recommendations.append(
                self._create_recommendation(
                    title="Prepared Statement Discards Detected",
                    description=f"Found {total_count} prepared statement discard warnings",
                    severity=Severity.WARNING,
                    category="operations",
                    impact="Potential performance impact from statement cache evictions",
                    recommendation="Review prepared statement cache configuration",
                    total_count=total_count,
                    hourly_rate=0,  # No histogram data available
                    total_discards=total_count
                )
            )
        
        return recommendations
    
    def _analyze_batches(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze batch size warnings from logs"""
        recommendations = []
        
        # Get histogram data for batch warnings
        histogram_data = cluster_state.log_events.get("batch_warnings", {})
        
        if not histogram_data or not isinstance(histogram_data, dict):
            return recommendations
        
        # Extract total count from metadata
        total_count = 0
        if "metadata" in histogram_data:
            total_count = int(histogram_data["metadata"].get("_count", 0))
        
        if total_count == 0:
            return recommendations
        
        # Analyze histogram data
        histogram = histogram_data.get("histogram", [])
        if histogram:
            # Calculate time range and rate
            timestamps = [point[0] for point in histogram]
            if timestamps:
                start_ts = min(timestamps)
                end_ts = max(timestamps)
                time_range_hours = max((end_ts - start_ts) / (1000 * 3600), 1)
                
                warnings_per_hour = total_count / time_range_hours
                
                # Find peak activity
                max_count = max(point[1] for point in histogram) if histogram else 0
                
                # Note about log search limitation
                note = "Note: Batch warnings detected via histogram analysis. Individual log entries may not be retrievable through search API."
                
                if total_count > 1000:
                    recommendations.append(
                        self._create_recommendation(
                            title="Excessive Large Batch Usage (Detected via Histogram)",
                            description=f"Found {total_count} large batch indicators ({warnings_per_hour:.1f} per hour). {note}",
                            severity=Severity.WARNING,
                            category="operations",
                            impact="Performance degradation and increased GC pressure",
                            recommendation="Review and optimize batch usage patterns in the application. Consider using batch_size_warn_threshold_in_kb and batch_size_fail_threshold_in_kb settings.",
                            total_count=total_count,
                            hourly_rate=warnings_per_hour,
                            total_warnings=total_count,
                            warnings_per_hour=warnings_per_hour,
                            peak_count=max_count,
                            api_note=note
                        )
                    )
                elif total_count > 100:
                    recommendations.append(
                        self._create_recommendation(
                            title="Batch Size Indicators Detected",
                            description=f"Found {total_count} batch-related indicators. {note}",
                            severity=Severity.INFO,
                            category="operations",
                            impact="Potential performance impact from batch operations",
                            recommendation="Monitor batch sizes using nodetool or metrics. Consider enabling batch size warnings in cassandra.yaml.",
                            total_count=total_count,
                            hourly_rate=warnings_per_hour,
                            total_warnings=total_count,
                            warnings_per_hour=warnings_per_hour,
                            api_note=note
                        )
                    )
                else:
                    # Don't report low counts as they may be false positives
                    pass
        elif total_count > 100:
            # No histogram data but we have a significant count
            note = "Note: Batch indicators detected via histogram analysis. Individual log entries may not be retrievable through search API."
            recommendations.append(
                self._create_recommendation(
                    title="Batch Activity Detected",
                    description=f"Found {total_count} batch-related indicators. {note}",
                    severity=Severity.INFO,
                    category="operations",
                    impact="Batch operations detected in cluster activity",
                    recommendation="Monitor batch performance metrics and consider batch size thresholds in cassandra.yaml",
                    total_count=total_count,
                    hourly_rate=0,  # No histogram data available
                    total_warnings=total_count,
                    api_note=note
                )
            )
        
        return recommendations
    
    def _analyze_tombstone_warnings(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze tombstone warnings from logs"""
        recommendations = []
        
        # Get histogram data for tombstone warnings
        histogram_data = cluster_state.log_events.get("tombstone_warnings", {})
        
        if not histogram_data or not isinstance(histogram_data, dict):
            return recommendations
        
        # Extract total count from metadata
        total_count = 0
        if "metadata" in histogram_data:
            total_count = int(histogram_data["metadata"].get("_count", 0))
        
        if total_count == 0:
            return recommendations
        
        # Analyze histogram data
        histogram = histogram_data.get("histogram", [])
        if histogram:
            # Calculate time patterns
            timestamps = [point[0] for point in histogram]
            if timestamps:
                start_ts = min(timestamps)
                end_ts = max(timestamps)
                time_range_hours = max((end_ts - start_ts) / (1000 * 3600), 1)
                
                warnings_per_hour = total_count / time_range_hours
                max_count = max(point[1] for point in histogram) if histogram else 0
                
                if total_count > 10000:
                    recommendations.append(
                        self._create_recommendation(
                            title="Excessive Tombstone Warnings",
                            description=f"Found {total_count} tombstone warnings ({warnings_per_hour:.1f} per hour)",
                            severity=Severity.CRITICAL,
                            category="operations",
                            impact="Severe read performance degradation and potential timeouts",
                            recommendation="Review data model and deletion patterns, consider TWCS for TTL data",
                            total_count=total_count,
                            hourly_rate=warnings_per_hour,
                            total_warnings=total_count,
                            warnings_per_hour=warnings_per_hour,
                            peak_count=max_count
                        )
                    )
                elif total_count > 1000:
                    recommendations.append(
                        self._create_recommendation(
                            title="High Tombstone Warning Rate",
                            description=f"Found {total_count} tombstone warnings",
                            severity=Severity.CRITICAL,
                            category="operations",
                            impact="Poor read performance due to tombstone scanning",
                            recommendation="Review deletion patterns and consider compaction strategy changes",
                            total_count=total_count,
                            hourly_rate=warnings_per_hour,
                            total_warnings=total_count,
                            warnings_per_hour=warnings_per_hour
                        )
                    )
                elif total_count > 100:
                    recommendations.append(
                        self._create_recommendation(
                            title="Tombstone Warnings Detected",
                            description=f"Found {total_count} tombstone warnings",
                            severity=Severity.WARNING,
                            category="operations",
                            impact="Potential read performance impact",
                            recommendation="Monitor tombstone patterns and optimize data model if needed",
                            total_count=total_count,
                            hourly_rate=warnings_per_hour,
                            total_warnings=total_count,
                            warnings_per_hour=warnings_per_hour
                        )
                    )
        elif total_count > 0:
            recommendations.append(
                self._create_recommendation(
                    title="Tombstone Issues Detected",
                    description=f"Found {total_count} tombstone-related warnings",
                    severity=Severity.WARNING,
                    category="operations",
                    impact="Tombstones can degrade read performance",
                    recommendation="Review deletion patterns in your data model",
                    total_count=total_count,
                    hourly_rate=0,  # No histogram data available
                    total_warnings=total_count
                )
            )
        
        return recommendations
    
    def _analyze_aggregation_queries(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze aggregation query warnings from logs"""
        recommendations = []
        
        # Get histogram data for aggregation queries
        histogram_data = cluster_state.log_events.get("aggregation_queries", {})
        
        if not histogram_data or not isinstance(histogram_data, dict):
            return recommendations
        
        # Extract total count from metadata
        total_count = 0
        if "metadata" in histogram_data:
            total_count = int(histogram_data["metadata"].get("_count", 0))
        
        if total_count == 0:
            return recommendations
        
        # Analyze histogram data
        histogram = histogram_data.get("histogram", [])
        if histogram:
            # Calculate time patterns
            timestamps = [point[0] for point in histogram]
            if timestamps:
                start_ts = min(timestamps)
                end_ts = max(timestamps)
                time_range_hours = max((end_ts - start_ts) / (1000 * 3600), 1)
                
                queries_per_hour = total_count / time_range_hours
                max_count = max(point[1] for point in histogram) if histogram else 0
                
                if queries_per_hour > 10:
                    recommendations.append(
                        self._create_recommendation(
                            title="Excessive Aggregation Query Usage",
                            description=f"Found {total_count} aggregation queries ({queries_per_hour:.1f} per hour)",
                            severity=Severity.CRITICAL,
                            category="operations",
                            impact="High coordinator CPU usage and potential timeouts",
                            recommendation="Pre-aggregate data or use analytics tools instead of aggregation queries",
                            total_count=total_count,
                            hourly_rate=queries_per_hour,
                            queries_per_hour=queries_per_hour,
                            total_queries=total_count,
                            peak_count=max_count
                        )
                    )
                elif queries_per_hour > 5:
                    recommendations.append(
                        self._create_recommendation(
                            title="Moderate Aggregation Query Usage",
                            description=f"Found {total_count} aggregation queries ({queries_per_hour:.1f} per hour)",
                            severity=Severity.WARNING,
                            category="operations",
                            impact="Increased coordinator load from aggregation processing",
                            recommendation="Consider pre-aggregating frequently queried data",
                            total_count=total_count,
                            hourly_rate=queries_per_hour,
                            queries_per_hour=queries_per_hour,
                            total_queries=total_count
                        )
                    )
                else:
                    recommendations.append(
                        self._create_recommendation(
                            title="Aggregation Queries Detected",
                            description=f"Found {total_count} aggregation queries",
                            severity=Severity.INFO,
                            category="operations",
                            impact="Aggregation queries can impact cluster performance",
                            recommendation="Monitor aggregation query patterns",
                            total_count=total_count,
                            hourly_rate=queries_per_hour,
                            queries_per_hour=queries_per_hour,
                            total_queries=total_count
                        )
                    )
        elif total_count > 0:
            recommendations.append(
                self._create_recommendation(
                    title="Aggregation Query Usage",
                    description=f"Found {total_count} aggregation query warnings",
                    severity=Severity.INFO,
                    category="operations",
                    impact="Aggregation queries consume coordinator resources",
                    recommendation="Consider data model optimizations for aggregations",
                    total_count=total_count,
                    hourly_rate=0,  # No histogram data available
                    total_queries=total_count
                )
            )
        
        return recommendations
    
    def _analyze_gc_pauses(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze GC pause warnings from logs"""
        recommendations = []
        
        # Get histogram data for GC pauses
        histogram_data = cluster_state.log_events.get("gc_pauses", {})
        
        if not histogram_data or not isinstance(histogram_data, dict):
            return recommendations
        
        # Extract total count from metadata
        total_count = 0
        if "metadata" in histogram_data:
            total_count = int(histogram_data["metadata"].get("_count", 0))
        
        if total_count == 0:
            return recommendations
        
        # Analyze histogram data
        histogram = histogram_data.get("histogram", [])
        if histogram:
            # Calculate time patterns
            timestamps = [point[0] for point in histogram]
            if timestamps:
                start_ts = min(timestamps)
                end_ts = max(timestamps)
                time_range_hours = max((end_ts - start_ts) / (1000 * 3600), 1)
                
                pauses_per_hour = total_count / time_range_hours
                max_count = max(point[1] for point in histogram) if histogram else 0
                
                # Since we can't see individual pause durations, we base severity on frequency
                if pauses_per_hour > 100:
                    recommendations.append(
                        self._create_recommendation(
                            title="Extreme GC Pause Frequency",
                            description=f"Found {total_count} GC pause warnings ({pauses_per_hour:.1f} per hour)",
                            severity=Severity.CRITICAL,
                            category="operations",
                            impact="Frequent GC pauses causing performance degradation",
                            recommendation="Review heap size and GC tuning, consider G1GC or heap reduction",
                            total_count=total_count,
                            hourly_rate=pauses_per_hour,
                            pauses_per_hour=pauses_per_hour,
                            total_pauses=total_count,
                            peak_count=max_count
                        )
                    )
                elif pauses_per_hour > 50:
                    recommendations.append(
                        self._create_recommendation(
                            title="High GC Pause Frequency",
                            description=f"Found {total_count} GC pause warnings ({pauses_per_hour:.1f} per hour)",
                            severity=Severity.CRITICAL,
                            category="operations",
                            impact="Frequent GC activity impacting performance",
                            recommendation="Optimize GC settings or reduce heap pressure",
                            total_count=total_count,
                            hourly_rate=pauses_per_hour,
                            pauses_per_hour=pauses_per_hour,
                            total_pauses=total_count
                        )
                    )
                elif pauses_per_hour > 10:
                    recommendations.append(
                        self._create_recommendation(
                            title="Moderate GC Pause Activity",
                            description=f"Found {total_count} GC pause warnings",
                            severity=Severity.WARNING,
                            category="operations",
                            impact="Periodic performance impact from GC",
                            recommendation="Monitor GC behavior and tune if necessary",
                            total_count=total_count,
                            hourly_rate=pauses_per_hour,
                            pauses_per_hour=pauses_per_hour,
                            total_pauses=total_count
                        )
                    )
        elif total_count > 0:
            recommendations.append(
                self._create_recommendation(
                    title="GC Pause Warnings Detected",
                    description=f"Found {total_count} GC-related warnings",
                    severity=Severity.WARNING,
                    category="operations",
                    impact="GC pauses can impact node performance",
                    recommendation="Review GC logs and heap configuration",
                    total_count=total_count,
                    hourly_rate=0,  # No histogram data available
                    total_pauses=total_count
                )
            )
        
        return recommendations
    
    def _analyze_gossip_pauses(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze gossip failure detector pause warnings from logs"""
        recommendations = []
        
        # Get histogram data for gossip pauses
        histogram_data = cluster_state.log_events.get("gossip_pauses", {})
        
        if not histogram_data or not isinstance(histogram_data, dict):
            return recommendations
        
        # Extract total count from metadata
        total_count = 0
        if "metadata" in histogram_data:
            total_count = int(histogram_data["metadata"].get("_count", 0))
        
        if total_count == 0:
            return recommendations
        
        # Analyze histogram data
        histogram = histogram_data.get("histogram", [])
        if histogram:
            # Calculate time patterns
            timestamps = [point[0] for point in histogram]
            if timestamps:
                start_ts = min(timestamps)
                end_ts = max(timestamps)
                time_range_hours = max((end_ts - start_ts) / (1000 * 3600), 1)
                
                pauses_per_hour = total_count / time_range_hours
                max_count = max(point[1] for point in histogram) if histogram else 0
                
                if total_count > 50 or pauses_per_hour > 10:
                    recommendations.append(
                        self._create_recommendation(
                            title="Significant Gossip Protocol Disruptions",
                            description=f"Found {total_count} gossip pause warnings ({pauses_per_hour:.1f} per hour)",
                            severity=Severity.CRITICAL,
                            category="operations",
                            impact="Cluster membership instability and false failure detections",
                            recommendation="Investigate network issues, GC pauses, or system resource constraints",
                            total_count=total_count,
                            hourly_rate=pauses_per_hour,
                            pause_count=total_count,
                            pauses_per_hour=pauses_per_hour,
                            peak_count=max_count
                        )
                    )
                elif total_count > 10:
                    recommendations.append(
                        self._create_recommendation(
                            title="Gossip Protocol Pauses Detected",
                            description=f"Found {total_count} gossip pause warnings",
                            severity=Severity.WARNING,
                            category="operations",
                            impact="Potential cluster communication delays",
                            recommendation="Monitor for network or resource issues",
                            total_count=total_count,
                            hourly_rate=pauses_per_hour,
                            pause_count=total_count,
                            pauses_per_hour=pauses_per_hour
                        )
                    )
        elif total_count > 0:
            recommendations.append(
                self._create_recommendation(
                    title="Gossip Pauses Detected",
                    description=f"Found {total_count} gossip-related warnings",
                    severity=Severity.WARNING,
                    category="operations",
                    impact="Gossip pauses can affect cluster stability",
                    recommendation="Review system resources and network health",
                    total_count=total_count,
                    hourly_rate=0,  # No histogram data available
                    pause_count=total_count
                )
            )
        
        return recommendations