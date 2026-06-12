"""Command palette registry - extracted helper functions and command definitions.

This module contains the extracted helper functions and command definitions
that were previously nested inside build_default_commands(). The refactoring
reduces cyclomatic complexity while maintaining identical behavior.

The command definitions are stored in DEFAULT_COMMAND_DEFS as a deterministic
ordered list. Each definition is converted to a CommandSpec at runtime.
"""

# ruff: noqa: F401

from __future__ import annotations

from typing import Any, Callable

from . import command_palette_registry_actions as _actions
from . import command_palette_registry_defs as _defs
from . import command_palette_registry_options as _options
from . import command_palette_registry_parse_helpers as _parse_helpers
from . import command_palette_registry_support as _support
from .command_palette_registry_selection import (
    entity_has_behaviour as _entity_has_behaviour,
)
from .command_palette_registry_selection import (
    get_authored_payload as _get_authored_payload,
)
from .command_palette_registry_selection import (
    get_selection_ids_and_primary as _get_selection_ids_and_primary,
)
from .command_palette_registry_selection import (
    parse_float as _parse_float,
)

_list_prefab_ids_from_assets_cached = _options._list_prefab_ids_from_assets_cached
_list_behaviour_names_cached = _options._list_behaviour_names_cached


enabled_always = _support.enabled_always
enabled_has_scene = _support.enabled_has_scene
enabled_has_scene_and_authored_payload = _support.enabled_has_scene_and_authored_payload
enabled_scene_persist_armed = _support.enabled_scene_persist_armed
enabled_persist_armed_only = _support.enabled_persist_armed_only
enabled_scene_index_nonempty = _support.enabled_scene_index_nonempty
enabled_recent_nonempty = _support.enabled_recent_nonempty
enabled_selection_has_non_player = _support.enabled_selection_has_non_player
enabled_selection_has_primary_non_player = _support.enabled_selection_has_primary_non_player

# ---------------------------------------------------------------------------
# Options providers - functions returning [(value, label), ...]
# ---------------------------------------------------------------------------

options_all_scenes = _options.options_all_scenes
options_recent_scenes = _options.options_recent_scenes
options_prefab_ids = _options.options_prefab_ids
options_behaviour_names = _options.options_behaviour_names
options_behaviours_in_selection = _options.options_behaviours_in_selection
options_scene_paths = _options.options_scene_paths
options_dialogue_speakers = _options.options_dialogue_speakers
options_macro_anchor = _options.options_macro_anchor


default_empty = _support.default_empty
default_save_as = _support.default_save_as
default_scene_create = _support.default_scene_create
default_cursor = _support.default_cursor
default_radius_72 = _support.default_radius_72


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


_set_last_props_action = _support._set_last_props_action
_set_last_config_action = _support._set_last_config_action


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


def action_align_selection(w: Any, arg: str | None) -> None:
    return _actions.action_align_selection(w, arg)

def action_distribute_selection(w: Any, arg: str | None) -> None:
    return _actions.action_distribute_selection(w, arg)

def action_snap_to_grid(w: Any, arg: str | None) -> None:
    return _actions.action_snap_to_grid(w, arg)

def action_nudge_selection(w: Any, arg: str | None) -> None:
    return _actions.action_nudge_selection(w, arg)

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


_parse_toast_and_seconds = _parse_helpers._parse_toast_and_seconds
_parse_align_args = _parse_helpers._parse_align_args
_parse_distribute_args = _parse_helpers._parse_distribute_args
_parse_snap_args = _parse_helpers._parse_snap_args
_parse_nudge_args = _parse_helpers._parse_nudge_args
_parse_rotate_args = _parse_helpers._parse_rotate_args
_parse_planes_toggle_repeat_args = _parse_helpers._parse_planes_toggle_repeat_args
_parse_planes_select_args = _parse_helpers._parse_planes_select_args
_parse_planes_move_to_args = _parse_helpers._parse_planes_move_to_args


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


_get_player_pos_from_authored = _support._get_player_pos_from_authored
_get_entity_pos_from_authored = _support._get_entity_pos_from_authored
_get_cursor_world_pos = _support._get_cursor_world_pos
_resolve_macro_anchor_pos = _support._resolve_macro_anchor_pos


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
