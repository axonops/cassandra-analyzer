"""
Unit tests for cassandra_analyzer.utils.version
"""

import pytest

from cassandra_analyzer.utils.version import (
    V3_0,
    V4_0,
    V5_0,
    cluster_at_least,
    cluster_max_version,
    cluster_min_version,
    parse_version,
    version_at_least,
    version_below,
)
from tests.utils import create_cluster_state


class TestParseVersion:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("4.0.11", (4, 0, 11)),
            ("5.0.0", (5, 0, 0)),
            ("5.0", (5, 0, 0)),
            ("5", (5, 0, 0)),
            ("4.1.3-SNAPSHOT", (4, 1, 3)),
            ("5.0-alpha2", (5, 0, 0)),
            ("3.11.16", (3, 11, 16)),
            ("  5.0.2  ", (5, 0, 2)),
        ],
    )
    def test_well_formed(self, raw, expected):
        assert parse_version(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "unknown", "abc", "garbage"])
    def test_unparseable(self, raw):
        assert parse_version(raw) is None


class TestVersionComparisons:
    def test_at_least_string_target(self):
        assert version_at_least("5.0.2", "5.0") is True
        assert version_at_least("4.1.3", "5.0") is False
        assert version_at_least("5.0.0", "5.0.0") is True

    def test_at_least_tuple_target(self):
        assert version_at_least("5.0.2", V5_0) is True
        assert version_at_least("4.0.11", V5_0) is False

    def test_below(self):
        assert version_below("4.0.11", V5_0) is True
        assert version_below("5.0.2", V5_0) is False
        assert version_below("3.11.16", V4_0) is True

    def test_unknown_versions_are_neither(self):
        # Unparseable versions return False for both at_least and below — callers
        # must explicitly handle the unknown case.
        assert version_at_least(None, V5_0) is False
        assert version_below(None, V5_0) is False
        assert version_at_least("garbage", V5_0) is False


class TestClusterHelpers:
    def test_cluster_min_max(self):
        cs = create_cluster_state(num_nodes=3, version="4.0.11")
        assert cluster_min_version(cs) == (4, 0, 11)
        assert cluster_max_version(cs) == (4, 0, 11)

    def test_cluster_min_with_mixed_versions(self):
        cs = create_cluster_state(num_nodes=3, version="5.0.0")
        # Force one node to a lower version
        first_node = next(iter(cs.nodes.values()))
        first_node.Details["comp_releaseVersion"] = "4.1.3"
        first_node.Details["comp_cassandra_version"] = "4.1.3"
        assert cluster_min_version(cs) == (4, 1, 3)
        assert cluster_max_version(cs) == (5, 0, 0)

    def test_cluster_at_least_requires_all_nodes(self):
        cs = create_cluster_state(num_nodes=3, version="5.0.2")
        assert cluster_at_least(cs, V5_0) is True

        # Mixed cluster — one node still on 4.x.
        first_node = next(iter(cs.nodes.values()))
        first_node.Details["comp_releaseVersion"] = "4.1.3"
        first_node.Details["comp_cassandra_version"] = "4.1.3"
        assert cluster_at_least(cs, V5_0) is False

    def test_cluster_at_least_unknown_returns_false(self):
        cs = create_cluster_state(num_nodes=2, version="5.0.0")
        first_node = next(iter(cs.nodes.values()))
        first_node.Details["comp_releaseVersion"] = ""
        first_node.Details["comp_cassandra_version"] = "unknown"
        assert cluster_at_least(cs, V5_0) is False
