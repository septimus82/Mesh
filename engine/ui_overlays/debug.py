from __future__ import annotations

from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade
from engine.swallowed_exceptions import _log_swallow

from ..animation_state import get_animation_state_snapshot
from ..text_draw import TextCache
from ..ui_text_cache import UiTextCache, draw_text
from .common import (
    UIElement,
    _draw_rectangle_filled,
    _draw_tb_rectangle_outline,
    _sprite_under_cursor,
)

if TYPE_CHECKING:  # pragma: no cover
    from arcade import Sprite

    from ..game import GameWindow

def format_encounter_debug_text(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        payload = {}

    scene_path = str(payload.get("scene_path") or "-")
    difficulty = str(payload.get("difficulty") or "-")
    preset_id = payload.get("encounter_preset_id")
    preset = str(preset_id) if isinstance(preset_id, str) and preset_id.strip() else "-"

    budget = payload.get("encounter_budget")
    reserve = payload.get("boss_budget_reserve")

    elite_cap = payload.get("elite_cap")
    mini_boss_cap = payload.get("mini_boss_cap")
    allow_elites = bool(payload.get("allow_elites")) if payload.get("allow_elites") is not None else True
    allow_mini_bosses = payload.get("allow_mini_bosses")

    spawn_count = int(payload.get("spawn_count") or 0)
    elite_count = int(payload.get("elite_count") or 0)
    mini_boss_count = int(payload.get("mini_boss_count") or 0)
    total_spawn_cost = float(payload.get("total_spawn_cost") or 0.0)
    elite_cost_share = float(payload.get("elite_cost_share") or 0.0)
    mini_boss_cost_share = float(payload.get("mini_boss_cost_share") or 0.0)

    cap_mini = "->elite" if mini_boss_cap is None else str(int(mini_boss_cap))
    allow_mini = "->elites" if allow_mini_bosses is None else ("Y" if bool(allow_mini_bosses) else "N")

    elite_cap_text = "-" if elite_cap is None else str(int(elite_cap))
    allow_elites_text = "Y" if allow_elites else "N"

    budget_val = float(budget) if budget is not None else 0.0
    reserve_val = float(reserve) if reserve is not None else 0.0

    lines = [
        "Encounter Debug (F8)",
        f"scene: {scene_path}",
        f"difficulty: {difficulty} preset: {preset}",
        f"budget: {budget_val:.2f} reserve: {reserve_val:.2f}",
        f"caps elite={elite_cap_text} mini={cap_mini}  allow elites={allow_elites_text} mini={allow_mini}",
        f"spawns={spawn_count} elite={elite_count} mini={mini_boss_count}",
        f"cost={total_spawn_cost:.2f} shares elite={elite_cost_share:.4f} mini={mini_boss_cost_share:.4f}",
    ]
    return "\n".join(lines)


def _encounter_report_to_debug_payload(report: Any) -> dict[str, Any] | None:
    if report is None:
        return None
    fields = (
        "scene_path",
        "difficulty",
        "encounter_preset_id",
        "encounter_budget",
        "boss_budget_reserve",
        "elite_cap",
        "mini_boss_cap",
        "allow_elites",
        "allow_mini_bosses",
        "spawn_count",
        "elite_count",
        "mini_boss_count",
        "total_spawn_cost",
        "elite_cost_share",
        "mini_boss_cost_share",
    )
    out: dict[str, Any] = {}
    for key in fields:
        try:
            out[key] = getattr(report, key)
        except Exception:  # noqa: BLE001  # REASON: debug fallback isolation
            _log_swallow("DBGO-001", "encounter report attribute extraction fallback")
            out[key] = None
    return out


class EncounterDebugOverlay(UIElement):
    def __init__(self, window: "GameWindow", *, provider: Any | None = None) -> None:
        super().__init__(window)
        self.visible = False
        self.provider = provider

    def toggle(self) -> bool:
        self.visible = not self.visible
        return self.visible

    def draw(self) -> None:
        if not self.visible:
            return

        payload: dict[str, Any] | None = None
        if callable(self.provider):
            try:
                value = self.provider(self.window)
            except Exception:  # noqa: BLE001  # REASON: debug fallback isolation
                _log_swallow("DBGO-002", "encounter debug provider fallback")
                value = None
        else:
            value = None

        if isinstance(value, dict):
            payload = value
        elif isinstance(value, str):
            payload = {"scene_path": "-", "difficulty": "-", "encounter_preset_id": "-", "text": value}
        else:
            payload = _encounter_report_to_debug_payload(value)

        text = format_encounter_debug_text(payload)

        width = min(560.0, max(360.0, self.window.width - 40.0))
        height = 150.0
        left = 20.0
        right = left + width
        top = self.window.height - 20.0
        bottom = top - height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 170),
        )
        _draw_tb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        optional_arcade.arcade.draw_text(
            text,
            left + 12.0,
            top - 12.0,
            optional_arcade.arcade.color.LIGHT_GRAY,
            12,
            anchor_y="top",
            font_name=("Consolas", "Courier New", "Courier"),
        )
        optional_arcade.arcade.draw_text(
            "Press H to close",
            left + 12.0,
            bottom + 24.0,
            optional_arcade.arcade.color.LIGHT_GRAY,
            12,
        )


def format_scene_inspector_text(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        payload = {}

    scene_path = str(payload.get("scene_path") or "-")

    player_value = payload.get("player")
    player = player_value if isinstance(player_value, dict) else {}
    player_x = player.get("x")
    player_y = player.get("y")
    if isinstance(player_x, (int, float)) and isinstance(player_y, (int, float)):
        player_text = f"{float(player_x):.1f},{float(player_y):.1f}"
    else:
        player_text = "-"

    hover_value = payload.get("hover")
    hover = hover_value if isinstance(hover_value, dict) else {}
    hover_id = hover.get("id")
    hover_prefab = hover.get("prefab_id")
    hover_name = hover.get("mesh_name")
    hover_pos_value = hover.get("pos")
    hover_pos = hover_pos_value if isinstance(hover_pos_value, dict) else {}
    hover_x = hover_pos.get("x")
    hover_y = hover_pos.get("y")
    if isinstance(hover_x, (int, float)) and isinstance(hover_y, (int, float)):
        hover_xy = f"{float(hover_x):.1f},{float(hover_y):.1f}"
    else:
        hover_xy = "-"

    hover_id_text = "-"
    hover_prefab_text = "-"
    hover_name_text = "-"
    if any(v not in (None, "", "-") for v in (hover_id, hover_prefab, hover_name)) or hover_xy != "-":
        hover_id_text = str(hover_id) if hover_id not in (None, "") else "-"
        hover_prefab_text = str(hover_prefab) if hover_prefab not in (None, "") else "-"
        hover_name_text = str(hover_name) if hover_name not in (None, "") else "-"
        hover_text = f"id={hover_id_text} prefab={hover_prefab_text} name={hover_name_text} pos={hover_xy}"
    else:
        hover_text = "-"

    hover_source = hover.get("prefab_source")
    if isinstance(hover_source, str) and hover_source.strip():
        prefab_source_text = hover_source
    elif hover_prefab_text != "-":
        prefab_source_text = "unknown"
    else:
        prefab_source_text = "-"

    flags_value = payload.get("flags")
    flags = flags_value if isinstance(flags_value, dict) else {}
    flags_total = flags.get("total")
    flags_on = flags.get("on")
    if isinstance(flags_total, (int, float)) and isinstance(flags_on, (int, float)):
        flags_count_text = f"{int(flags_on)}/{int(flags_total)}"
    else:
        flags_count_text = "-/-"

    keys = flags.get("keys")
    if isinstance(keys, list):
        keys_text = ", ".join(str(k) for k in keys[:5])
    else:
        keys_text = "-"

    # HD-2D info
    render_sort_mode = str(payload.get("render_sort_mode") or "y_sort")
    background_planes_count = int(payload.get("background_planes_count") or 0)

    lines = [
        "Scene Inspector (F10)",
        f"scene: {scene_path}",
        f"player: {player_text}",
        f"hover: {hover_text}",
        f"prefab: id={hover_prefab_text} source={prefab_source_text}",
        f"flags: on={flags_count_text} keys={keys_text}",
        f"render: sort={render_sort_mode} bg_planes={background_planes_count}",
    ]
    return "\n".join(lines)


class SceneInspectorOverlay(UIElement):
    def __init__(self, window: "GameWindow", *, provider: Any | None = None) -> None:
        super().__init__(window)
        self.visible = False
        self.provider = provider

    def toggle(self) -> bool:
        self.visible = not self.visible
        return self.visible

    def draw(self) -> None:
        if not self.visible:
            return

        payload: dict[str, Any] | None = None
        if callable(self.provider):
            try:
                value = self.provider(self.window)
            except Exception:  # noqa: BLE001  # REASON: debug fallback isolation
                _log_swallow("DBGO-003", "scene inspector provider fallback")
                value = None
        else:
            value = None

        if isinstance(value, dict):
            payload = value
        else:
            payload = None

        text = format_scene_inspector_text(payload)

        width = min(680.0, max(380.0, self.window.width - 40.0))
        height = 120.0
        left = 20.0
        right = left + width
        bottom = 20.0
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 170),
        )
        _draw_tb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        optional_arcade.arcade.draw_text(
            text,
            left + 12.0,
            top - 12.0,
            optional_arcade.arcade.color.LIGHT_GRAY,
            12,
            anchor_y="top",
            font_name=("Consolas", "Courier New", "Courier"),
        )


def format_scene_dirty_overlay_lines(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        payload = {}
    if not bool(payload.get("enabled", False)):
        return []

    undo_n = payload.get("undo")
    redo_n = payload.get("redo")
    undo_text = str(int(undo_n)) if isinstance(undo_n, int) else "0"
    redo_text = str(int(redo_n)) if isinstance(redo_n, int) else "0"
    counts_line = f"undo={undo_text} redo={redo_text}"

    dirty = bool(payload.get("dirty", False))
    if not dirty:
        return ["SCENE CLEAN", counts_line]

    reason = str(payload.get("reason") or "").strip() or "-"
    counter = payload.get("counter")
    rev = str(int(counter)) if isinstance(counter, int) else "0"
    return [f"SCENE DIRTY reason={reason} rev={rev}", counts_line]


def format_physics_broadphase_lines(payload: dict[str, Any] | None) -> list[str]:
    if not isinstance(payload, dict):
        payload = {}
    enabled = bool(payload.get("enabled", False))
    build = int(payload.get("build_count") or 0)
    candidate = int(payload.get("candidate_count") or 0)
    exact = int(payload.get("exact_checks_count") or 0)
    enabled_text = "Y" if enabled else "N"
    return [
        "PHYSICS BROADPHASE",
        f"enabled={enabled_text} build={build}",
        f"candidates={candidate} exact={exact}",
    ]


class SceneDirtyOverlay(UIElement):
    def __init__(self, window: "GameWindow", *, provider: Any | None = None) -> None:
        super().__init__(window)
        self.provider = provider

    def get_lines(self) -> list[str]:
        payload = None
        if callable(self.provider):
            try:
                payload = self.provider(self.window)
            except Exception:  # noqa: BLE001  # REASON: debug fallback isolation
                _log_swallow("DBGO-004", "scene dirty provider fallback")
                payload = None
        return format_scene_dirty_overlay_lines(payload if isinstance(payload, dict) else None)

    def draw(self) -> None:
        lines = self.get_lines()
        if not lines:
            return

        left = 20.0
        top = float(getattr(self.window, "height", 720) or 720) - 20.0
        optional_arcade.arcade.draw_text(
            "\n".join(lines),
            left,
            top,
            optional_arcade.arcade.color.WHITE,
            12,
            anchor_y="top",
            font_name=("Consolas", "Courier New", "Courier"),
        )


class PhysicsBroadphaseOverlay(UIElement):
    def __init__(self, window: "GameWindow", *, provider: Any | None = None) -> None:
        super().__init__(window)
        self.provider = provider
        self._ui_cache = UiTextCache(getattr(window, "text_cache", TextCache()))

    def draw(self) -> None:
        if not bool(getattr(self.window, "show_debug", False)):
            return

        payload: dict[str, Any] | None = None
        if callable(self.provider):
            try:
                result = self.provider(self.window)
                payload = result if isinstance(result, dict) else None
            except Exception:  # noqa: BLE001  # REASON: debug fallback isolation
                _log_swallow("DBGO-005", "physics broadphase provider fallback")
                payload = None

        lines = format_physics_broadphase_lines(payload if isinstance(payload, dict) else None)
        if not lines:
            return

        line_height = 16.0
        padding = 12.0
        width = 240.0
        height = len(lines) * line_height + padding * 2.0

        right = float(getattr(self.window, "width", 1280) or 1280) - 20.0
        left = right - width
        bottom = 20.0
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 170),
        )
        _draw_tb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        y = top - padding
        for line in lines:
            draw_text(
                self._ui_cache,
                text=line,
                x=left + padding,
                y=y,
                color=optional_arcade.arcade.color.LIGHT_GRAY,
                font_size=12,
                anchor_y="top",
                font_name=("Consolas", "Courier New", "Courier"),
            )
            y -= line_height


class HD2DDepthDebugOverlay(UIElement):
    """Overlay showing HD-2D render ordering debug info.

    Shows render_sort_mode, sprite count, plane count,
    and optionally per-entity render key components.
    """

    def __init__(self, window: "GameWindow", *, provider: Any | None = None) -> None:
        super().__init__(window)
        self.visible = False
        self.provider = provider
        self.show_details = True  # Show per-entity info

    def toggle(self) -> bool:
        """Toggle overlay visibility."""
        self.visible = not self.visible
        return self.visible

    def toggle_details(self) -> bool:
        """Toggle per-entity detail display."""
        self.show_details = not self.show_details
        return self.show_details

    def draw(self) -> None:
        if not self.visible:
            return

        from engine.hd2d_debug_model import format_hd2d_debug_text, format_hd2d_summary

        payload: dict[str, Any] | None = None
        if callable(self.provider):
            try:
                value = self.provider(self.window)
            except Exception:  # noqa: BLE001  # REASON: debug fallback isolation
                _log_swallow("DBGO-006", "hd2d depth provider fallback")
                value = None
        else:
            value = None

        if isinstance(value, dict):
            payload = value
        else:
            payload = {}

        sort_mode = str(payload.get("sort_mode") or "y_sort")
        sprite_count = int(payload.get("sprite_count") or 0)
        plane_count = int(payload.get("plane_count") or 0)
        sprite_infos = payload.get("sprite_infos") or []

        if self.show_details:
            text = format_hd2d_debug_text(
                sort_mode=sort_mode,
                sprite_count=sprite_count,
                plane_count=plane_count,
                sprite_infos=sprite_infos,
                max_entries=10,
            )
        else:
            text = "HD-2D Depth Debug\n" + format_hd2d_summary(
                sort_mode=sort_mode,
                sprite_count=sprite_count,
                plane_count=plane_count,
            )

        # Count lines for dynamic height
        line_count = text.count("\n") + 1
        line_height = 16.0
        padding = 24.0
        height = line_count * line_height + padding

        width = 340.0
        right = float(self.window.width) - 20.0
        left = right - width
        top = float(self.window.height) - 20.0
        bottom = top - height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 180),
        )
        _draw_tb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.CYAN, 2)

        optional_arcade.arcade.draw_text(
            text,
            left + 10.0,
            top - 10.0,
            optional_arcade.arcade.color.LIGHT_CYAN,
            11,
            anchor_y="top",
            font_name=("Consolas", "Courier New", "Courier"),
        )


class HotReloadOverlay(UIElement):
    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)

    @property
    def blocks_input(self) -> bool:
        return bool(getattr(self.window, "hot_reload_error_visible", False))

    def on_key_press(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        if not bool(getattr(self.window, "hot_reload_error_visible", False)):
            return False
        if key == optional_arcade.arcade.key.ESCAPE:
            clear = getattr(self.window, "clear_hot_reload_error", None)
            if callable(clear):
                clear()
            else:
                self.window.hot_reload_error_visible = False
            return True
        return True

    def draw(self) -> None:
        if not bool(getattr(self.window, "hot_reload_error_visible", False)):
            return

        message = str(getattr(self.window, "hot_reload_error_message", "") or "").strip()
        scene_path = str(getattr(self.window, "hot_reload_error_scene_path", "") or "").strip() or "-"
        if not message:
            return

        lines = [
            "Hot reload failed",
            f"scene: {scene_path}",
            f"error: {message}",
            "Press Esc to dismiss",
        ]

        width = min(720.0, max(400.0, self.window.width - 60.0))
        height = 120.0
        left = (self.window.width - width) / 2.0
        right = left + width
        top = self.window.height - 80.0
        bottom = top - height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 200),
        )
        _draw_tb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.ORANGE, 2)

        optional_arcade.arcade.draw_text(
            "\n".join(lines),
            left + 16.0,
            top - 16.0,
            optional_arcade.arcade.color.WHITE,
            12,
            anchor_y="top",
            font_name=("Consolas", "Courier New", "Courier"),
        )

class EntityInspector(UIElement):
    """Debug overlay that displays info about the sprite under the mouse."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_obj = optional_arcade.arcade.Text(
            text="",
            x=12,
            y=self.window.height - 12,
            color=optional_arcade.arcade.color.YELLOW,
            font_size=12,
            anchor_y="top",
        )

    def update(self, dt: float) -> None:  # noqa: D401 ARG002
        return

    def _find_target_sprite(self) -> "Sprite | None":
        return _sprite_under_cursor(self.window)

    def _format_behaviours(self, behaviours: list[object] | tuple[object, ...]) -> str:
        if not behaviours:
            return "<none>"
        names: list[str] = []
        for entry in behaviours:
            if isinstance(entry, dict):
                names.append(str(entry.get("type", "<unknown>")))
            else:
                names.append(str(entry))
        return ", ".join(names)

    def draw(self) -> None:
        if not self.window.show_debug:
            return

        target = self._find_target_sprite()
        if target is None:
            return

        name = getattr(target, "mesh_name", "<unnamed>")
        tag = getattr(target, "mesh_tag", "<none>")
        behaviours = getattr(target, "mesh_behaviours", [])

        hp_text = ""
        behaviours_runtime = getattr(target, "mesh_behaviours_runtime", [])
        if behaviours_runtime:
            health_cls: type[Any] | None = None
            try:
                from ..behaviours.health import Health
                health_cls = Health
            except ImportError:
                health_cls = None
            except Exception:
                _log_swallow("ui_health_import", "Failed to import Health behaviour")
                health_cls = None

            if health_cls is not None:
                for behaviour in behaviours_runtime:
                    if isinstance(behaviour, health_cls):
                        hp_text = f"HP: {behaviour.hp:.1f}/{behaviour.max_hp:.1f}"
                        break

        info_lines = [
            f"Name: {name}",
            f"Tag: {tag}",
            f"Behaviours: {self._format_behaviours(behaviours)}",
        ]
        if hp_text:
            info_lines.append(hp_text)

        text = "\n".join(info_lines)
        x = 12
        y = self.window.height - 150

        optional_arcade.arcade.draw_lrbt_rectangle_filled(
            left=x - 4,
            right=x + 260,
            bottom=y - 70,
            top=y + 10,
            color=(0, 0, 0, 160),
        )

        self._text_obj.text = text
        self._text_obj.x = x
        self._text_obj.y = y
        self._text_obj.draw()


class AnimationStateOverlay(UIElement):
    """Shows live animation/movement state for the sprite under the cursor."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_obj = optional_arcade.arcade.Text(
            text="",
            x=12,
            y=self.window.height - 260,
            color=optional_arcade.arcade.color.CYAN,
            font_size=11,
            anchor_y="top",
        )

    def update(self, dt: float) -> None:  # noqa: D401 ARG002
        return

    def on_resize(self, width: int, height: int) -> None:  # noqa: ARG002
        self._text_obj.y = self.window.height - 260

    def draw(self) -> None:
        if not self.window.show_debug:
            return

        target = _sprite_under_cursor(self.window)
        if target is None:
            return

        snapshot = get_animation_state_snapshot(target)
        animator = getattr(target, "mesh_animator", None)
        clip_state = getattr(animator, "current_state", None) if animator else None
        clip = animator.clips.get(clip_state) if animator and clip_state else None
        frame_total = len(clip.frames) if clip else 0
        frame_cursor = getattr(animator, "frame_cursor", 0) if animator else 0
        movement = snapshot.get("movement_state") or "<unset>"
        requested = snapshot.get("animation_state") or "<unset>"
        default = snapshot.get("default_animation") or "<unset>"
        priority = float(snapshot.get("priority", 0.0))
        timer = float(snapshot.get("timer", 0.0))
        override_flag = "active" if snapshot.get("override_active") else "inactive"
        clip_line = "<no animator>"
        if clip_state:
            clip_line = clip_state
            if clip:
                clip_line += f" ({frame_cursor + 1}/{frame_total} @ {clip.fps:.1f}fps)"
        available_states: list[str] = []
        if animator:
            enumerator = getattr(animator, "available_states", None)
            if callable(enumerator):
                result = enumerator()
                available_states = result if isinstance(result, list) else []
        blend_duration = float(getattr(animator, "_blend_duration", 0.0)) if animator else 0.0
        blend_elapsed = float(getattr(animator, "_blend_elapsed", 0.0)) if animator else 0.0
        blend_active = bool(getattr(animator, "_blend_from_texture", None)) if animator else False
        default_blend = float(getattr(animator, "default_blend", 0.0)) if animator else 0.0

        name = getattr(target, "mesh_name", "<unnamed>")
        lines = [
            f"Anim Target: {name}",
            f"movement_state: {movement}",
            f"animation_state: {requested} (default: {default})",
            f"animator: {clip_line}",
            f"override: pri={priority:.1f} ttl={timer:.2f}s [{override_flag}]",
        ]
        if blend_active or default_blend > 0.0:
            if blend_duration <= 0.0:
                blend_text = f"default blend: {default_blend:.2f}s"
            else:
                blend_text = (
                    f"blend: {blend_elapsed:.2f}/{blend_duration:.2f}s"
                    f" (default {default_blend:.2f}s)"
                )
            lines.append(blend_text)
        if available_states:
            preview_pool = available_states[:6]
            preview = ", ".join(preview_pool)
            remainder = len(available_states) - len(preview_pool)
            if remainder > 0:
                preview += f", +{remainder}"
            lines.append(f"states: {preview}")

        text = "\n".join(lines)
        self._text_obj.text = text
        self._text_obj.x = 12
        self._text_obj.y = self.window.height - 260

        line_count = len(lines)
        line_height = self._text_obj.font_size + 4
        block_height = line_count * line_height + 16
        bottom = self._text_obj.y - block_height
        optional_arcade.arcade.draw_lrbt_rectangle_filled(
            left=8,
            right=348,
            bottom=bottom,
            top=self._text_obj.y + 8,
            color=(0, 0, 0, 180),
        )
        self._text_obj.draw()


class DevConsole(UIElement):
    """Simple bottom-bar console that echoes the buffer and recent output."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._prompt_text = optional_arcade.arcade.Text(
            text="",
            x=10,
            y=12,
            color=optional_arcade.arcade.color.WHITE,
            font_size=14,
        )
        self._output_text = optional_arcade.arcade.Text(
            text="",
            x=10,
            y=32,
            color=optional_arcade.arcade.color.LIGHT_GRAY,
            font_size=12,
        )
        self._status_text = optional_arcade.arcade.Text(
            text="",
            x=10,
            y=52,
            color=optional_arcade.arcade.color.GRAY,
            font_size=10,
        )

    @property
    def blocks_input(self) -> bool:
        return self.window.console_controller.active

    def update(self, dt: float) -> None:  # noqa: D401 ARG002
        return

    def on_resize(self, width: int, height: int) -> None:  # noqa: ARG002
        """Ensure any cached text alignment resets on window resize."""
        # Positions are recomputed in draw(), but keep anchors fresh.
        self._prompt_text.x = 10
        self._output_text.x = 10
        self._status_text.x = 10

    def draw(self) -> None:
        controller = self.window.console_controller
        if not controller.active:
            return

        # Fallback for input manager access
        input_mgr = getattr(self.window, "input", None)
        if input_mgr is None:
            ctrl = getattr(self.window, "input_controller", None)
            input_mgr = getattr(ctrl, "manager", None)

        buffer = input_mgr.get_text_buffer() if input_mgr else ""
        prompt = f"> {buffer}"

        visible_target = max(1, controller.visible_line_count)
        line_height = self._output_text.font_size + 4
        bar_height = 32 + visible_target * line_height
        _draw_rectangle_filled(
            center_x=self.window.width / 2,
            center_y=bar_height / 2,
            width=self.window.width,
            height=bar_height,
            color=optional_arcade.arcade.color.BLACK,
        )
        optional_arcade.arcade.draw_line(
            0,
            bar_height,
            self.window.width,
            bar_height,
            optional_arcade.arcade.color.DARK_SLATE_GRAY,
            2,
        )

        visible_lines = controller.get_visible_lines()
        output_text = "\n".join(visible_lines)

        self._output_text.text = output_text
        self._output_text.x = 10
        self._output_text.y = bar_height - 32
        self._output_text.draw()

        scroll_state = controller.get_scroll_state()
        total_lines = scroll_state.get("total", 0)
        visible_lines_count = len(visible_lines)
        offset = scroll_state.get("offset", 0)
        max_offset = scroll_state.get("max_offset", 0)
        history_above = offset < max_offset
        history_below = offset > 0

        indicator = ""
        if history_above:
            indicator += "^"
        if history_below:
            indicator += "v"
        status = f"{visible_lines_count}/{total_lines} lines"
        if indicator:
            status = f"{status} {indicator}"
        if max_offset:
            status += f"  offset:{offset}"
        status += "  PgUp/PgDn/Home/End"

        self._status_text.text = status
        self._status_text.x = 10
        self._status_text.y = bar_height - 14
        self._status_text.draw()

        self._prompt_text.text = prompt
        self._prompt_text.x = 10
        self._prompt_text.y = 12
        self._prompt_text.draw()


class PaletteOverlay(UIElement):
    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)

    def get_lines(self) -> list[str]:
        from ..palette_mode import get_state
        state = get_state()
        if not state.enabled:
            return []

        item = state.selected_item
        item_str = f"{item.pack_id}/{item.id}" if item else "<none>"
        idx_str = f"{state.selected_index + 1}/{len(state.current_list)}" if state.current_list else "0/0"

        cam_x = getattr(self.window.camera_controller, "camera_x", 0)
        cam_y = getattr(self.window.camera_controller, "camera_y", 0)
        mx = getattr(self.window.input_controller, "mouse_x", 0)
        my = getattr(self.window.input_controller, "mouse_y", 0)

        world_x = cam_x + mx
        world_y = cam_y + my
        tx = int(world_x // 32)
        ty = int(world_y // 32)

        layer_id = "ground" # Default

        lines = [
            f"PALETTE: ON {state.mode}",
            f"selected={item_str}",
            f"index={idx_str}",
            f"hover=({tx},{ty}) layer={layer_id}",
            (f"last_saved={state.last_saved_display}" if getattr(state, "last_saved_display", "") else "last_saved=<none>"),
            "Enter=apply Tab=switch Up/Down=select",
            "P=preview F3=close"
        ]

        if state.last_warnings:
            lines.append(f"WARNING: {state.last_warnings[0]}")
        return lines

    def draw(self) -> None:
        if not getattr(self.window, "show_debug", False):
            return

        import json

        from ..palette_mode import get_state
        from ..paths import resolve_path

        lines = self.get_lines()
        if not lines:
            return

        state = get_state()
        width = 400.0
        height = 140.0
        left = 20.0
        bottom = 200.0
        right = left + width
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 220),
        )
        _draw_tb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.MAGENTA, 2)

        optional_arcade.arcade.draw_text(
            "\n".join(lines),
            left + 12.0,
            top - 12.0,
            optional_arcade.arcade.color.WHITE,
            12,
            anchor_y="top",
            font_name=("Consolas", "Courier New", "Courier"),
        )

        item = state.selected_item
        if state.preview_on and item:
            preview_lines = []
            try:
                with open(resolve_path(item.path), "r", encoding="utf-8") as f:
                    payload = json.load(f)

                if item.type == "stamp":
                    from ..stamps import pick_stamp_layer_id, render_stamp_layer_ascii

                    target_layer = pick_stamp_layer_id(payload, None)
                    preview_lines = render_stamp_layer_ascii(payload, layer_id=target_layer, tile_filter=None)
                elif item.type == "brush":
                    from ..brushes import pick_brush_layer_id, render_brush_layer_ascii

                    target_layer = pick_brush_layer_id(payload, None)
                    preview_lines = render_brush_layer_ascii(payload, layer_id=target_layer, tile_filter=None)
            except Exception:  # noqa: BLE001  # REASON: debug fallback isolation
                _log_swallow("DBGO-007", "palette preview render fallback")
                preview_lines = ["(preview error)"]

            if preview_lines:
                p_left = right + 10
                p_top = top

                # Draw background for preview
                p_width = 200 # Estimate
                p_height = len(preview_lines) * 14 + 10

                _draw_rectangle_filled(
                    center_x=p_left + p_width/2,
                    center_y=p_top - p_height/2,
                    width=p_width,
                    height=p_height,
                    color=(0, 0, 0, 200),
                )

                optional_arcade.arcade.draw_text(
                    "\n".join(preview_lines),
                    p_left + 5,
                    p_top - 5,
                    optional_arcade.arcade.color.YELLOW,
                    10,
                    anchor_y="top",
                    font_name=("Consolas", "Courier New", "Courier"),
                )


class HD2DPreviewIndicatorOverlay(UIElement):
    """Overlay showing an indicator when HD-2D look preset preview is active.

    Displays text like "HD2D Preview: Soft (Esc cancel, Enter apply)"
    at the top-center of the screen.
    """

    def __init__(self, window: "GameWindow", *, provider: Any | None = None) -> None:
        super().__init__(window)
        self.provider = provider

    def draw(self) -> None:
        payload: dict[str, Any] | None = None
        if callable(self.provider):
            try:
                result = self.provider(self.window)
                payload = result if isinstance(result, dict) else None
            except Exception:  # noqa: BLE001  # REASON: debug fallback isolation
                _log_swallow("DBGO-008", "hd2d preview indicator provider fallback")
                payload = None

        if not isinstance(payload, dict) or not payload.get("visible"):
            return

        from engine.editor.hd2d_preview_indicator_model import format_hd2d_preview_indicator_text

        preset_id = payload.get("preset_id")
        text = format_hd2d_preview_indicator_text(preset_id)
        if not text:
            return

        width = float(getattr(self.window, "width", 1280) or 1280)
        top = float(getattr(self.window, "height", 720) or 720) - 60.0

        # Draw semi-transparent background pill
        text_width = len(text) * 8  # Rough estimate
        pill_width = text_width + 20
        pill_height = 24
        center_x = width / 2

        _draw_rectangle_filled(
            center_x=center_x,
            center_y=top,
            width=pill_width,
            height=pill_height,
            color=(40, 40, 60, 220),
        )

        # Draw text centered
        optional_arcade.arcade.draw_text(
            text,
            center_x,
            top,
            optional_arcade.arcade.color.CYAN,
            12,
            anchor_x="center",
            anchor_y="center",
            font_name=("Consolas", "Courier New", "Courier"),
        )
