from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from ..swallowed_exceptions import _log_swallow


def _registry() -> Any:
    from .. import command_palette_registry as registry  # noqa: PLC0415
    return registry


def _call_registry(name: str, *args: Any, **kwargs: Any) -> Any:
    fn = getattr(_registry(), name)
    return fn(*args, **kwargs)


def _get_authored_payload(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_get_authored_payload", *args, **kwargs)


def _get_selection_ids_and_primary(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_get_selection_ids_and_primary", *args, **kwargs)


def _list_prefab_ids_from_assets_cached(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_list_prefab_ids_from_assets_cached", *args, **kwargs)


def _list_behaviour_names_cached(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_list_behaviour_names_cached", *args, **kwargs)


def _set_last_props_action(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_set_last_props_action", *args, **kwargs)


def _set_last_config_action(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_set_last_config_action", *args, **kwargs)


def _parse_float(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_parse_float", *args, **kwargs)


def _parse_toast_and_seconds(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_parse_toast_and_seconds", *args, **kwargs)


def _parse_align_args(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_parse_align_args", *args, **kwargs)


def _parse_distribute_args(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_parse_distribute_args", *args, **kwargs)


def _parse_snap_args(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_parse_snap_args", *args, **kwargs)


def _parse_nudge_args(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_parse_nudge_args", *args, **kwargs)


def _parse_rotate_args(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_parse_rotate_args", *args, **kwargs)


def _parse_planes_toggle_repeat_args(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_parse_planes_toggle_repeat_args", *args, **kwargs)


def _parse_planes_select_args(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_parse_planes_select_args", *args, **kwargs)


def _parse_planes_move_to_args(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_parse_planes_move_to_args", *args, **kwargs)


def _get_player_pos_from_authored(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_get_player_pos_from_authored", *args, **kwargs)


def _get_entity_pos_from_authored(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_get_entity_pos_from_authored", *args, **kwargs)


def _get_cursor_world_pos(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_get_cursor_world_pos", *args, **kwargs)


def _resolve_macro_anchor_pos(*args: Any, **kwargs: Any) -> Any:
    return _call_registry("_resolve_macro_anchor_pos", *args, **kwargs)


def _run_editor_action(w: Any, action_id: str) -> bool:
    try:
        from engine.editor.editor_actions import run_editor_action  # noqa: PLC0415
    except Exception:
        _log_swallow(
            "CPRA-001",
            "engine.command_palette_registry_actions_impl._run_editor_action import_run_editor_action",
            once=False,
        )
        return False
    controller = getattr(w, "editor_controller", None)
    try:
        return bool(run_editor_action(action_id, controller, w))
    except Exception:
        _log_swallow(
            "CPRA-002",
            "engine.command_palette_registry_actions_impl._run_editor_action invoke_run_editor_action",
            once=False,
        )
        return False


def _set_selected_plane_id(w: Any, plane_id: str) -> bool:
    state = getattr(w, "background_plane_editor_state", None)
    if state is None:
        state = SimpleNamespace(selected_plane_id="")
        try:
            setattr(w, "background_plane_editor_state", state)
        except Exception:
            _log_swallow(
                "CPRA-003",
                "engine.command_palette_registry_actions_impl._set_selected_plane_id set_background_plane_editor_state",
                once=False,
            )
            return False
    try:
        state.selected_plane_id = str(plane_id or "").strip()
    except Exception:
        _log_swallow(
            "CPRA-004",
            "engine.command_palette_registry_actions_impl._set_selected_plane_id set_selected_plane_id",
            once=False,
        )
        return False
    return True
