from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.swallowed_exceptions import _log_swallow

from .command_palette_registry_selection import (
    get_authored_payload as _get_authored_payload,
)
from .command_palette_registry_selection import (
    get_selection_ids_and_primary as _get_selection_ids_and_primary,
)
from .command_palette_registry_selection import (
    selection_non_player_ids as _selection_non_player_ids,
)


def enabled_always(_w: Any) -> tuple[bool, str]:
    return True, ""


def enabled_has_scene(w: Any) -> tuple[bool, str]:
    sc = getattr(w, "scene_controller", None)
    scene_path = str(getattr(sc, "current_scene_path", "") or "").strip() if sc is not None else ""
    if not scene_path:
        return False, "no_scene"
    return True, ""


def enabled_has_scene_and_authored_payload(w: Any) -> tuple[bool, str]:
    ok, reason = enabled_has_scene(w)
    if not ok:
        return ok, reason
    if _get_authored_payload(w) is None:
        return False, "no_authored_payload"
    return True, ""


def enabled_scene_persist_armed(w: Any) -> tuple[bool, str]:
    ok, reason = enabled_has_scene(w)
    if not ok:
        return ok, reason
    if not bool(getattr(w, "scene_persist_armed", False)):
        return False, "not_armed"
    return True, ""


def enabled_persist_armed_only(w: Any) -> tuple[bool, str]:
    if not bool(getattr(w, "scene_persist_armed", False)):
        return False, "not_armed"
    return True, ""


def enabled_scene_index_nonempty(_w: Any) -> tuple[bool, str]:
    from engine.scene_index import iter_known_scene_paths  # noqa: PLC0415

    if not iter_known_scene_paths():
        return False, "no_scenes"
    return True, ""


def enabled_recent_nonempty(w: Any) -> tuple[bool, str]:
    getter = getattr(w, "get_recent_scenes", None)
    recent = getter() if callable(getter) else []
    if not isinstance(recent, list) or not recent:
        return False, "empty"
    return True, ""


def enabled_selection_has_non_player(w: Any) -> tuple[bool, str]:
    selected_ids, _primary = _get_selection_ids_and_primary(w)
    if not selected_ids:
        return False, "no_selection"
    if _get_authored_payload(w) is None:
        return False, "no_authored_payload"
    non_player, saw_player = _selection_non_player_ids(w, selected_ids)
    if not non_player and saw_player:
        return False, "only_player"
    if not non_player:
        return False, "no_selection"
    return True, ""


def enabled_selection_has_primary_non_player(w: Any) -> tuple[bool, str]:
    selected_ids, _primary_id = _get_selection_ids_and_primary(w)
    if not selected_ids:
        return False, "no_selection"
    if _get_authored_payload(w) is None:
        return False, "no_authored_payload"
    non_player, saw_player = _selection_non_player_ids(w, selected_ids)
    if not non_player and saw_player:
        return False, "only_player"
    if not non_player:
        return False, "no_selection"
    return True, ""


def default_empty(_w: Any) -> str:
    return ""


def default_save_as(_w: Any) -> str:
    return ""


def default_scene_create(w: Any) -> str:
    sc = getattr(w, "scene_controller", None)
    scene_path = str(getattr(sc, "current_scene_path", "") or "").strip() if sc is not None else ""
    if not scene_path:
        return "scenes/new_scene.json"
    base = Path(scene_path)
    return str(base.parent / f"{base.stem}__new.json")


def default_cursor(_w: Any) -> str:
    return "cursor"


def default_radius_72(_w: Any) -> str:
    return "72"


def _set_last_props_action(w: Any, *, action: str, changed: int) -> None:
    try:
        w.last_props_action = str(action)
        w.last_props_changed = int(changed)
        w.last_props_counter = int(getattr(w, "scene_dirty_counter", 0) or 0)
    except Exception:  # noqa: BLE001  # REASON: command palette registry fallback isolation
        _log_swallow("COMM-001", "engine/command_palette_registry.py pass-only blanket swallow")


def _set_last_config_action(w: Any, *, action: str, changed: int) -> None:
    try:
        w.last_config_action = str(action)
        w.last_config_changed = int(changed)
        w.last_config_counter = int(getattr(w, "scene_dirty_counter", 0) or 0)
    except Exception:  # noqa: BLE001  # REASON: command palette registry fallback isolation
        _log_swallow("COMM-002", "engine/command_palette_registry.py pass-only blanket swallow")


def _get_player_pos_from_authored(w: Any) -> tuple[float, float] | None:
    from engine.entity_paint_mode import ensure_entities_list, is_player_entity  # noqa: PLC0415

    authored = _get_authored_payload(w)
    if authored is None:
        return None
    entities = ensure_entities_list(authored)
    for ent in entities:
        if not isinstance(ent, dict) or not is_player_entity(ent):
            continue
        try:
            x = float(ent.get("x", 0.0))
        except (TypeError, ValueError):
            _log_swallow("CPRG-001", "engine/command_palette_registry.py blanket swallow", once=True)
            x = 0.0
        try:
            y = float(ent.get("y", 0.0))
        except (TypeError, ValueError):
            _log_swallow("CPRG-002", "engine/command_palette_registry.py blanket swallow", once=True)
            y = 0.0
        return float(x), float(y)
    return None


def _get_entity_pos_from_authored(w: Any, entity_id: str) -> tuple[float, float] | None:
    from engine.entity_paint_mode import ensure_entities_list, find_entity_by_id  # noqa: PLC0415

    authored = _get_authored_payload(w)
    if authored is None:
        return None
    entities = ensure_entities_list(authored)
    ent = find_entity_by_id(entities, entity_id)
    if not isinstance(ent, dict):
        return None
    try:
        x = float(ent.get("x", 0.0))
    except (TypeError, ValueError):
        _log_swallow("CPRG-003", "engine/command_palette_registry.py blanket swallow", once=True)
        x = 0.0
    try:
        y = float(ent.get("y", 0.0))
    except (TypeError, ValueError):
        _log_swallow("CPRG-004", "engine/command_palette_registry.py blanket swallow", once=True)
        y = 0.0
    return float(x), float(y)


def _get_cursor_world_pos(w: Any) -> tuple[float, float] | None:
    input_ctrl = getattr(w, "input_controller", None)
    mx = getattr(input_ctrl, "mouse_x", None) if input_ctrl is not None else None
    my = getattr(input_ctrl, "mouse_y", None) if input_ctrl is not None else None
    to_world = getattr(w, "screen_to_world", None)
    if callable(to_world) and isinstance(mx, (int, float)) and isinstance(my, (int, float)):
        try:
            result = to_world(float(mx), float(my))
        except Exception:  # noqa: BLE001  # REASON: command palette registry fallback isolation
            _log_swallow("CPRG-005", "engine/command_palette_registry.py blanket swallow", once=True)
            return None
        if isinstance(result, tuple) and len(result) >= 2:
            x, y = result[0], result[1]
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                return float(x), float(y)
    return None


def _resolve_macro_anchor_pos(w: Any, anchor: str) -> tuple[tuple[float, float] | None, str]:
    anchor_text = str(anchor or "").strip().lower()
    if anchor_text == "primary":
        selected_ids, primary_id = _get_selection_ids_and_primary(w)
        if not selected_ids or not primary_id:
            return None, "no_selection"
        pos = _get_entity_pos_from_authored(w, primary_id)
        if pos is None:
            return None, "no_selection"
        return pos, ""
    if anchor_text == "player":
        pos = _get_player_pos_from_authored(w)
        if pos is None:
            return (0.0, 0.0), ""
        return pos, ""
    pos = _get_cursor_world_pos(w)
    if pos is not None:
        return pos, ""
    pos = _get_player_pos_from_authored(w)
    if pos is None:
        return (0.0, 0.0), ""
    return pos, ""
