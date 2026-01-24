from __future__ import annotations

from typing import Any, Callable, Iterable


def _normalize_flag_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if isinstance(v, str) and v.strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def is_player_entity_payload(entity: Any) -> bool:
    if not isinstance(entity, dict):
        return False
    if entity.get("tag") == "player":
        return True
    tags = entity.get("tags")
    if isinstance(tags, list) and any(isinstance(t, str) and t.strip() == "player" for t in tags):
        return True
    if entity.get("prefab_id") == "player":
        return True
    behaviours = entity.get("behaviours")
    if isinstance(behaviours, list):
        for b in behaviours:
            if isinstance(b, str) and b.strip() == "PlayerController":
                return True
            if isinstance(b, dict) and str(b.get("type") or "").strip() == "PlayerController":
                return True
    return False


def entity_passes_flag_gates(entity: Any, *, get_flag: Callable[[str, bool], bool] | None) -> bool:
    if not isinstance(entity, dict):
        return False
    if is_player_entity_payload(entity):
        return True
    if not callable(get_flag):
        return True

    require_flags = _normalize_flag_list(entity.get("require_flags"))
    forbid_flags = _normalize_flag_list(entity.get("forbid_flags"))

    for flag in require_flags:
        if not bool(get_flag(flag, False)):
            return False
    for flag in forbid_flags:
        if bool(get_flag(flag, False)):
            return False
    return True


def runtime_entity_passes_flag_gates(entity: Any, *, get_flag: Callable[[str, bool], bool] | None) -> bool:
    """
    Return True when a runtime sprite/entity should be considered "active" for interactions.

    Supports:
    - Sprite-like objects with `mesh_entity_data` dict payload
    - Raw authored payload dicts
    """
    if isinstance(entity, dict):
        return entity_passes_flag_gates(entity, get_flag=get_flag)
    payload = getattr(entity, "mesh_entity_data", None)
    if isinstance(payload, dict):
        return entity_passes_flag_gates(payload, get_flag=get_flag)
    return True


def filter_entities_by_flags(
    entities: Iterable[Any],
    *,
    get_flag: Callable[[str, bool], bool] | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ent in entities:
        if entity_passes_flag_gates(ent, get_flag=get_flag):
            out.append(ent)
    return out
