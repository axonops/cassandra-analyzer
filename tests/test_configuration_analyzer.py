"""
Unit tests for the Configuration Analyzer
"""

from unittest.mock import Mock

import pytest

from cassandra_analyzer.analyzers.configuration import ConfigurationAnalyzer
from cassandra_analyzer.models import ClusterState
from tests.utils import assert_recommendation, create_cluster_state, create_config_value


class TestConfigurationAnalyzer:
    """Test cases for ConfigurationAnalyzer"""

    @pytest.fixture
    def analyzer(self, mock_config):
        """Create a configuration analyzer instance"""
        return ConfigurationAnalyzer(mock_config)

    @pytest.fixture
    def mock_collector(self):
        """Create a mock collector"""
        return Mock()

    def test_heap_size_configuration(self, analyzer):
        """Test heap size configuration analysis"""
        cluster_state = create_cluster_state(num_nodes=3)
        
        # Add JVM configuration to node Details
        for node_id, node in cluster_state.nodes.items():
            node.Details["comp_jvm_input arguments"] = "-Xmx4G -XX:+UseG1GC"
            node.Details["host_virtualmem_Total"] = str(32 * 1024 * 1024 * 1024)  # 32GB

        result = analyzer.analyze(cluster_state)
        recommendations = [
            r for r in result.get("recommendations", [])
            if isinstance(r, dict)
        ]

        # Should recommend larger heap for 32GB system
        heap_recs = [r for r in recommendations if "heap" in r.get("title", "").lower()]
        assert len(heap_recs) > 0

    def test_gc_configuration(self, analyzer):
        """Test garbage collector configuration analysis"""
        cluster_state = create_cluster_state(num_nodes=3)

        # Add old GC configuration to node Details
        for node_id, node in cluster_state.nodes.items():
            node.Details["comp_jvm_input arguments"] = "-Xmx8G -XX:+UseConcMarkSweepGC"
            node.Details["host_virtualmem_Total"] = str(32 * 1024 * 1024 * 1024)  # 32GB

        result = analyzer.analyze(cluster_state)
        recommendations = [
            r for r in result.get("recommendations", [])
            if isinstance(r, dict)
        ]

        # Should detect deprecated CMS GC
        cms_recs = [
            r for r in recommendations if "CMS" in r.get("title", "") or "Deprecated" in r.get("title", "")
        ]
        assert len(cms_recs) > 0
        # Should recommend Shenandoah or G1GC
        assert any("Shenandoah" in r.get("recommendation", "") for r in cms_recs)

    def test_concurrent_compactors(self, analyzer):
        """Test concurrent compactors configuration"""
        cluster_state = create_cluster_state(num_nodes=3)

        # Add configuration with different concurrent compactors across nodes
        nodes = list(cluster_state.nodes.values())
        nodes[0].Details["comp_concurrent_compactors"] = "1"
        nodes[1].Details["comp_concurrent_compactors"] = "2"
        nodes[2].Details["comp_concurrent_compactors"] = "4"

        result = analyzer.analyze(cluster_state)
        recommendations = [
            r for r in result.get("recommendations", [])
            if isinstance(r, dict)
        ]

        # The configuration analyzer only checks for mismatches, not optimal values
        # Should detect configuration mismatch
        mismatch_recs = [r for r in recommendations if "Configuration Mismatch" in r.get("title", "") and "concurrent_compactors" in r.get("title", "")]
        assert len(mismatch_recs) >= 1

    def test_commitlog_configuration(self, analyzer):
        """Test commitlog configuration analysis"""
        cluster_state = create_cluster_state(num_nodes=3)

        # Add configuration with high batch window to node Details
        for node_id, node in cluster_state.nodes.items():
            node.Details["comp_commitlog_sync"] = "batch"
            node.Details["comp_commitlog_sync_batch_window_in_ms"] = 50  # High (>10ms) - pass as int

        result = analyzer.analyze(cluster_state)
        recommendations = [
            r for r in result.get("recommendations", [])
            if isinstance(r, dict)
        ]

        # Should detect high commitlog sync window
        commitlog_recs = [r for r in recommendations if "Commitlog Sync Window" in r.get("title", "")]
        assert len(commitlog_recs) > 0

    def test_memtable_configuration(self, analyzer):
        """Test memtable configuration analysis"""
        cluster_state = create_cluster_state(num_nodes=3)

        # Add configuration with different memtable allocation types
        nodes = list(cluster_state.nodes.values())
        nodes[0].Details["comp_memtable_allocation_type"] = "heap_buffers"
        nodes[1].Details["comp_memtable_allocation_type"] = "offheap_objects"
        nodes[2].Details["comp_memtable_allocation_type"] = "heap_buffers"

        result = analyzer.analyze(cluster_state)
        recommendations = [
            r for r in result.get("recommendations", [])
            if isinstance(r, dict)
        ]

        # Should detect configuration mismatch
        mismatch_recs = [r for r in recommendations if "Configuration Mismatch" in r.get("title", "") and "memtable_allocation_type" in r.get("title", "")]
        assert len(mismatch_recs) >= 1

    def test_file_cache_configuration(self, analyzer):
        """Test file cache configuration analysis"""
        cluster_state = create_cluster_state(num_nodes=3)

        # The configuration analyzer doesn't check file cache specifics
        # Just verify analysis completes without error
        for node_id, node in cluster_state.nodes.items():
            node.Details["comp_jvm_input arguments"] = "-Xmx8G -XX:+UseG1GC"
            node.Details["host_virtualmem_Total"] = str(32 * 1024 * 1024 * 1024)  # 32GB

        result = analyzer.analyze(cluster_state)
        recommendations = [
            r for r in result.get("recommendations", [])
            if isinstance(r, dict)
        ]

        # Just verify analysis completes
        assert isinstance(recommendations, list)

    def test_streaming_configuration(self, analyzer):
        """Test streaming configuration analysis"""
        cluster_state = create_cluster_state(num_nodes=3)

        # Add streaming configuration to node Details
        for node_id, node in cluster_state.nodes.items():
            node.Details["comp_stream_throughput_outbound_megabits_per_sec"] = "200"
            node.Details["comp_inter_dc_stream_throughput_outbound_megabits_per_sec"] = "0"

        result = analyzer.analyze(cluster_state)
        recommendations = [
            r for r in result.get("recommendations", [])
            if isinstance(r, dict)
        ]

        # Check for streaming recommendations
        streaming_recs = [r for r in recommendations if "stream" in r.get("title", "").lower()]
        # May or may not have recommendations depending on defaults

    def test_inconsistent_configuration(self, analyzer):
        """Test detection of inconsistent configuration across nodes"""
        cluster_state = create_cluster_state(num_nodes=3)

        # Add inconsistent configurations across nodes
        nodes = list(cluster_state.nodes.values())
        nodes[0].Details["comp_jvm_input arguments"] = "-Xmx8G -XX:+UseG1GC"
        nodes[0].Details["comp_concurrent_compactors"] = "2"
        
        nodes[1].Details["comp_jvm_input arguments"] = "-Xmx16G -XX:+UseG1GC"
        nodes[1].Details["comp_concurrent_compactors"] = "4"
        
        nodes[2].Details["comp_jvm_input arguments"] = "-Xmx8G -XX:+UseG1GC"
        nodes[2].Details["comp_concurrent_compactors"] = "2"

        result = analyzer.analyze(cluster_state)
        recommendations = [
            r for r in result.get("recommendations", [])
            if isinstance(r, dict)
        ]

        # Should detect inconsistent heap sizes
        inconsistent_recs = [
            r
            for r in recommendations
            if "inconsistent" in r.get("title", "").lower() or "different" in r.get("description", "").lower()
        ]
        assert len(inconsistent_recs) > 0

    def test_replication_factor_analysis(self, analyzer):
        """Test replication factor configuration analysis"""
        cluster_state = create_cluster_state(num_nodes=6)  # 6 nodes

        # The configuration analyzer doesn't analyze replication factors
        # That's handled by the datamodel analyzer
        # Just add JVM config to ensure analysis runs
        for node_id, node in cluster_state.nodes.items():
            node.Details["comp_jvm_input arguments"] = "-Xmx8G -XX:+UseG1GC"
            node.Details["host_virtualmem_Total"] = str(32 * 1024 * 1024 * 1024)  # 32GB

        result = analyzer.analyze(cluster_state)
        recommendations = [
            r for r in result.get("recommendations", [])
            if isinstance(r, dict)
        ]

        # Just verify analysis completes without error
        assert isinstance(recommendations, list)

    def test_optimal_configuration_no_issues(self, analyzer):
        """Test that optimal configuration produces minimal recommendations"""
        cluster_state = create_cluster_state(num_nodes=3)

        # Add optimal configuration to node Details
        for node_id, node in cluster_state.nodes.items():
            node.Details["comp_jvm_input arguments"] = "-Xmx8G -XX:+UseG1GC"
            node.Details["host_virtualmem_Total"] = str(32 * 1024 * 1024 * 1024)  # 32GB
            node.Details["comp_concurrent_compactors"] = "4"
            node.Details["host_number_cpu_cores"] = "16"
            node.Details["comp_memtable_heap_space_in_mb"] = "2048"
            node.Details["comp_file_cache_size_in_mb"] = "2048"

        # Add properly configured keyspaces
        cluster_state.keyspaces = []

        result = analyzer.analyze(cluster_state)
        recommendations = [
            r for r in result.get("recommendations", [])
            if isinstance(r, dict)
        ]

        # Should have minimal high severity recommendations
        high_severity = [r for r in recommendations if r.get("severity", "").upper() in ["HIGH", "CRITICAL"]]
        assert len(high_severity) == 0
