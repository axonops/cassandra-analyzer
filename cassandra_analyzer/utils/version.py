"""
Cassandra version parsing and comparison helpers.

Replaces the naive ``float(version.split('.')[0] + '.' + version.split('.')[1])``
pattern that several analyzers were using. Handles strings like ``"4.1.3"``,
``"5.0.0"``, ``"5.0-alpha2"``, and ``"4.1.3-SNAPSHOT"``.
"""

import re
from typing import Optional, Tuple

VersionTuple = Tuple[int, int, int]

V3_0: VersionTuple = (3, 0, 0)
V4_0: VersionTuple = (4, 0, 0)
V4_1: VersionTuple = (4, 1, 0)
V5_0: VersionTuple = (5, 0, 0)

_VERSION_RE = re.compile(r"^\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def parse_version(version_str: Optional[str]) -> Optional[VersionTuple]:
    """Parse a Cassandra version string into a (major, minor, patch) tuple.

    Returns ``None`` for empty / unknown / unparseable inputs. Trailing
    qualifiers like ``-alpha2`` or ``-SNAPSHOT`` are ignored — only the
    numeric prefix is used for comparison purposes.
    """
    if not version_str or version_str == "unknown":
        return None
    match = _VERSION_RE.match(str(version_str))
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2)) if match.group(2) else 0
    patch = int(match.group(3)) if match.group(3) else 0
    return (major, minor, patch)


def _coerce(target) -> Optional[VersionTuple]:
    if isinstance(target, tuple):
        a, b, c = (list(target) + [0, 0, 0])[:3]
        return (int(a), int(b), int(c))
    return parse_version(target)


def version_at_least(version_str: Optional[str], target) -> bool:
    """Return True if ``version_str`` parses and is >= ``target``.

    ``target`` may be either a string (``"5.0"``) or a tuple (``V5_0``).
    Unparseable versions return False — callers that want a permissive
    default should handle that explicitly.
    """
    parsed = parse_version(version_str)
    target_t = _coerce(target)
    if parsed is None or target_t is None:
        return False
    return parsed >= target_t


def version_below(version_str: Optional[str], target) -> bool:
    """Return True if ``version_str`` parses and is < ``target``."""
    parsed = parse_version(version_str)
    target_t = _coerce(target)
    if parsed is None or target_t is None:
        return False
    return parsed < target_t


def node_version(node) -> Optional[str]:
    """Best-effort version string for a Node, checking the keys AxonOps
    surfaces. Returns the raw string; use ``parse_version`` for comparisons."""
    details = getattr(node, "Details", {}) or {}
    return (
        details.get("comp_releaseVersion")
        or details.get("comp_cassandra_version")
        or details.get("release_version")
    )


def cluster_min_version(cluster_state) -> Optional[VersionTuple]:
    """Lowest parseable Cassandra version across all nodes, or None."""
    versions = [parse_version(node_version(n)) for n in cluster_state.nodes.values()]
    versions = [v for v in versions if v is not None]
    return min(versions) if versions else None


def cluster_max_version(cluster_state) -> Optional[VersionTuple]:
    """Highest parseable Cassandra version across all nodes, or None."""
    versions = [parse_version(node_version(n)) for n in cluster_state.nodes.values()]
    versions = [v for v in versions if v is not None]
    return max(versions) if versions else None


def cluster_at_least(cluster_state, target) -> bool:
    """True if every node parses and meets ``target``. Used to gate
    recommendations that only make sense when the *whole* cluster has
    moved to a given version."""
    target_t = _coerce(target)
    if target_t is None:
        return False
    parsed = [parse_version(node_version(n)) for n in cluster_state.nodes.values()]
    if not parsed or any(v is None for v in parsed):
        return False
    return all(v >= target_t for v in parsed)
