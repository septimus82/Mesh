"""Controller for editor world-space drawing (selection highlights, tool visuals, overlays).

This module extracts draw_world from EditorModeController for the Vertical Slice Diet V2.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Tuple

import engine.optional_arcade as optional_arcade
from engine.asset_place_overlay import draw_asset_placement_ghost
from engine.editor.state import (
    TOOL_MODE_PATH,
    TOOL_MODE_ZONE,
)
from engine.editor_light_occluder_ops import snap_world_point
from engine.ui_overlays.common import _draw_tb_rectangle_filled, draw_outline_centered

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController


def _draw_rectangle_filled(
    cx: float, cy: float, width: float, height: float, color: Tuple[int, ...]
) -> None:
    """Draw a filled rectangle (arcade shim)."""
    _draw_tb_rectangle_filled(
        left=cx - width / 2,
        right=cx + width / 2,
        top=cy + height / 2,
        bottom=cy - height / 2,
        color=color,
    )


class EditorDrawController:
    """Handles world-space drawing for the editor (selection, tools, overlays)."""

    def __init__(self, editor: EditorModeController) -> None:
        self._editor = editor

    @property
    def _window(self) -> Any:
        return self._editor.window

    def draw_world(self) -> None:
        """Draws in world space (camera active)."""
        editor = self._editor
        if not editor.active:
            return

        # Draw selection highlight
        if editor.selected_entity:
            color = (
                optional_arcade.arcade.color.NEON_GREEN
                if not editor.inspector_active
                else optional_arcade.arcade.color.CYAN
            )
            draw_outline_centered(
                editor.selected_entity.center_x,
                editor.selected_entity.center_y,
                editor.selected_entity.width,
                editor.selected_entity.height,
                color,
                2,
            )

            # Draw Tool Visuals
            self._draw_tool_visuals(editor)

            # Draw shape edit points
            self._draw_shape_edit_visuals(editor)

        # Draw lights overlay
        overlay = getattr(self._window, "light_occluder_overlay", None)
        if overlay is not None and callable(getattr(overlay, "draw_world", None)):
            overlay.draw_world()
        else:
            editor._draw_lights_overlay()

        # Draw Asset Placement Ghost
        if editor.asset_place_active and editor.asset_place_path:
            mx = getattr(self._window, "_mouse_x", 0)
            my = getattr(self._window, "_mouse_y", 0)
            wx, wy = self._window.screen_to_world(mx, my)

            if editor.snap_enabled:
                wx, wy = snap_world_point((wx, wy), editor.snap_mode, editor.grid_size)

            draw_asset_placement_ghost(editor.asset_place_path, wx, wy)

        self._draw_editor_collision_tile_overlay(editor)

        # Draw Palette Preview
        editor.palette.draw_palette_preview()

    def _draw_tool_visuals(self, editor: EditorModeController) -> None:
        """Draw tool-specific visuals (patrol path, zone/hitbox shapes)."""
        if editor.tool_mode == TOOL_MODE_PATH:
            self._draw_patrol_path_visuals(editor)
        elif editor.tool_mode == TOOL_MODE_ZONE:
            self._draw_zone_visuals(editor)

    def _draw_patrol_path_visuals(self, editor: EditorModeController) -> None:
        """Draw patrol path waypoints and lines."""
        patrol = editor._get_patrol_behaviour(editor.selected_entity)
        if not patrol:
            return
        points = editor._get_patrol_points(patrol)
        if not points:
            return

        # Draw lines connecting points
        if len(points) > 1:
            optional_arcade.arcade.draw_line_strip(
                points, optional_arcade.arcade.color.CYAN, 2
            )

        # Draw points
        for i, (px, py) in enumerate(points):
            color = (
                optional_arcade.arcade.color.ORANGE
                if i == editor.selected_waypoint_index
                else optional_arcade.arcade.color.CYAN
            )
            optional_arcade.arcade.draw_circle_filled(px, py, 4, color)
            # Draw index number
            optional_arcade.arcade.draw_text(
                str(i), px + 5, py + 5, optional_arcade.arcade.color.WHITE, 10
            )

    def _draw_zone_visuals(self, editor: EditorModeController) -> None:
        """Draw zone/hitbox shapes for the selected entity."""
        selected = editor.selected_entity
        if selected is None:
            return
        zone_behaviours = editor._get_zone_behaviours(selected)
        active_behaviour = (
            editor._get_zone_behaviour(selected)
            if zone_behaviours
            else None
        )

        for behaviour in zone_behaviours:
            is_active = behaviour is active_behaviour
            owner = getattr(behaviour, "entity", selected)
            cx = getattr(owner, "center_x", selected.center_x)
            cy = getattr(owner, "center_y", selected.center_y)

            if hasattr(behaviour, "radius"):
                self._draw_circle_zone(cx, cy, behaviour, is_active)
            else:
                self._draw_rect_zone(cx, cy, behaviour, is_active)

    def _draw_circle_zone(
        self, cx: float, cy: float, behaviour: Any, is_active: bool
    ) -> None:
        """Draw a circular zone (trigger_zone with radius)."""
        radius = max(0.0, float(getattr(behaviour, "radius", 0.0)))
        outline = (
            optional_arcade.arcade.color.NEON_GREEN
            if is_active
            else optional_arcade.arcade.color.DARK_SPRING_GREEN
        )
        fill_alpha = 80 if is_active else 30
        fill_color = (outline[0], outline[1], outline[2], fill_alpha)
        optional_arcade.arcade.draw_circle_outline(cx, cy, radius, outline, 2)
        optional_arcade.arcade.draw_circle_filled(cx, cy, radius, fill_color)

    def _draw_rect_zone(
        self, cx: float, cy: float, behaviour: Any, is_active: bool
    ) -> None:
        """Draw a rectangular zone (hitbox with width/height)."""
        width = max(0.0, float(getattr(behaviour, "width", 0.0)))
        height = max(0.0, float(getattr(behaviour, "height", 0.0)))
        outline = (
            optional_arcade.arcade.color.RED
            if is_active
            else optional_arcade.arcade.color.DARK_RED
        )
        fill_alpha = 80 if is_active else 30
        fill_color = (outline[0], outline[1], outline[2], fill_alpha)
        draw_outline_centered(cx, cy, width, height, outline, 2)
        _draw_rectangle_filled(cx, cy, width, height, fill_color)

    def _draw_shape_edit_visuals(self, editor: EditorModeController) -> None:
        """Draw shape edit mode vertices and outline."""
        if not editor.shape_edit_mode:
            return
        selected = editor.selected_entity
        if selected is None:
            return
        if editor.shape_edit_entity is not selected:
            return

        points = [
            (
                selected.center_x + px,
                selected.center_y + py,
            )
            for px, py in editor.shape_edit_points
        ]
        if len(points) >= 2:
            optional_arcade.arcade.draw_line_strip(
                points, optional_arcade.arcade.color.YELLOW, 2
            )
            optional_arcade.arcade.draw_line(
                points[-1][0],
                points[-1][1],
                points[0][0],
                points[0][1],
                optional_arcade.arcade.color.YELLOW,
                2,
            )
        for px, py in points:
            optional_arcade.arcade.draw_circle_filled(
                px, py, 4, optional_arcade.arcade.color.YELLOW
            )

    def _draw_editor_collision_tile_overlay(self, editor: EditorModeController) -> None:
        """Faint overlay for collision-only tile layers while tile paint is active."""
        if not editor.tile_panel_active:
            return
        scene_controller = getattr(self._window, "scene_controller", None)
        instance = getattr(scene_controller, "tilemap_instance", None) if scene_controller is not None else None
        if instance is None:
            return
        draw_layer_ids = {layer.id for layer in instance.draw_layers}
        layer_name = editor.tile.current_tile_layer()
        if not layer_name or layer_name in draw_layer_ids:
            return
        sprites = instance.layer_lookup.get(layer_name)
        if sprites is None:
            return
        tile_w, tile_h = instance.tile_size
        overlay_color = (255, 64, 64, 96)
        for sprite in sprites:
            _draw_rectangle_filled(
                sprite.center_x,
                sprite.center_y,
                float(tile_w),
                float(tile_h),
                overlay_color,
            )
