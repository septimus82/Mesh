"""Binder: Entity Panels, Inspector & Prefab delegation shims.

Extracted from ``engine.editor_controller`` to reduce god-class bloat.
Every function takes ``self`` (an ``EditorModeController``) as first arg.
``bind_entity_panels_bridge_methods`` monkey-patches them onto the class.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

import engine.optional_arcade as optional_arcade

if TYPE_CHECKING:
    from arcade import Sprite
    from engine.editor_controller import EditorModeController
    from engine.editor_entity_ops import EntitySummary
    from engine.editor_prefab_variant_ops import DiffRow


# -- Lights tool shims ------------------------------------------------------

def _hit_test_light(self: "EditorModeController", world_x: float, world_y: float, pick_radius: float = 16.0) -> "Optional[int]":
    return self.lights.hit_test_light(world_x, world_y, pick_radius=pick_radius)


def _add_light(self: "EditorModeController", x: float, y: float) -> None:
    self.lights.add_light(x, y)


def _delete_selected_light(self: "EditorModeController") -> None:
    self.lights.delete_selected_light()


def _draw_lights_overlay(self: "EditorModeController") -> None:
    self.lights.draw_lights_overlay()


# -- Inspector shims -------------------------------------------------------

def _update_param(self: "EditorModeController", behaviour_name: str, param_name: str, value: Any) -> None:
    self.inspector.update_param(behaviour_name, param_name, value)


def _update_param_internal(self: "EditorModeController", behaviour_name: str, param_name: str, value: Any, entity_name: str) -> None:
    self.inspector.update_param_internal(behaviour_name, param_name, value, entity_name)


def _remove_param_internal(self: "EditorModeController", behaviour_name: str, param_name: str, entity_name: str) -> None:
    self.inspector.remove_param_internal(behaviour_name, param_name, entity_name)


def _apply_behaviour_config_map(self: "EditorModeController", entity: "Sprite", config_map: dict[str, Any]) -> None:
    self.inspector.apply_behaviour_config_map(entity, config_map)


def _get_prefab_base_entity(self: "EditorModeController", entity_data: dict[str, Any]) -> dict[str, Any] | None:
    return self.inspector.get_prefab_base_entity(entity_data)


def _refresh_inspector_items(self: "EditorModeController") -> None:
    self.inspector.refresh_inspector_items()


def _get_inspector_items(self: "EditorModeController") -> List[Dict[str, Any]]:
    return self.inspector.get_inspector_items()


def _build_inspector_items(self: "EditorModeController") -> List[Dict[str, Any]]:
    return self.inspector.build_inspector_items()


def _get_selected_entity_json_for_inspector(self: "EditorModeController") -> dict[str, Any] | None:
    return self.inspector.get_selected_entity_json_for_inspector()


def _inspector_begin_text_edit(self: "EditorModeController", initial: str) -> None:
    self.inspector.inspector_begin_text_edit(initial)


def _inspector_cancel_text_edit(self: "EditorModeController") -> None:
    self.inspector.inspector_cancel_text_edit()


def _inspector_commit_text_edit(self: "EditorModeController") -> bool:
    return self.inspector.inspector_commit_text_edit()


def _apply_inspector_entity_update(self: "EditorModeController", new_entity_json: dict[str, Any], field_key: str) -> None:
    self.inspector.apply_inspector_entity_update(new_entity_json, field_key)


def _get_entity_id_for_inspector(self: "EditorModeController") -> str | None:
    return self.inspector.get_entity_id_for_inspector()


def _apply_inspector_to_sprite(self: "EditorModeController", field_key: str, value: Any) -> None:
    self.inspector.apply_inspector_to_sprite(field_key, value)


def _component_inspector_commit_text_edit(
    self: "EditorModeController", entity_json: Dict[str, Any], selection: Optional[Dict[str, Any]]
) -> bool:
    return self.inspector.component_inspector_commit_text_edit(entity_json, selection)


def _apply_component_entity_update(self: "EditorModeController", new_entity_json: Dict[str, Any]) -> None:
    self.inspector.apply_component_entity_update(new_entity_json)


def _sync_sprite_from_component_json(self: "EditorModeController", entity_json: Dict[str, Any]) -> None:
    """Sync runtime sprite state from component JSON."""
    if not self.selected_entity:
        return

    sprite = self.selected_entity

    # Get transform from components or legacy
    components = entity_json.get("components", {})
    transform = components.get("transform", {})

    # Fall back to top-level if not in components
    x = transform.get("x") if "x" in transform else entity_json.get("x")
    y = transform.get("y") if "y" in transform else entity_json.get("y")
    rot = transform.get("rot") if "rot" in transform else entity_json.get("rotation", 0.0)

    if x is not None:
        self.window.scene_controller._apply_entity_mutation(sprite, x=float(x))
    if y is not None:
        self.window.scene_controller._apply_entity_mutation(sprite, y=float(y))
    if rot is not None:
        sprite.angle = float(rot) % 360.0
        entity_data = getattr(sprite, "mesh_entity_data", {})
        if isinstance(entity_data, dict):
            entity_data["rotation"] = float(rot) % 360.0


# -- Prefab shims -----------------------------------------------------------

def _prefab_override_info(
    self: "EditorModeController", entity_data: dict[str, Any]
) -> tuple[dict[str, Any] | None, set[str]]:
    return self.prefab.prefab_override_info(entity_data)


def _reset_selected_prefab_override(self: "EditorModeController", selected_item: dict[str, Any]) -> bool:
    return self.prefab.reset_selected_prefab_override(selected_item)


def _reset_all_prefab_overrides(self: "EditorModeController") -> bool:
    return self.prefab.reset_all_prefab_overrides()


def _prefab_variant_label(self: "EditorModeController", entity_data: dict[str, Any]) -> str | None:
    return self.prefab.prefab_variant_label(entity_data)


def _prefab_variant_override_rows(self: "EditorModeController", entity_data: dict[str, Any]) -> "list[DiffRow]":
    return self.prefab.prefab_variant_override_rows(entity_data)


def _entity_panels_prefab_override_rows(self: "EditorModeController") -> "list[DiffRow]":
    return self.prefab.entity_panels_prefab_override_rows()


def _prefab_override_base_value(self: "EditorModeController", base_entity: dict[str, Any], key: str) -> tuple[bool, Any]:
    return self.prefab.prefab_override_base_value(base_entity, key)


def _apply_prefab_override_payload(self: "EditorModeController", entity_data: dict[str, Any], updated: dict[str, Any]) -> None:
    self.prefab.apply_prefab_override_payload(entity_data, updated)


def _apply_prefab_override_entity_value(
    self: "EditorModeController",
    sprite: "Sprite",
    key: str,
    value: Any,
    *,
    present: bool,
) -> None:
    self.prefab.apply_prefab_override_entity_value(sprite, key, value, present=present)


def _apply_prefab_override_command(self: "EditorModeController", cmd: Dict[str, Any], *, use_before: bool) -> None:
    self.prefab.apply_prefab_override_command(cmd, use_before=use_before)


def _apply_prefab_override_bulk_command(self: "EditorModeController", cmd: Dict[str, Any], *, use_before: bool) -> None:
    self.prefab.apply_prefab_override_bulk_command(cmd, use_before=use_before)


def _entity_panels_apply_prefab_override(self: "EditorModeController", key: str, value: Any) -> bool:
    return self.prefab.entity_panels_apply_prefab_override(key, value)


def _entity_panels_revert_prefab_override(self: "EditorModeController", row: "DiffRow") -> bool:
    return self.prefab.entity_panels_revert_prefab_override(row)


def _entity_panels_clear_prefab_overrides(self: "EditorModeController") -> bool:
    return self.prefab.entity_panels_clear_prefab_overrides()


# -- Entity Panels Controller shims ----------------------------------------

def _entity_panels_scene_data(self: "EditorModeController") -> Dict[str, Any]:
    return self.entity_panels_controller.entity_panels_scene_data()


def _resolve_entity_panels_id(self: "EditorModeController", entity: Dict[str, Any], fallback_index: Optional[int] = None) -> str:
    return self.entity_panels_controller.resolve_entity_panels_id(entity, fallback_index)


def _entity_panels_selected_id_value(self: "EditorModeController") -> str | None:
    return self.entity_panels_controller.entity_panels_selected_id_value()


def _filter_entity_panels_items(self: "EditorModeController", items: "list[EntitySummary]") -> "list[EntitySummary]":
    return self.entity_panels_controller.filter_entity_panels_items(items)


def _refresh_entity_panels_list(self: "EditorModeController", *, sync_selected: bool = False) -> None:
    self.entity_panels_controller.refresh_entity_panels_list(sync_selected=sync_selected)


def _get_entity_panels_list(self: "EditorModeController") -> "list[EntitySummary]":
    return self.entity_panels_controller.get_entity_panels_list()


def _resolve_display_name(self: "EditorModeController", sprite: "Sprite", fallback_index: Optional[int] = None) -> str:
    return self.entity_panels_controller.resolve_display_name(sprite, fallback_index)


def _get_sprite_index(self: "EditorModeController", sprite: "Sprite") -> Optional[int]:
    return self.entity_panels_controller.get_sprite_index(sprite)


def _get_display_name_for_sprite(self: "EditorModeController", sprite: "Sprite") -> str:
    return self.entity_panels_controller.get_display_name_for_sprite(sprite)


def _entity_panels_outliner_lines(self: "EditorModeController") -> list[str]:
    return self.entity_panels_controller.entity_panels_outliner_lines()


def _entity_panels_inspector_lines(self: "EditorModeController") -> list[str]:
    return self.entity_panels_controller.entity_panels_inspector_lines()


def _entity_panels_format_field_value(
    self: "EditorModeController",
    entity_data: Dict[str, Any],
    sprite: "Sprite",
    key: str,
    kind: str,
) -> str:
    return self.entity_panels_controller.entity_panels_format_field_value(entity_data, sprite, key, kind)


def _entity_panels_numeric_value(
    self: "EditorModeController",
    entity_data: Dict[str, Any],
    sprite: "Sprite",
    key: str,
) -> float:
    return self.entity_panels_controller.entity_panels_numeric_value(entity_data, sprite, key)


def _entity_panels_select_current(self: "EditorModeController") -> bool:
    return self.entity_panels_controller.entity_panels_select_current()


def _entity_panels_find_sprite(self: "EditorModeController", summary: "EntitySummary") -> "Optional[Sprite]":
    return self.entity_panels_controller.entity_panels_find_sprite(summary)


def _entity_panels_begin_text_edit(self: "EditorModeController", field: str, initial: str) -> None:
    self.entity_panels_controller.entity_panels_begin_text_edit(field, initial)


def _entity_panels_cancel_text_edit(self: "EditorModeController") -> None:
    self.entity_panels_controller.entity_panels_cancel_text_edit()


def _entity_panels_commit_text_edit(self: "EditorModeController") -> bool:
    return self.entity_panels_controller.entity_panels_commit_text_edit()


def _entity_panels_apply_field_update(self: "EditorModeController", field: str, value: Any) -> bool:
    return self.entity_panels_controller.entity_panels_apply_field_update(field, value)


# ---------------------------------------------------------------------------
# Binder
# ---------------------------------------------------------------------------

def bind_entity_panels_bridge_methods(cls: Any) -> None:
    # Lights tool
    cls._hit_test_light = _hit_test_light
    cls._add_light = _add_light
    cls._delete_selected_light = _delete_selected_light
    cls._draw_lights_overlay = _draw_lights_overlay
    # Inspector
    cls._update_param = _update_param
    cls._update_param_internal = _update_param_internal
    cls._remove_param_internal = _remove_param_internal
    cls._apply_behaviour_config_map = _apply_behaviour_config_map
    cls._get_prefab_base_entity = _get_prefab_base_entity
    cls._refresh_inspector_items = _refresh_inspector_items
    cls._get_inspector_items = _get_inspector_items
    cls._build_inspector_items = _build_inspector_items
    cls._get_selected_entity_json_for_inspector = _get_selected_entity_json_for_inspector
    cls._inspector_begin_text_edit = _inspector_begin_text_edit
    cls._inspector_cancel_text_edit = _inspector_cancel_text_edit
    cls._inspector_commit_text_edit = _inspector_commit_text_edit
    cls._apply_inspector_entity_update = _apply_inspector_entity_update
    cls._get_entity_id_for_inspector = _get_entity_id_for_inspector
    cls._apply_inspector_to_sprite = _apply_inspector_to_sprite
    cls._component_inspector_commit_text_edit = _component_inspector_commit_text_edit
    cls._apply_component_entity_update = _apply_component_entity_update
    cls._sync_sprite_from_component_json = _sync_sprite_from_component_json
    # Prefab
    cls._prefab_override_info = _prefab_override_info
    cls._reset_selected_prefab_override = _reset_selected_prefab_override
    cls._reset_all_prefab_overrides = _reset_all_prefab_overrides
    cls._prefab_variant_label = _prefab_variant_label
    cls._prefab_variant_override_rows = _prefab_variant_override_rows
    cls._entity_panels_prefab_override_rows = _entity_panels_prefab_override_rows
    cls._prefab_override_base_value = _prefab_override_base_value
    cls._apply_prefab_override_payload = _apply_prefab_override_payload
    cls._apply_prefab_override_entity_value = _apply_prefab_override_entity_value
    cls._apply_prefab_override_command = _apply_prefab_override_command
    cls._apply_prefab_override_bulk_command = _apply_prefab_override_bulk_command
    cls._entity_panels_apply_prefab_override = _entity_panels_apply_prefab_override
    cls._entity_panels_revert_prefab_override = _entity_panels_revert_prefab_override
    cls._entity_panels_clear_prefab_overrides = _entity_panels_clear_prefab_overrides
    # Entity Panels Controller
    cls._entity_panels_scene_data = _entity_panels_scene_data
    cls._resolve_entity_panels_id = _resolve_entity_panels_id
    cls._entity_panels_selected_id_value = _entity_panels_selected_id_value
    cls._filter_entity_panels_items = _filter_entity_panels_items
    cls._refresh_entity_panels_list = _refresh_entity_panels_list
    cls._get_entity_panels_list = _get_entity_panels_list
    cls._resolve_display_name = _resolve_display_name
    cls._get_sprite_index = _get_sprite_index
    cls._get_display_name_for_sprite = _get_display_name_for_sprite
    cls._entity_panels_outliner_lines = _entity_panels_outliner_lines
    cls._entity_panels_inspector_lines = _entity_panels_inspector_lines
    cls._entity_panels_format_field_value = _entity_panels_format_field_value
    cls._entity_panels_numeric_value = _entity_panels_numeric_value
    cls._entity_panels_select_current = _entity_panels_select_current
    cls._entity_panels_find_sprite = _entity_panels_find_sprite
    cls._entity_panels_begin_text_edit = _entity_panels_begin_text_edit
    cls._entity_panels_cancel_text_edit = _entity_panels_cancel_text_edit
    cls._entity_panels_commit_text_edit = _entity_panels_commit_text_edit
    cls._entity_panels_apply_field_update = _entity_panels_apply_field_update
