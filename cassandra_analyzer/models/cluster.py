"""
Cluster state models
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class Node(BaseModel):
    """Represents a Cassandra node"""
    host_id: str
    org: str
    type: str = "cassandra"
    cluster: str
    DC: str  # datacenter
    
    # Details from the API response
    Details: Dict[str, Any] = Field(default_factory=dict)
    
    # Computed properties
    @property
    def datacenter(self) -> str:
        return self.DC
    
    @property
    def rack(self) -> Optional[str]:
        return self.Details.get("comp_rack", self.Details.get("rack"))
    
    @property
    def endpoint_snitch(self) -> Optional[str]:
        return self.Details.get("comp_endpoint_snitch")
    
    @property
    def cassandra_version(self) -> Optional[str]:
        return self.Details.get("comp_releaseVersion", self.Details.get("release_version"))
    
    @property
    def agent_version(self) -> Optional[str]:
        return self.Details.get("agent_version")
    
    @property
    def data_directories(self) -> List[str]:
        dirs = self.Details.get("comp_data_file_directories", "[]")
        if isinstance(dirs, str) and dirs.startswith("[") and dirs.endswith("]"):
            # Parse the string representation of a list
            return eval(dirs)
        return []
    
    @property
    def commitlog_directory(self) -> Optional[str]:
        return self.Details.get("comp_commitlog_directory")
    
    @property
    def is_active(self) -> bool:
        """Determine if node is active based on available AxonOps data"""
        # Check if we have recent metrics or status information
        # In AxonOps, presence of recent data typically indicates an active node
        
        # First check if we have any meaningful details at all
        if not self.Details:
            return False
            
        # Check for common indicators that a node is reporting data
        # These are fields that would typically be present for active nodes
        active_indicators = [
            "host_uptime",
            "agent_version", 
            "release_version",
            "comp_listen_address",
            "host_CPU_Percent",
            "host_Memory_Total"
        ]
        
        # Node is considered active if it has any of these key indicators
        has_indicators = any(self.Details.get(field) for field in active_indicators)
        
        return has_indicators


class Table(BaseModel):
    """Represents a Cassandra table"""
    Name: str
    Keyspace: str
    GCGrace: int
    CompactionStrategy: str
    ID: str
    CQL: str
    
    # Cached parsed data
    _parsed_data: Optional[Dict[str, Any]] = None
    
    # Computed properties
    @property
    def name(self) -> str:
        return self.Name
    
    @property
    def keyspace(self) -> str:
        return self.Keyspace
    
    @property
    def gc_grace_seconds(self) -> int:
        return self.GCGrace
    
    @property
    def compaction_strategy(self) -> str:
        return self.CompactionStrategy
    
    @property
    def parsed_data(self) -> Dict[str, Any]:
        """Get parsed table data (cached)"""
        if self._parsed_data is None:
            # Import here to avoid circular import
            from .table_parser import TableCQLParser
            parser = TableCQLParser()
            self._parsed_data = parser.parse_create_table(self.CQL)
        return self._parsed_data
    
    @property
    def is_counter_table(self) -> bool:
        return self.parsed_data.get("is_counter", False)
    
    @property
    def has_collections(self) -> bool:
        return self.parsed_data.get("has_collections", False)
    
    @property
    def has_frozen_collections(self) -> bool:
        return self.parsed_data.get("has_frozen_collections", False)
    
    @property
    def columns(self) -> List[Any]:
        return self.parsed_data.get("columns", [])
    
    @property
    def primary_key(self) -> Any:
        return self.parsed_data.get("primary_key")
    
    @property
    def partition_keys(self) -> List[str]:
        pk = self.primary_key
        return pk.partition_keys if pk else []
    
    @property
    def clustering_keys(self) -> List[str]:
        pk = self.primary_key
        return pk.clustering_keys if pk else []
    
    @property
    def table_options(self) -> Any:
        return self.parsed_data.get("options")
    
    def get_compaction_options(self) -> Dict[str, Any]:
        """Get compaction options from parsed data"""
        options = self.table_options
        if options and options.compaction:
            return options.compaction
        return {}
    
    def get_compression_options(self) -> Dict[str, Any]:
        """Get compression options from parsed data"""
        options = self.table_options
        if options and options.compression:
            return options.compression
        return {}
    
    def get_caching_options(self) -> Dict[str, str]:
        """Get caching options from parsed data"""
        options = self.table_options
        if options and options.caching:
            return options.caching
        return {}
    
    def get_speculative_retry(self) -> str:
        """Get speculative retry setting"""
        options = self.table_options
        return options.speculative_retry if options else "NONE"
    
    def get_bloom_filter_fp_chance(self) -> float:
        """Get bloom filter false positive chance"""
        options = self.table_options
        return options.bloom_filter_fp_chance if options else 0.01
    
    def has_secondary_indexes(self) -> bool:
        """Check if table has secondary indexes (would need additional API call)"""
        # This would require additional information not in the CQL
        return False
    
    def get_ttl(self) -> int:
        """Get default TTL in seconds"""
        options = self.table_options
        return options.default_time_to_live if options else 0


class Keyspace(BaseModel):
    """Represents a Cassandra keyspace"""
    Name: str
    Tables: List[Table] = Field(default_factory=list)
    
    # Additional properties that might come from other API calls
    replication_strategy: Optional[str] = None
    replication_options: Dict[str, Any] = Field(default_factory=dict)
    durable_writes: bool = True
    
    @property
    def name(self) -> str:
        return self.Name
    
    @property
    def tables_dict(self) -> Dict[str, Table]:
        """Get tables as a dictionary keyed by table name"""
        return {table.Name: table for table in self.Tables}
    
    def get_replication_factor(self) -> int:
        """Get the replication factor for the keyspace"""
        if self.replication_strategy == "SimpleStrategy":
            rf = self.replication_options.get("replication_factor", "1")
            try:
                return int(rf)
            except ValueError:
                return 1
        elif self.replication_strategy == "NetworkTopologyStrategy":
            # Return the minimum RF across all DCs
            factors = []
            for dc, rf in self.replication_options.items():
                try:
                    factors.append(int(rf))
                except ValueError:
                    continue
            return min(factors) if factors else 1
        return 1


class ClusterState(BaseModel):
    """Represents the complete state of a Cassandra cluster"""
    name: str
    cluster_type: str = "cassandra"
    
    # Cluster composition
    nodes: Dict[str, Node] = Field(default_factory=dict)
    keyspaces: Dict[str, Keyspace] = Field(default_factory=dict)
    
    
    # Metrics data
    metrics: Dict[str, Any] = Field(default_factory=dict)
    
    # Events
    events: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Log events for operations analysis (histograms)
    log_events: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    
    # Collection metadata
    collection_time: datetime = Field(default_factory=datetime.utcnow)
    collection_duration_seconds: Optional[float] = None
    
    def get_datacenters(self) -> List[str]:
        """Get list of datacenters in the cluster"""
        dcs = set()
        for node in self.nodes.values():
            if node.datacenter:
                dcs.add(node.datacenter)
        return sorted(list(dcs))
    
    def get_nodes_by_dc(self) -> Dict[str, List[Node]]:
        """Get nodes grouped by datacenter"""
        nodes_by_dc = {}
        for node in self.nodes.values():
            dc = node.datacenter or "unknown"
            if dc not in nodes_by_dc:
                nodes_by_dc[dc] = []
            nodes_by_dc[dc].append(node)
        return nodes_by_dc
    
    def get_total_nodes(self) -> int:
        """Get total number of nodes"""
        return len(self.nodes)
    
    def get_active_nodes(self) -> int:
        """Get number of active nodes"""
        return sum(1 for node in self.nodes.values() if node.is_active)