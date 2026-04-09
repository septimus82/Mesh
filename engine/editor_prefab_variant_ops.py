from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import copy

_MISSING = object()


@dataclass(frozen=True, slots=True)
class DiffRow:
    key: str
    base_value: Any
    override_value: Any
    effective_value: Any


def resolve_prefab_base(
    prefab_ref: dict[str, Any] | str | None,
    repo_root: Path | str | None = None,
    pack_resolver: Callable[[dict[str, Any] | str | None, Path | str | None], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """Resolve prefab base entity data from a prefab reference.

    Args:
        prefab_ref: Prefab reference (entity dict or prefab id).
        repo_root: Optional repo root for custom resolvers.
        pack_resolver: Optional resolver callback for tests/alternate sources.

    Returns:
        Resolved prefab base entity dict (empty if unresolved).
    """
    if callable(pack_resolver):
        resolved = pack_resolver(prefab_ref, repo_root)
        if isinstance(resolved, dict):
            entity = resolved.get("entity")
            return dict(entity) if isinstance(entity, dict) else dict(resolved)
        return {}

    prefab_id = None
    variant_id = None
    if isinstance(prefab_ref, dict):
        prefab_id = prefab_ref.get("prefab_id") or prefab_ref.get("prefab_path")
        variant_id = prefab_ref.get("variant_id")
    elif isinstance(prefab_ref, str):
        prefab_id = prefab_ref

    if not isinstance(prefab_id, str) or not prefab_id.strip():
        return {}

    try:
        from .prefabs import get_prefab_manager  # noqa: PLC0415
    except Exception:  # noqa: BLE001  # REASON: prefab manager imports are optional and should fall back to no resolved variant data
        return {}

    try:
        manager = get_prefab_manager()
        resolved = manager.resolve_with_variant(prefab_id.strip(), variant_id)
    except Exception:  # noqa: BLE001  # REASON: prefab variant resolution failures should fall back to no resolved variant data
        return {}

    if not isinstance(resolved, dict):
        return {}
    entity = resolved.get("entity")
    return dict(entity) if isinstance(entity, dict) else {}


def compute_prefab_override_diff(
    base: dict[str, Any] | None,
    effective: dict[str, Any] | None,
    overrides: dict[str, Any] | None,
) -> list[DiffRow]:
    """Build deterministic diff rows for prefab overrides."""
    base_dict = base if isinstance(base, dict) else {}
    effective_dict = effective if isinstance(effective, dict) else {}
    overrides_dict = overrides if isinstance(overrides, dict) else {}

    rows: list[DiffRow] = []
    for key in sorted(str(k) for k in overrides_dict.keys()):
        override_value = overrides_dict.get(key)
        base_value = _lookup_path_value(base_dict, key)
        effective_value = _lookup_path_value(effective_dict, key)
        if effective_value is _MISSING:
            effective_value = override_value
        rows.append(
            DiffRow(
                key=key,
                base_value=None if base_value is _MISSING else base_value,
                override_value=override_value,
                effective_value=None if effective_value is _MISSING else effective_value,
            )
        )
    return rows


def apply_override_delta(
    entity_json: dict[str, Any],
    key: str,
    new_value: Any,
) -> dict[str, Any]:
    """Return an updated entity json with a prefab override applied."""
    if not isinstance(entity_json, dict):
        return entity_json
    override_key = str(key or "").strip()
    if not override_key:
        return entity_json

    updated = dict(entity_json)
    overrides = entity_json.get("prefab_overrides")
    override_copy: dict[str, Any]
    if isinstance(overrides, dict):
        override_copy = copy.deepcopy(overrides)
    else:
        override_copy = {}

    override_copy[override_key] = copy.deepcopy(new_value)
    updated["prefab_overrides"] = _sorted_dict(override_copy)
    return updated


def revert_override_key(entity_json: dict[str, Any], key: str) -> dict[str, Any]:
    """Return an updated entity json with a prefab override removed."""
    if not isinstance(entity_json, dict):
        return entity_json
    override_key = str(key or "").strip()
    if not override_key:
        return entity_json

    overrides = entity_json.get("prefab_overrides")
    if not isinstance(overrides, dict) or override_key not in overrides:
        return entity_json

    updated = dict(entity_json)
    override_copy = copy.deepcopy(overrides)
    override_copy.pop(override_key, None)
    if override_copy:
        updated["prefab_overrides"] = _sorted_dict(override_copy)
    else:
        updated.pop("prefab_overrides", None)
    return updated


def clear_all_overrides(entity_json: dict[str, Any]) -> dict[str, Any]:
    """Return an updated entity json with prefab overrides cleared."""
    if not isinstance(entity_json, dict):
        return entity_json
    if "prefab_overrides" not in entity_json:
        return entity_json
    updated = dict(entity_json)
    updated.pop("prefab_overrides", None)
    return updated


def _sorted_dict(values: dict[str, Any]) -> dict[str, Any]:
    return {key: values[key] for key in sorted(values.keys())}


def _lookup_path_value(root: dict[str, Any], path: str) -> Any:
    if not path:
        return _MISSING
    parts = path.split(".")
    current: Any = root
    for part in parts:
        if not isinstance(current, dict):
            return _MISSING
        if part not in current:
            return _MISSING
        current = current.get(part)
    return current
