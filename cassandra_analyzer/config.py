"""
Configuration models and defaults for the analyzer
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class ClusterConfig(BaseModel):
    """Cluster identification configuration"""
    org: str = Field(description="Organization name")
    cluster: str = Field(description="Cluster name")
    cluster_type: str = Field(default="cassandra", description="Cluster type")


class AxonOpsConfig(BaseModel):
    """AxonOps API configuration"""
    api_url: str = Field(default="http://localhost:9090", description="AxonOps API URL")
    token: str = Field(description="API authentication token")
    timeout: int = Field(default=30, description="API request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum number of API retry attempts")


class ThresholdsConfig(BaseModel):
    """Analysis thresholds configuration"""
    # Infrastructure thresholds
    cpu_usage_warn: float = Field(default=80.0, description="CPU usage warning threshold (%)")
    memory_usage_warn: float = Field(default=85.0, description="Memory usage warning threshold (%)")
    disk_usage_warn: float = Field(default=80.0, description="Disk usage warning threshold (%)")
    
    # JVM thresholds
    heap_usage_warn: float = Field(default=75.0, description="Heap usage warning threshold (%)")
    gc_pause_warn_ms: int = Field(default=200, description="GC pause warning threshold (ms)")
    gc_pause_critical_ms: int = Field(default=1000, description="GC pause critical threshold (ms)")
    
    # Operations thresholds
    dropped_messages_warn: int = Field(default=1000, description="Dropped messages warning threshold")
    dropped_messages_critical: int = Field(default=10000, description="Dropped messages critical threshold")
    pending_compactions_warn: int = Field(default=100, description="Pending compactions warning threshold")
    pending_compactions_critical: int = Field(default=1000, description="Pending compactions critical threshold")
    blocked_tasks_warn: int = Field(default=1, description="Blocked tasks warning threshold")
    
    # Table thresholds
    sstables_per_read_warn: int = Field(default=4, description="SSTables per read warning threshold")
    partition_size_warn_mb: int = Field(default=100, description="Partition size warning threshold (MB)")
    partition_size_critical_mb: int = Field(default=1000, description="Partition size critical threshold (MB)")
    tombstone_ratio_warn: float = Field(default=0.1, description="Tombstone ratio warning threshold")
    
    # Replication thresholds
    min_replication_factor: int = Field(default=3, description="Minimum recommended replication factor")


class AnalysisConfig(BaseModel):
    """Analysis configuration"""
    hours: int = Field(default=24, description="Number of hours to analyze (from current time backwards)")
    metrics_resolution_seconds: int = Field(default=60, description="Metrics query resolution (seconds)")
    enable_sections: Dict[str, bool] = Field(
        default={
            "infrastructure": True,
            "configuration": True,
            "operations": True,
            "datamodel": True,
            "security": True
        },
        description="Enable/disable analysis sections"
    )
    thresholds: ThresholdsConfig = Field(default_factory=ThresholdsConfig)


class Config(BaseModel):
    """Main configuration model"""
    cluster: ClusterConfig
    axonops: AxonOpsConfig
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    
    class Config:
        extra = "allow"  # Allow additional fields for extensibility