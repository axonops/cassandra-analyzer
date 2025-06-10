"""
Configuration parsing utilities
"""

from typing import Dict, Any, Optional, List
import re


def parse_node_config(details: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse node configuration from the Details field
    
    Args:
        details: The Details dict from the nodes-full API response
    
    Returns:
        Parsed configuration dict
    """
    config = {
        "cassandra": {},
        "jvm": {},
        "system": {},
        "agent": {}
    }
    
    for key, value in details.items():
        if key.startswith("comp_"):
            # Cassandra configuration
            config_key = key[5:]  # Remove "comp_" prefix
            config["cassandra"][config_key] = parse_value(value)
        elif key.startswith("jvm_"):
            # JVM configuration
            config["jvm"][key] = parse_value(value)
        elif key.startswith("agent_"):
            # Agent configuration
            config["agent"][key] = parse_value(value)
        else:
            # System/other configuration
            config["system"][key] = parse_value(value)
    
    return config


def parse_value(value: str) -> Any:
    """
    Parse string values into appropriate types
    """
    if not isinstance(value, str):
        return value
    
    # Handle boolean values
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    
    # Handle numeric values
    if value.isdigit():
        return int(value)
    
    # Handle float values
    try:
        return float(value)
    except ValueError:
        pass
    
    # Handle size values (e.g., "32MiB", "100KiB")
    size_match = re.match(r"^(\d+(?:\.\d+)?)\s*([KMGT]i?B)$", value)
    if size_match:
        number = float(size_match.group(1))
        unit = size_match.group(2)
        return convert_to_bytes(number, unit)
    
    # Handle duration values (e.g., "10s", "5m", "2h")
    duration_match = re.match(r"^(\d+(?:\.\d+)?)\s*([smhd])$", value)
    if duration_match:
        number = float(duration_match.group(1))
        unit = duration_match.group(2)
        return convert_to_seconds(number, unit)
    
    # Handle list values
    if value.startswith("[") and value.endswith("]"):
        # Simple list parsing
        items = value[1:-1].split(",")
        return [item.strip() for item in items if item.strip()]
    
    return value


def convert_to_bytes(value: float, unit: str) -> int:
    """Convert size with unit to bytes"""
    units = {
        "B": 1,
        "KB": 1024,
        "KiB": 1024,
        "MB": 1024 * 1024,
        "MiB": 1024 * 1024,
        "GB": 1024 * 1024 * 1024,
        "GiB": 1024 * 1024 * 1024,
        "TB": 1024 * 1024 * 1024 * 1024,
        "TiB": 1024 * 1024 * 1024 * 1024,
    }
    return int(value * units.get(unit, 1))


def convert_to_seconds(value: float, unit: str) -> float:
    """Convert duration with unit to seconds"""
    units = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
    }
    return value * units.get(unit, 1)


def extract_cassandra_version(details: Dict[str, Any]) -> Optional[str]:
    """Extract Cassandra version from node details"""
    # Try different possible fields
    version_fields = ["release_version", "version", "cassandra_version", "dse_version"]
    
    for field in version_fields:
        if field in details and details[field]:
            return details[field]
    
    # Try to extract from system info if available
    if "system_info" in details:
        system_info = details["system_info"]
        if isinstance(system_info, dict) and "release_version" in system_info:
            return system_info["release_version"]
    
    return None


def get_jvm_settings(details: Dict[str, Any]) -> Dict[str, Any]:
    """Extract JVM settings from node details"""
    jvm_settings = {}
    
    # Common JVM settings to look for
    jvm_keys = [
        "max_heap_size",
        "heap_newsize",
        "jvm_version",
        "jvm_vendor",
        "garbage_collector"
    ]
    
    for key in jvm_keys:
        if key in details:
            jvm_settings[key] = details[key]
        # Also check with comp_ prefix
        if f"comp_{key}" in details:
            jvm_settings[key] = details[f"comp_{key}"]
    
    return jvm_settings