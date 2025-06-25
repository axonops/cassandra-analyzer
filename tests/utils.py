"""
Test utilities and helper functions
"""

import random
from datetime import datetime, timedelta
from typing import Any, Dict, List

from cassandra_analyzer.models import ClusterState, MetricData, Node, Recommendation


def create_metric_data(
    metric_name: str,
    node: str,
    hours: int = 24,
    base_value: float = 50.0,
    variance: float = 10.0,
    spike_times: List[int] = None,
) -> MetricData:
    """Create synthetic metric data for testing"""
    from cassandra_analyzer.models import MetricPoint

    now = datetime.now()
    data_points = []

    for i in range(hours * 60):  # One data point per minute
        timestamp = now - timedelta(minutes=i)

        # Base value with some variance
        value = base_value + random.uniform(-variance, variance)

        # Add spikes at specified times
        if spike_times and i in spike_times:
            value += 30.0  # Spike value

        data_points.append(MetricPoint(timestamp=timestamp, value=value))

    return MetricData(
        metric_name=metric_name,
        labels={"node": node},
        data_points=data_points[::-1],  # Reverse to have chronological order
    )


def create_node_info(
    node_id: str, dc: str = "dc1", rack: str = "rack1", status: str = "UN", state: str = "NORMAL"
) -> Node:
    """Create a node info object for testing"""
    return Node(
        host_id=node_id,
        org="test-org",
        cluster="test-cluster",
        DC=dc,
        Details={
            "comp_rack": rack,
            "status": status,
            "state": state,
            "address": f"10.0.0.{node_id[-1]}",
            "num_tokens": 256,
        },
    )


def create_table_stats(
    keyspace: str = "test_ks",
    table: str = "test_table",
    partition_size_p99: int = 1048576,  # 1MB
    sstable_count: int = 4,
    tombstone_ratio: float = 0.05,
) -> Dict[str, Any]:
    """Create table statistics for testing"""
    return {
        "keyspace": keyspace,
        "table": table,
        "partition_count": 1000000,
        "partition_size_min": 1024,
        "partition_size_max": partition_size_p99 * 2,
        "partition_size_mean": partition_size_p99 / 2,
        "partition_size_p50": partition_size_p99 / 2,
        "partition_size_p75": partition_size_p99 * 0.75,
        "partition_size_p95": partition_size_p99 * 0.95,
        "partition_size_p99": partition_size_p99,
        "sstable_count": sstable_count,
        "sstables_per_read_p50": 2.0,
        "sstables_per_read_p75": 3.0,
        "sstables_per_read_p95": 4.0,
        "sstables_per_read_p99": float(sstable_count),
        "tombstone_ratio": tombstone_ratio,
        "compression_ratio": 0.5,
        "read_latency_p99": 10.0,
        "write_latency_p99": 5.0,
    }


def create_config_value(
    node: str, category: str, name: str, value: Any, default: Any = None
) -> Dict[str, Any]:
    """Create a configuration value for testing"""
    return {
        "node": node,
        "category": category,
        "name": name,
        "value": value,
        "default": default if default is not None else value,
        "is_modified": value != default if default is not None else False,
    }


def create_cluster_state(
    num_nodes: int = 3, unhealthy_nodes: int = 0, version: str = "4.0.11"
) -> ClusterState:
    """Create a cluster state for testing"""
    nodes = {}
    for i in range(1, num_nodes + 1):
        status = "DN" if i <= unhealthy_nodes else "UN"
        node = create_node_info(f"node{i}", status=status)
        nodes[node.host_id] = node

    return ClusterState(name="test-cluster", cluster_type="cassandra", nodes=nodes)


def assert_recommendation(
    recommendation: Recommendation,
    expected_category: str,
    expected_severity: str,
    expected_keywords: List[str] = None,
):
    """Assert that a recommendation matches expected values"""
    assert recommendation.category == expected_category
    assert recommendation.severity == expected_severity

    if expected_keywords:
        for keyword in expected_keywords:
            assert (
                keyword.lower() in recommendation.description.lower()
                or keyword.lower() in recommendation.title.lower()
            ), f"Expected keyword '{keyword}' not found in recommendation"


def create_gc_metrics(node: str, pause_times: List[float]) -> Dict[str, MetricData]:
    """Create GC-related metrics for testing"""
    now = datetime.now()
    timestamps = [(now - timedelta(minutes=i)).isoformat() for i in range(len(pause_times), 0, -1)]

    return {
        "gc_pause_times": MetricData(
            metric="gc_pause_ms", node=node, timestamps=timestamps, values=pause_times
        ),
        "gc_count": MetricData(
            metric="gc_count",
            node=node,
            timestamps=timestamps,
            values=list(range(len(pause_times))),
        ),
    }


def create_compaction_metrics(
    node: str, pending: List[int], completed: List[int]
) -> Dict[str, MetricData]:
    """Create compaction-related metrics for testing"""
    now = datetime.now()
    timestamps = [(now - timedelta(minutes=i)).isoformat() for i in range(len(pending), 0, -1)]

    return {
        "pending_compactions": MetricData(
            metric="pending_compactions",
            node=node,
            timestamps=timestamps,
            values=[float(v) for v in pending],
        ),
        "completed_compactions": MetricData(
            metric="completed_compactions",
            node=node,
            timestamps=timestamps,
            values=[float(v) for v in completed],
        ),
    }
