"""
Recommendation models
"""

from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Severity levels for recommendations"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Recommendation(BaseModel):
    """Represents an analysis recommendation"""
    title: str
    description: str
    severity: Severity
    category: str  # e.g., "infrastructure", "configuration", etc.
    
    # Optional fields
    current_value: Optional[str] = None  # Current observed value
    impact: Optional[str] = None
    recommendation: Optional[str] = None
    reference_url: Optional[str] = None
    
    # Additional context data
    context: Dict[str, Any] = Field(default_factory=dict)
    
    def to_markdown(self) -> str:
        """Convert recommendation to markdown format"""
        md = f"### {self.title}\n\n"
        md += f"**Severity:** {self.severity.value.upper()}\n\n"
        md += f"{self.description}\n\n"
        
        if self.impact:
            md += f"**Impact:** {self.impact}\n\n"
        
        if self.recommendation:
            md += f"**Recommendation:** {self.recommendation}\n\n"
        
        if self.reference_url:
            md += f"**Reference:** [{self.reference_url}]({self.reference_url})\n\n"
        
        return md