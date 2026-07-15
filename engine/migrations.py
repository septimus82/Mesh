from typing import Any, Callable, Dict, List, Tuple

# Registry of migrators: content_type -> list of (from_ver, to_ver, func)
_MIGRATORS: Dict[str, List[Tuple[int, int, Callable[[Dict[str, Any]], Dict[str, Any]]]]] = {}

# Current schema versions - update these when adding new migrations
SCENE_SCHEMA_VERSION = 1
PREFAB_SCHEMA_VERSION = 1
DEFAULT_LEGACY_LIGHT_MODE = "soft"


def register_migrator(content_type: str, from_version: int, to_version: int, func: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
    """Register a migration function for a specific content type and version step."""
    if content_type not in _MIGRATORS:
        _MIGRATORS[content_type] = []
    _MIGRATORS[content_type].append((from_version, to_version, func))
    # Sort by from_version to ensure correct application order
    _MIGRATORS[content_type].sort(key=lambda x: x[0])


def get_current_schema_version(content_type: str) -> int:
    """Get the current schema version for a content type."""
    versions = {
        "scene": SCENE_SCHEMA_VERSION,
        "prefab": PREFAB_SCHEMA_VERSION,
        "trace": 1,
        "world": 1,
        "quests": 1,
    }
    return versions.get(content_type, 1)


def migrate_payload(content_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Apply all applicable migrations to the payload."""
    # Determine current version
    # Default to 1 if missing, or 0 if it's a trace (special case handled by caller usually, but we can support it)
    current_version = payload.get("schema_version", 1)

    # Special case: if it's a trace and missing schema_version, treat as 0
    if content_type == "trace" and "schema_version" not in payload:
        current_version = 0

    # Find applicable migrations
    migrators = _MIGRATORS.get(content_type, [])

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

    if content_type == "scene":
        payload = migrate_scene_legacy_lights(payload)

    return payload


def migrate_scene(data: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate a scene to the current schema version.
    
    This is the canonical entry point for scene migration.
    """
    return migrate_payload("scene", data)


def migrate_scene_legacy_lights(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Add the historical static-light mode default before scene schema validation."""

    lights = payload.get("lights")
    if not isinstance(lights, list):
        return payload

    migrated_lights: list[Any] | None = None
    for index, light in enumerate(lights):
        if not isinstance(light, dict) or light.get("mode"):
            continue
        if migrated_lights is None:
            migrated_lights = list(lights)
        migrated = dict(light)
        migrated["mode"] = DEFAULT_LEGACY_LIGHT_MODE
        migrated_lights[index] = migrated

    if migrated_lights is None:
        return payload

    migrated_payload = dict(payload)
    migrated_payload["lights"] = migrated_lights
    return migrated_payload


def migrate_prefab(data: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate a prefab to the current schema version.
    
    This is the canonical entry point for prefab migration.
    """
    return migrate_payload("prefab", data)


# --- Trace Migrators ---

def _migrate_trace_v0_to_v1(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize trace event: ensure timestamp key exists."""
    # v0 traces might have missing timestamp or different keys
    if "timestamp" not in payload:
        payload["timestamp"] = 0.0
    return payload

# Register default migrators
register_migrator("trace", 0, 1, _migrate_trace_v0_to_v1)


# --- Scene Migrators ---
# Currently at v1 - no migrations needed yet.
# When adding v1->v2 migration, add:
# def _migrate_scene_v1_to_v2(payload: Dict[str, Any]) -> Dict[str, Any]:
#     # ... migration logic ...
#     return payload
# register_migrator("scene", 1, 2, _migrate_scene_v1_to_v2)


# --- Prefab Migrators ---
# Currently at v1 - no migrations needed yet.
# When adding v1->v2 migration, add:
# def _migrate_prefab_v1_to_v2(payload: Dict[str, Any]) -> Dict[str, Any]:
#     # ... migration logic ...
#     return payload
# register_migrator("prefab", 1, 2, _migrate_prefab_v1_to_v2)
