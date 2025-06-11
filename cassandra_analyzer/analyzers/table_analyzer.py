"""
Comprehensive table analyzer - checks table design and performance
"""

from typing import Dict, Any, List
from ..models import ClusterState, Recommendation, Severity, Table, Keyspace
from .base import BaseAnalyzer


class TableAnalyzer(BaseAnalyzer):
    """Analyzes table design, structure, and performance"""
    
    def analyze(self, cluster_state: ClusterState) -> Dict[str, Any]:
        """Analyze table structure and configuration"""
        recommendations = []
        summary = {}
        details = {}
        
        # Analyze table structures
        recommendations.extend(self._analyze_table_structures(cluster_state))
        
        # Analyze compaction strategies
        recommendations.extend(self._analyze_compaction_strategies(cluster_state))
        
        # Analyze caching configurations
        recommendations.extend(self._analyze_caching_configurations(cluster_state))
        
        # Analyze bloom filter settings
        recommendations.extend(self._analyze_bloom_filters(cluster_state))
        
        # Analyze collection usage
        recommendations.extend(self._analyze_collections(cluster_state))
        
        # Analyze GC grace settings
        recommendations.extend(self._analyze_gc_grace_settings(cluster_state))
        
        # Analyze speculative retry settings
        recommendations.extend(self._analyze_speculative_retry(cluster_state))
        
        # Create summary
        total_tables = sum(len(ks.Tables) for ks in cluster_state.keyspaces.values())
        counter_tables = sum(
            1 for ks in cluster_state.keyspaces.values() 
            for table in ks.Tables if table.is_counter_table
        )
        
        summary = {
            "total_tables": total_tables,
            "counter_tables": counter_tables,
            "keyspaces_analyzed": len(cluster_state.keyspaces),
            "recommendations_count": len(recommendations)
        }
        
        return {
            "recommendations": [r.dict() for r in recommendations],
            "summary": summary,
            "details": details
        }
    
    def _analyze_table_structures(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze table structure and primary key design"""
        recommendations = []
        
        for keyspace in cluster_state.keyspaces.values():
            # Skip system keyspaces
            if self._is_system_keyspace(keyspace.name):
                continue
                
            for table in keyspace.Tables:
                # Removed check for tables without clustering columns - this is a valid design choice
                # Many tables legitimately have no clustering columns when they store one row per partition
                
                # Removed check for complex partition keys - having multiple partition key columns
                # is often necessary for proper data distribution and query patterns
                
                # Check for many clustering columns
                if len(table.clustering_keys) > 5:
                    recommendations.append(
                        self._create_recommendation(
                            title=f"Many Clustering Columns in {keyspace.name}.{table.name}",
                            description=f"Table has {len(table.clustering_keys)} clustering columns",
                            severity=Severity.WARNING,
                            category="datamodel",
                            impact="Too many clustering columns can affect query performance",
                            recommendation="Consider if all clustering columns are necessary",
                            keyspace=keyspace.name,
                            table=table.name,
                            clustering_key_count=len(table.clustering_keys)
                        )
                    )
        
        return recommendations
    
    def _analyze_compaction_strategies(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze compaction strategy choices"""
        recommendations = []
        
        for keyspace in cluster_state.keyspaces.values():
            if self._is_system_keyspace(keyspace.name):
                continue
                
            for table in keyspace.Tables:
                strategy = table.compaction_strategy
                
                # Check for inappropriate LCS usage
                if "LeveledCompactionStrategy" in strategy:
                    if table.is_counter_table:
                        recommendations.append(
                            self._create_recommendation(
                                title=f"LCS Used with Counter Table {keyspace.name}.{table.name}",
                                description="LeveledCompactionStrategy is not recommended for counter tables",
                                severity=Severity.WARNING,
                                category="datamodel",
                                impact="Poor performance for counter tables with LCS",
                                recommendation="Use SizeTieredCompactionStrategy for counter tables",
                                keyspace=keyspace.name,
                                table=table.name,
                                current_strategy=strategy
                            )
                        )
                
                # Check for STCS with many SSTables
                elif "SizeTieredCompactionStrategy" in strategy:
                    options = table.get_compaction_options()
                    min_threshold = int(options.get("min_threshold", 4))
                    max_threshold = int(options.get("max_threshold", 32))
                    
                    if max_threshold > 32:
                        recommendations.append(
                            self._create_recommendation(
                                title=f"High STCS Max Threshold in {keyspace.name}.{table.name}",
                                description=f"STCS max_threshold is {max_threshold}, default is 32",
                                severity=Severity.INFO,
                                category="datamodel",
                                impact="May delay compaction and affect read performance",
                                recommendation="Consider if high threshold is necessary",
                                keyspace=keyspace.name,
                                table=table.name,
                                max_threshold=max_threshold
                            )
                        )
        
        return recommendations
    
    def _analyze_caching_configurations(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze table caching configurations"""
        recommendations = []
        
        for keyspace in cluster_state.keyspaces.values():
            if self._is_system_keyspace(keyspace.name):
                continue
                
            for table in keyspace.Tables:
                caching = table.get_caching_options()
                
                # Check for row cache usage
                if caching.get("rows_per_partition", "NONE") != "NONE":
                    recommendations.append(
                        self._create_recommendation(
                            title=f"Row Cache Enabled in {keyspace.name}.{table.name}",
                            description="Table has row cache enabled",
                            severity=Severity.INFO,
                            category="datamodel",
                            impact="Row cache can cause GC pressure in modern Cassandra versions",
                            recommendation="Consider disabling row cache unless specifically needed",
                            keyspace=keyspace.name,
                            table=table.name,
                            row_cache_setting=caching.get("rows_per_partition")
                        )
                    )
                
                # Check key cache setting
                if caching.get("keys", "ALL") == "NONE":
                    recommendations.append(
                        self._create_recommendation(
                            title=f"Key Cache Disabled in {keyspace.name}.{table.name}",
                            description="Table has key cache disabled",
                            severity=Severity.WARNING,
                            category="datamodel",
                            impact="Disabling key cache can hurt read performance",
                            recommendation="Enable key cache unless there's a specific reason to disable it",
                            keyspace=keyspace.name,
                            table=table.name
                        )
                    )
        
        return recommendations
    
    def _analyze_bloom_filters(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze bloom filter configurations"""
        recommendations = []
        
        for keyspace in cluster_state.keyspaces.values():
            if self._is_system_keyspace(keyspace.name):
                continue
                
            for table in keyspace.Tables:
                bf_chance = table.get_bloom_filter_fp_chance()
                
                # Check for high bloom filter FP chance
                if bf_chance > 0.1:
                    recommendations.append(
                        self._create_recommendation(
                            title=f"High Bloom Filter FP Chance in {keyspace.name}.{table.name}",
                            description=f"Bloom filter false positive chance is {bf_chance}",
                            severity=Severity.WARNING,
                            category="datamodel",
                            impact="High FP chance reduces bloom filter effectiveness",
                            recommendation="Consider lowering bloom_filter_fp_chance to 0.01 or 0.1",
                            keyspace=keyspace.name,
                            table=table.name,
                            current_fp_chance=bf_chance
                        )
                    )
                
                # Check for very low bloom filter FP chance
                elif bf_chance < 0.001:
                    recommendations.append(
                        self._create_recommendation(
                            title=f"Very Low Bloom Filter FP Chance in {keyspace.name}.{table.name}",
                            description=f"Bloom filter false positive chance is {bf_chance}",
                            severity=Severity.INFO,
                            category="datamodel",
                            impact="Very low FP chance uses more memory for bloom filters",
                            recommendation="Consider if such low FP chance is necessary",
                            keyspace=keyspace.name,
                            table=table.name,
                            current_fp_chance=bf_chance
                        )
                    )
        
        return recommendations
    
    def _analyze_collections(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze collection column usage"""
        recommendations = []
        
        # We no longer warn about non-frozen collections as they are 
        # the preferred choice for regular table columns.
        # Non-frozen collections allow partial updates which is usually desired.
        # Frozen collections are only required for:
        # 1. Collections inside UDTs
        # 2. Nested collections (list<frozen<map<text, text>>>)
        
        # For now, we don't have access to detailed schema analysis to detect
        # these specific cases, so we'll skip collection warnings entirely.
        
        return recommendations
    
    def _analyze_gc_grace_settings(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze GC grace period settings"""
        recommendations = []
        
        for keyspace in cluster_state.keyspaces.values():
            if self._is_system_keyspace(keyspace.name):
                continue
                
            for table in keyspace.Tables:
                gc_grace = table.gc_grace_seconds
                
                # Check for very long GC grace
                if gc_grace > 864000:  # > 10 days
                    recommendations.append(
                        self._create_recommendation(
                            title=f"Long GC Grace Period in {keyspace.name}.{table.name}",
                            description=f"GC grace seconds is {gc_grace} ({gc_grace / 86400:.1f} days)",
                            severity=Severity.INFO,
                            category="datamodel",
                            impact="Long GC grace periods delay tombstone cleanup",
                            recommendation="Consider if long GC grace is necessary for your repair schedule",
                            keyspace=keyspace.name,
                            table=table.name,
                            gc_grace_seconds=gc_grace,
                            gc_grace_days=gc_grace / 86400
                        )
                    )
                
                # Check for very short GC grace
                elif gc_grace < 7200:  # < 2 hours
                    recommendations.append(
                        self._create_recommendation(
                            title=f"Short GC Grace Period in {keyspace.name}.{table.name}",
                            description=f"GC grace seconds is {gc_grace} ({gc_grace / 3600:.1f} hours)",
                            severity=Severity.WARNING,
                            category="datamodel",
                            impact="Short GC grace can cause zombie data if repairs don't complete in time",
                            recommendation="Ensure GC grace is longer than your repair interval",
                            keyspace=keyspace.name,
                            table=table.name,
                            gc_grace_seconds=gc_grace,
                            gc_grace_hours=gc_grace / 3600
                        )
                    )
        
        return recommendations
    
    def _analyze_speculative_retry(self, cluster_state: ClusterState) -> List[Recommendation]:
        """Analyze speculative retry settings across tables"""
        recommendations = []
        
        # Group tables by speculative retry setting
        speculative_retry_tables = {}
        
        for ks_name, keyspace in cluster_state.keyspaces.items():
            # Skip system keyspaces
            if self._is_system_keyspace(ks_name):
                continue
            
            for table in keyspace.Tables:
                speculative_retry = table.get_speculative_retry()
                
                # Check if speculative retry is set to anything other than NEVER
                # Note: NEVER is the correct value for Cassandra 4.0+, NONE was used in older versions
                if speculative_retry and speculative_retry.upper() not in ['NEVER', 'NONE', 'DISABLED']:
                    if speculative_retry not in speculative_retry_tables:
                        speculative_retry_tables[speculative_retry] = []
                    speculative_retry_tables[speculative_retry].append(f"{ks_name}.{table.name}")
        
        # Create grouped recommendations
        for retry_setting, tables in speculative_retry_tables.items():
            if len(tables) > 5:
                # Summarize if many tables affected
                recommendations.append(
                    self._create_recommendation(
                        title="Speculative Retry Enabled (Multiple Tables)",
                        description=f"{len(tables)} tables have speculative_retry set to '{retry_setting}'",
                        severity=Severity.WARNING,
                        category="datamodel",
                        impact="Speculative retry can cause unnecessary load and is often counterproductive in modern deployments",
                        recommendation="Set speculative_retry to NEVER unless you have specific latency requirements that benefit from it",
                        current_value=f"{len(tables)} tables affected",
                        tables_affected=tables,
                        speculative_retry=retry_setting,
                        recommended_value="NEVER",
                        group_summary=True,
                        appendix_details="speculative_retry_tables"
                    )
                )
            else:
                # List individual tables if few
                for table_name in tables:
                    recommendations.append(
                        self._create_recommendation(
                            title="Speculative Retry Enabled",
                            description=f"Table {table_name} has speculative_retry set to '{retry_setting}'",
                            severity=Severity.WARNING,
                            category="datamodel",
                            impact="Speculative retry can cause unnecessary load and is often counterproductive in modern deployments",
                            recommendation="Set speculative_retry to NEVER unless you have specific latency requirements that benefit from it",
                            current_value=f"speculative_retry={retry_setting}",
                            speculative_retry=retry_setting,
                            recommended_value="NEVER"
                        )
                    )
        
        return recommendations