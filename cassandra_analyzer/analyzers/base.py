"""
Base analyzer class
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
from ..models import ClusterState, Recommendation
from ..config import Config


class BaseAnalyzer(ABC):
    """Base class for all analyzers"""
    
    def __init__(self, config: Config):
        self.config = config
        self.thresholds = config.analysis.thresholds
    
    @abstractmethod
    def analyze(self, cluster_state: ClusterState) -> Dict[str, Any]:
        """
        Analyze the cluster state and return results
        
        Returns:
            Dict containing:
            - recommendations: List of Recommendation objects
            - summary: Dict with summary statistics
            - details: Dict with detailed analysis data
        """
        pass
    
    def _create_recommendation(
        self,
        title: str,
        description: str,
        severity: str,
        category: str,
        impact: str = None,
        recommendation: str = None,
        current_value: str = None,
        reference_url: str = None,
        **context
    ) -> Recommendation:
        """Helper method to create recommendations"""
        return Recommendation(
            title=title,
            description=description,
            severity=severity,
            category=category,
            impact=impact,
            recommendation=recommendation,
            current_value=current_value,
            reference_url=reference_url,
            context=context
        )
    
    def _get_metric_average(self, metrics: Dict[str, Any], metric_name: str) -> float:
        """Get average value for a metric"""
        metric_data = metrics.get(metric_name, [])
        if not metric_data:
            return 0.0
        
        # Assuming metric_data is a list of MetricData objects
        total_points = 0
        total_value = 0.0
        
        for metric in metric_data:
            if hasattr(metric, 'data_points'):
                for point in metric.data_points:
                    total_value += point.value
                    total_points += 1
        
        return total_value / total_points if total_points > 0 else 0.0
    
    def _get_metric_max(self, metrics: Dict[str, Any], metric_name: str) -> float:
        """Get maximum value for a metric"""
        metric_data = metrics.get(metric_name, [])
        if not metric_data:
            return 0.0
        
        max_value = 0.0
        for metric in metric_data:
            if hasattr(metric, 'data_points'):
                for point in metric.data_points:
                    max_value = max(max_value, point.value)
        
        return max_value
    
    def _is_system_keyspace(self, keyspace_name: str) -> bool:
        """Check if a keyspace is a system keyspace"""
        system_keyspaces = {
            'system',
            'system_auth', 
            'system_distributed',
            'system_schema',
            'system_traces'
        }
        return keyspace_name in system_keyspaces