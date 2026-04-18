from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade

from engine.encounter_debug import get_encounter_debug_lines
from engine.game_runtime import tick as game_tick
from engine.logging_tools import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from typing import Any
    from engine.game import GameWindow


def _draw_debug_overlay(self) -> None:
    """Draw debug information on the screen."""
    fps = engine.optional_arcade.arcade.get_fps()
    cam_x, cam_y = self.camera_controller.get_camera_center()
    mx, my = self.mouse_x, self.mouse_y
    wx, wy = self.screen_to_world(mx, my)

    debug_info = [
        f"FPS: {fps:.1f}",
        f"Camera: ({cam_x:.1f}, {cam_y:.1f})",
        f"Mouse Screen: ({mx:.1f}, {my:.1f})",
        f"Mouse World: ({wx:.1f}, {wy:.1f})",
        f"Zoom: {self.camera_controller.zoom:.2f}",
        f"Entities: {len(self.scene_controller.get_all_entities())}",
    ]
    lighting = getattr(self, "lighting", None)
    if lighting is not None:
        stats = lighting.get_stats()
        status = "avail" if stats["available"] else "no-api"
        state = "on" if stats["enabled"] else "off"
        s_info = str(stats["static_count"])
        if stats["max_static"] is not None:
            s_info += f"/{stats['max_static']}"
        d_info = str(stats["dynamic_count"])
        if stats["max_dynamic"] is not None:
            d_info += f"/{stats['max_dynamic']}"
        debug_info.append(f"Lighting: {state} ({status}) S:{s_info} D:{d_info}")

    debug_info.extend(get_encounter_debug_lines(self.scene_controller))

    self._debug_text.text = "\n".join(debug_info)
    self._debug_text.draw()


def on_draw(self) -> None:
    self.perf_stats.mark_draw_start()
    game_tick.on_draw(self)
    self.perf_stats.mark_draw_end()


def _draw_shadowcast_debug(self) -> None:
    """Draw shadowcast rays if enabled."""
    lighting = getattr(self, "lighting", None)
    if lighting is None:
        return

    self.camera.use()

    snapshot = lighting.get_lighting_snapshot()
    shadowcast = snapshot.get("shadowcast", {})

    for light_id, rays in shadowcast.items():
        try:
            idx = int(light_id.split("_")[1])
            if idx < len(snapshot["lights"]):
                light = snapshot["lights"][idx]
                lx = light.get("x", 0)
                ly = light.get("y", 0)

                for ray in rays:
                    hit = ray["hit"]
                    engine.optional_arcade.arcade.draw_line(lx, ly, hit[0], hit[1], engine.optional_arcade.arcade.color.YELLOW, 1)
                    engine.optional_arcade.arcade.draw_circle_filled(hit[0], hit[1], 2, engine.optional_arcade.arcade.color.RED)
        except (ValueError, IndexError):
            continue

    self.camera_controller.gui_camera.use()


def on_update(self, delta_time: float) -> None:
    self.perf_stats.enter_frame()
    self.perf_stats.mark_update_start()
    game_tick.on_update(self, delta_time)
    self.perf_stats.mark_update_end()


def _resolve_collisions_stage(self, delta_time: float) -> None:  # noqa: ARG001
    """Reserved hook for deterministic collision processing."""


def _toggle_paused_state(self: "GameWindow") -> bool:
    """Flip the paused flag and report the new state."""
    self.paused = not getattr(self, "paused", False)
    logger.info("[Mesh][Debug] paused = %s", self.paused)
    return self.paused


def draw_debug_overlay(self) -> None:
    """Draw a lightweight developer HUD."""
    if not self.engine_config.debug_mode:
        return

    page = self.engine_config.debug_page
    lines = [f"DEBUG MODE (F3) - Page {page+1}/3 (F4)"]

    if page == 0:
        scene_id = self.scene_controller.current_scene_path if self.scene_controller else "N/A"
        player_pos = "N/A"
        if self.scene_controller:
            player = self.scene_controller._find_player_sprite()
            if player:
                player_pos = f"{int(player.center_x)}, {int(player.center_y)}"

        lines.append(f"Scene: {scene_id}")
        lines.append(f"Player: {player_pos}")
        lines.append("Recent Events:")

        if hasattr(self.event_bus, "get_recent_event_names"):
            for name in self.event_bus.get_recent_event_names(5):
                lines.append(f"  {name}")
        elif hasattr(self.event_bus, "get_recent_events"):
            for event in self.event_bus.get_recent_events(5):
                lines.append(f"  {getattr(event, 'type', str(event))}")

    elif page == 1:
        lines.append("Active Quests:")
        quest_manager = getattr(self, "quest_manager", None)
        if not quest_manager and self.game_state_controller:
            quest_manager = getattr(self.game_state_controller, "quests", None)

        if quest_manager:
            for _quest_id, quest in quest_manager._quests.items():
                if quest.state == "active":
                    lines.append(f"  {quest.title}: {quest.state}")
                    for req, val in quest.requirements.items():
                        lines.append(f"    req: {req}={val}")

    elif page == 2:
        lines.append("Counters:")
        if self.game_state_controller:
            counters = self.game_state_controller.state.counters
            quest_counters = {k: v for k, v in counters.items() if "quest:" in k}
            other_counters = {k: v for k, v in counters.items() if "quest:" not in k}

            for key, value in quest_counters.items():
                lines.append(f"  [Q] {key}: {value}")
            for key, value in other_counters.items():
                lines.append(f"  {key}: {value}")

            lines.append("Flags:")
            for key, value in self.game_state_controller.state.flags.items():
                lines.append(f"  {key}: {value}")

    self._draw_debug_output(lines)


def _draw_debug_output(self, lines: list[str]) -> None:
    """Draw debug text lines and legacy overlays."""
    from engine.text_draw import TextCache, draw_text_cached

    if getattr(self, "text_cache", None) is None:
        self.text_cache = TextCache()

    start_y = self.height - 20
    for line in lines:
        draw_text_cached(line, 10, start_y, color=engine.optional_arcade.arcade.color.YELLOW, font_size=12, cache=self.text_cache)
        start_y -= 16

    if getattr(self, "encounter_debug_overlay", False) is True:
        from engine.encounter_debug import get_encounter_debug_lines as _get_encounter_debug_lines

        enc_lines = _get_encounter_debug_lines(self.scene_controller)
        start_y = self.height - 20
        for line in enc_lines:
            draw_text_cached(
                line,
                self.width - 10,
                start_y,
                color=engine.optional_arcade.arcade.color.CYAN,
                font_size=12,
                anchor_x="right",
                cache=self.text_cache,
            )
            start_y -= 16


def bind_update_loop_methods(cls) -> None:
    cls._draw_debug_overlay = _draw_debug_overlay
    cls.on_draw = on_draw
    cls._draw_shadowcast_debug = _draw_shadowcast_debug
    cls.on_update = on_update
    cls._resolve_collisions_stage = _resolve_collisions_stage
    cls._toggle_paused_state = _toggle_paused_state
    cls.draw_debug_overlay = draw_debug_overlay
    cls._draw_debug_output = _draw_debug_output