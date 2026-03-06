"""Command palette registry - extracted helper functions and command definitions.

This module contains the extracted helper functions and command definitions
that were previously nested inside build_default_commands(). The refactoring
reduces cyclomatic complexity while maintaining identical behavior.

The command definitions are stored in DEFAULT_COMMAND_DEFS as a deterministic
ordered list. Each definition is converted to a CommandSpec at runtime.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from . import command_palette_registry_options as _options
from . import command_palette_registry_actions as _actions
from . import command_palette_registry_defs as _defs
from . import command_palette_registry_parse as _parse
from .command_palette_registry_selection import (
    entity_has_behaviour as _entity_has_behaviour,
    get_authored_payload as _get_authored_payload,
    get_selection_ids_and_primary as _get_selection_ids_and_primary,
    parse_float as _parse_float,
    selection_non_player_ids as _selection_non_player_ids,
)


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)

if TYPE_CHECKING:
    from engine.command_palette import CommandSpec, PromptSpec

# ---------------------------------------------------------------------------
# Lazy imports cached once
# ---------------------------------------------------------------------------

def _list_prefab_ids_from_assets_cached() -> tuple[str, ...]:
    """Return cached list of prefab IDs from assets/prefabs.json."""
    from engine.command_palette import _list_prefab_ids_from_assets
    return _list_prefab_ids_from_assets()


def _list_behaviour_names_cached() -> tuple[str, ...]:
    """Return cached list of behaviour names from the registry."""
    from engine.command_palette import _list_behaviour_names
    return _list_behaviour_names()


# ---------------------------------------------------------------------------
# Enablement checks - pure functions taking window (w) -> (bool, reason)
# ---------------------------------------------------------------------------

def enabled_always(_w: Any) -> tuple[bool, str]:
    """Always enabled."""
    return True, ""


def enabled_has_scene(w: Any) -> tuple[bool, str]:
    """Enabled when a scene is loaded."""
    sc = getattr(w, "scene_controller", None)
    scene_path = str(getattr(sc, "current_scene_path", "") or "").strip() if sc is not None else ""
    if not scene_path:
        return False, "no_scene"
    return True, ""


def enabled_has_scene_and_authored_payload(w: Any) -> tuple[bool, str]:
    """Enabled when a scene with authored payload is loaded."""
    ok, reason = enabled_has_scene(w)
    if not ok:
        return ok, reason
    if _get_authored_payload(w) is None:
        return False, "no_authored_payload"
    return True, ""


def enabled_scene_persist_armed(w: Any) -> tuple[bool, str]:
    """Enabled when scene is loaded and persist is armed."""
    ok, reason = enabled_has_scene(w)
    if not ok:
        return ok, reason
    if not bool(getattr(w, "scene_persist_armed", False)):
        return False, "not_armed"
    return True, ""


def enabled_persist_armed_only(w: Any) -> tuple[bool, str]:
    """Enabled when persist is armed (no scene required)."""
    if not bool(getattr(w, "scene_persist_armed", False)):
        return False, "not_armed"
    return True, ""


def enabled_scene_index_nonempty(_w: Any) -> tuple[bool, str]:
    """Enabled when scene index has at least one scene."""
    from engine.scene_index import iter_known_scene_paths  # noqa: PLC0415
    paths = iter_known_scene_paths()
    if not paths:
        return False, "no_scenes"
    return True, ""


def enabled_recent_nonempty(w: Any) -> tuple[bool, str]:
    """Enabled when there are recent scenes."""
    getter = getattr(w, "get_recent_scenes", None)
    recent = getter() if callable(getter) else []
    if not isinstance(recent, list) or not recent:
        return False, "empty"
    return True, ""


def enabled_selection_has_non_player(w: Any) -> tuple[bool, str]:
    """Enabled when selection contains at least one non-player entity."""
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
    """Enabled when selection has a non-player primary (or deterministic fallback)."""
    selected_ids, primary_id = _get_selection_ids_and_primary(w)
    if not selected_ids:
        return False, "no_selection"
    if _get_authored_payload(w) is None:
        return False, "no_authored_payload"
    non_player, saw_player = _selection_non_player_ids(w, selected_ids)
    if not non_player and saw_player:
        return False, "only_player"
    if not non_player:
        return False, "no_selection"
    # Primary might be the player; still allow since we can deterministically pick a non-player primary.
    return True, ""


# ---------------------------------------------------------------------------
# Options providers - functions returning [(value, label), ...]
# ---------------------------------------------------------------------------

def options_all_scenes(_w: Any) -> list[tuple[str, str]]:
    """Return all known scene paths as options."""
    return _options.options_all_scenes(_w)


def options_recent_scenes(w: Any) -> list[tuple[str, str]]:
    """Return recent scene paths as options."""
    return _options.options_recent_scenes(w)


def options_prefab_ids(_w: Any) -> list[tuple[str, str]]:
    """Return all prefab IDs as options."""
    return _options.options_prefab_ids(
        _w,
        list_prefab_ids=_list_prefab_ids_from_assets_cached,
    )


def options_behaviour_names(_w: Any) -> list[tuple[str, str]]:
    """Return all behaviour names as options."""
    return _options.options_behaviour_names(
        _w,
        list_behaviour_names=_list_behaviour_names_cached,
    )


def options_behaviours_in_selection(w: Any) -> list[tuple[str, str]]:
    """Return behaviours present in selected entities as options."""
    return _options.options_behaviours_in_selection(
        w,
        get_authored_payload=_get_authored_payload,
        get_selection_ids_and_primary=_get_selection_ids_and_primary,
    )


def options_scene_paths(_w: Any) -> list[tuple[str, str]]:
    """Return all known scene paths as options (alias for options_all_scenes)."""
    return _options.options_scene_paths(_w)


def options_dialogue_speakers(w: Any) -> list[tuple[str, str]]:
    """Return entity IDs of dialogue speakers in scene."""
    return _options.options_dialogue_speakers(
        w,
        get_authored_payload=_get_authored_payload,
        entity_has_behaviour=_entity_has_behaviour,
    )


def options_macro_anchor(w: Any) -> list[tuple[str, str]]:
    """Return anchor options for macros."""
    return _options.options_macro_anchor(
        w,
        get_selection_ids_and_primary=_get_selection_ids_and_primary,
    )


# ---------------------------------------------------------------------------
# Default value providers
# ---------------------------------------------------------------------------

def default_empty(_w: Any) -> str:
    """Return empty string as default."""
    return ""


def default_save_as(_w: Any) -> str:
    """Return empty string for save-as default."""
    return ""


def default_scene_create(w: Any) -> str:
    """Return default path for scene creation."""
    sc = getattr(w, "scene_controller", None)
    scene_path = str(getattr(sc, "current_scene_path", "") or "").strip() if sc is not None else ""
    if not scene_path:
        return "scenes/new_scene.json"
    base = Path(scene_path)
    return str(base.parent / f"{base.stem}__new.json")


def default_cursor(_w: Any) -> str:
    """Return 'cursor' as default anchor."""
    return "cursor"


def default_radius_72(_w: Any) -> str:
    """Return '72' as default radius."""
    return "72"


# ---------------------------------------------------------------------------
# Action handlers - functions taking (window, arg) -> None
# ---------------------------------------------------------------------------

def action_toggle_tile_paint(w: Any, _arg: str | None) -> None:
    return _actions.action_toggle_tile_paint(w, _arg)


def action_toggle_entity_paint(w: Any, _arg: str | None) -> None:
    return _actions.action_toggle_entity_paint(w, _arg)


def action_toggle_palette_mode(_w: Any, _arg: str | None) -> None:
    return _actions.action_toggle_palette_mode(_w, _arg)


def action_toggle_capture(w: Any, _arg: str | None) -> None:
    return _actions.action_toggle_capture(w, _arg)


def action_toggle_ghost_originals(w: Any, _arg: str | None) -> None:
    return _actions.action_toggle_ghost_originals(w, _arg)


def action_palette_clear_recent(w: Any, _arg: str | None) -> None:
    return _actions.action_palette_clear_recent(w, _arg)


def action_palette_reset_ui_layout(w: Any, _arg: str | None) -> None:
    return _actions.action_palette_reset_ui_layout(w, _arg)


def action_scene_reload(w: Any, _arg: str | None) -> None:
    return _actions.action_scene_reload(w, _arg)


def action_scene_toggle_persist_armed(w: Any, _arg: str | None) -> None:
    return _actions.action_scene_toggle_persist_armed(w, _arg)


def action_scene_persist(w: Any, _arg: str | None) -> None:
    return _actions.action_scene_persist(w, _arg)


def action_scene_save_as(w: Any, arg: str | None) -> None:
    return _actions.action_scene_save_as(w, arg)


def action_scene_create(w: Any, arg: str | None) -> None:
    return _actions.action_scene_create(w, arg)


def action_go_to_scene(w: Any, arg: str | None) -> None:
    return _actions.action_go_to_scene(w, arg)


def action_recent_scene(w: Any, arg: str | None) -> None:
    return _actions.action_recent_scene(w, arg)


# ---------------------------------------------------------------------------
# Plane actions
# ---------------------------------------------------------------------------

_PLANES_TOGGLE_REPEAT_MAP: dict[str, tuple[str, ...]] = _defs._PLANES_TOGGLE_REPEAT_MAP
_PLANES_SELECT_MAP: dict[str, str] = _defs._PLANES_SELECT_MAP
_PLANES_MOVE_TO_MAP: dict[str, str] = _defs._PLANES_MOVE_TO_MAP


def action_planes_add(w: Any, arg: str | None) -> None:
    return _actions.action_planes_add(w, arg)


def action_planes_duplicate(w: Any, arg: str | None) -> None:
    return _actions.action_planes_duplicate(w, arg)


def action_planes_remove(w: Any, arg: str | None) -> None:
    return _actions.action_planes_remove(w, arg)


def action_planes_move_up(w: Any, arg: str | None) -> None:
    return _actions.action_planes_move_up(w, arg)


def action_planes_move_down(w: Any, arg: str | None) -> None:
    return _actions.action_planes_move_down(w, arg)


def action_planes_move_top(w: Any, arg: str | None) -> None:
    return _actions.action_planes_move_top(w, arg)


def action_planes_move_bottom(w: Any, arg: str | None) -> None:
    return _actions.action_planes_move_bottom(w, arg)


def action_planes_move_to(w: Any, arg: str | None) -> None:
    return _actions.action_planes_move_to(w, arg)


def action_planes_toggle_repeat_x(w: Any, arg: str | None) -> None:
    return _actions.action_planes_toggle_repeat_x(w, arg)


def action_planes_toggle_repeat_y(w: Any, arg: str | None) -> None:
    return _actions.action_planes_toggle_repeat_y(w, arg)


def action_planes_toggle_repeat(w: Any, arg: str | None) -> None:
    return _actions.action_planes_toggle_repeat(w, arg)


def action_planes_select_prev(w: Any, arg: str | None) -> None:
    return _actions.action_planes_select_prev(w, arg)


def action_planes_select_next(w: Any, arg: str | None) -> None:
    return _actions.action_planes_select_next(w, arg)


def action_planes_select(w: Any, arg: str | None) -> None:
    return _actions.action_planes_select(w, arg)


# ---------------------------------------------------------------------------
# Selection property actions
# ---------------------------------------------------------------------------

def _set_last_props_action(w: Any, *, action: str, changed: int) -> None:
    """Record last property action for repeat commands."""
    try:
        w.last_props_action = str(action)
        w.last_props_changed = int(changed)
        w.last_props_counter = int(getattr(w, "scene_dirty_counter", 0) or 0)
    except Exception:  # noqa: BLE001  # REASON: command palette registry fallback isolation
        _log_swallow("COMM-001", "engine/command_palette_registry.py pass-only blanket swallow")
        pass


def _set_last_config_action(w: Any, *, action: str, changed: int) -> None:
    """Record last config action for repeat commands."""
    try:
        w.last_config_action = str(action)
        w.last_config_changed = int(changed)
        w.last_config_counter = int(getattr(w, "scene_dirty_counter", 0) or 0)
    except Exception:  # noqa: BLE001  # REASON: command palette registry fallback isolation
        _log_swallow("COMM-002", "engine/command_palette_registry.py pass-only blanket swallow")
        pass


def action_props_set_prefab_id(w: Any, arg: str | None) -> None:
    return _actions.action_props_set_prefab_id(w, arg)


def action_props_add_behaviour(w: Any, arg: str | None) -> None:
    return _actions.action_props_add_behaviour(w, arg)


def action_props_remove_behaviour(w: Any, arg: str | None) -> None:
    return _actions.action_props_remove_behaviour(w, arg)


def action_props_set_name(w: Any, arg: str | None) -> None:
    return _actions.action_props_set_name(w, arg)


def action_props_add_tag(w: Any, arg: str | None) -> None:
    return _actions.action_props_add_tag(w, arg)


def action_props_remove_tag(w: Any, arg: str | None) -> None:
    return _actions.action_props_remove_tag(w, arg)


def action_props_toggle_tag(w: Any, arg: str | None) -> None:
    return _actions.action_props_toggle_tag(w, arg)


def action_batch_rename(w: Any, arg: str | None) -> None:
    return _actions.action_batch_rename(w, arg)


def action_set_names(w: Any, arg: str | None) -> None:
    return _actions.action_set_names(w, arg)


_ALIGN_SIMPLE_MAP: dict[str, tuple[str, str]] = _defs._ALIGN_SIMPLE_MAP


def action_align_selection(w: Any, arg: str | None) -> None:
    return _actions.action_align_selection(w, arg)


_DISTRIBUTE_SIMPLE_MAP: dict[str, tuple[str, str]] = _defs._DISTRIBUTE_SIMPLE_MAP


def action_distribute_selection(w: Any, arg: str | None) -> None:
    return _actions.action_distribute_selection(w, arg)


_SNAP_SIMPLE_MAP: dict[str, tuple[str, str]] = _defs._SNAP_SIMPLE_MAP


def action_snap_to_grid(w: Any, arg: str | None) -> None:
    return _actions.action_snap_to_grid(w, arg)


_NUDGE_DIR_MAP: dict[str, tuple[float, float]] = _defs._NUDGE_DIR_MAP


def action_nudge_selection(w: Any, arg: str | None) -> None:
    return _actions.action_nudge_selection(w, arg)


_ROTATE_SIMPLE_MAP: dict[str, float] = _defs._ROTATE_SIMPLE_MAP


def action_rotate_selection(w: Any, arg: str | None) -> None:
    return _actions.action_rotate_selection(w, arg)


def action_mirror_selection(w: Any, arg: str | None) -> None:
    return _actions.action_mirror_selection(w, arg)


# ---------------------------------------------------------------------------
# Selection group / ungroup
# ---------------------------------------------------------------------------

def action_group_selection(w: Any, arg: str | None) -> None:
    return _actions.action_group_selection(w, arg)


def action_ungroup_selection(w: Any, arg: str | None) -> None:
    return _actions.action_ungroup_selection(w, arg)


# ---------------------------------------------------------------------------
# Selection duplicate-to-grid
# ---------------------------------------------------------------------------

def action_duplicate_to_grid(w: Any, arg: str | None) -> None:
    return _actions.action_duplicate_to_grid(w, arg)


def action_duplicate_along_path(w: Any, arg: str | None) -> None:
    return _actions.action_duplicate_along_path(w, arg)


def action_scatter_selection(w: Any, arg: str | None) -> None:
    return _actions.action_scatter_selection(w, arg)


# ---------------------------------------------------------------------------
# Entity config actions (TriggerZone, SetGameStateOnEvent, SceneTransition)
# ---------------------------------------------------------------------------

def action_config_tz_set_zone_id(w: Any, arg: str | None) -> None:
    return _actions.action_config_tz_set_zone_id(w, arg)


def action_config_tz_set_radius(w: Any, arg: str | None) -> None:
    return _actions.action_config_tz_set_radius(w, arg)


def _parse_toast_and_seconds(arg: str | None) -> tuple[str, float | None] | None:
    """Parse 'toast[|seconds]' format."""
    return _parse.parse_toast_and_seconds(arg, parse_float=_parse_float)


def _parse_align_args(arg: str | None) -> dict[str, Any]:
    """Parse align action args."""
    return _parse.parse_align_args(arg, simple_map=_ALIGN_SIMPLE_MAP)


def _parse_distribute_args(arg: str | None) -> dict[str, Any]:
    """Parse distribute action args."""
    return _parse.parse_distribute_args(arg, simple_map=_DISTRIBUTE_SIMPLE_MAP)


def _parse_snap_args(arg: str | None) -> dict[str, Any]:
    """Parse snap action args."""
    return _parse.parse_snap_args(arg, simple_map=_SNAP_SIMPLE_MAP)


def _parse_nudge_args(arg: str | None) -> dict[str, Any]:
    """Parse nudge action args."""
    return _parse.parse_nudge_args(arg, direction_map=_NUDGE_DIR_MAP)


def _parse_rotate_args(arg: str | None) -> dict[str, Any]:
    """Parse rotate action args."""
    return _parse.parse_rotate_args(arg, simple_map=_ROTATE_SIMPLE_MAP)


def _parse_planes_toggle_repeat_args(arg: str | None) -> dict[str, Any]:
    """Parse planes toggle repeat args."""
    return _parse.parse_planes_toggle_repeat_args(arg, axis_map=_PLANES_TOGGLE_REPEAT_MAP)


def _parse_planes_select_args(arg: str | None) -> dict[str, Any]:
    """Parse planes select args."""
    return _parse.parse_planes_select_args(arg, mode_map=_PLANES_SELECT_MAP)


def _parse_planes_move_to_args(arg: str | None) -> dict[str, Any]:
    """Parse planes move-to args."""
    return _parse.parse_planes_move_to_args(arg, mode_map=_PLANES_MOVE_TO_MAP)


def action_config_sgs_set_toast(w: Any, arg: str | None) -> None:
    return _actions.action_config_sgs_set_toast(w, arg)


def action_config_sgs_add_require_flag(w: Any, arg: str | None) -> None:
    return _actions.action_config_sgs_add_require_flag(w, arg)


def action_config_sgs_add_forbid_flag(w: Any, arg: str | None) -> None:
    return _actions.action_config_sgs_add_forbid_flag(w, arg)


def action_config_sgs_set_flag_true(w: Any, arg: str | None) -> None:
    return _actions.action_config_sgs_set_flag_true(w, arg)


def action_config_st_set_target_scene(w: Any, arg: str | None) -> None:
    return _actions.action_config_st_set_target_scene(w, arg)


def action_config_st_set_spawn_id(w: Any, arg: str | None) -> None:
    return _actions.action_config_st_set_spawn_id(w, arg)


# ---------------------------------------------------------------------------
# Macro helpers
# ---------------------------------------------------------------------------

def _get_player_pos_from_authored(w: Any) -> tuple[float, float] | None:
    """Get player position from authored payload."""
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
        except Exception:  # noqa: BLE001  # REASON: command palette registry fallback isolation
            _log_swallow("CPRG-001", "engine/command_palette_registry.py blanket swallow", once=True)
            x = 0.0
        try:
            y = float(ent.get("y", 0.0))
        except Exception:  # noqa: BLE001  # REASON: command palette registry fallback isolation
            _log_swallow("CPRG-002", "engine/command_palette_registry.py blanket swallow", once=True)
            y = 0.0
        return float(x), float(y)
    return None


def _get_entity_pos_from_authored(w: Any, entity_id: str) -> tuple[float, float] | None:
    """Get entity position from authored payload by ID."""
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
    except Exception:  # noqa: BLE001  # REASON: command palette registry fallback isolation
        _log_swallow("CPRG-003", "engine/command_palette_registry.py blanket swallow", once=True)
        x = 0.0
    try:
        y = float(ent.get("y", 0.0))
    except Exception:  # noqa: BLE001  # REASON: command palette registry fallback isolation
        _log_swallow("CPRG-004", "engine/command_palette_registry.py blanket swallow", once=True)
        y = 0.0
    return float(x), float(y)


def _get_cursor_world_pos(w: Any) -> tuple[float, float] | None:
    """Get cursor position in world coordinates."""
    input_ctrl = getattr(w, "input_controller", None)
    mx = getattr(input_ctrl, "mouse_x", None) if input_ctrl is not None else None
    my = getattr(input_ctrl, "mouse_y", None) if input_ctrl is not None else None
    to_world = getattr(w, "screen_to_world", None)
    if callable(to_world) and isinstance(mx, (int, float)) and isinstance(my, (int, float)):
        try:
            result = to_world(float(mx), float(my))
            if isinstance(result, tuple) and len(result) >= 2:
                x, y = result[0], result[1]
            else:
                return None
        except Exception:  # noqa: BLE001  # REASON: command palette registry fallback isolation
            _log_swallow("CPRG-005", "engine/command_palette_registry.py blanket swallow", once=True)
            return None
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            return float(x), float(y)
    return None


def _resolve_macro_anchor_pos(w: Any, anchor: str) -> tuple[tuple[float, float] | None, str]:
    """Resolve anchor position for macros."""
    a = str(anchor or "").strip().lower()
    if a == "primary":
        selected_ids, primary_id = _get_selection_ids_and_primary(w)
        if not selected_ids or not primary_id:
            return None, "no_selection"
        pos = _get_entity_pos_from_authored(w, primary_id)
        if pos is None:
            return None, "no_selection"
        return pos, ""
    if a == "player":
        pos = _get_player_pos_from_authored(w)
        if pos is None:
            return (0.0, 0.0), ""
        return pos, ""
    # Default: cursor (fallback to player).
    pos = _get_cursor_world_pos(w)
    if pos is not None:
        return pos, ""
    pos = _get_player_pos_from_authored(w)
    if pos is None:
        return (0.0, 0.0), ""
    return pos, ""


# ---------------------------------------------------------------------------
# Macro actions
# ---------------------------------------------------------------------------

def action_macro_objective_zone(w: Any, arg: str | None) -> None:
    return _actions.action_macro_objective_zone(w, arg)


def action_macro_door_transition(w: Any, arg: str | None) -> None:
    return _actions.action_macro_door_transition(w, arg)


def action_macro_dialogue_choice_flag(w: Any, arg: str | None) -> None:
    return _actions.action_macro_dialogue_choice_flag(w, arg)


# ---------------------------------------------------------------------------
# Macro runners registry (used by macro asset commands)
# ---------------------------------------------------------------------------

MACRO_RUNNERS: dict[str, Callable[[Any, str | None], None]] = {
    _defs.MACRO_RUNNER_COMMAND_IDS[0]: action_macro_objective_zone,
    _defs.MACRO_RUNNER_COMMAND_IDS[1]: action_macro_door_transition,
    _defs.MACRO_RUNNER_COMMAND_IDS[2]: action_macro_dialogue_choice_flag,
}
