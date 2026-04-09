from __future__ import annotations

from typing import Any, TYPE_CHECKING
import engine.optional_arcade as optional_arcade

from .common import UIElement, _draw_rectangle_filled
from ..text_draw import TextCache, draw_text_cached

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


class LightOccluderEditorOverlay(UIElement):
    """Editor-only overlay for light and occluder authoring."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=64)

    def draw_world(self) -> None:
        if optional_arcade.arcade is None:
            return
        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return
        if getattr(controller, "lights_tool_active", False):
            self._draw_lights(controller)
        if getattr(controller, "occluder_tool_active", False):
            self._draw_occluders(controller)

    def draw(self) -> None:
        if optional_arcade.arcade is None:
            return
        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return
        lines = self._build_panel_lines(controller)
        if not lines:
            return
        width = 360.0
        height = max(80.0, 30.0 + 16.0 * float(len(lines)))
        right = float(getattr(self.window, "width", 0) or 0) - 20.0
        top = float(getattr(self.window, "height", 0) or 0) - 80.0
        left = right - width
        bottom = top - height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 170),
        )
        draw_text_cached(
            "\n".join(lines),
            left + 12.0,
            top - 12.0,
            color=(255, 255, 255, 255),
            font_size=12,
            anchor_y="top",
            font_name="Consolas",
            cache=self._text_cache,
        )

    def _build_panel_lines(self, controller: Any) -> list[str]:
        lines: list[str] = []
        if getattr(controller, "lights_tool_active", False):
            lines.append("LIGHT TOOL (L)")
            preset_label = None
            getter = getattr(controller, "get_active_lighting_preset_label", None)
            if callable(getter):
                preset_label = getter()
            if preset_label:
                lines.append(preset_label)
            sel = getattr(controller, "lights_selection", None)
            lights = []
            if callable(getattr(controller, "_get_scene_lights", None)):
                lights = controller._get_scene_lights()
            if isinstance(sel, int) and 0 <= sel < len(lights):
                light = lights[sel]
                color = light.get("color", "-")
                flicker = "on" if bool(light.get("flicker_enabled", False)) else "off"
                cookie = light.get("cookie_id") if light.get("cookie_id") else "none"
                lines.append(f"selected={sel} color={color}")
                lines.append(f"flicker={flicker} cookie={cookie}")
                lines.append("C: cycle color  F: toggle flicker  K: cycle cookie")
                props = getattr(controller, "_light_property_defs", [])
                idx = int(getattr(controller, "light_property_index", 0))
                if props:
                    lines.append("----")
                    lines.append("PROPERTIES (Up/Down select, Left/Right adjust, R reset)")
                    for i, prop in enumerate(props):
                        key = prop.get("key") or prop.get("name")
                        default = float(prop.get("default", 0.0))
                        try:
                            value = float(light.get(key, default))
                        except Exception:  # noqa: BLE001  # REASON: light occluder editor should fall back to the property default when a stored value is malformed
                            value = default
                        prefix = ">" if i == idx else " "
                        lines.append(f"{prefix} {prop.get('name')}: {value:.2f}")
            else:
                lines.append("click: add/select light")
        if getattr(controller, "occluder_tool_active", False):
            if lines:
                lines.append("----------------")
            lines.append("OCCLUDER TOOL (O)")
            points = getattr(controller, "occluder_points", [])
            if points:
                lines.append(f"drawing points={len(points)} (Enter to finish)")
                lines.append("Backspace: undo point")
            else:
                lines.append("click: add point / select vertex")
        return lines

    def _draw_lights(self, controller: Any) -> None:
        lights = controller._get_scene_lights()
        if not lights:
            return
        for idx, light in enumerate(lights):
            x = float(light.get("x", 0.0))
            y = float(light.get("y", 0.0))
            radius = float(light.get("radius", 160.0))
            is_selected = controller.lights_selection == idx
            color = optional_arcade.arcade.color.YELLOW if is_selected else optional_arcade.arcade.color.LIGHT_GRAY
            optional_arcade.arcade.draw_circle_outline(x, y, radius, color, 2)
            optional_arcade.arcade.draw_circle_filled(x, y, 4, color)
            if is_selected:
                draw_text_cached(
                    f"r={int(radius)}",
                    x + 8,
                    y + 8,
                    color=(color[0], color[1], color[2], 255),
                    font_size=10,
                    cache=self._text_cache,
                )

    def _draw_occluders(self, controller: Any) -> None:
        occluders = []
        if callable(getattr(controller, "_get_scene_occluders", None)):
            occluders = controller._get_scene_occluders()
        selected_idx = getattr(controller, "occluder_selection", None)
        selected_point = getattr(controller, "occluder_vertex_selection", None)
        for idx, occ in enumerate(occluders):
            if not isinstance(occ, dict) or occ.get("type") != "poly":
                continue
            points = occ.get("points")
            if not isinstance(points, list):
                continue
            poly = []
            for entry in points:
                if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                    continue
                try:
                    poly.append((float(entry[0]), float(entry[1])))
                except Exception:  # noqa: BLE001  # REASON: malformed stored polygon points should be skipped so the remaining occluder path can still be previewed
                    continue
            if len(poly) >= 2:
                optional_arcade.arcade.draw_line_strip(poly, optional_arcade.arcade.color.YELLOW, 2)
                if len(poly) >= 3:
                    optional_arcade.arcade.draw_line(poly[-1][0], poly[-1][1], poly[0][0], poly[0][1], optional_arcade.arcade.color.YELLOW, 2)
            for p_idx, (px, py) in enumerate(poly):
                is_selected = idx == selected_idx and p_idx == selected_point
                color = optional_arcade.arcade.color.LIME if is_selected else optional_arcade.arcade.color.YELLOW
                optional_arcade.arcade.draw_circle_filled(px, py, 4, color)
        draft = getattr(controller, "occluder_points", [])
        if isinstance(draft, list) and len(draft) >= 1:
            try:
                draft_poly = [(float(x), float(y)) for x, y in draft]
            except Exception:  # noqa: BLE001  # REASON: malformed draft points should clear the preview instead of breaking the light occluder overlay
                draft_poly = []
            if len(draft_poly) >= 2:
                optional_arcade.arcade.draw_line_strip(draft_poly, optional_arcade.arcade.color.ORANGE, 2)
            for px, py in draft_poly:
                optional_arcade.arcade.draw_circle_filled(px, py, 4, optional_arcade.arcade.color.ORANGE)
