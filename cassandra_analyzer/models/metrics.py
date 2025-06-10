"""
Metrics data models
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class MetricPoint(BaseModel):
    """Represents a single metric data point"""
    timestamp: datetime
    value: float
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class MetricData(BaseModel):
    """Represents a time series metric"""
    metric_name: str
    labels: Dict[str, str] = Field(default_factory=dict)
    data_points: List[MetricPoint] = Field(default_factory=list)
    
    def get_average(self) -> Optional[float]:
        """Calculate average value"""
        if not self.data_points:
            return None
        return sum(p.value for p in self.data_points) / len(self.data_points)
    
    def get_max(self) -> Optional[float]:
        """Get maximum value"""
        if not self.data_points:
            return None
        return max(p.value for p in self.data_points)
    
    def get_min(self) -> Optional[float]:
        """Get minimum value"""
        if not self.data_points:
            return None
        return min(p.value for p in self.data_points)
    
    def get_percentile(self, percentile: float) -> Optional[float]:
        """Get percentile value (0-100)"""
        if not self.data_points:
            return None
        
        sorted_values = sorted(p.value for p in self.data_points)
        index = int(len(sorted_values) * percentile / 100)
        return sorted_values[min(index, len(sorted_values) - 1)]