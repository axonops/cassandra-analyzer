"""
Base analyzer class
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..config import Config
from ..models import ClusterState, Recommendation

# Cassandra 5.0 renamed many ``*_in_ms`` / ``*_in_mb`` settings to use the
# duration / data-size syntax (``200ms``, ``5s``, ``1h``, ``128MiB``). The
# AxonOps agent surfaces whichever form the node actually has, so analyzers
# need to be able to read either variant.
_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h|d)?\s*$", re.IGNORECASE)
_DURATION_UNITS_MS = {
    None: 1,
    "ms": 1,
    "s": 1000,
    "m": 60_000,
    "h": 3_600_000,
    "d": 86_400_000,
}


def _parse_duration_to_ms(value: Any) -> Optional[int]:
    """Parse a Cassandra duration into milliseconds.

    Accepts plain integers (treated as milliseconds, matching the legacy
    ``*_in_ms`` convention), bare numeric strings, and the 5.x duration
    syntax (``200ms``, ``5s``, ``1h``). Returns ``None`` for unparseable
    input.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = _DURATION_RE.match(str(value))
    if not match:
        return None
    number = float(match.group(1))
    unit = (match.group(2) or "").lower() or None
    factor = _DURATION_UNITS_MS.get(unit)
    if factor is None:
        return None
    return int(number * factor)


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

    def _get_duration_ms(self, node, base_name: str) -> Optional[int]:
        """Read a duration setting from a node's Details, in milliseconds.

        Tries ``comp_<base_name>_in_ms`` (legacy 4.x and earlier) first, then
        falls back to ``comp_<base_name>`` which on 5.x carries duration syntax
        like ``200ms`` / ``5s`` / ``1h``. Returns ``None`` if neither is set
        or the value cannot be parsed.
        """
        details = getattr(node, "Details", {}) or {}
        legacy = details.get(f"comp_{base_name}_in_ms")
        if legacy is not None:
            parsed = _parse_duration_to_ms(legacy)
            if parsed is not None:
                return parsed
        modern = details.get(f"comp_{base_name}")
        if modern is not None:
            return _parse_duration_to_ms(modern)
        return None