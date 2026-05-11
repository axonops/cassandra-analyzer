"""
Recommendation and coverage models.
"""

from enum import Enum
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Severity levels for recommendations"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# The five vocabulary values downstream consumers (LLM services) use to
# classify recommendations. Each `_create_recommendation` call site sets one
# of these via `recommendation_category` so the consumer doesn't need a
# section→category lookup table.
RecommendationCategory = Literal[
    "performance",
    "reliability",
    "configuration",
    "capacity",
    "security",
]


class AffectedResources(BaseModel):
    """Normalized identification of the cluster resources a recommendation
    applies to. Always present (default-empty) so downstream JSON consumers
    can rely on the field existing without conditional checks.

    Each list is opt-in per check — checks that are genuinely cluster-wide
    leave every list empty. Checks that affect specific keyspaces / tables /
    nodes populate the relevant list. Multi-resource findings can list more
    than one entry, and the LLM-service slicer fans these out as needed.
    """

    keyspaces: List[str] = Field(default_factory=list)
    # Each entry is a dict {"keyspace": "...", "table": "..."}.
    tables: List[Dict[str, str]] = Field(default_factory=list)
    nodes: List[str] = Field(default_factory=list)
    datacenters: List[str] = Field(default_factory=list)


class CheckStatus(str, Enum):
    """Outcome of a single declarative analyzer check.

    `pass`     — the check ran and the cluster met expectations.
    `fail`     — the check ran and produced a recommendation.
    `skipped`  — a precondition was not met (e.g. single-node test cluster
                 for a cross-DC check, no nodes returned by the API).
    `no_data`  — the analyzer would have run the check but the required
                 data source was empty / absent / unreachable. Downstream
                 consumers should treat these as *not yet checked*.
    """

    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"
    NO_DATA = "no_data"


class Check(BaseModel):
    """A single declarative check executed (or considered) by an analyzer.

    The set of checks emitted by every analysis run forms the *coverage
    manifest* that downstream consumers (LLM agents, dashboards) use to
    decide what they still need to query for themselves.
    """

    id: str  # hierarchical, e.g. "infra.rack.heterogeneous"
    description: str
    category: str
    data_source: str  # what API surface / metric the check inspects
    status: CheckStatus
    skipped_reason: Optional[str] = None
    recommendation_id: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)


class Recommendation(BaseModel):
    """Represents an analysis recommendation"""
    id: Optional[str] = None  # stable check id this recommendation maps to
    title: str
    description: str
    severity: Severity
    category: str  # analyzer section, e.g., "infrastructure", "configuration", etc.

    # Downstream consumer vocabulary. The LLM service routes recommendations by
    # this value rather than translating from `category`. Required at construction
    # — every `_create_recommendation` call must pick one of the five values.
    recommendation_category: RecommendationCategory

    # Cluster resources this recommendation applies to. Always present, defaults
    # to all-empty lists for cluster-wide findings. Populated per check where
    # the affected keyspaces / tables / nodes / datacenters are knowable.
    affected_resources: AffectedResources = Field(default_factory=AffectedResources)

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
