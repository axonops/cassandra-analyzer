"""
Data model analyzer - checks schema design and table configurations
"""

from typing import Dict, Any, List
import html
import re
from ..models import ClusterState, Recommendation, Severity
from ..utils import V5_0, cluster_at_least, cluster_min_version
from .base import BaseAnalyzer
from .table_analyzer import TableAnalyzer


_DATAMODEL_SECTION_CHECKS = {
    "_analyze_replication": (
        "schema.replication",
        "Keyspaces use NetworkTopologyStrategy with adequate RF",
        "schema.keyspaces",
    ),
    "_analyze_table_performance": (
        "schema.table_performance",
        "Per-table read/write metrics indicate no hotspots or wide-row issues",
        "metrics.cas_Table_*",
    ),
    "_analyze_bloom_filters": (
        "schema.bloom_filters",
        "Bloom filter false-positive rates are within healthy bounds",
        "metrics.cas_Table_BloomFilter*",
    ),
    "_analyze_compression": (
        "schema.compression",
        "Tables use compression appropriate for their access pattern",
        "schema.tables.compression",
    ),
    "_analyze_compaction_strategies": (
        "schema.compaction_strategy",
        "Tables use a compaction strategy appropriate for their workload",
        "schema.tables.compaction",
    ),
    "_analyze_secondary_indexes": (
        "schema.secondary_indexes",
        "No problematic / wide-cardinality secondary indexes",
        "schema.tables.cql",
    ),
    "_analyze_collection_types": (
        "schema.collections",
        "Collection columns are sized within recommended bounds",
        "schema.tables.cql",
    ),
    "_analyze_materialized_views": (
        "schema.materialized_views",
        "Materialized views are absent or appropriate for the workload",
        "schema.tables.materialized_views",
    ),
    "_analyze_unused_tables": (
        "schema.unused_tables",
        "All user tables show recent read/write activity",
        "metrics.cas_Table_*Latency",
    ),
}


class DataModelAnalyzer(BaseAnalyzer):
    """Analyzes data model and schema design"""

    category = "schema"
    # Most schema findings are about read/write performance shape — compaction
    # strategy, bloom filters, secondary indexes. Replication and MV-fanout
    # findings (which are reliability concerns) override per call.
    default_recommendation_category = "performance"

    def _format_cql_schema(self, cql: str) -> str:
        """Format CQL schema for better readability"""
        # First, unescape HTML entities
        cql = html.unescape(cql)
        
        # Find the WITH clause
        with_match = re.search(r'(\s+WITH\s+)', cql, re.IGNORECASE)
        if not with_match:
            return cql
        
        # Split the CQL at WITH
        before_with = cql[:with_match.start()]
        with_text = with_match.group(1)
        after_with = cql[with_match.end():]
        
        # Parse the WITH options
        options = []
        current_option = []
        paren_count = 0
        bracket_count = 0
        in_quotes = False
        quote_char = None
        
        i = 0
        while i < len(after_with):
            char = after_with[i]
            
            # Track quotes
            if char in ["'", '"'] and (i == 0 or after_with[i-1] != '\\'):
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif char == quote_char:
                    in_quotes = False
                    quote_char = None
            
            # Track parentheses and brackets when not in quotes
            if not in_quotes:
                if char == '(':
                    paren_count += 1
                elif char == ')':
                    paren_count -= 1
                elif char == '{':
                    bracket_count += 1
                elif char == '}':
                    bracket_count -= 1
                elif char == ';' and paren_count == 0 and bracket_count == 0:
                    # End of statement
                    if current_option:
                        options.append(''.join(current_option).strip())
                    after_with = after_with[:i+1]
                    break
            
            # Split on AND when not inside parentheses/brackets/quotes
            if (not in_quotes and paren_count == 0 and bracket_count == 0 and 
                i + 4 <= len(after_with) and after_with[i:i+4].upper() == ' AND'):
                if current_option:
                    options.append(''.join(current_option).strip())
                    current_option = []
                i += 4  # Skip past ' AND'
                continue
            
            current_option.append(char)
            i += 1
        
        # Add the last option if there is one
        if current_option and ''.join(current_option).strip():
            last_option = ''.join(current_option).strip()
            if last_option.endswith(';'):
                last_option = last_option[:-1].strip()
            options.append(last_option)
        
        # Remove duplicate options (keep first occurrence)
        seen_options = {}
        unique_options = []
        for option in options:
            # Extract the option name (everything before '=')
            option_name = option.split('=')[0].strip().upper()
            if option_name not in seen_options:
                seen_options[option_name] = True
                unique_options.append(option)
        
        # Find CLUSTERING ORDER option and move it to the front
        clustering_order = None
        other_options = []
        for option in unique_options:
            if 'CLUSTERING ORDER' in option.upper():
                clustering_order = option
            else:
                other_options.append(option)
        
        # Reconstruct the WITH clause
        if clustering_order:
            formatted_options = [clustering_order] + other_options
        else:
            formatted_options = other_options
        
        # Build the final CQL
        result = before_with + with_text
        if formatted_options:
            result += formatted_options[0]
            for option in formatted_options[1:]:
                result += '\n    AND ' + option
        
        # Ensure it ends with semicolon
        if not result.rstrip().endswith(';'):
            result += ';'
        
        return result
    
    def analyze(self, cluster_state: ClusterState) -> Dict[str, Any]:
        """Analyze data model"""
        self._reset_checks()
        recommendations = []
        details = {}

        section_helpers = [
            self._analyze_replication,
            self._analyze_table_performance,
            self._analyze_bloom_filters,
            self._analyze_compression,
            self._analyze_compaction_strategies,
            self._analyze_secondary_indexes,
            self._analyze_collection_types,
            self._analyze_materialized_views,
        ]
        for helper in section_helpers:
            section_recs = helper(cluster_state)
            recommendations.extend(section_recs)
            check_id, description, data_source = _DATAMODEL_SECTION_CHECKS[helper.__name__]
            for rec in section_recs:
                if rec.id is None:
                    rec.id = check_id
            self._record_check(
                check_id, description, data_source,
                "fail" if section_recs else "pass",
                finding_count=len(section_recs),
            )

        # Comprehensive table analysis
        table_analyzer = TableAnalyzer(self.config)
        table_results = table_analyzer.analyze(cluster_state)
        table_recs = [Recommendation(**rec) for rec in table_results["recommendations"]]
        recommendations.extend(table_recs)
        for rec in table_recs:
            if rec.id is None:
                rec.id = "schema.table_design"
        self._record_check(
            "schema.table_design",
            "Per-table CQL design (PK shape, types, options) follows best practices",
            "schema.tables",
            "fail" if table_recs else "pass",
            finding_count=len(table_recs),
        )

        # Analyze unused tables
        unused_recs = self._analyze_unused_tables(cluster_state)
        recommendations.extend(unused_recs)
        check_id, description, data_source = _DATAMODEL_SECTION_CHECKS["_analyze_unused_tables"]
        for rec in unused_recs:
            if rec.id is None:
                rec.id = check_id
        self._record_check(
            check_id, description, data_source,
            "fail" if unused_recs else "pass",
            finding_count=len(unused_recs),
        )

        total_tables = sum(len(ks.Tables) for ks in cluster_state.keyspaces.values())
        summary = {
            "total_keyspaces": len(cluster_state.keyspaces),
            "total_tables": total_tables,
            "table_analysis": table_results["summary"],
            "recommendations_count": len(recommendations),
        }

        return {
            "recommendations": [r.dict() for r in recommendations],
            "summary": summary,
            "details": details,
            "checks": [c.model_dump() for c in self._checks],
        }
    
    def _analyze_replication(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze replication factor settings"""
        recommendations = []
        
        for ks_name, keyspace in cluster_state.keyspaces.items():
            # Skip system keyspaces
            if self._is_system_keyspace(ks_name):
                continue
            
            rf = keyspace.get_replication_factor()
            
            if rf < self.thresholds.min_replication_factor:
                recommendations.append(
                    self._create_recommendation(
                        title=f"Low Replication Factor for {ks_name}",
                        description=f"Keyspace {ks_name} has replication factor {rf}",
                        severity=Severity.WARNING,
                        category="datamodel",
                        impact="Reduced availability and data durability",
                        recommendation=f"Increase replication factor to at least {self.thresholds.min_replication_factor}",
                        keyspace=ks_name,
                        current_rf=rf,
                        recommended_rf=self.thresholds.min_replication_factor
                    )
                )
        
        return recommendations
    
    def _analyze_bloom_filters(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze bloom filter performance using AxonOps metrics"""
        recommendations = []
        
        # Get bloom filter metrics: cas_Table_BloomFilterFalseRatio and cas_Table_BloomFilterDiskSpaceUsed
        bloom_false_ratio = cluster_state.metrics.get("bloom_filter_false_ratio", [])
        bloom_disk_usage = cluster_state.metrics.get("bloom_filter_disk_space", [])
        
        # Analyze false positive ratios
        for metric_point in bloom_false_ratio:
            if hasattr(metric_point, 'labels') and hasattr(metric_point, 'value'):
                keyspace = metric_point.labels.get("keyspace", "unknown")
                table = metric_point.labels.get("scope", "unknown")
                false_ratio = float(metric_point.value)
                
                # Skip system keyspaces
                if self._is_system_keyspace(keyspace):
                    continue
                
                # Check if false positive ratio is significantly higher than configured
                if false_ratio > 0.1:  # 10% false positive rate is concerning
                    recommendations.append(
                        self._create_recommendation(
                            title=f"High Bloom Filter False Positive Rate: {keyspace}.{table}",
                            description=f"Table has {false_ratio:.2%} bloom filter false positive rate",
                            severity=Severity.WARNING,
                            category="datamodel",
                            impact="Unnecessary disk reads and increased latency",
                            recommendation="Consider rebuilding bloom filters or adjusting bloom_filter_fp_chance",
                            keyspace=keyspace,
                            table=table,
                            false_positive_rate=false_ratio
                        )
                    )
                elif false_ratio > 0.05:  # 5% is moderate concern
                    recommendations.append(
                        self._create_recommendation(
                            title=f"Moderate Bloom Filter False Positive Rate: {keyspace}.{table}",
                            description=f"Table has {false_ratio:.2%} bloom filter false positive rate",
                            severity=Severity.INFO,
                            category="datamodel",
                            impact="Some unnecessary disk reads",
                            recommendation="Monitor bloom filter performance and consider tuning",
                            keyspace=keyspace,
                            table=table,
                            false_positive_rate=false_ratio
                        )
                    )
        
        # Analyze bloom filter disk space usage
        total_bloom_space = 0
        large_bloom_tables = []
        
        for metric_point in bloom_disk_usage:
            if hasattr(metric_point, 'labels') and hasattr(metric_point, 'value'):
                keyspace = metric_point.labels.get("keyspace", "unknown")
                table = metric_point.labels.get("scope", "unknown")
                disk_bytes = float(metric_point.value)
                
                # Skip system keyspaces
                if self._is_system_keyspace(keyspace):
                    continue
                
                total_bloom_space += disk_bytes
                
                # Check for tables with large bloom filters (>100MB)
                if disk_bytes > 100 * 1024 * 1024:
                    large_bloom_tables.append({
                        "keyspace": keyspace,
                        "table": table,
                        "size_mb": disk_bytes / (1024 * 1024)
                    })
        
        # Report on large bloom filters
        if large_bloom_tables:
            recommendations.append(
                self._create_recommendation(
                    title="Tables with Large Bloom Filters",
                    description=f"Found {len(large_bloom_tables)} tables with bloom filters > 100MB",
                    severity=Severity.INFO,
                    category="datamodel",
                    impact="Significant memory and disk usage for bloom filters",
                    recommendation="Consider if bloom filter settings are optimal for these large tables",
                    large_bloom_tables=large_bloom_tables
                )
            )
        
        return recommendations
    
    def _analyze_compression(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze compression effectiveness using cas_Table_CompressionRatio"""
        recommendations = []
        
        # Get compression ratio metrics
        compression_metrics = cluster_state.metrics.get("compression_ratio", [])
        
        for metric_point in compression_metrics:
            if hasattr(metric_point, 'labels') and hasattr(metric_point, 'value'):
                keyspace = metric_point.labels.get("keyspace", "unknown")
                table = metric_point.labels.get("scope", "unknown")
                compression_ratio = float(metric_point.value)
                
                # Skip system keyspaces
                if self._is_system_keyspace(keyspace):
                    continue
                
                # Check for poor compression ratios
                if compression_ratio < 0.3:  # Less than 30% compression
                    recommendations.append(
                        self._create_recommendation(
                            title=f"Poor Compression Ratio: {keyspace}.{table}",
                            description=f"Table has {compression_ratio:.1%} compression ratio",
                            severity=Severity.WARNING,
                            category="datamodel",
                            impact="Inefficient storage usage and increased I/O",
                            recommendation="Consider different compression algorithm or review data patterns",
                            keyspace=keyspace,
                            table=table,
                            compression_ratio=compression_ratio
                        )
                    )
                elif compression_ratio > 0.9:  # Very little compression benefit
                    recommendations.append(
                        self._create_recommendation(
                            title=f"Minimal Compression Benefit: {keyspace}.{table}",
                            description=f"Table has {compression_ratio:.1%} compression ratio",
                            severity=Severity.INFO,
                            category="datamodel",
                            impact="Little storage benefit from compression",
                            recommendation="Consider disabling compression or using different algorithm",
                            keyspace=keyspace,
                            table=table,
                            compression_ratio=compression_ratio
                        )
                    )
        
        return recommendations
    
    def _analyze_compaction_strategies(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze compaction strategies from keyspace schema"""
        recommendations = []

        cluster_is_5x = cluster_at_least(cluster_state, V5_0)
        min_version = cluster_min_version(cluster_state)
        any_node_pre_5 = min_version is not None and min_version < V5_0

        ucs_legacy_tables = []
        stcs_lcs_on_5x = []

        for ks_name, keyspace in cluster_state.keyspaces.items():
            # Skip system keyspaces
            if self._is_system_keyspace(ks_name):
                continue

            for table_name, table in keyspace.tables_dict.items():
                compaction_strategy = table.CompactionStrategy

                # Cassandra 5.0 introduced UnifiedCompactionStrategy. It will
                # fail to start on a node running an older release, so flag
                # any pre-5.0 node in the cluster as a hard incompatibility.
                if "UnifiedCompactionStrategy" in compaction_strategy:
                    if any_node_pre_5:
                        ucs_legacy_tables.append(f"{ks_name}.{table_name}")
                    # On a fully-5.x cluster UCS is the recommended default,
                    # so we don't emit a recommendation for it.
                    continue

                # On 5.0+ clusters, surface STCS/LCS as candidates for UCS
                # migration (TWCS still has a legitimate niche for time-series
                # data so we leave its existing recommendation alone).
                if cluster_is_5x and (
                    "SizeTieredCompactionStrategy" in compaction_strategy
                    or "LeveledCompactionStrategy" in compaction_strategy
                ):
                    stcs_lcs_on_5x.append(
                        (f"{ks_name}.{table_name}", compaction_strategy)
                    )

                # Check for deprecated strategies
                if "SizeTieredCompactionStrategy" in compaction_strategy:
                    # Get table read/write patterns if available
                    read_count = self._get_table_metric_value(cluster_state.metrics, "table_reads", ks_name, table_name)
                    write_count = self._get_table_metric_value(cluster_state.metrics, "table_writes", ks_name, table_name)
                    
                    if read_count and write_count:
                        read_write_ratio = read_count / write_count if write_count > 0 else float('inf')
                        
                        # Recommend LCS for read-heavy workloads
                        if read_write_ratio > 10:
                            recommendations.append(
                                self._create_recommendation(
                                    title=f"Suboptimal Compaction Strategy: {ks_name}.{table_name}",
                                    description=f"Read-heavy table using STCS (R/W ratio: {read_write_ratio:.1f})",
                                    severity=Severity.INFO,
                                    category="datamodel",
                                    impact="Suboptimal read performance due to multiple SSTables",
                                    recommendation="Consider LeveledCompactionStrategy for read-heavy workloads",
                                    keyspace=ks_name,
                                    table=table_name,
                                    current_strategy="SizeTieredCompactionStrategy",
                                    read_write_ratio=read_write_ratio
                                )
                            )
                
                # Check for TimeWindowCompactionStrategy without time-series data
                elif "TimeWindowCompactionStrategy" in compaction_strategy:
                    recommendations.append(
                        self._create_recommendation(
                            title=f"Verify TWCS Usage: {ks_name}.{table_name}",
                            description="Table uses TimeWindowCompactionStrategy",
                            severity=Severity.INFO,
                            category="datamodel",
                            impact="TWCS should only be used for time-series data",
                            recommendation="Ensure table contains time-series data with time-based queries",
                            keyspace=ks_name,
                            table=table_name,
                            current_strategy="TimeWindowCompactionStrategy"
                        )
                    )

        if ucs_legacy_tables:
            recommendations.append(
                self._create_recommendation(
                    title="UnifiedCompactionStrategy Used on Pre-5.0 Cluster",
                    description=(
                        f"{len(ucs_legacy_tables)} tables use UnifiedCompactionStrategy "
                        f"but at least one node is running Cassandra < 5.0"
                    ),
                    severity=Severity.CRITICAL,
                    category="datamodel",
                    impact="Pre-5.0 nodes cannot load tables with UnifiedCompactionStrategy and will fail to start or refuse the schema",
                    recommendation="Either complete the upgrade to Cassandra 5.x on all nodes, or switch the affected tables back to STCS/LCS/TWCS until the upgrade is complete",
                    tables_affected=ucs_legacy_tables,
                    current_strategy="UnifiedCompactionStrategy",
                )
            )

        if stcs_lcs_on_5x:
            tables_summary = [t for t, _ in stcs_lcs_on_5x]
            recommendations.append(
                self._create_recommendation(
                    title="Consider Unified Compaction Strategy (UCS) on 5.x",
                    description=(
                        f"{len(stcs_lcs_on_5x)} tables use STCS or LCS on a Cassandra 5.x cluster"
                    ),
                    severity=Severity.INFO,
                    category="datamodel",
                    impact="UCS adapts between size-tiered and leveled behaviour automatically and is the recommended default in Cassandra 5.0",
                    recommendation="Evaluate migrating to UnifiedCompactionStrategy. Keep TWCS where time-series semantics matter.",
                    tables_affected=tables_summary,
                )
            )

        return recommendations
    
    # Each CREATE [CUSTOM] INDEX statement; group 1 is the body of the
    # statement (up to the next semicolon or end of input) which we then
    # inspect for USING '...'.
    _CREATE_INDEX_RE = re.compile(
        r"(CREATE\s+(?:CUSTOM\s+)?INDEX\b[^;]*)",
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    _CREATE_INDEX_USING_RE = re.compile(r"USING\s+'([^']+)'", re.IGNORECASE)

    @classmethod
    def _classify_index(cls, statement: str) -> str:
        """Return 'sai', 'sasi', 'custom', or 'legacy' for a CREATE INDEX statement."""
        is_custom = bool(re.match(r"\s*CREATE\s+CUSTOM\s+INDEX", statement, re.IGNORECASE))
        if not is_custom:
            return "legacy"
        using_match = cls._CREATE_INDEX_USING_RE.search(statement)
        u = using_match.group(1).lower() if using_match else ""
        if u in ("sai", "storageattachedindex") or u.endswith(".storageattachedindex"):
            return "sai"
        if "sasi" in u:
            return "sasi"
        return "custom"

    def _analyze_secondary_indexes(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze secondary indexes in schema, distinguishing SAI from legacy 2i."""
        recommendations = []

        legacy_by_keyspace: Dict[str, List[str]] = {}
        sai_by_keyspace: Dict[str, List[str]] = {}
        sasi_by_keyspace: Dict[str, List[str]] = {}
        legacy_total = 0
        sai_total = 0
        sasi_total = 0

        for ks_name, keyspace in cluster_state.keyspaces.items():
            if self._is_system_keyspace(ks_name):
                continue

            for table_name, table in keyspace.tables_dict.items():
                if not (hasattr(table, "CQL") and table.CQL):
                    continue
                for match in self._CREATE_INDEX_RE.finditer(table.CQL):
                    kind = self._classify_index(match.group(1))
                    if kind == "sai":
                        sai_total += 1
                        sai_by_keyspace.setdefault(ks_name, []).append(table_name)
                    elif kind == "sasi":
                        sasi_total += 1
                        sasi_by_keyspace.setdefault(ks_name, []).append(table_name)
                    elif kind == "legacy":
                        legacy_total += 1
                        legacy_by_keyspace.setdefault(ks_name, []).append(table_name)
                    # 'custom' (non-SAI/SASI) is rare and we don't have generic guidance.

        cluster_is_5x = cluster_at_least(cluster_state, V5_0)
        min_version = cluster_min_version(cluster_state)
        any_node_pre_5 = min_version is not None and min_version < V5_0

        if legacy_total > 0:
            if cluster_is_5x:
                recommendations.append(
                    self._create_recommendation(
                        title="Legacy Secondary Indexes Detected (Consider SAI)",
                        description=f"Found {legacy_total} legacy secondary indexes on a Cassandra 5.x cluster",
                        severity=Severity.WARNING,
                        category="datamodel",
                        impact="Legacy 2i scales poorly on writes and across nodes; Storage-Attached Indexes (SAI) are the recommended replacement on 5.x",
                        recommendation="Evaluate migrating these indexes to SAI (CREATE CUSTOM INDEX ... USING 'StorageAttachedIndex'), or denormalise the data if the index is purely a query-side convenience",
                        total_indexes=legacy_total,
                        indexes_by_keyspace=legacy_by_keyspace,
                    )
                )
            else:
                recommendations.append(
                    self._create_recommendation(
                        title="Secondary Indexes Detected",
                        description=f"Found {legacy_total} tables with secondary indexes",
                        severity=Severity.WARNING,
                        category="datamodel",
                        impact="Secondary indexes can severely impact write performance and cluster stability",
                        recommendation="Consider denormalizing data or using application-level indexing instead",
                        total_indexes=legacy_total,
                        indexes_by_keyspace=legacy_by_keyspace,
                    )
                )

        if sai_total > 0:
            if any_node_pre_5:
                # SAI requires 5.0+ on every node that needs to load the schema.
                recommendations.append(
                    self._create_recommendation(
                        title="SAI Indexes Used on Pre-5.0 Cluster",
                        description=f"Found {sai_total} Storage-Attached Indexes but at least one node is running Cassandra < 5.0",
                        severity=Severity.CRITICAL,
                        category="datamodel",
                        impact="Pre-5.0 nodes cannot load tables with SAI indexes",
                        recommendation="Complete the upgrade to Cassandra 5.x on all nodes before introducing SAI",
                        total_indexes=sai_total,
                        indexes_by_keyspace=sai_by_keyspace,
                    )
                )

        if sasi_total > 0:
            recommendations.append(
                self._create_recommendation(
                    title="SASI Indexes Detected",
                    description=f"Found {sasi_total} SASI indexes",
                    severity=Severity.WARNING,
                    category="datamodel",
                    impact="SASI is experimental and not recommended for production",
                    recommendation="Migrate to SAI on Cassandra 5.x, or denormalise the data on older versions",
                    total_indexes=sasi_total,
                    indexes_by_keyspace=sasi_by_keyspace,
                )
            )

        return recommendations
    
    def _analyze_collection_types(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze collection type usage in tables"""
        recommendations = []
        
        collection_table_details = []
        large_collection_concerns = []
        
        for ks_name, keyspace in cluster_state.keyspaces.items():
            # Skip system keyspaces
            if self._is_system_keyspace(ks_name):
                continue
            
            for table_name, table in keyspace.tables_dict.items():
                if hasattr(table, 'CQL') and table.CQL:
                    cql = table.CQL
                    cql_lower = cql.lower()
                    
                    # Check for collection types
                    if any(collection in cql_lower for collection in ['set<', 'list<', 'map<']):
                        # Extract relevant schema info
                        collection_table_details.append({
                            "table": f"{ks_name}.{table_name}",
                            "schema": self._format_cql_schema(table.CQL)  # Format CQL for display
                        })
                        
                        # Check for potentially problematic patterns
                        # 1. Collections of collections (which would require frozen)
                        if 'list<frozen<' in cql_lower or 'set<frozen<' in cql_lower or 'map<frozen<' in cql_lower:
                            # This is fine - nested collections are properly frozen
                            pass
                        
                        # 2. Large collections without explicit size limits
                        # This is more of a design concern than a frozen/non-frozen issue
                        if table_name in ['events', 'logs', 'history', 'timeline']:
                            large_collection_concerns.append(f"{ks_name}.{table_name}")
        
        # Report on tables with potential for large collections
        if large_collection_concerns:
            recommendations.append(
                self._create_recommendation(
                    title="Collections in Potentially Large Tables",
                    description=f"Found {len(large_collection_concerns)} tables with collections that may grow large",
                    severity=Severity.INFO,
                    category="datamodel",
                    impact="Large collections can cause performance issues and memory pressure",
                    recommendation="Monitor collection sizes and consider time-based partitioning or separate tables",
                    tables_of_concern=large_collection_concerns
                )
            )
        
        # General collection usage info with schema details
        if collection_table_details:
            recommendations.append(
                self._create_recommendation(
                    title="Collection Types Usage",
                    description=f"Found {len(collection_table_details)} tables using collection types",
                    severity=Severity.INFO,
                    category="datamodel",
                    impact="Collections are useful but should be kept reasonably sized",
                    recommendation="Keep collections under 100KB and monitor their growth",
                    collection_tables=[t["table"] for t in collection_table_details],
                    collection_table_details=collection_table_details
                )
            )
        
        return recommendations
    
    def _analyze_materialized_views(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze materialized views usage"""
        recommendations = []

        materialized_views = []

        for ks_name, keyspace in cluster_state.keyspaces.items():
            # Skip system keyspaces
            if self._is_system_keyspace(ks_name):
                continue

            for table_name, table in keyspace.tables_dict.items():
                if hasattr(table, 'CQL') and table.CQL:
                    cql_lower = table.CQL.lower()
                    if 'create materialized view' in cql_lower or 'materialized view' in cql_lower:
                        materialized_views.append(f"{ks_name}.{table_name}")

        if not materialized_views:
            return recommendations

        cluster_is_5x = cluster_at_least(cluster_state, V5_0)
        if cluster_is_5x:
            recommendation_text = (
                "Materialized views remain marked experimental in Cassandra 5.x and are not recommended for "
                "new workloads. Replace with application-side denormalisation, or — where the use case fits — "
                "a Storage-Attached Index (SAI) on the source table."
            )
            impact_text = (
                "Materialized views in 5.x carry the same long-standing correctness and operational issues as "
                "earlier releases (silent data loss on repair, write amplification) and have no roadmap to GA"
            )
        else:
            recommendation_text = "Consider denormalization or application-level view maintenance instead"
            impact_text = "Materialized views are experimental and can cause serious performance issues"

        recommendations.append(
            self._create_recommendation(
                title="Materialized Views Detected",
                description=f"Found {len(materialized_views)} materialized views",
                severity=Severity.CRITICAL,
                category="datamodel",
                impact=impact_text,
                recommendation=recommendation_text,
                materialized_views=materialized_views,
            )
        )

        return recommendations
    
    def _get_table_metric_value(self, metrics: Dict, metric_name: str, keyspace: str, table: str) -> float:
        """Helper to get metric value for specific table"""
        metric_data = metrics.get(metric_name, [])
        for metric_point in metric_data:
            if (hasattr(metric_point, 'labels') and 
                metric_point.labels.get("keyspace") == keyspace and 
                metric_point.labels.get("scope") == table):
                return float(metric_point.value)
        return 0.0
    
    def _analyze_unused_tables(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze potentially unused tables using AxonOps table performance metrics"""
        recommendations = []
        
        # Use coordinator read/write count metrics from dashboard queries
        table_reads = cluster_state.metrics.get("table_coordinator_reads", [])
        table_writes = cluster_state.metrics.get("table_coordinator_writes", [])
        
        # Track all tables from schema
        all_tables = set()
        for ks_name, keyspace in cluster_state.keyspaces.items():
            if not self._is_system_keyspace(ks_name):
                for table_name in keyspace.tables_dict.keys():
                    all_tables.add(f"{ks_name}.{table_name}")
        
        # Track tables with activity
        active_tables = set()
        unused_tables = []
        low_activity_tables = []
        
        # Check read activity
        for metric_point in table_reads:
            if hasattr(metric_point, 'labels') and hasattr(metric_point, 'value'):
                keyspace = metric_point.labels.get("keyspace", "unknown")
                table = metric_point.labels.get("scope", "unknown")
                read_count = float(metric_point.value)
                
                if self._is_system_keyspace(keyspace):
                    continue
                
                table_key = f"{keyspace}.{table}"
                if read_count > 0:
                    active_tables.add(table_key)
                elif read_count == 0:
                    low_activity_tables.append({
                        "table": table_key,
                        "reads": read_count,
                        "activity_type": "no_reads"
                    })
        
        # Check write activity
        for metric_point in table_writes:
            if hasattr(metric_point, 'labels') and hasattr(metric_point, 'value'):
                keyspace = metric_point.labels.get("keyspace", "unknown")
                table = metric_point.labels.get("scope", "unknown")
                write_count = float(metric_point.value)
                
                if self._is_system_keyspace(keyspace):
                    continue
                
                table_key = f"{keyspace}.{table}"
                if write_count > 0:
                    active_tables.add(table_key)
                elif write_count == 0 and table_key not in [t["table"] for t in low_activity_tables]:
                    low_activity_tables.append({
                        "table": table_key,
                        "writes": write_count,
                        "activity_type": "no_writes"
                    })
        
        # Find completely unused tables (no reads or writes)
        for table_key in all_tables:
            if table_key not in active_tables:
                # Check if it's in low activity list
                found_in_low_activity = False
                for low_table in low_activity_tables:
                    if low_table["table"] == table_key:
                        found_in_low_activity = True
                        break
                
                if not found_in_low_activity:
                    unused_tables.append(table_key)
        
        # Report completely unused tables
        if unused_tables:
            recommendations.append(
                self._create_recommendation(
                    title="Unused Tables Detected",
                    description=f"Found {len(unused_tables)} tables with no read or write activity",
                    severity=Severity.WARNING,
                    category="datamodel",
                    impact="Unused tables consume disk space and backup resources",
                    recommendation="Consider dropping unused tables after verifying they're no longer needed",
                    unused_tables=unused_tables
                )
            )
        
        # Report tables with very low activity
        if len(low_activity_tables) > 0:
            recommendations.append(
                self._create_recommendation(
                    title="Low Activity Tables",
                    description=f"Found {len(low_activity_tables)} tables with minimal activity",
                    severity=Severity.INFO,
                    category="datamodel",
                    impact="Low-activity tables may indicate unused or rarely used data",
                    recommendation="Review if these tables are still needed or can be archived",
                    low_activity_tables=low_activity_tables
                )
            )
        
        return recommendations
    
    def _analyze_table_performance(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze table-level performance metrics"""
        recommendations = []
        
        # Note: Due to the way AxonOps metrics work, we can't query table-specific metrics
        # without knowing the keyspace and table names in advance. The metrics API requires
        # these to be specified in the query, not filtered after the fact.
        # 
        # For now, we'll analyze the metrics that are available without table-specific queries
        # such as coordinator read/write counts to identify unused tables.
        
        return recommendations
    
