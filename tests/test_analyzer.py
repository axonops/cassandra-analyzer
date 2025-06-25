"""
Tests for the main analyzer module
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from cassandra_analyzer.analyzer import CassandraAnalyzer
from cassandra_analyzer.models import Recommendation


class TestCassandraAnalyzer:
    """Test cases for CassandraAnalyzer class"""

    @pytest.fixture
    def analyzer_params(self):
        """Common parameters for creating analyzer"""
        from datetime import datetime, timedelta

        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=24)

        return {
            "org": "test-org",
            "cluster_type": "cassandra",
            "cluster": "test-cluster",
            "start_time": start_time,
            "end_time": end_time,
            "output_dir": Path("/tmp"),
        }

    def test_analyzer_initialization(self, mock_config):
        """Test that analyzer initializes correctly with config"""
        from datetime import datetime, timedelta

        with patch("cassandra_analyzer.analyzer.AxonOpsClient") as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=24)

            analyzer = CassandraAnalyzer(
                client=mock_client,
                config=mock_config,
                org="test-org",
                cluster_type="cassandra",
                cluster="test-cluster",
                start_time=start_time,
                end_time=end_time,
                output_dir=Path("/tmp"),
            )

            assert analyzer.config == mock_config
            assert analyzer.client == mock_client
            assert analyzer.collector is not None
            assert len(analyzer.analyzers) > 0

    @patch("cassandra_analyzer.analyzer.ClusterDataCollector")
    @patch("cassandra_analyzer.analyzer.AxonOpsClient")
    def test_analyze_success(
        self, mock_client_class, mock_collector_class, mock_config, sample_cluster_state, analyzer_params
    ):
        """Test successful analysis execution"""
        # Setup mocks
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_collector = Mock()
        mock_collector.collect.return_value = sample_cluster_state
        mock_collector_class.return_value = mock_collector

        # Create analyzer
        analyzer = CassandraAnalyzer(
            client=mock_client,
            config=mock_config,
            **analyzer_params
        )

        # Mock the _run_analyzers method to return test recommendations
        with patch.object(analyzer, "_run_analyzers") as mock_run_analyzers:
            mock_run_analyzers.return_value = {
                "infrastructure": {
                    "recommendations": [
                        Recommendation(
                            category="test",
                            severity="info",
                            title="Test Recommendation",
                            description="This is a test",
                            impact="Low",
                            remediation="No action needed",
                        )
                    ]
                }
            }

            # Run analysis
            report_path = analyzer.analyze()

        # Verify
        assert isinstance(report_path, Path)
        mock_collector.collect.assert_called_once()

    @patch("cassandra_analyzer.analyzer.ClusterDataCollector")
    @patch("cassandra_analyzer.analyzer.AxonOpsClient")
    def test_analyze_with_failed_analyzer(
        self, mock_client_class, mock_collector_class, mock_config, sample_cluster_state, analyzer_params
    ):
        """Test analysis continues when individual analyzer fails"""
        # Setup mocks
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        mock_collector = Mock()
        mock_collector.collect.return_value = sample_cluster_state
        mock_collector_class.return_value = mock_collector

        # Create analyzer
        analyzer = CassandraAnalyzer(
            client=mock_client,
            config=mock_config,
            **analyzer_params
        )

        # Mock the _run_analyzers method to simulate one analyzer failing
        def mock_run_analyzers_with_failure(cluster_state):
            results = {}
            # Simulate first analyzer failing
            results["infrastructure"] = {
                "error": "Analyzer failed",
                "recommendations": []
            }
            # Other analyzers succeed
            results["configuration"] = {
                "recommendations": [
                    Recommendation(
                        category="test",
                        severity="info",
                        title="Test Recommendation",
                        description="This is a test",
                        impact="Low",
                        remediation="No action needed",
                    )
                ]
            }
            return results

        with patch.object(analyzer, "_run_analyzers", side_effect=mock_run_analyzers_with_failure):
            # Run analysis - should not raise exception
            report_path = analyzer.analyze()

        # Verify
        assert isinstance(report_path, Path)

    def test_generate_report(self, mock_config, sample_cluster_state, analyzer_params):
        """Test report generation"""
        # Need to create mock client for analyzer
        with patch("cassandra_analyzer.analyzer.AxonOpsClient") as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            analyzer = CassandraAnalyzer(
                client=mock_client,
                config=mock_config,
                **analyzer_params
            )

        # Mock the internal methods
        with patch.object(analyzer, "_collect_data") as mock_collect:
            with patch.object(analyzer, "_run_analyzers") as mock_run:
                with patch.object(analyzer, "_generate_report") as mock_generate:
                    mock_collect.return_value = sample_cluster_state
                    mock_run.return_value = {"infrastructure": []}
                    mock_generate.return_value = Path("/tmp/report.md")

                    # Run analysis
                    report_path = analyzer.analyze()

                    # Verify calls
                    mock_collect.assert_called_once()
                    mock_run.assert_called_once_with(sample_cluster_state)
                    mock_generate.assert_called_once()
                    assert report_path == Path("/tmp/report.md")

    def test_disabled_analyzers(self, mock_config, analyzer_params):
        """Test that disabled analyzers are not included"""
        # Disable some sections
        mock_config.analysis.enable_sections["infrastructure"] = False
        mock_config.analysis.enable_sections["security"] = False

        with patch("cassandra_analyzer.analyzer.AxonOpsClient") as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            analyzer = CassandraAnalyzer(
                client=mock_client,
                config=mock_config,
                **analyzer_params
            )

        # Check that disabled analyzers are not in the list
        analyzer_names = [type(a).__name__ for a in analyzer.analyzers.values()]
        assert "InfrastructureAnalyzer" not in analyzer_names
        assert "SecurityAnalyzer" not in analyzer_names
        assert "ConfigurationAnalyzer" in analyzer_names  # Should still be enabled
