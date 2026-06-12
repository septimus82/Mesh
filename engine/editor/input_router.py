# mypy: disable-error-code=no-any-return

from __future__ import annotations

from typing import Any, Optional

import engine.optional_arcade as optional_arcade
from engine.editor_light_occluder_ops import snap_world_point
from engine.editor_runtime import input as editor_input


def handle_mouse_click(self: Any, x: float, y: float, button: int, modifiers: int) -> bool:
    return editor_input.handle_mouse_click(self, x, y, button, modifiers)


def handle_input(self: Any, key: int, modifiers: int) -> bool:
    """Handle keyboard input when editor is active. Returns True if consumed."""
    panels = getattr(self, "panels", None)
    if panels is not None and panels.dispatch_input(key, modifiers):
        return True
    return editor_input.handle_input(self, key, modifiers)


def on_text(self: Any, text: str) -> bool:
    """Handle text input when editor is active. Returns True if consumed."""
    panels = getattr(self, "panels", None)
    if panels is not None and panels.dispatch_text(text):
        return True
    return False


def _cycle_tool_mode(self: Any) -> None:
    self.tool.cycle_tool_mode()


def _handle_palette_input(self: Any, key: int, modifiers: int) -> bool:
    return self.palette.handle_palette_input(key, modifiers)


def _handle_movement_input(self: Any, key: int, modifiers: int) -> bool:
    if not self.selected_entity:
        return False

    grid = self.grid_size
    dx, dy = 0.0, 0.0

    if key == optional_arcade.arcade.key.LEFT:
        dx = -grid
    elif key == optional_arcade.arcade.key.RIGHT:
        dx = grid
    elif key == optional_arcade.arcade.key.UP:
        dy = grid
    elif key == optional_arcade.arcade.key.DOWN:
        dy = -grid
    else:
        return False

    self.nudge_selected(dx, dy)
    return True


def _handle_inspector_input(self: Any, key: int, modifiers: int) -> bool:
    return self.inspector.handle_inspector_input(key, modifiers)


def _handle_dialogue_input(self: Any, key: int, modifiers: int) -> bool:
    return self.dialogue.handle_dialogue_input(key, modifiers)


def _handle_animation_input(self: Any, key: int, modifiers: int) -> bool:
    return self.animation.handle_animation_input(key, modifiers)


def _handle_tile_input(self: Any, key: int, modifiers: int) -> bool:
    return self.tile.handle_tile_input(key, modifiers)


def _handle_lights_mouse_press(self: Any, world_x: float, world_y: float) -> None:
    self.lights.handle_lights_mouse_press(world_x, world_y)


def _handle_lights_key_input(self: Any, key: int, modifiers: int) -> bool:
    return self.lights.handle_lights_key_input(key, modifiers)


def handle_mouse_drag(
    self: Any,
    x: float,
    y: float,
    dx: float,
    dy: float,
    buttons: int,
    modifiers: int,
) -> bool:
    return editor_input.handle_mouse_drag(self, x, y, dx, dy, buttons, modifiers)


def handle_mouse_release(self: Any, x: float, y: float, button: int, modifiers: int) -> bool:
    return editor_input.handle_mouse_release(self, x, y, button, modifiers)


def toggle_occluder_tool(self: Any) -> None:
    self.lights.toggle_occluder_tool()


def _toggle_occluder_mode(self: Any, enabled: bool) -> None:
    self.lights.toggle_occluder_mode(enabled)


def _handle_occluder_mouse_press(self: Any, world_x: float, world_y: float) -> None:
    self.lights.handle_occluder_mouse_press(world_x, world_y)


def _hit_test_occluder_vertex(
    self: Any,
    world_x: float,
    world_y: float,
    *,
    radius_px: float = 10.0,
) -> Optional[tuple[int, int]]:
    return self.lights.hit_test_occluder_vertex(world_x, world_y, radius_px=radius_px)


def _commit_occluder_polygon(self: Any) -> bool:
    return self.lights.commit_occluder_polygon()


def _remove_occluder_point(self: Any) -> bool:
    return self.lights.remove_occluder_point()


def _update_occluder_point(
    self: Any,
    world_x: float,
    world_y: float,
    *,
    push_command: bool = True,
) -> bool:
    return self.lights.update_occluder_point(world_x, world_y, push_command=push_command)


def _get_occluder_point(self: Any, occ_idx: int, pt_idx: int) -> Optional[tuple[float, float]]:
    return self.lights.get_occluder_point(occ_idx, pt_idx)


def _build_move_occluder_cmd(
    self: Any,
    occ_idx: int,
    pt_idx: int,
    start: tuple[float, float],
    end: tuple[float, float],
) -> Any | None:
    return self.lights.build_move_occluder_cmd(occ_idx, pt_idx, start, end)


def _snap_world_point(self: Any, world_x: float, world_y: float) -> tuple[float, float]:
    if not self.snap_enabled:
        return (float(world_x), float(world_y))
    tile_size = None
    instance = getattr(self.window.scene_controller, "tilemap_instance", None)
    if instance is not None:
        tile_size_value = getattr(instance, "tile_size", None)
        if isinstance(tile_size_value, tuple) and len(tile_size_value) >= 1:
            try:
                tile_size = int(tile_size_value[0])
            except Exception:  # noqa: BLE001  # REASON: invalid tile-size metadata should fall back to unsnapped world-space routing
                tile_size = None
    return snap_world_point((float(world_x), float(world_y)), self.snap_mode, tile_size)


def _delete_selected_occluder(self: Any) -> bool:
    return self.lights.delete_selected_occluder()


def _remove_selected_occluder_vertex(self: Any) -> bool:
    return self.lights.remove_selected_occluder_vertex()


def _handle_occluder_key_input(self: Any, key: int) -> bool:
    return self.lights.handle_occluder_key_input(key)


def _insert_occluder_point(self: Any, world_x: float, world_y: float) -> bool:
    return self.lights.insert_occluder_point(world_x, world_y)


def toggle_lights_tool(self: Any) -> None:
    self.lights.toggle_lights_tool()


def _toggle_lights_mode(self: Any, enabled: bool) -> None:
    self.lights.toggle_lights_mode(enabled)


def _handle_unsaved_confirm_input(self: Any, key: int, modifiers: int) -> bool:  # noqa: ARG002
    confirm = getattr(self, "unsaved_confirm", None)
    if confirm is None:
        return False
    return confirm.handle_input(key, modifiers)


def _handle_find_everything_input(self: Any, key: int, modifiers: int) -> bool:
    return self.search.handle_find_everything_input(key, modifiers)


def _handle_asset_browser_input(self: Any, key: int, modifiers: int) -> bool:
    return self.asset_browser.handle_asset_browser_input(key, modifiers)


def _handle_project_explorer_input(self: Any, key: int, modifiers: int) -> bool:
    return self.project_explorer_actions.handle_input(key, modifiers)


def _handle_history_input(self: Any, key: int, modifiers: int) -> bool:  # noqa: ARG002
    return self.history.handle_input(key, modifiers)


def _problems_input_blocked(self: Any) -> bool:
    return self.problems.input_blocked(self)


def _handle_problems_input(self: Any, key: int, modifiers: int) -> bool:
    return self.problems.handle_input(self, key, modifiers)


def _handle_context_menu_input(self: Any, key: int, modifiers: int) -> bool:
    from engine.editor.editor_panels_query import panels_is_open  # noqa: PLC0415

    if not panels_is_open(self, "project_context_menu"):
        return False
    return editor_input._handle_editor_action_shortcut(self, key, modifiers)


def handle_text_input(self: Any, text: str) -> None:
    editor_input.handle_text_input(self, text)


def _handle_inspector_component_input(self: Any, key: int, modifiers: int) -> bool:
    return self.inspector.handle_inspector_component_input(key, modifiers)


def _handle_inspector_text_input(self: Any, text: str) -> bool:
    return self.inspector.handle_inspector_text_input(text)


def _handle_component_inspector_v1_input(self: Any, key: int, modifiers: int) -> bool:
    return self.inspector.handle_component_inspector_v1_input(key, modifiers)


def _handle_add_component_picker_input(self: Any, key: int, entity_json: dict[str, Any]) -> bool:
    return self.inspector.handle_add_component_picker_input(key, entity_json)


def _handle_hierarchy_input(self: Any, key: int, modifiers: int) -> bool:
    return self.hierarchy.handle_hierarchy_input(key, modifiers)


def _handle_entity_panels_input(self: Any, key: int, modifiers: int) -> bool:
    return self.entity_panels_controller.handle_entity_panels_input(key, modifiers)


def _handle_scene_switcher_input(self: Any, key: int, modifiers: int) -> bool:  # noqa: ARG002
    return self.scene_browse.handle_scene_switcher_input(key, modifiers)


def _handle_scene_browser_input(self: Any, key: int, modifiers: int) -> bool:  # noqa: ARG002
    return self.scene_browse.handle_scene_browser_input(key, modifiers)


def _handle_entity_panels_text_input(self: Any, text: str) -> bool:
    return self.entity_panels_controller.handle_entity_panels_text_input(text)


def _handle_scene_switcher_text_input(self: Any, text: str) -> bool:
    return self.scene_browse.handle_scene_switcher_text_input(text)


def _handle_scene_browser_text_input(self: Any, text: str) -> bool:
    return self.scene_browse.handle_scene_browser_text_input(text)


def bind_input_router_methods(controller_cls: Any) -> None:
    method_map = {
        "handle_mouse_click": handle_mouse_click,
        "handle_input": handle_input,
        "on_text": on_text,
        "_cycle_tool_mode": _cycle_tool_mode,
        "_handle_palette_input": _handle_palette_input,
        "_handle_movement_input": _handle_movement_input,
        "_handle_inspector_input": _handle_inspector_input,
        "_handle_dialogue_input": _handle_dialogue_input,
        "_handle_animation_input": _handle_animation_input,
        "_handle_tile_input": _handle_tile_input,
        "_handle_lights_mouse_press": _handle_lights_mouse_press,
        "_handle_lights_key_input": _handle_lights_key_input,
        "handle_mouse_drag": handle_mouse_drag,
        "handle_mouse_release": handle_mouse_release,
        "toggle_occluder_tool": toggle_occluder_tool,
        "_toggle_occluder_mode": _toggle_occluder_mode,
        "_handle_occluder_mouse_press": _handle_occluder_mouse_press,
        "_hit_test_occluder_vertex": _hit_test_occluder_vertex,
        "_commit_occluder_polygon": _commit_occluder_polygon,
        "_remove_occluder_point": _remove_occluder_point,
        "_update_occluder_point": _update_occluder_point,
        "_get_occluder_point": _get_occluder_point,
        "_build_move_occluder_cmd": _build_move_occluder_cmd,
        "_snap_world_point": _snap_world_point,
        "_delete_selected_occluder": _delete_selected_occluder,
        "_remove_selected_occluder_vertex": _remove_selected_occluder_vertex,
        "_handle_occluder_key_input": _handle_occluder_key_input,
        "_insert_occluder_point": _insert_occluder_point,
        "toggle_lights_tool": toggle_lights_tool,
        "_toggle_lights_mode": _toggle_lights_mode,
        "_handle_unsaved_confirm_input": _handle_unsaved_confirm_input,
        "_handle_find_everything_input": _handle_find_everything_input,
        "_handle_asset_browser_input": _handle_asset_browser_input,
        "_handle_project_explorer_input": _handle_project_explorer_input,
        "_handle_history_input": _handle_history_input,
        "_problems_input_blocked": _problems_input_blocked,
        "_handle_problems_input": _handle_problems_input,
        "_handle_context_menu_input": _handle_context_menu_input,
        "handle_text_input": handle_text_input,
        "_handle_inspector_component_input": _handle_inspector_component_input,
        "_handle_inspector_text_input": _handle_inspector_text_input,
        "_handle_component_inspector_v1_input": _handle_component_inspector_v1_input,
        "_handle_add_component_picker_input": _handle_add_component_picker_input,
        "_handle_hierarchy_input": _handle_hierarchy_input,
        "_handle_entity_panels_input": _handle_entity_panels_input,
        "_handle_scene_switcher_input": _handle_scene_switcher_input,
        "_handle_scene_browser_input": _handle_scene_browser_input,
        "_handle_entity_panels_text_input": _handle_entity_panels_text_input,
        "_handle_scene_switcher_text_input": _handle_scene_switcher_text_input,
        "_handle_scene_browser_text_input": _handle_scene_browser_text_input,
    }
    for name, fn in method_map.items():
        setattr(controller_cls, name, fn)
