from __future__ import annotations

import copy
import time
from typing import Any, Dict, List, Optional, cast

import engine.optional_arcade as optional_arcade

from engine.editor_light_occluder_ops import (
    COOKIE_PRESETS,
    LIGHT_COLOR_PRESETS,
    LIGHTING_PRESET_ORDER,
    LIGHTING_PRESETS,
    add_occluder,
    add_light,
    apply_lighting_preset as apply_lighting_preset_ops,
    apply_occluder_command,
    build_delete_polygon_cmd,
    build_finish_polygon_cmd,
    build_insert_point_cmd,
    build_move_point_cmd,
    build_remove_point_cmd,
    capture_lighting_preset,
    cycle_light_color,
    cycle_light_cookie,
    ensure_scene_lights,
    ensure_scene_occluders,
    find_closest_edge_insert_index,
    invert_occluder_command,
    toggle_light_flicker,
    update_light_property,
)
from engine.editor_runtime import ops as editor_ops
from engine.i18n import tr
from engine.logging_tools import get_logger

logger = get_logger(__name__)


class EditorLightsController:
    """Encapsulates lights + occluder tool orchestration and runtime sync."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def get_scene_lights(self) -> List[Dict[str, Any]]:
        scene = getattr(getattr(self._editor.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            scene = {}
            if hasattr(self._editor.window, "scene_controller"):
                self._editor.window.scene_controller._loaded_scene_data = scene
        return ensure_scene_lights(scene)

    def get_scene_occluders(self) -> List[Dict[str, Any]]:
        scene = getattr(getattr(self._editor.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            scene = {}
            if hasattr(self._editor.window, "scene_controller"):
                self._editor.window.scene_controller._loaded_scene_data = scene
        return ensure_scene_occluders(scene)

    def sync_lighting_runtime(self) -> None:
        lighting = getattr(self._editor.window, "lighting", None)
        if lighting is not None:
            lights = copy.deepcopy(self.get_scene_lights())
            try:
                lighting.configure_scene_lights(lights)
            except Exception as exc:  # noqa: BLE001
                if not getattr(self._editor, "_mesh_lighting_sync_error_logged", False):
                    logger.error("[Mesh][Editor] ERROR syncing lighting runtime: %s", exc)
                    setattr(self._editor, "_mesh_lighting_sync_error_logged", True)

    def sync_lighting_settings(self) -> None:
        lighting = getattr(self._editor.window, "lighting", None)
        if lighting is None:
            return
        scene = getattr(getattr(self._editor.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            return
        settings = scene.get("settings")
        if not isinstance(settings, dict):
            return
        ambient_tint = settings.get("ambient_light_rgba")
        if ambient_tint is not None:
            try:
                lighting.set_ambient_tint(ambient_tint)
            except Exception:  # noqa: BLE001
                pass
        if "ambient_darkness_alpha" in settings:
            value = settings.get("ambient_darkness_alpha")
            if value is not None:
                try:
                    lighting.set_ambient_darkness_alpha(int(value))
                except Exception:  # noqa: BLE001
                    pass

    def apply_lighting_preset(self, preset_id: str) -> bool:
        preset_id = str(preset_id or "")
        if preset_id not in LIGHTING_PRESETS:
            scene = getattr(getattr(self._editor.window, "scene_controller", None), "_loaded_scene_data", None)
            if not isinstance(scene, dict):
                return False
            settings = scene.get("settings")
            if not isinstance(settings, dict):
                return False
            custom = settings.get("custom_lighting_presets")
            if not isinstance(custom, dict) or preset_id not in custom:
                return False
        scene = getattr(getattr(self._editor.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            scene = {}
            if hasattr(self._editor.window, "scene_controller"):
                self._editor.window.scene_controller._loaded_scene_data = scene
        apply_lighting_preset_ops(scene, preset_id)
        settings = scene.get("settings")
        if isinstance(settings, dict) and hasattr(self._editor.window, "scene_controller"):
            self._editor.window.scene_controller.scene_settings = settings
        self.sync_lighting_settings()
        self._editor.lighting_preset_label = tr("UI_APPLIED_PRESET", slot=preset_id)
        self._editor.lighting_preset_until = time.time() + 1.5
        hud = getattr(self._editor.window, "player_hud", None)
        enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
        if callable(enqueue) and self._editor.lighting_preset_label:
            enqueue(self._editor.lighting_preset_label, seconds=2.5)
        self._editor._mark_dirty()
        return True

    def apply_lighting_preset_hotkey(self, index: int) -> bool:
        if not (0 <= index < len(LIGHTING_PRESET_ORDER)):
            return False
        return self.apply_lighting_preset(LIGHTING_PRESET_ORDER[index])

    def apply_custom_lighting_preset(self, slot: str) -> bool:
        return self.apply_lighting_preset(slot)

    def capture_lighting_preset(self, slot: str) -> bool:
        slot = str(slot or "")
        if slot not in ("custom_1", "custom_2"):
            return False
        scene = getattr(getattr(self._editor.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            scene = {}
            if hasattr(self._editor.window, "scene_controller"):
                self._editor.window.scene_controller._loaded_scene_data = scene
        capture_lighting_preset(scene, slot)
        settings = scene.get("settings")
        if isinstance(settings, dict) and hasattr(self._editor.window, "scene_controller"):
            self._editor.window.scene_controller.scene_settings = settings
        self._editor.lighting_preset_label = tr("UI_SAVED_PRESET", slot=slot)
        self._editor.lighting_preset_until = time.time() + 1.5
        hud = getattr(self._editor.window, "player_hud", None)
        enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
        if callable(enqueue) and self._editor.lighting_preset_label:
            enqueue(self._editor.lighting_preset_label, seconds=2.5)
        self._editor._mark_dirty()
        return True

    def get_active_lighting_preset_label(self) -> str | None:
        label = cast(Optional[str], self._editor.lighting_preset_label)
        if not label:
            return None
        if time.time() > self._editor.lighting_preset_until:
            return None
        return label

    def sync_occluders_runtime(self) -> None:
        lighting = getattr(self._editor.window, "lighting", None)
        if lighting is None:
            return
        occluders = copy.deepcopy(self.get_scene_occluders())
        try:
            from engine.lighting.occluders import build_entity_occluders_from_scene_payload  # noqa: PLC0415
            scene = getattr(getattr(self._editor.window, "scene_controller", None), "_loaded_scene_data", None)
            entity_occluders = build_entity_occluders_from_scene_payload(scene) if isinstance(scene, dict) else []
        except Exception:  # noqa: BLE001
            entity_occluders = []
        if entity_occluders:
            occluders.extend(entity_occluders)
        try:
            lighting.configure_scene_occluders(occluders)
        except Exception as exc:  # noqa: BLE001
            if not getattr(self._editor, "_mesh_occluder_sync_error_logged", False):
                logger.error("[Mesh][Editor] ERROR syncing occluders runtime: %s", exc)
                setattr(self._editor, "_mesh_occluder_sync_error_logged", True)

    def handle_lights_mouse_press(self, world_x: float, world_y: float) -> None:
        ref = self.hit_test_light(world_x, world_y)
        if ref is not None:
            self._editor.lights_selection = ref
            self._editor.lights_dragging = True
            self._editor.lights_drag_start = (world_x, world_y)
            lights = self.get_scene_lights()
            light = lights[ref] if 0 <= ref < len(lights) else {}
            self._editor.lights_original_pos = (
                float(light.get("x", world_x)),
                float(light.get("y", world_y)),
            )
        else:
            self.add_light(world_x, world_y)

    def handle_lights_key_input(self, key: int, modifiers: int) -> bool:
        if self._editor.lights_selection is None:
            return False
        lights = self.get_scene_lights()
        if not (0 <= self._editor.lights_selection < len(lights)):
            return False
        light = lights[self._editor.lights_selection]
        if key in (optional_arcade.arcade.key.DELETE, optional_arcade.arcade.key.BACKSPACE):
            self.delete_selected_light()
            return True
        if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.DOWN):
            delta = -1 if key == optional_arcade.arcade.key.UP else 1
            count = len(self._editor._light_property_defs)
            if count:
                self._editor.light_property_index = (self._editor.light_property_index + delta) % count
            return True
        if key in (optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.RIGHT):
            prop = self._editor._light_property_defs[self._editor.light_property_index]
            step = float(prop.get("step", 1.0))
            if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
                step *= 5.0
            prop_delta: float = step if key == optional_arcade.arcade.key.RIGHT else -step
            key_name = str(prop.get("key") or prop.get("name"))
            default = float(prop.get("default", 0.0))
            current = light.get(key_name, default)
            try:
                current_val = float(current)
            except Exception:  # noqa: BLE001
                current_val = default
            new_value = current_val + prop_delta
            if "min" in prop:
                new_value = max(float(prop["min"]), new_value)
            if "max" in prop:
                new_value = min(float(prop["max"]), new_value)
            if "wrap" in prop:
                new_value = new_value % float(prop["wrap"])
            if new_value != current_val:
                before = current_val
                scene = getattr(getattr(self._editor.window, "scene_controller", None), "_loaded_scene_data", None)
                if not isinstance(scene, dict):
                    scene = {}
                    if hasattr(self._editor.window, "scene_controller"):
                        self._editor.window.scene_controller._loaded_scene_data = scene
                update_light_property(scene, self._editor.lights_selection, prop.get("name", key_name), new_value)
                self._editor._push_command({
                    "type": "EditLight",
                    "index": self._editor.lights_selection,
                    "field": key_name,
                    "before": before,
                    "after": new_value,
                })
                self.sync_lighting_runtime()
            return True
        if key == optional_arcade.arcade.key.R:
            prop = self._editor._light_property_defs[self._editor.light_property_index]
            key_name = str(prop.get("key") or prop.get("name"))
            default = float(prop.get("default", 0.0))
            before = float(light.get(key_name, default))
            scene = getattr(getattr(self._editor.window, "scene_controller", None), "_loaded_scene_data", None)
            if not isinstance(scene, dict):
                scene = {}
                if hasattr(self._editor.window, "scene_controller"):
                    self._editor.window.scene_controller._loaded_scene_data = scene
            update_light_property(scene, self._editor.lights_selection, prop.get("name", key_name), default)
            if before != default:
                self._editor._push_command({
                    "type": "EditLight",
                    "index": self._editor.lights_selection,
                    "field": key_name,
                    "before": before,
                    "after": default,
                })
                self.sync_lighting_runtime()
            return True
        if key == optional_arcade.arcade.key.M:
            old_mode = str(light.get("mode", "soft"))
            new_mode = "hard" if old_mode == "soft" else "soft"
            light["mode"] = new_mode
            self._editor._push_command({
                "type": "EditLight",
                "index": self._editor.lights_selection,
                "field": "mode",
                "before": old_mode,
                "after": new_mode,
            })
            self.sync_lighting_runtime()
            return True
        if key == optional_arcade.arcade.key.C:
            old_color, new_color = cycle_light_color(light, self._editor._light_color_palette)
            self._editor._push_command({
                "type": "EditLight",
                "index": self._editor.lights_selection,
                "field": "color",
                "before": old_color,
                "after": new_color,
            })
            self.sync_lighting_runtime()
            return True
        if key == optional_arcade.arcade.key.F:
            old_value, new_value = toggle_light_flicker(light)
            self._editor._push_command({
                "type": "EditLight",
                "index": self._editor.lights_selection,
                "field": "flicker_enabled",
                "before": old_value,
                "after": new_value,
            })
            self.sync_lighting_runtime()
            return True
        if key == optional_arcade.arcade.key.K:
            old_cookie, new_cookie = cycle_light_cookie(light, self._editor._light_cookie_palette)
            self._editor._push_command({
                "type": "EditLight",
                "index": self._editor.lights_selection,
                "field": "cookie_id",
                "before": old_cookie,
                "after": new_cookie,
            })
            self.sync_lighting_runtime()
            return True
        return False

    def hit_test_light(self, world_x: float, world_y: float, pick_radius: float = 16.0) -> Optional[int]:
        lights = self.get_scene_lights()
        for idx, light in enumerate(lights):
            lx = float(light.get("x", 0.0))
            ly = float(light.get("y", 0.0))
            dx = world_x - lx
            dy = world_y - ly
            if dx * dx + dy * dy <= pick_radius * pick_radius:
                return idx
        return None

    def add_light(self, x: float, y: float) -> None:
        scene = getattr(getattr(self._editor.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            scene = {}
            if hasattr(self._editor.window, "scene_controller"):
                self._editor.window.scene_controller._loaded_scene_data = scene
        sx, sy = self._editor._snap_world_point(float(x), float(y))
        index, light = add_light(scene, sx, sy)
        self._editor.lights_selection = index
        self._editor._push_command({
            "type": "AddLight",
            "index": index,
            "light": copy.deepcopy(light),
        })
        self.sync_lighting_runtime()

    def delete_selected_light(self) -> None:
        if self._editor.lights_selection is None:
            return
        lights = self.get_scene_lights()
        if not (0 <= self._editor.lights_selection < len(lights)):
            return
        removed = lights.pop(self._editor.lights_selection)
        self._editor._push_command({
            "type": "DeleteLight",
            "index": self._editor.lights_selection,
            "light": copy.deepcopy(removed),
        })
        self._editor.lights_selection = None
        self.sync_lighting_runtime()

    def draw_lights_overlay(self) -> None:
        if not (self._editor.active and self._editor.lights_tool_active):
            return
        lights = self.get_scene_lights()
        if not lights:
            return
        for idx, light in enumerate(lights):
            x = float(light.get("x", 0.0))
            y = float(light.get("y", 0.0))
            radius = float(light.get("radius", 160.0))
            is_selected = self._editor.lights_selection == idx
            color = optional_arcade.arcade.color.YELLOW if is_selected else optional_arcade.arcade.color.LIGHT_GRAY
            optional_arcade.arcade.draw_circle_outline(x, y, radius, color, 2)
            optional_arcade.arcade.draw_circle_filled(x, y, 4, color)
            if is_selected:
                optional_arcade.arcade.draw_text(f"r={int(radius)}", x + 8, y + 8, color, 10)

    def toggle_lights_tool(self) -> None:
        editor_ops.toggle_lights_tool(self._editor)
        self._editor._autosave_workspace()

    def toggle_lights_mode(self, enabled: bool) -> None:
        self._editor.lights_tool_active = enabled
        if enabled:
            self.toggle_occluder_mode(False)
            self._editor.shape.cancel_shape_edit()
            inspector = getattr(self._editor, "inspector", None)
            if inspector is not None:
                inspector.set_inspector_active(False)
            self._editor.palette_active = False
            self._editor.palette_filter_active = False
            self._editor.hierarchy_active = False
            self._editor.dialogue_panel_active = False
            self._editor.animation_active = False
            self._editor._set_tile_panel_active(False)
        else:
            self._editor.lights_selection = None
            self._editor.lights_dragging = False
            self._editor.lights_drag_start = None
            self._editor.lights_original_pos = None

    def toggle_occluder_tool(self) -> None:
        editor_ops.toggle_occluder_tool(self._editor)
        self._editor._autosave_workspace()

    def toggle_occluder_mode(self, enabled: bool) -> None:
        self._editor.occluder_tool_active = enabled
        if enabled:
            self._editor.lights_tool_active = False
            self._editor.shape.cancel_shape_edit()
        self._editor.occluder_points = []
        self._editor.occluder_selection = None
        self._editor.occluder_vertex_selection = None
        self._editor.occluder_dragging = False
        self._editor.occluder_drag_origin = None

    def handle_occluder_mouse_press(self, world_x: float, world_y: float) -> None:
        hit = self.hit_test_occluder_vertex(world_x, world_y)
        if hit is not None:
            occ_idx, pt_idx = hit
            self._editor.occluder_selection = occ_idx
            self._editor.occluder_vertex_selection = pt_idx
            self._editor.occluder_dragging = True
            self._editor.occluder_drag_origin = self.get_occluder_point(occ_idx, pt_idx)
            return
        sx, sy = self._editor._snap_world_point(world_x, world_y)
        if self._editor.occluder_points:
            self._editor.occluder_points.append((sx, sy))
        else:
            self._editor.occluder_points = [(sx, sy)]
            self._editor.occluder_selection = None
            self._editor.occluder_vertex_selection = None

    def hit_test_occluder_vertex(
        self,
        world_x: float,
        world_y: float,
        *,
        radius_px: float = 10.0,
    ) -> Optional[tuple[int, int]]:
        radius_world = self._editor.shape.shape_pick_radius_world(radius_px)
        radius_sq = radius_world * radius_world
        occluders = self.get_scene_occluders()
        for occ_idx, occ in enumerate(occluders):
            if not isinstance(occ, dict) or occ.get("type") != "poly":
                continue
            points = occ.get("points")
            if not isinstance(points, list):
                continue
            for pt_idx, entry in enumerate(points):
                if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                    continue
                try:
                    px = float(entry[0])
                    py = float(entry[1])
                except Exception:  # noqa: BLE001
                    continue
                dx = float(world_x) - px
                dy = float(world_y) - py
                if dx * dx + dy * dy <= radius_sq:
                    return (occ_idx, pt_idx)
        return None

    def commit_occluder_polygon(self) -> bool:
        if len(self._editor.occluder_points) < 3:
            return False
        scene = getattr(getattr(self._editor.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            scene = {}
            if hasattr(self._editor.window, "scene_controller"):
                self._editor.window.scene_controller._loaded_scene_data = scene
        index, occ = add_occluder(scene, list(self._editor.occluder_points))
        self._editor.occluder_points = []
        self._editor.occluder_selection = index
        self._editor.occluder_vertex_selection = None
        cmd = build_finish_polygon_cmd(index=index, occluder=copy.deepcopy(occ))
        self._editor._push_command({
            "type": "EditOccluder",
            "cmd": {"kind": cmd.kind, "payload": cmd.payload},
        })
        self.sync_occluders_runtime()
        return True

    def remove_occluder_point(self) -> bool:
        if self._editor.occluder_points:
            self._editor.occluder_points.pop()
            return True
        if self._editor.occluder_selection is None:
            return False
        if self._editor.occluder_vertex_selection is not None:
            return self.remove_selected_occluder_vertex()
        return self.delete_selected_occluder()

    def update_occluder_point(self, world_x: float, world_y: float, *, push_command: bool = True) -> bool:
        if self._editor.occluder_selection is None or self._editor.occluder_vertex_selection is None:
            return False
        occluders = self.get_scene_occluders()
        occ_idx = self._editor.occluder_selection
        pt_idx = self._editor.occluder_vertex_selection
        if not (0 <= occ_idx < len(occluders)):
            return False
        occ = occluders[occ_idx]
        points = occ.get("points")
        if not isinstance(points, list) or not (0 <= pt_idx < len(points)):
            return False
        before = points[pt_idx]
        sx, sy = self._editor._snap_world_point(world_x, world_y)
        after = [float(sx), float(sy)]
        if before != after:
            points[pt_idx] = after
            if push_command:
                cmd = build_move_point_cmd(
                    occ_index=occ_idx,
                    point_index=pt_idx,
                    before=before if isinstance(before, list) else after,
                    after=after,
                    occ_id=occ.get("id") if isinstance(occ, dict) else None,
                )
                self._editor._push_command({
                    "type": "EditOccluder",
                    "cmd": {"kind": cmd.kind, "payload": cmd.payload},
                })
            else:
                self._editor._mark_dirty()
            self.sync_occluders_runtime()
        return True

    def get_occluder_point(self, occ_idx: int, pt_idx: int) -> Optional[tuple[float, float]]:
        occluders = self.get_scene_occluders()
        if not (0 <= occ_idx < len(occluders)):
            return None
        occ = occluders[occ_idx]
        points = occ.get("points")
        if not isinstance(points, list) or not (0 <= pt_idx < len(points)):
            return None
        entry = points[pt_idx]
        if isinstance(entry, (list, tuple)) and len(entry) == 2:
            try:
                return (float(entry[0]), float(entry[1]))
            except Exception:  # noqa: BLE001
                return None
        return None

    def build_move_occluder_cmd(
        self,
        occ_idx: int,
        pt_idx: int,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> Any | None:
        occluders = self.get_scene_occluders()
        if not (0 <= occ_idx < len(occluders)):
            return None
        occ = occluders[occ_idx]
        return build_move_point_cmd(
            occ_index=occ_idx,
            point_index=pt_idx,
            before=[float(start[0]), float(start[1])],
            after=[float(end[0]), float(end[1])],
            occ_id=occ.get("id") if isinstance(occ, dict) else None,
        )

    def delete_selected_occluder(self) -> bool:
        if self._editor.occluder_selection is None:
            return False
        occluders = self.get_scene_occluders()
        if not (0 <= self._editor.occluder_selection < len(occluders)):
            return False
        removed = occluders.pop(self._editor.occluder_selection)
        cmd = build_delete_polygon_cmd(index=self._editor.occluder_selection, occluder=copy.deepcopy(removed))
        self._editor._push_command({
            "type": "EditOccluder",
            "cmd": {"kind": cmd.kind, "payload": cmd.payload},
        })
        self._editor.occluder_selection = None
        self._editor.occluder_vertex_selection = None
        self.sync_occluders_runtime()
        return True

    def remove_selected_occluder_vertex(self) -> bool:
        if self._editor.occluder_selection is None or self._editor.occluder_vertex_selection is None:
            return False
        occluders = self.get_scene_occluders()
        occ_idx = self._editor.occluder_selection
        pt_idx = self._editor.occluder_vertex_selection
        if not (0 <= occ_idx < len(occluders)):
            return False
        occ = occluders[occ_idx]
        points = occ.get("points")
        if not isinstance(points, list) or not (0 <= pt_idx < len(points)):
            return False
        if len(points) <= 3:
            return False
        removed = points.pop(pt_idx)
        cmd = build_remove_point_cmd(
            occ_index=occ_idx,
            point_index=pt_idx,
            point=removed if isinstance(removed, list) else [float(removed[0]), float(removed[1])],
            occ_id=occ.get("id") if isinstance(occ, dict) else None,
        )
        self._editor._push_command({
            "type": "EditOccluder",
            "cmd": {"kind": cmd.kind, "payload": cmd.payload},
        })
        self._editor.occluder_vertex_selection = None
        self.sync_occluders_runtime()
        return True

    def handle_occluder_key_input(self, key: int) -> bool:
        if key in (optional_arcade.arcade.key.BACKSPACE, optional_arcade.arcade.key.DELETE):
            return self.remove_occluder_point()
        if key == optional_arcade.arcade.key.I:
            mx = getattr(self._editor.window, "_mouse_x", None)
            my = getattr(self._editor.window, "_mouse_y", None)
            if isinstance(mx, (int, float)) and isinstance(my, (int, float)):
                wx, wy = self._editor.window.screen_to_world(mx, my)
                return self.insert_occluder_point(wx, wy)
        return False

    def insert_occluder_point(self, world_x: float, world_y: float) -> bool:
        if self._editor.occluder_selection is None:
            return False
        occluders = self.get_scene_occluders()
        occ_idx = self._editor.occluder_selection
        if not (0 <= occ_idx < len(occluders)):
            return False
        occ = occluders[occ_idx]
        points = occ.get("points")
        if not isinstance(points, list) or len(points) < 2:
            return False
        insert_idx, proj = find_closest_edge_insert_index(points, (world_x, world_y))
        sx, sy = self._editor._snap_world_point(proj[0], proj[1])
        cmd = build_insert_point_cmd(
            occ_index=occ_idx,
            insert_index=insert_idx,
            point=(sx, sy),
            occ_id=occ.get("id") if isinstance(occ, dict) else None,
        )
        scene = getattr(getattr(self._editor.window, "scene_controller", None), "_loaded_scene_data", None)
        if not isinstance(scene, dict):
            scene = {}
            if hasattr(self._editor.window, "scene_controller"):
                self._editor.window.scene_controller._loaded_scene_data = scene
        apply_occluder_command(scene, {"kind": cmd.kind, "payload": cmd.payload})
        self._editor._push_command({"type": "EditOccluder", "cmd": {"kind": cmd.kind, "payload": cmd.payload}})
        self._editor.occluder_vertex_selection = insert_idx
        self.sync_occluders_runtime()
        return True

    def draw_lights_editor_overlay(self) -> None:
        overlay = getattr(self._editor.window, "light_occluder_overlay", None)
        if overlay is None:
            return
        if self._editor.lights_tool_active:
            overlay.draw_lights_tool()
        if self._editor.occluder_tool_active:
            overlay.draw_occluder_tool()

    def invert_occluder_and_apply(self, scene: dict[str, Any], raw_cmd: dict[str, Any]) -> None:
        inverse = invert_occluder_command(raw_cmd)
        apply_occluder_command(scene, {"kind": inverse.kind, "payload": inverse.payload})
        self.sync_occluders_runtime()
