"""
Simple test to verify basic functionality
"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from cassandra_analyzer.config import Config
from cassandra_analyzer.models import ClusterState, Node, Recommendation


def test_imports():
    """Test that all imports work"""
    from cassandra_analyzer.analyzer import CassandraAnalyzer
    from cassandra_analyzer.client import AxonOpsClient
    from cassandra_analyzer.collectors import ClusterDataCollector

    assert True


def test_config_creation():
    """Test configuration object creation"""
    config = Config(
        cluster={"org": "test-org", "cluster": "test-cluster", "cluster_type": "cassandra"},
        axonops={"api_url": "http://localhost:9090", "token": "test-token"},
        analysis={"hours": 24},
    )
    assert config.cluster.org == "test-org"
    assert config.cluster.cluster == "test-cluster"


def test_cluster_state_creation():
    """Test cluster state model"""
    node = Node(host_id="node1", org="test-org", cluster="test-cluster", DC="dc1")

    cluster_state = ClusterState(name="test-cluster", nodes={"node1": node})

    assert cluster_state.name == "test-cluster"
    assert len(cluster_state.nodes) == 1


def test_recommendation_creation():
    """Test recommendation model"""
    from cassandra_analyzer.models import Severity

    rec = Recommendation(
        title="Test Issue", description="This is a test", severity=Severity.WARNING, category="test"
    )

    assert rec.title == "Test Issue"
    assert rec.severity == Severity.WARNING
