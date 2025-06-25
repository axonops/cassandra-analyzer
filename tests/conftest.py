"""
Pytest configuration and fixtures for Cassandra Analyzer tests
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock

import pytest

from cassandra_analyzer.config import Config
from cassandra_analyzer.models import ClusterState, MetricData, Node


@pytest.fixture
def mock_config():
    """Create a mock configuration for testing"""
    return Config(
        cluster={"org": "test-org", "cluster": "test-cluster", "cluster_type": "cassandra"},
        axonops={
            "api_url": "http://localhost:9090",
            "token": "test-token",
            "timeout": 30,
            "max_retries": 3,
        },
        analysis={
            "hours": 24,
            "metrics_resolution_seconds": 60,
            "enable_sections": {
                "infrastructure": True,
                "configuration": True,
                "operations": True,
                "datamodel": True,
                "security": True,
            },
            "thresholds": {
                "cpu_usage_warn": 80.0,
                "memory_usage_warn": 85.0,
                "disk_usage_warn": 80.0,
                "heap_usage_warn": 75.0,
                "gc_pause_warn_ms": 200,
                "gc_pause_critical_ms": 1000,
                "dropped_messages_warn": 1000,
                "dropped_messages_critical": 10000,
                "pending_compactions_warn": 100,
                "pending_compactions_critical": 1000,
                "blocked_tasks_warn": 1,
                "sstables_per_read_warn": 4,
                "partition_size_warn_mb": 100,
                "partition_size_critical_mb": 1000,
                "tombstone_ratio_warn": 0.1,
                "min_replication_factor": 3,
            },
        },
    )


@pytest.fixture
def mock_axonops_client():
    """Create a mock AxonOps client"""
    client = Mock()
    client.get_cluster_info.return_value = {"name": "test-cluster", "version": "4.0.11", "nodes": 3}
    return client


@pytest.fixture
def sample_cluster_state():
    """Create a sample cluster state for testing"""
    nodes = [
        Node(
            host_id="node1",
            org="test-org",
            cluster="test-cluster",
            DC="dc1",
            Details={
                "comp_rack": "rack1",
                "status": "UN",
                "state": "NORMAL",
                "address": "10.0.0.1",
                "num_tokens": 256,
            },
        ),
        Node(
            host_id="node2",
            org="test-org",
            cluster="test-cluster",
            DC="dc1",
            Details={
                "comp_rack": "rack2",
                "status": "UN",
                "state": "NORMAL",
                "address": "10.0.0.2",
                "num_tokens": 256,
            },
        ),
        Node(
            host_id="node3",
            org="test-org",
            cluster="test-cluster",
            DC="dc1",
            Details={
                "comp_rack": "rack3",
                "status": "UN",
                "state": "NORMAL",
                "address": "10.0.0.3",
                "num_tokens": 256,
            },
        ),
    ]

    nodes_dict = {node.host_id: node for node in nodes}

    return ClusterState(name="test-cluster", cluster_type="cassandra", nodes=nodes_dict)


@pytest.fixture
def sample_metrics():
    """Create sample metrics data for testing"""
    now = datetime.now()
    timestamps = [(now - timedelta(minutes=i)).isoformat() for i in range(60, 0, -1)]

    return {
        "cpu": MetricData(
            metric="cpu_usage",
            node="node1",
            timestamps=timestamps,
            values=[50.0 + (i % 10) for i in range(60)],
        ),
        "memory": MetricData(
            metric="memory_usage",
            node="node1",
            timestamps=timestamps,
            values=[70.0 + (i % 5) for i in range(60)],
        ),
        "disk": MetricData(
            metric="disk_usage",
            node="node1",
            timestamps=timestamps,
            values=[60.0 + (i % 3) for i in range(60)],
        ),
    }


@pytest.fixture
def mock_logger():
    """Create a mock logger"""
    return Mock()


class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)
