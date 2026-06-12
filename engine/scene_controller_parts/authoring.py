# mypy: ignore-errors
from __future__ import annotations

import time
from typing import Any, Callable, Dict

from engine.paths import resolve_path


def _call_authoring(self, fn_name: str, *args: Any, authoring_runtime: Any, **kwargs: Any) -> Any:
    """Dispatch to ``engine.scene_runtime.authoring.<fn_name>(self, *args, **kwargs)``."""
    fn = getattr(authoring_runtime, fn_name)
    if not self._authoring_trace_enabled:
        return fn(self, *args, **kwargs)
    start = time.perf_counter()
    try:
        return fn(self, *args, **kwargs)
    except Exception as exc:
        entry = self._authoring_trace_data.get(fn_name)
        if entry is not None:
            entry["last_err"] = f"{type(exc).__name__}:{str(exc)[:120]}"
        else:
            self._authoring_trace_data[fn_name] = {
                "count": 0,
                "total_ms": 0,
                "last_err": f"{type(exc).__name__}:{str(exc)[:120]}",
            }
        raise
    finally:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        entry = self._authoring_trace_data.get(fn_name)
        if entry is not None:
            entry["count"] += 1
            entry["total_ms"] += elapsed_ms
        else:
            self._authoring_trace_data[fn_name] = {
                "count": 1,
                "total_ms": elapsed_ms,
                "last_err": None,
            }


def enable_authoring_trace(self, enabled: bool) -> None:
    """Enable or disable per-function tracing for authoring proxy calls."""
    self._authoring_trace_enabled = bool(enabled)
    if enabled and not isinstance(self.__dict__.get("_authoring_trace_data"), dict):
        self._authoring_trace_data = {}


def reset_authoring_trace(self) -> None:
    """Clear all accumulated trace data."""
    self._authoring_trace_data = {}


def get_authoring_trace_snapshot(self, limit: int = 20) -> dict[str, Any]:
    """Return a snapshot of authoring proxy trace stats."""
    data = self._authoring_trace_data
    total_calls = sum(e["count"] for e in data.values())
    items: list[dict[str, Any]] = []
    for name, entry in data.items():
        count = entry["count"]
        total_ms = entry["total_ms"]
        items.append({
            "name": name,
            "count": count,
            "total_ms": total_ms,
            "avg_ms": total_ms // count if count else 0,
            "last_err": entry["last_err"],
        })
    items.sort(key=lambda it: (-it["total_ms"], it["name"]))
    return {
        "schema_version": 1,
        "enabled": self._authoring_trace_enabled,
        "total_calls": total_calls,
        "functions": items[:limit],
    }


def refresh_tilemap_layers(self) -> bool:
    """Debug-only: rebuild tilemap sprite layers from the current loaded scene payload."""
    scene_path = str(self.current_scene_path or "").strip()
    if not scene_path:
        return False
    scene = self._loaded_scene_data
    if not isinstance(scene, dict):
        return False
    tilemap = scene.get("tilemap")
    if not isinstance(tilemap, dict) or "tile_layers" not in tilemap:
        return False
    scene_file = resolve_path(scene_path)
    self._clear_tilemap_layers()
    self._load_tilemap_layers(scene, scene_file.parent)
    return True


def debug_find_sprite_by_entity_id(self, entity_id: str) -> Any:
    return self._call_authoring("debug_find_sprite_by_entity_id", entity_id)


def _debug_iter_authoring_payloads(self) -> list[Dict[str, Any]]:
    return self._call_authoring("_debug_iter_authoring_payloads")


def _debug_remove_sprite(self, sprite: Any) -> None:
    self._call_authoring("_debug_remove_sprite", sprite)


def debug_add_entity_payload(self, entity_payload: Dict[str, Any]) -> bool:
    return self._call_authoring("debug_add_entity_payload", entity_payload)


def debug_remove_entity_by_id(self, entity_id: str) -> bool:
    return self._call_authoring("debug_remove_entity_by_id", entity_id)


def debug_move_entity_by_id(self, entity_id: str, *, x: float, y: float) -> bool:
    return self._call_authoring("debug_move_entity_by_id", entity_id, x=x, y=y)


def debug_duplicate_entities_by_ids(self, ids: list[str], *, dx: float, dy: float) -> dict[str, str]:
    return self._call_authoring("debug_duplicate_entities_by_ids", ids, dx=dx, dy=dy)


def debug_copy_entities_by_ids(
    self,
    ids: list[str],
    *,
    primary_id: str | None = None,
) -> Dict[str, Any] | None:
    return self._call_authoring("debug_copy_entities_by_ids", ids, primary_id=primary_id)


def debug_paste_entities_from_clipboard(
    self,
    clipboard: Dict[str, Any],
    *,
    anchor_x: float,
    anchor_y: float,
    snap_to_tile: bool = False,
) -> tuple[list[str], str]:
    return self._call_authoring(
        "debug_paste_entities_from_clipboard",
        clipboard,
        anchor_x=anchor_x,
        anchor_y=anchor_y,
        snap_to_tile=snap_to_tile,
    )


def debug_transform_entities_by_ids(
    self,
    ids: list[str],
    *,
    op: str,
    snap_to_tile: bool = False,
) -> int:
    return self._call_authoring("debug_transform_entities_by_ids", ids, op=op, snap_to_tile=snap_to_tile)


def debug_set_prefab_id(self, selected_ids: list[str], prefab_id: str) -> tuple[int, int]:
    return self._call_authoring("debug_set_prefab_id", selected_ids, prefab_id)


def debug_add_behaviour(self, selected_ids: list[str], behaviour_name: str) -> tuple[int, int]:
    return self._call_authoring("debug_add_behaviour", selected_ids, behaviour_name)


def debug_remove_behaviour(self, selected_ids: list[str], behaviour_name: str) -> tuple[int, int]:
    return self._call_authoring("debug_remove_behaviour", selected_ids, behaviour_name)


def debug_set_name(self, primary_id: str, name: str) -> tuple[int, int]:
    return self._call_authoring("debug_set_name", primary_id, name)


def debug_add_tag(self, selected_ids: list[str], tag: str) -> tuple[int, int]:
    return self._call_authoring("debug_add_tag", selected_ids, tag)


def debug_remove_tag(self, selected_ids: list[str], tag: str) -> tuple[int, int]:
    return self._call_authoring("debug_remove_tag", selected_ids, tag)


def debug_toggle_tag(self, selected_ids: list[str], tag: str) -> tuple[int, int, int]:
    return self._call_authoring("debug_toggle_tag", selected_ids, tag)


def debug_batch_rename(self, selected_ids: list[str], prefix: str = "", suffix: str = "") -> tuple[int, int]:
    return self._call_authoring("debug_batch_rename", selected_ids, prefix=prefix, suffix=suffix)


def debug_set_names(self, entity_ids: list[str], base: str, start: int = 1, width: int = 3) -> dict:
    return self._call_authoring("debug_set_names", entity_ids, base, start=start, width=width)


def debug_config_triggerzone_set_zone_id(self, selected_ids: list[str], zone_id: str) -> tuple[int, int, int]:
    return self._call_authoring("debug_config_triggerzone_set_zone_id", selected_ids, zone_id)


def debug_config_triggerzone_set_radius(self, selected_ids: list[str], trigger_radius: float) -> tuple[int, int, int]:
    return self._call_authoring("debug_config_triggerzone_set_radius", selected_ids, trigger_radius)


def _debug_config_entity_has_behaviour(self, entity_payload: dict[str, Any], behaviour_name: str) -> bool:
    return self._call_authoring("_debug_config_entity_has_behaviour", entity_payload, behaviour_name)


def _debug_config_mutate_for_behaviour(
    self,
    selected_ids: list[str],
    *,
    behaviour_name: str,
    mutate: Callable[[dict[str, Any]], bool],
) -> tuple[int, int, int]:
    return self._call_authoring(
        "_debug_config_mutate_for_behaviour",
        selected_ids,
        behaviour_name=behaviour_name,
        mutate=mutate,
    )


def _debug_config_set_field_for_behaviour(
    self,
    selected_ids: list[str],
    *,
    behaviour_name: str,
    field_path: tuple[str, ...],
    value: Any,
) -> tuple[int, int, int]:
    return self._call_authoring(
        "_debug_config_set_field_for_behaviour",
        selected_ids,
        behaviour_name=behaviour_name,
        field_path=field_path,
        value=value,
    )


def debug_build_macro_objective_zone_payload(
    self,
    *,
    center_x: float,
    center_y: float,
    zone_id: str,
    set_flag: str,
    radius: float,
    toast: str | None,
    require_flags: list[str] | None = None,
    forbid_flags: list[str] | None = None,
    toast_seconds: float | None = None,
) -> tuple[Dict[str, Any], int, int]:
    return self._call_authoring(
        "debug_build_macro_objective_zone_payload",
        center_x=center_x,
        center_y=center_y,
        zone_id=zone_id,
        set_flag=set_flag,
        radius=radius,
        toast=toast,
        require_flags=require_flags,
        forbid_flags=forbid_flags,
        toast_seconds=toast_seconds,
    )


def debug_build_macro_door_transition_payload(
    self,
    *,
    center_x: float,
    center_y: float,
    target_scene: str,
    spawn_id: str,
    primary_id: str | None,
    require_flags: list[str] | None = None,
    forbid_flags: list[str] | None = None,
) -> tuple[Dict[str, Any], int, int]:
    return self._call_authoring(
        "debug_build_macro_door_transition_payload",
        center_x=center_x,
        center_y=center_y,
        target_scene=target_scene,
        spawn_id=spawn_id,
        primary_id=primary_id,
        require_flags=require_flags,
        forbid_flags=forbid_flags,
    )


def debug_build_macro_dialogue_choice_flag_payload(
    self,
    *,
    speaker_id: str,
    choice_id: str,
    choice_text: str,
    set_flag: str,
    toast: str | None,
) -> tuple[Dict[str, Any], int, int]:
    return self._call_authoring(
        "debug_build_macro_dialogue_choice_flag_payload",
        speaker_id=speaker_id,
        choice_id=choice_id,
        choice_text=choice_text,
        set_flag=set_flag,
        toast=toast,
    )


def _debug_preview_diff(self, before_payload: Dict[str, Any], after_payload: Dict[str, Any]) -> Dict[str, Any]:
    return self._call_authoring("_debug_preview_diff", before_payload, after_payload)


def debug_preview_macro_objective_zone(
    self,
    *,
    center_x: float,
    center_y: float,
    zone_id: str,
    set_flag: str,
    radius: float,
    toast: str | None,
    require_flags: list[str] | None = None,
    forbid_flags: list[str] | None = None,
    toast_seconds: float | None = None,
) -> Dict[str, Any]:
    return self._call_authoring(
        "debug_preview_macro_objective_zone",
        center_x=center_x,
        center_y=center_y,
        zone_id=zone_id,
        set_flag=set_flag,
        radius=radius,
        toast=toast,
        require_flags=require_flags,
        forbid_flags=forbid_flags,
        toast_seconds=toast_seconds,
    )


def debug_preview_macro_door_transition(
    self,
    *,
    center_x: float,
    center_y: float,
    target_scene: str,
    spawn_id: str,
    primary_id: str | None,
) -> Dict[str, Any]:
    return self._call_authoring(
        "debug_preview_macro_door_transition",
        center_x=center_x,
        center_y=center_y,
        target_scene=target_scene,
        spawn_id=spawn_id,
        primary_id=primary_id,
    )


def debug_preview_macro_dialogue_choice_flag(
    self,
    *,
    speaker_id: str,
    choice_id: str,
    choice_text: str,
    set_flag: str,
    toast: str | None,
) -> Dict[str, Any]:
    return self._call_authoring(
        "debug_preview_macro_dialogue_choice_flag",
        speaker_id=speaker_id,
        choice_id=choice_id,
        choice_text=choice_text,
        set_flag=set_flag,
        toast=toast,
    )


def bind_authoring_methods(cls, *, authoring_runtime: Any) -> None:
    cls._call_authoring = lambda self, fn_name, *args, **kwargs: _call_authoring(
        self,
        fn_name,
        *args,
        authoring_runtime=authoring_runtime,
        **kwargs,
    )
    cls.enable_authoring_trace = enable_authoring_trace
    cls.reset_authoring_trace = reset_authoring_trace
    cls.get_authoring_trace_snapshot = get_authoring_trace_snapshot
    cls.refresh_tilemap_layers = refresh_tilemap_layers
    cls.debug_find_sprite_by_entity_id = debug_find_sprite_by_entity_id
    cls._debug_iter_authoring_payloads = _debug_iter_authoring_payloads
    cls._debug_remove_sprite = _debug_remove_sprite
    cls.debug_add_entity_payload = debug_add_entity_payload
    cls.debug_remove_entity_by_id = debug_remove_entity_by_id
    cls.debug_move_entity_by_id = debug_move_entity_by_id
    cls.debug_duplicate_entities_by_ids = debug_duplicate_entities_by_ids
    cls.debug_copy_entities_by_ids = debug_copy_entities_by_ids
    cls.debug_paste_entities_from_clipboard = debug_paste_entities_from_clipboard
    cls.debug_transform_entities_by_ids = debug_transform_entities_by_ids
    cls.debug_set_prefab_id = debug_set_prefab_id
    cls.debug_add_behaviour = debug_add_behaviour
    cls.debug_remove_behaviour = debug_remove_behaviour
    cls.debug_set_name = debug_set_name
    cls.debug_add_tag = debug_add_tag
    cls.debug_remove_tag = debug_remove_tag
    cls.debug_toggle_tag = debug_toggle_tag
    cls.debug_batch_rename = debug_batch_rename
    cls.debug_set_names = debug_set_names
    cls.debug_config_triggerzone_set_zone_id = debug_config_triggerzone_set_zone_id
    cls.debug_config_triggerzone_set_radius = debug_config_triggerzone_set_radius
    cls._debug_config_entity_has_behaviour = _debug_config_entity_has_behaviour
    cls._debug_config_mutate_for_behaviour = _debug_config_mutate_for_behaviour
    cls._debug_config_set_field_for_behaviour = _debug_config_set_field_for_behaviour
    cls.debug_build_macro_objective_zone_payload = debug_build_macro_objective_zone_payload
    cls.debug_build_macro_door_transition_payload = debug_build_macro_door_transition_payload
    cls.debug_build_macro_dialogue_choice_flag_payload = debug_build_macro_dialogue_choice_flag_payload
    cls._debug_preview_diff = _debug_preview_diff
    cls.debug_preview_macro_objective_zone = debug_preview_macro_objective_zone
    cls.debug_preview_macro_door_transition = debug_preview_macro_door_transition
    cls.debug_preview_macro_dialogue_choice_flag = debug_preview_macro_dialogue_choice_flag
