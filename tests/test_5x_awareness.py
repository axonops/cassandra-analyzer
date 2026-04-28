"""
Tests for Cassandra 5.x-specific recommendations:
- UnifiedCompactionStrategy detection
- SAI vs legacy 2i indexes
- Materialized view warning text
- Java 17/21 + ZGC awareness
- Streaming-timeout key fallback
"""

import pytest

from cassandra_analyzer.analyzers.configuration import ConfigurationAnalyzer
from cassandra_analyzer.analyzers.datamodel import DataModelAnalyzer
from cassandra_analyzer.analyzers.extended_configuration import (
    ExtendedConfigurationAnalyzer,
)
from cassandra_analyzer.models import Keyspace, Table
from tests.utils import create_cluster_state


def _table(keyspace: str, name: str, cql: str, compaction: str = "SizeTieredCompactionStrategy") -> Table:
    return Table(
        Name=name,
        Keyspace=keyspace,
        GCGrace=864000,
        CompactionStrategy=compaction,
        ID=f"{keyspace}_{name}_id",
        CQL=cql,
    )


def _keyspace(name: str, tables) -> Keyspace:
    return Keyspace(
        Name=name,
        Tables=tables,
        replication_strategy="SimpleStrategy",
        replication_options={"replication_factor": "3"},
    )


def _titles(recs):
    return [r.get("title", "") for r in recs if isinstance(r, dict)]


def _by_title(recs, needle: str):
    return [r for r in recs if isinstance(r, dict) and needle.lower() in r.get("title", "").lower()]


# ---------------------------------------------------------------------------
# Compaction strategies
# ---------------------------------------------------------------------------


class TestUnifiedCompactionStrategy:
    @pytest.fixture
    def analyzer(self, mock_config):
        return DataModelAnalyzer(mock_config)

    def test_ucs_on_5x_cluster_is_not_flagged(self, analyzer):
        cs = create_cluster_state(num_nodes=3, version="5.0.2")
        cs.keyspaces = {
            "app": _keyspace(
                "app",
                [
                    _table(
                        "app",
                        "events",
                        "CREATE TABLE app.events (id text PRIMARY KEY)",
                        compaction="UnifiedCompactionStrategy",
                    )
                ],
            )
        }
        recs = analyzer.analyze(cs).get("recommendations", [])
        assert _by_title(recs, "UnifiedCompactionStrategy Used on Pre-5.0 Cluster") == []

    def test_ucs_on_pre_5_cluster_is_critical(self, analyzer):
        cs = create_cluster_state(num_nodes=3, version="4.1.3")
        cs.keyspaces = {
            "app": _keyspace(
                "app",
                [
                    _table(
                        "app",
                        "events",
                        "CREATE TABLE app.events (id text PRIMARY KEY)",
                        compaction="UnifiedCompactionStrategy",
                    )
                ],
            )
        }
        recs = analyzer.analyze(cs).get("recommendations", [])
        critical = _by_title(recs, "UnifiedCompactionStrategy Used on Pre-5.0 Cluster")
        assert len(critical) == 1
        assert critical[0]["severity"] == "critical"

    def test_stcs_on_5x_recommends_ucs(self, analyzer):
        cs = create_cluster_state(num_nodes=3, version="5.0.0")
        cs.keyspaces = {
            "app": _keyspace(
                "app",
                [
                    _table(
                        "app",
                        "events",
                        "CREATE TABLE app.events (id text PRIMARY KEY)",
                        compaction="SizeTieredCompactionStrategy",
                    )
                ],
            )
        }
        recs = analyzer.analyze(cs).get("recommendations", [])
        ucs_suggestions = _by_title(recs, "Consider Unified Compaction Strategy")
        assert len(ucs_suggestions) == 1
        assert ucs_suggestions[0]["severity"] == "info"

    def test_stcs_on_4x_does_not_recommend_ucs(self, analyzer):
        cs = create_cluster_state(num_nodes=3, version="4.1.3")
        cs.keyspaces = {
            "app": _keyspace(
                "app",
                [
                    _table(
                        "app",
                        "events",
                        "CREATE TABLE app.events (id text PRIMARY KEY)",
                        compaction="SizeTieredCompactionStrategy",
                    )
                ],
            )
        }
        recs = analyzer.analyze(cs).get("recommendations", [])
        assert _by_title(recs, "Consider Unified Compaction Strategy") == []


# ---------------------------------------------------------------------------
# Secondary indexes — SAI vs legacy 2i vs SASI
# ---------------------------------------------------------------------------


class TestIndexClassification:
    @pytest.fixture
    def analyzer(self, mock_config):
        return DataModelAnalyzer(mock_config)

    def test_legacy_2i_on_5x_recommends_sai(self, analyzer):
        cs = create_cluster_state(num_nodes=3, version="5.0.0")
        cql = (
            "CREATE TABLE app.users (id uuid PRIMARY KEY, email text);\n"
            "CREATE INDEX users_email_idx ON app.users (email);"
        )
        cs.keyspaces = {"app": _keyspace("app", [_table("app", "users", cql)])}
        recs = analyzer.analyze(cs).get("recommendations", [])
        sai_recommend = _by_title(recs, "Legacy Secondary Indexes Detected")
        assert len(sai_recommend) == 1
        assert "SAI" in sai_recommend[0]["recommendation"]

    def test_legacy_2i_on_4x_uses_existing_text(self, analyzer):
        cs = create_cluster_state(num_nodes=3, version="4.1.3")
        cql = (
            "CREATE TABLE app.users (id uuid PRIMARY KEY, email text);\n"
            "CREATE INDEX users_email_idx ON app.users (email);"
        )
        cs.keyspaces = {"app": _keyspace("app", [_table("app", "users", cql)])}
        recs = analyzer.analyze(cs).get("recommendations", [])
        # The pre-5.0 path keeps the historical "Secondary Indexes Detected" title.
        assert _by_title(recs, "Secondary Indexes Detected")
        assert _by_title(recs, "Legacy Secondary Indexes Detected") == []

    def test_sai_on_5x_is_info(self, analyzer):
        cs = create_cluster_state(num_nodes=3, version="5.0.2")
        cql = (
            "CREATE TABLE app.users (id uuid PRIMARY KEY, email text);\n"
            "CREATE CUSTOM INDEX users_email_sai ON app.users (email) "
            "USING 'StorageAttachedIndex';"
        )
        cs.keyspaces = {"app": _keyspace("app", [_table("app", "users", cql)])}
        recs = analyzer.analyze(cs).get("recommendations", [])
        sai_info = _by_title(recs, "Storage-Attached Indexes (SAI) Detected")
        assert len(sai_info) == 1
        assert sai_info[0]["severity"] == "info"
        # Legacy bucket should remain empty on a SAI-only schema.
        assert _by_title(recs, "Secondary Indexes Detected") == []

    def test_sai_on_pre_5_is_critical(self, analyzer):
        cs = create_cluster_state(num_nodes=3, version="4.1.3")
        cql = (
            "CREATE TABLE app.users (id uuid PRIMARY KEY, email text);\n"
            "CREATE CUSTOM INDEX users_email_sai ON app.users (email) "
            "USING 'StorageAttachedIndex';"
        )
        cs.keyspaces = {"app": _keyspace("app", [_table("app", "users", cql)])}
        recs = analyzer.analyze(cs).get("recommendations", [])
        critical = _by_title(recs, "SAI Indexes Used on Pre-5.0 Cluster")
        assert len(critical) == 1
        assert critical[0]["severity"] == "critical"

    def test_sasi_is_warning(self, analyzer):
        cs = create_cluster_state(num_nodes=3, version="4.1.3")
        cql = (
            "CREATE TABLE app.users (id uuid PRIMARY KEY, email text);\n"
            "CREATE CUSTOM INDEX users_email_sasi ON app.users (email) "
            "USING 'org.apache.cassandra.index.sasi.SASIIndex';"
        )
        cs.keyspaces = {"app": _keyspace("app", [_table("app", "users", cql)])}
        recs = analyzer.analyze(cs).get("recommendations", [])
        sasi = _by_title(recs, "SASI Indexes Detected")
        assert len(sasi) == 1
        assert sasi[0]["severity"] == "warning"


# ---------------------------------------------------------------------------
# Materialized views
# ---------------------------------------------------------------------------


class TestMaterializedViewMessaging:
    @pytest.fixture
    def analyzer(self, mock_config):
        return DataModelAnalyzer(mock_config)

    def _mv_cluster(self, version: str):
        cs = create_cluster_state(num_nodes=3, version=version)
        cs.keyspaces = {
            "app": _keyspace(
                "app",
                [
                    _table(
                        "app",
                        "users_by_email",
                        "CREATE MATERIALIZED VIEW app.users_by_email AS "
                        "SELECT * FROM app.users WHERE email IS NOT NULL "
                        "PRIMARY KEY (email, id)",
                    )
                ],
            )
        }
        return cs

    def test_mv_on_5x_uses_5x_specific_text(self, analyzer):
        recs = analyzer.analyze(self._mv_cluster("5.0.0")).get("recommendations", [])
        mv = _by_title(recs, "Materialized Views Detected")
        assert len(mv) == 1
        assert "5.x" in mv[0]["impact"]

    def test_mv_on_4x_uses_legacy_text(self, analyzer):
        recs = analyzer.analyze(self._mv_cluster("4.1.3")).get("recommendations", [])
        mv = _by_title(recs, "Materialized Views Detected")
        assert len(mv) == 1
        assert "experimental" in mv[0]["impact"].lower()
        assert "5.x" not in mv[0]["impact"]


# ---------------------------------------------------------------------------
# Native transport / MV writes term gating
# ---------------------------------------------------------------------------


class TestNativeTransportMVGating:
    @pytest.fixture
    def analyzer(self, mock_config):
        return ExtendedConfigurationAnalyzer(mock_config)

    def _populate_node(self, node):
        node.Details.update(
            {
                "host_cpu_CPU": "7",  # 8 cores
                "comp_concurrent_reads": "32",
                "comp_concurrent_writes": "32",
                "comp_concurrent_counter_writes": "32",
                "comp_concurrent_materialized_view_writes": "32",
                "comp_native_transport_max_threads": "128",
            }
        )

    def test_with_no_mvs_drops_mv_term(self, analyzer):
        cs = create_cluster_state(num_nodes=1, version="5.0.0")
        for node in cs.nodes.values():
            self._populate_node(node)
        # No keyspaces → no materialized views.
        cs.keyspaces = {}
        recs = analyzer.analyze(cs).get("recommendations", [])
        ntm = _by_title(recs, "Low Native Transport Max Threads")
        assert len(ntm) == 1
        # Without MVs the formula in the recommendation text drops the MV term.
        assert "concurrent_materialized_view_writes" not in ntm[0]["recommendation"]

    def test_with_mvs_keeps_mv_term(self, analyzer):
        cs = create_cluster_state(num_nodes=1, version="5.0.0")
        for node in cs.nodes.values():
            self._populate_node(node)
        cs.keyspaces = {
            "app": _keyspace(
                "app",
                [
                    _table(
                        "app",
                        "u_by_email",
                        "CREATE MATERIALIZED VIEW app.u_by_email AS SELECT * "
                        "FROM app.u WHERE email IS NOT NULL "
                        "PRIMARY KEY (email, id)",
                    )
                ],
            )
        }
        recs = analyzer.analyze(cs).get("recommendations", [])
        ntm = _by_title(recs, "Low Native Transport Max Threads")
        assert len(ntm) == 1
        assert "concurrent_materialized_view_writes" in ntm[0]["recommendation"]


# ---------------------------------------------------------------------------
# Version-floor / consistency
# ---------------------------------------------------------------------------


class TestVersionFloor:
    @pytest.fixture
    def analyzer(self, mock_config):
        return ExtendedConfigurationAnalyzer(mock_config)

    def test_pre_4_is_critical(self, analyzer):
        cs = create_cluster_state(num_nodes=3, version="3.11.16")
        recs = analyzer.analyze(cs).get("recommendations", [])
        unsupported = _by_title(recs, "Unsupported Cassandra Version")
        assert len(unsupported) == 1
        assert unsupported[0]["severity"] == "critical"
        assert "5.x" in unsupported[0]["recommendation"]

    def test_4x_gets_5x_upgrade_nudge(self, analyzer):
        cs = create_cluster_state(num_nodes=3, version="4.1.3")
        recs = analyzer.analyze(cs).get("recommendations", [])
        nudge = _by_title(recs, "Consider Upgrading to Cassandra 5.x")
        assert len(nudge) == 1
        assert nudge[0]["severity"] == "info"

    def test_5x_no_version_floor_recommendations(self, analyzer):
        cs = create_cluster_state(num_nodes=3, version="5.0.0")
        recs = analyzer.analyze(cs).get("recommendations", [])
        assert _by_title(recs, "Unsupported Cassandra Version") == []
        assert _by_title(recs, "Consider Upgrading to Cassandra 5.x") == []


# ---------------------------------------------------------------------------
# Streaming timeout — duration-key fallback
# ---------------------------------------------------------------------------


class TestStreamingTimeoutKey:
    @pytest.fixture
    def analyzer(self, mock_config):
        return ExtendedConfigurationAnalyzer(mock_config)

    def test_legacy_in_ms_key_still_works(self, analyzer):
        cs = create_cluster_state(num_nodes=1, version="4.1.3")
        for node in cs.nodes.values():
            node.Details["comp_streaming_socket_timeout_in_ms"] = "3600000"  # 1 hour
        recs = analyzer.analyze(cs).get("recommendations", [])
        rec = _by_title(recs, "Non-Default Streaming Timeout")
        assert len(rec) == 1
        assert "streaming_socket_timeout_in_ms" in rec[0]["title"]

    def test_5x_duration_string_key(self, analyzer):
        cs = create_cluster_state(num_nodes=1, version="5.0.0")
        for node in cs.nodes.values():
            # 5.0 form: bare key with duration syntax.
            node.Details["comp_streaming_socket_timeout"] = "1h"
        recs = analyzer.analyze(cs).get("recommendations", [])
        rec = _by_title(recs, "Non-Default Streaming Timeout")
        assert len(rec) == 1
        # On 5.x the title surfaces the modern key name.
        assert "streaming_socket_timeout" in rec[0]["title"]
        assert "_in_ms" not in rec[0]["title"]


# ---------------------------------------------------------------------------
# JVM — Java 17/21 and ZGC
# ---------------------------------------------------------------------------


class TestJvmAwareness:
    @pytest.fixture
    def analyzer(self, mock_config):
        return ConfigurationAnalyzer(mock_config)

    def _setup(self, cs, jvm_args: str, java_version: str = None, mem_gb: int = 32):
        for node in cs.nodes.values():
            node.Details["comp_jvm_input arguments"] = jvm_args
            node.Details["host_virtualmem_Total"] = str(mem_gb * 1024 * 1024 * 1024)
            if java_version is not None:
                node.Details["comp_jvm_version"] = java_version

    def test_zgc_on_java_17_is_recommended(self, analyzer):
        cs = create_cluster_state(num_nodes=1, version="5.0.0")
        self._setup(cs, "-Xmx40G -XX:+UseZGC", java_version="17.0.10", mem_gb=128)
        recs = analyzer.analyze(cs).get("recommendations", [])
        zgc = _by_title(recs, "ZGC Detected (Recommended on Java 17+)")
        assert len(zgc) == 1
        assert zgc[0]["severity"] == "info"

    def test_zgc_on_java_11_is_warned_about(self, analyzer):
        cs = create_cluster_state(num_nodes=1, version="4.1.3")
        self._setup(cs, "-Xmx20G -XX:+UseZGC", java_version="11.0.21", mem_gb=64)
        recs = analyzer.analyze(cs).get("recommendations", [])
        zgc = [r for r in recs if isinstance(r, dict) and r.get("title", "").startswith("ZGC Detected") and "Recommended" not in r.get("title", "")]
        assert len(zgc) == 1
        assert "Java 17+" in zgc[0]["recommendation"]

    def test_g1gc_on_java_17_mentions_zgc(self, analyzer):
        cs = create_cluster_state(num_nodes=1, version="5.0.0")
        self._setup(cs, "-Xmx24G -XX:+UseG1GC", java_version="17.0.10", mem_gb=64)
        recs = analyzer.analyze(cs).get("recommendations", [])
        g1 = [r for r in recs if isinstance(r, dict) and "Instead of G1GC" in r.get("title", "")]
        assert len(g1) == 1
        assert "ZGC" in g1[0]["recommendation"]

    def test_g1gc_on_java_11_only_mentions_shenandoah(self, analyzer):
        cs = create_cluster_state(num_nodes=1, version="4.1.3")
        self._setup(cs, "-Xmx24G -XX:+UseG1GC", java_version="11.0.21", mem_gb=64)
        recs = analyzer.analyze(cs).get("recommendations", [])
        g1 = [r for r in recs if isinstance(r, dict) and "Instead of G1GC" in r.get("title", "")]
        assert len(g1) == 1
        assert "Shenandoah" in g1[0]["recommendation"]
        assert "ZGC" not in g1[0]["recommendation"]

    def test_5x_on_java_11_recommends_java_17(self, analyzer):
        cs = create_cluster_state(num_nodes=1, version="5.0.0")
        self._setup(cs, "-Xmx24G -XX:+UseG1GC", java_version="11.0.21", mem_gb=64)
        recs = analyzer.analyze(cs).get("recommendations", [])
        java = [r for r in recs if isinstance(r, dict) and "Java 11" in r.get("title", "")]
        assert len(java) == 1
        assert "Java 17" in java[0]["recommendation"]

    def test_4x_on_java_11_does_not_recommend_java_17(self, analyzer):
        cs = create_cluster_state(num_nodes=1, version="4.1.3")
        self._setup(cs, "-Xmx24G -XX:+UseG1GC", java_version="11.0.21", mem_gb=64)
        recs = analyzer.analyze(cs).get("recommendations", [])
        # The "Cassandra 5.x Running on Java 11" rec should not appear when not on 5.x.
        assert [r for r in recs if isinstance(r, dict) and "Cassandra 5.x Running on Java" in r.get("title", "")] == []
