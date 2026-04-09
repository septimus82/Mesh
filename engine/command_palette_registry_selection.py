"""Selection/entity helper functions for command palette actions.

Extracted from ``engine.command_palette_registry`` to keep the main registry
module slimmer while preserving behavior and call contracts.
"""

from __future__ import annotations

from typing import Any


def get_selection_ids_and_primary(w: Any) -> tuple[list[str], str]:
    """Return ``(selected_ids, primary_id)`` from ``entity_select_state``."""
    state = getattr(w, "entity_select_state", None)
    ids = getattr(state, "selected_ids", None) if state is not None else None
    if not isinstance(ids, list):
        ids = []
    selected_ids = sorted({str(i).strip() for i in ids if isinstance(i, str) and str(i).strip()})
    primary_id = getattr(state, "primary_id", None) if state is not None else None
    primary_id = str(primary_id).strip() if isinstance(primary_id, str) and str(primary_id).strip() else (selected_ids[0] if selected_ids else "")
    return selected_ids, primary_id


def get_authored_payload(w: Any) -> dict[str, Any] | None:
    """Return the authored scene payload dict, or ``None``."""
    sc = getattr(w, "scene_controller", None)
    getter = getattr(sc, "get_authored_scene_payload", None) if sc is not None else None
    payload = getter() if callable(getter) else None
    return payload if isinstance(payload, dict) else None


def selection_non_player_ids(w: Any, selected_ids: list[str]) -> tuple[list[str], bool]:
    """Return ``(non_player_ids, saw_player)`` for given selection."""
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id, is_player_entity  # noqa: PLC0415

    authored = get_authored_payload(w)
    if authored is None:
        return ([], False)
    entities = ensure_entities_list(authored)
    non_player: list[str] = []
    saw_player = False
    for entity_id in selected_ids:
        ent = find_entity_by_id(entities, entity_id)
        if not isinstance(ent, dict):
            continue
        if is_player_entity(ent):
            saw_player = True
            continue
        non_player.append(entity_id)
    return (sorted(set(non_player)), saw_player)


def parse_float(text: str) -> float | None:
    """Parse float from text, returning ``None`` on failure."""
    try:
        return float(str(text).strip())
    except Exception:  # noqa: BLE001  # REASON: invalid numeric prompt input should fail closed to None without breaking palette parsing
        return None


def entity_has_behaviour(ent: dict[str, Any], behaviour: str) -> bool:
    """Check if an entity has a behaviour of given type."""
    behaviours = ent.get("behaviours")
    if not isinstance(behaviours, list):
        return False
    for b in behaviours:
        if isinstance(b, str) and b.strip() == behaviour:
            return True
        if isinstance(b, dict):
            bt = b.get("type")
            if isinstance(bt, str) and bt.strip() == behaviour:
                return True
    return False
