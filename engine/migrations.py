from typing import Any, Callable, Dict, List, Tuple

# Registry of migrators: content_type -> list of (from_ver, to_ver, func)
_MIGRATORS: Dict[str, List[Tuple[int, int, Callable[[Dict[str, Any]], Dict[str, Any]]]]] = {}

def register_migrator(content_type: str, from_version: int, to_version: int, func: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
    """Register a migration function for a specific content type and version step."""
    if content_type not in _MIGRATORS:
        _MIGRATORS[content_type] = []
    _MIGRATORS[content_type].append((from_version, to_version, func))
    # Sort by from_version to ensure correct application order
    _MIGRATORS[content_type].sort(key=lambda x: x[0])

def migrate_payload(content_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Apply all applicable migrations to the payload."""
    if content_type not in _MIGRATORS:
        return payload

    # Determine current version
    # Default to 1 if missing, or 0 if it's a trace (special case handled by caller usually, but we can support it)
    current_version = payload.get("schema_version", 1)

    # Special case: if it's a trace and missing schema_version, treat as 0
    if content_type == "trace" and "schema_version" not in payload:
        current_version = 0

    # Find applicable migrations
    migrators = _MIGRATORS[content_type]

    # Apply in chain
    for from_ver, to_ver, func in migrators:
        if current_version == from_ver:
            print(f"[Mesh][Migration] Migrating {content_type} from v{from_ver} to v{to_ver}")
            try:
                payload = func(payload)
                payload["schema_version"] = to_ver
                current_version = to_ver
            except Exception as e:
                print(f"[Mesh][Migration] ERROR migrating {content_type} v{from_ver}->v{to_ver}: {e}")
                raise e

    return payload

# --- Example / Default Migrators ---

def _migrate_trace_v0_to_v1(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize trace event: ensure timestamp key exists."""
    # v0 traces might have missing timestamp or different keys
    if "timestamp" not in payload:
        payload["timestamp"] = 0.0
    return payload

# Register default migrators
register_migrator("trace", 0, 1, _migrate_trace_v0_to_v1)
