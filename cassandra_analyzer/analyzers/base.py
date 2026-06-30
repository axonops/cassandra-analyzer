"""
Base analyzer class
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..config import Config
from ..models import (
    AffectedResources,
    Check,
    CheckStatus,
    ClusterState,
    Recommendation,
)

# Cassandra 5.0 renamed many ``*_in_ms`` / ``*_in_mb`` / ``*_mb_per_sec``
# settings to use duration, data-size, and data-rate syntax (``200ms``,
# ``5s``, ``1h``, ``128MiB``, ``64MiB/s``). The AxonOps agent surfaces
# whichever form the node actually has, so analyzers need to be able to read
# either variant.

# --- Durations -------------------------------------------------------------

_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(ms|s|m|h|d)?\s*$", re.IGNORECASE)
_DURATION_UNITS_MS = {
    None: 1,
    "ms": 1,
    "s": 1000,
    "m": 60_000,
    "h": 3_600_000,
    "d": 86_400_000,
}


def _parse_duration_to_ms(value: Any) -> Optional[int]:
    """Parse a Cassandra duration into milliseconds.

    Accepts plain integers (treated as milliseconds, matching the legacy
    ``*_in_ms`` convention), bare numeric strings, and the 5.x duration
    syntax (``200ms``, ``5s``, ``1h``). Returns ``None`` for unparseable
    input.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = _DURATION_RE.match(str(value))
    if not match:
        return None
    number = float(match.group(1))
    unit = (match.group(2) or "").lower() or None
    factor = _DURATION_UNITS_MS.get(unit)
    if factor is None:
        return None
    return int(number * factor)


# --- Data sizes ------------------------------------------------------------
#
# Cassandra 5.0 uses binary units: 1 KiB = 1024 B, 1 MiB = 1024 KiB, etc. The
# legacy ``*_in_mb`` style settings always meant binary MB (i.e. MiB). We
# accept both ``MB``/``MiB`` spellings (treating them identically) and the
# bare numeric form (which is interpreted using the caller-supplied default
# unit, matching the legacy semantics).

_SIZE_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*([KMGT]i?B|B)?\s*$",
    re.IGNORECASE,
)
_SIZE_UNITS_BYTES = {
    "B": 1,
    "KB": 1024,
    "KIB": 1024,
    "MB": 1024 * 1024,
    "MIB": 1024 * 1024,
    "GB": 1024 ** 3,
    "GIB": 1024 ** 3,
    "TB": 1024 ** 4,
    "TIB": 1024 ** 4,
}


def _parse_size_to_bytes(value: Any, default_unit: str = "MiB") -> Optional[int]:
    """Parse a Cassandra data-size value into bytes.

    Accepts the new 5.x style (``"32MiB"``, ``"4GiB"``, ``"128KiB"``), bare
    numeric values (interpreted using ``default_unit`` — typically ``MiB`` to
    match the legacy ``*_in_mb`` convention), and plain integers. Returns
    ``None`` if the value cannot be parsed.
    """
    if value is None or isinstance(value, bool):
        return None
    default_factor = _SIZE_UNITS_BYTES.get(default_unit.upper())
    if default_factor is None:
        return None
    if isinstance(value, (int, float)):
        return int(value * default_factor)
    match = _SIZE_RE.match(str(value))
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2)
    if unit is None:
        return int(number * default_factor)
    factor = _SIZE_UNITS_BYTES.get(unit.upper())
    if factor is None:
        return None
    return int(number * factor)


# --- Data rates ------------------------------------------------------------
#
# Cassandra exposes two distinct rate flavours:
#   - legacy ``*_mb_per_sec``: integer megabytes (binary) per second.
#   - legacy ``*_megabits_per_sec``: integer megabits per second.
#   - 5.x replacement keys carry units, e.g. ``"64MiB/s"`` or ``"200Mibps"``.
# We normalise to bytes-per-second internally; the call-site helpers convert
# back to the legacy unit so existing comparisons (against literals like 16
# or 200) keep working.

_RATE_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*([KMGT]i?B|B|[KMGT]i?bps|bps|[KMGT]i?b/s|[KMGT]i?B/s|b/s)?\s*(?:/s)?\s*$",
    re.IGNORECASE,
)
_RATE_UNITS_BYTES_PER_SEC = {
    # Bytes-per-second
    "B": 1,
    "KB": 1024,
    "KIB": 1024,
    "MB": 1024 * 1024,
    "MIB": 1024 * 1024,
    "GB": 1024 ** 3,
    "GIB": 1024 ** 3,
    # Bits-per-second (8 bits per byte)
    "BPS": 1 / 8,
    "KBPS": 1000 / 8,
    "KIBPS": 1024 / 8,
    "MBPS": 1_000_000 / 8,
    "MIBPS": 1024 * 1024 / 8,
    "GBPS": 1_000_000_000 / 8,
    "GIBPS": 1024 ** 3 / 8,
}


def _parse_rate_to_bytes_per_sec(value: Any, default_unit: str = "MiB/s") -> Optional[float]:
    """Parse a Cassandra data-rate value into bytes per second.

    Bare numeric values are interpreted using ``default_unit`` — pass
    ``"MiB/s"`` for legacy ``*_mb_per_sec`` keys and ``"Mibps"`` (megabits
    per second) for legacy ``*_megabits_per_sec`` keys. The 5.x string form
    is also accepted (``"64MiB/s"``, ``"200Mibps"``).
    """
    if value is None or isinstance(value, bool):
        return None

    def _unit_to_bps(unit: Optional[str]) -> Optional[float]:
        if unit is None:
            return None
        u = unit.upper().replace("/S", "").replace(" ", "")
        # "MIB" alone reads as bytes-per-second when used as a rate.
        if u in _RATE_UNITS_BYTES_PER_SEC:
            return _RATE_UNITS_BYTES_PER_SEC[u]
        return None

    default_bps = _unit_to_bps(default_unit)
    if default_bps is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) * default_bps
    match = _RATE_RE.match(str(value))
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2)
    if unit is None:
        return number * default_bps
    factor = _unit_to_bps(unit)
    if factor is None:
        return None
    return number * factor


def _infer_affected_resources(context: Dict[str, Any]) -> "AffectedResources":
    """Best-effort lift of standard scoping keys from a recommendation's
    ``**context`` dict into the typed ``AffectedResources`` field.

    Recognised keys (matching the conventions already used across the
    analyzers):

    - ``keyspace`` (str) → ``keyspaces=[value]``
    - ``table`` (str) — combined with ``keyspace`` if both present → one
      entry in ``tables=[{"keyspace": ks, "table": t}]``
    - ``node`` / ``node_id`` (str) → ``nodes=[value]``
    - ``affected_nodes`` (list) → ``nodes=[...]`` (existing security-analyzer
      convention)
    - ``datacenter`` / ``dc`` (str) → ``datacenters=[value]``

    Call sites needing richer scoping (multi-keyspace findings, per-table
    lists across many tables) pass ``affected_resources=`` explicitly.
    """
    keyspaces: List[str] = []
    tables: List[Dict[str, str]] = []
    nodes: List[str] = []
    datacenters: List[str] = []

    ks = context.get("keyspace")
    if isinstance(ks, str) and ks:
        keyspaces.append(ks)

    tbl = context.get("table")
    if isinstance(tbl, str) and tbl and isinstance(ks, str) and ks:
        tables.append({"keyspace": ks, "table": tbl})

    # some checks return tables_affected as a list of strings in keyspace.table format
    tables_affected = context.get("tables_affected")
    if isinstance(tables_affected, list) and len(tables_affected) > 0:
        for t in tables_affected:
            if isinstance(t, str) and "." in t:
                ks, tbl = t.split(".")
                if ks and tbl:
                    tables.append({"keyspace": ks, "table": tbl})

    for key in ("node", "node_id"):
        v = context.get(key)
        if isinstance(v, str) and v:
            nodes.append(v)
            break

    affected_nodes = context.get("affected_nodes")
    if isinstance(affected_nodes, list):
        for n in affected_nodes:
            if isinstance(n, str) and n and n not in nodes:
                nodes.append(n)

    for key in ("datacenter", "dc"):
        v = context.get(key)
        if isinstance(v, str) and v:
            datacenters.append(v)
            break

    return AffectedResources(
        keyspaces=keyspaces,
        tables=tables,
        nodes=nodes,
        datacenters=datacenters,
    )


class BaseAnalyzer(ABC):
    """Base class for all analyzers"""

    # Default category surfaced on Check entries created by this analyzer
    # if `_record_check` is called without an explicit category.
    category: str = ""

    def __init__(self, config: Config):
        self.config = config
        self.thresholds = config.analysis.thresholds
        self._checks: List[Check] = []

    @abstractmethod
    def analyze(self, cluster_state: ClusterState) -> Dict[str, Any]:
        """
        Analyze the cluster state and return results

        Returns:
            Dict containing:
            - recommendations: List of Recommendation objects
            - summary: Dict with summary statistics
            - details: Dict with detailed analysis data
            - checks: List of Check objects for the coverage manifest
        """
        pass

    # ------------------------------------------------------------------ checks

    def _reset_checks(self) -> None:
        """Clear the per-run check buffer. Call at the start of analyze()."""
        self._checks = []

    def _record_check(
        self,
        check_id: str,
        description: str,
        data_source: str,
        status: str,
        *,
        category: Optional[str] = None,
        skipped_reason: Optional[str] = None,
        recommendation_id: Optional[str] = None,
        **context: Any,
    ) -> Check:
        """Append a Check entry to this analyzer's coverage manifest.

        Use the four-status model:
        - "pass": ran cleanly
        - "fail": ran and produced a recommendation (set recommendation_id)
        - "skipped": precondition not met (set skipped_reason)
        - "no_data": data source absent / empty (set skipped_reason explaining what was missing)
        """
        check = Check(
            id=check_id,
            description=description,
            category=category or self.category or "unknown",
            data_source=data_source,
            status=CheckStatus(status),
            skipped_reason=skipped_reason,
            recommendation_id=recommendation_id,
            context=context,
        )
        self._checks.append(check)
        return check

    def _create_recommendation(
        self,
        title: str,
        description: str,
        severity: str,
        category: str,
        impact: str = None,
        recommendation: str = None,
        current_value: str = None,
        reference_url: str = None,
        check_id: Optional[str] = None,
        recommendation_category: Optional[str] = None,
        affected_resources: Any = None,
        **context
    ) -> Recommendation:
        """Helper method to create recommendations.

        ``recommendation_category`` is the downstream LLM-service vocabulary
        (one of performance/reliability/configuration/capacity/security). Each
        analyzer subclass MUST set ``default_recommendation_category`` so this
        helper has a sensible fallback when an individual call site doesn't
        override it. Per-call overrides take precedence — call sites that
        emit findings outside their analyzer's default lane should pass
        ``recommendation_category=`` explicitly.

        ``affected_resources`` accepts either an ``AffectedResources`` model
        or a dict mapping fields (``keyspaces=``, ``tables=``, ``nodes=``,
        ``datacenters=``). It's the slicer's hook for routing findings to
        per-keyspace buckets in the LLM service. Cluster-wide findings can
        omit it; the default is all-empty lists.
        """
        if current_value is not None and "current_value" not in context:
            context["current_value"] = current_value

        # Resolve the downstream category. Per-call kwarg wins; else fall back
        # to the analyzer subclass's default; else a coarse "configuration"
        # fallback for any analyzer that hasn't been audited yet.
        effective_recommendation_category = (
            recommendation_category
            or getattr(self, "default_recommendation_category", None)
            or "configuration"
        )

        if affected_resources is None:
            # Auto-populate from context kwargs when standard fields are
            # present. Existing call sites pass `keyspace=`, `table=`, `node=`
            # etc. as **context kwargs; lifting that data into a typed field
            # means downstream slicing works without a per-call-site rewrite.
            # Explicit `affected_resources=` always wins.
            affected_resources_obj = _infer_affected_resources(context)
        elif isinstance(affected_resources, AffectedResources):
            affected_resources_obj = affected_resources
        elif isinstance(affected_resources, dict):
            affected_resources_obj = AffectedResources(**affected_resources)
        else:
            raise TypeError(
                f"affected_resources must be AffectedResources, dict, or None; "
                f"got {type(affected_resources).__name__}"
            )

        return Recommendation(
            id=check_id,
            title=title,
            description=description,
            severity=severity,
            category=category,
            recommendation_category=effective_recommendation_category,
            affected_resources=affected_resources_obj,
            impact=impact,
            recommendation=recommendation,
            current_value=current_value,
            reference_url=reference_url,
            context=context
        )
    
    def _get_metric_average(self, metrics: Dict[str, Any], metric_name: str) -> float:
        """Get average value for a metric"""
        metric_data = metrics.get(metric_name, [])
        if not metric_data:
            return 0.0
        
        # Assuming metric_data is a list of MetricData objects
        total_points = 0
        total_value = 0.0
        
        for metric in metric_data:
            if hasattr(metric, 'data_points'):
                for point in metric.data_points:
                    total_value += point.value
                    total_points += 1
        
        return total_value / total_points if total_points > 0 else 0.0
    
    def _get_metric_max(self, metrics: Dict[str, Any], metric_name: str) -> float:
        """Get maximum value for a metric"""
        metric_data = metrics.get(metric_name, [])
        if not metric_data:
            return 0.0
        
        max_value = 0.0
        for metric in metric_data:
            if hasattr(metric, 'data_points'):
                for point in metric.data_points:
                    max_value = max(max_value, point.value)
        
        return max_value
    
    def _is_system_keyspace(self, keyspace_name: str) -> bool:
        """Check if a keyspace is a system keyspace"""
        system_keyspaces = {
            'system',
            'system_auth',
            'system_distributed',
            'system_schema',
            'system_traces'
        }
        return keyspace_name in system_keyspaces

    def _get_duration_ms(self, node, base_name: str) -> Optional[int]:
        """Read a duration setting from a node's Details, in milliseconds.

        Tries ``comp_<base_name>_in_ms`` (legacy 4.x and earlier) first, then
        falls back to ``comp_<base_name>`` which on 5.x carries duration syntax
        like ``200ms`` / ``5s`` / ``1h``. Returns ``None`` if neither is set
        or the value cannot be parsed.
        """
        details = getattr(node, "Details", {}) or {}
        legacy = details.get(f"comp_{base_name}_in_ms")
        if legacy is not None:
            parsed = _parse_duration_to_ms(legacy)
            if parsed is not None:
                return parsed
        modern = details.get(f"comp_{base_name}")
        if modern is not None:
            return _parse_duration_to_ms(modern)
        return None

    def _get_size_bytes(
        self,
        node,
        base_name: str,
        legacy_suffix: str = "in_mb",
        legacy_unit: str = "MiB",
    ) -> Optional[int]:
        """Read a data-size setting from a node's Details, in bytes.

        Tries ``comp_<base_name>_<legacy_suffix>`` first (interpreted with
        ``legacy_unit``) and then ``comp_<base_name>`` (5.x form, which
        carries an explicit unit such as ``32MiB``). Returns ``None`` if
        neither is set or the value cannot be parsed.
        """
        details = getattr(node, "Details", {}) or {}
        legacy = details.get(f"comp_{base_name}_{legacy_suffix}")
        if legacy is not None:
            parsed = _parse_size_to_bytes(legacy, default_unit=legacy_unit)
            if parsed is not None:
                return parsed
        modern = details.get(f"comp_{base_name}")
        if modern is not None:
            return _parse_size_to_bytes(modern)
        return None

    def _get_size_mb(
        self,
        node,
        base_name: str,
        legacy_suffix: str = "in_mb",
        legacy_unit: str = "MiB",
    ) -> Optional[float]:
        """Convenience wrapper around :meth:`_get_size_bytes` returning MiB."""
        b = self._get_size_bytes(node, base_name, legacy_suffix, legacy_unit)
        return None if b is None else b / (1024 * 1024)

    def _get_rate_bytes_per_sec(
        self,
        node,
        base_name: str,
        legacy_suffix: str,
        legacy_unit: str,
    ) -> Optional[float]:
        """Read a data-rate setting from a node's Details, in bytes/second.

        ``legacy_suffix`` and ``legacy_unit`` describe the pre-5.x key form,
        e.g. ``"mb_per_sec"`` / ``"MiB/s"`` for the compaction-throughput
        key, or ``"megabits_per_sec"`` / ``"Mibps"`` for stream-throughput.
        On 5.x the value is read from ``comp_<base_name>`` and parsed using
        the unit it carries.
        """
        details = getattr(node, "Details", {}) or {}
        legacy = details.get(f"comp_{base_name}_{legacy_suffix}")
        if legacy is not None:
            parsed = _parse_rate_to_bytes_per_sec(legacy, default_unit=legacy_unit)
            if parsed is not None:
                return parsed
        modern = details.get(f"comp_{base_name}")
        if modern is not None:
            return _parse_rate_to_bytes_per_sec(modern, default_unit=legacy_unit)
        return None

    def _get_rate_mibps(
        self,
        node,
        base_name: str,
        legacy_suffix: str = "mb_per_sec",
        legacy_unit: str = "MiB/s",
    ) -> Optional[float]:
        """Read a data-rate setting and return it in MiB/s. Defaults match
        the most common legacy form (``compaction_throughput_mb_per_sec``)."""
        bps = self._get_rate_bytes_per_sec(node, base_name, legacy_suffix, legacy_unit)
        return None if bps is None else bps / (1024 * 1024)