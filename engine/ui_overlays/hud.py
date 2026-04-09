from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Optional, Sequence
import engine.optional_arcade as optional_arcade

from ..hud_model import HudViewModel, build_hud_view_model, merge_event_histories
from .common import (
    _LOG_ONCE,
    UIElement,
    _draw_lrtb_rectangle_outline,
    _draw_rectangle_filled,
    logger,
)

if TYPE_CHECKING:  # pragma: no cover
    from arcade import Sprite

    from ..behaviours.health import Health
    from ..game import GameWindow
    from ..ui_toasts import ToastManager


def _collect_hud_history_entries(
    getter: Callable[[int], Any],
    *,
    limit: int,
    tag: str,
    source: str,
) -> list[Any]:
    try:
        return list(getter(limit))
    except (TypeError, ValueError):  # REASON: HUD history adapters should only fail on bad limit/coercion inputs
        if tag not in _LOG_ONCE:
            logger.debug("SWALLOW[%s] %s", tag, source, exc_info=True)
            _LOG_ONCE.add(tag)
        return []


def _read_active_quest_entries(
    quest_manager: Any,
    *,
    once_key: str,
    context: str,
) -> list[Any] | None:
    try:
        entries = quest_manager.list_active_quests()
    except (AttributeError, KeyError, TypeError, ValueError) as exc:  # REASON: quest overlay fallbacks only expect quest state shape/coercion failures
        if once_key not in _LOG_ONCE:
            logger.error("%s: %s", context, exc, exc_info=True)
            _LOG_ONCE.add(once_key)
        return None
    return entries if isinstance(entries, list) else None


class InteractPromptOverlay(UIElement):
    def __init__(self, window: "GameWindow", *, provider: Any | None = None) -> None:
        super().__init__(window)
        self.provider = provider

    def draw(self) -> None:
        payload = None
        if callable(self.provider):
            try:
                payload = self.provider(self.window)
            except Exception:  # noqa: BLE001  # REASON: interact prompt overlay should keep drawing even if an optional provider callback fails
                if "HUD-001" not in _LOG_ONCE:
                    logger.debug(
                        "SWALLOW[%s] %s",
                        "HUD-001",
                        "engine.ui_overlays.hud.InteractPromptOverlay.draw provider",
                        exc_info=True,
                    )
                    _LOG_ONCE.add("HUD-001")
                payload = None

        from ..interaction import get_interact_prompt  # noqa: PLC0415

        text = get_interact_prompt(self.window, payload)
        if not text:
            return

        width = 220.0
        height = 40.0
        left = 20.0
        bottom = 150.0
        right = left + width
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 170),
        )
        _draw_lrtb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        optional_arcade.arcade.draw_text(
            text,
            (left + right) / 2.0,
            (top + bottom) / 2.0,
            optional_arcade.arcade.color.WHITE,
            14,
            anchor_x="center",
            anchor_y="center",
            font_name=("Consolas", "Courier New", "Courier"),
        )


def compute_objective_tracker_lines(
    get_flag: Callable[[str, bool], bool],
    *,
    demo_complete_visible: bool = False,
) -> list[str]:
    if bool(demo_complete_visible):
        return []

    reached_cellar = bool(get_flag("demo.reached_cellar", False))
    if reached_cellar:
        return []

    lines: list[str] = []

    reached_interior = bool(get_flag("demo.reached_interior", False))
    objective_started = bool(get_flag("demo.objective_started", False))

    if reached_interior:
        lines.append("Objective: Find the cellar")
    elif objective_started:
        lines.append("Objective: Enter the cellar")

    upper_started = bool(get_flag("demo.objective_upper_started", False))
    if upper_started:
        reached_upper = bool(get_flag("demo.reached_upper_hall", False))
        lever_pulled = bool(get_flag("demo.upper_hall_lever_pulled", False))
        reached_vault = bool(get_flag("demo.reached_upper_hall_vault", False))
        if not reached_upper:
            lines.append("Optional: Visit the upper hall")
        elif not lever_pulled:
            lines.append("Optional: Pull the lever")
        elif not reached_vault:
            lines.append("Optional: Enter the vault")

    return lines[:2]


class ObjectiveTrackerOverlay(UIElement):
    def __init__(
        self,
        window: "GameWindow",
        *,
        provider: Callable[[Any], Sequence[str]] | None = None,
    ) -> None:
        super().__init__(window)
        self.provider = provider

    def draw(self) -> None:
        demo_complete_overlay = getattr(self.window, "demo_complete_overlay", None)
        if bool(getattr(demo_complete_overlay, "visible", False)):
            return

        lines: list[str] = []
        if callable(self.provider):
            try:
                value = self.provider(self.window)
            except Exception:  # noqa: BLE001  # REASON: objective tracker overlay should keep drawing even if an optional provider callback fails
                if "HUD-002" not in _LOG_ONCE:
                    logger.debug(
                        "SWALLOW[%s] %s",
                        "HUD-002",
                        "engine.ui_overlays.hud.ObjectiveTrackerOverlay.draw provider",
                        exc_info=True,
                    )
                    _LOG_ONCE.add("HUD-002")
                value = None
            if isinstance(value, (list, tuple)):
                lines = [str(line) for line in value if str(line)]
            elif isinstance(value, str):
                if value:
                    lines = [value]

        lines = lines[:2]
        if not lines:
            return

        max_len = max(len(line) for line in lines)
        width = min(520.0, max(260.0, 40.0 + (max_len * 7.5)))
        height = 22.0 + (len(lines) * 18.0)
        left = 20.0
        bottom = 200.0
        right = left + width
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 170),
        )
        _draw_lrtb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        y = top - 12.0
        for line in lines:
            optional_arcade.arcade.draw_text(
                line,
                left + 12.0,
                y,
                optional_arcade.arcade.color.WHITE,
                14,
                anchor_y="top",
                font_name=("Consolas", "Courier New", "Courier"),
            )
            y -= 18.0


class HealthBar(UIElement):
    """Simple bar rendered above a sprite that exposes a Health behaviour."""

    def __init__(self, window: "GameWindow", target: "Sprite") -> None:
        super().__init__(window)
        self.target = target
        self._health: Optional["Health"] = None

    def _ensure_health(self) -> None:
        if self._health is not None:
            return

        behaviours = getattr(self.target, "mesh_behaviours_runtime", [])
        if not behaviours:
            return

        from ..behaviours.health import Health

        for behaviour in behaviours:
            if isinstance(behaviour, Health):
                self._health = behaviour
                break

    def update(self, dt: float) -> None:  # noqa: D401 ARG002
        if getattr(self.target, "_sprite_list", None) is None:
            return
        if self._health is None:
            self._ensure_health()

    def draw(self) -> None:
        if getattr(self.target, "_sprite_list", None) is None:
            return

        if self._health is None:
            self._ensure_health()
        if self._health is None or self._health.max_hp <= 0:
            return

        hp = max(self._health.hp, 0.0)
        ratio = hp / self._health.max_hp if self._health.max_hp > 0 else 0.0
        if ratio <= 0.0:
            return

        sprite_width = getattr(self.target, "width", 32)
        bar_width = float(sprite_width)
        bar_height = 6.0

        x = float(self.target.center_x)
        top = getattr(self.target, "top", self.target.center_y + sprite_width / 2)
        y = float(top + 6.0)

        _draw_rectangle_filled(
            center_x=x,
            center_y=y,
            width=bar_width,
            height=bar_height,
            color=optional_arcade.arcade.color.BLACK,
        )

        filled_width = bar_width * ratio
        _draw_rectangle_filled(
            center_x=x - (bar_width - filled_width) / 2,
            center_y=y,
            width=filled_width,
            height=bar_height,
            color=optional_arcade.arcade.color.LIME_GREEN,
        )


class QuestLog(UIElement):
    """Side panel overlay that lists tracked quests and their objectives."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._visible = False
        self._selection_index = 0
        self._title_text = optional_arcade.arcade.Text(
            text="Quest Log",
            x=0,
            y=0,
            color=optional_arcade.arcade.color.WHITE,
            font_size=20,
            anchor_y="top",
        )
        self._hint_text = optional_arcade.arcade.Text(
            text="Press Q to close",
            x=0,
            y=0,
            color=optional_arcade.arcade.color.LIGHT_GRAY,
            font_size=12,
            anchor_y="top",
        )

    def on_resize(self, width: int, height: int) -> None:  # noqa: ARG002
        """QuestLog computes layout per draw; no persistent cache to update."""
        return

    def is_visible(self) -> bool:
        return self._visible

    @property
    def blocks_input(self) -> bool:
        return self._visible

    def set_visible(self, value: bool) -> None:
        self._visible = bool(value)

    def close(self) -> None:
        self._visible = False

    def toggle(self) -> bool:
        self._visible = not self._visible
        if hasattr(self.window, "audio"):
            sound = "assets/sounds/ui_open.wav" if self._visible else "assets/sounds/ui_close.wav"
            self.window.audio.play_sound(sound)
        if self._visible:
            self._selection_index = 0
        return self._visible

    def update(self, dt: float) -> None:  # noqa: ARG002
        if not self._visible:
            return
        manager = getattr(self.window, "input", None)
        if manager is None:
            return
        if getattr(manager, "input_source", "keyboard_mouse") != "gamepad":
            return
        if manager.was_action_pressed("move_up"):
            self._move_selection(-1)
        if manager.was_action_pressed("move_down"):
            self._move_selection(1)
        if manager.was_action_pressed("toggle_help"):
            self.close()

    def on_key_press(self, key: int, modifiers: int = 0) -> bool:  # noqa: ARG002
        if not self._visible:
            return False
        if key in (optional_arcade.arcade.key.ESCAPE, optional_arcade.arcade.key.Q, optional_arcade.arcade.key.J):
            self.close()
            return True
        if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.W):
            self._move_selection(-1)
            return True
        if key in (optional_arcade.arcade.key.DOWN, optional_arcade.arcade.key.S):
            self._move_selection(1)
            return True
        return True

    def draw(self) -> None:
        if not self._visible:
            return

        entries = self._collect_entries()
        width = min(420.0, max(280.0, self.window.width * 0.4))
        height = max(220.0, self.window.height - 160.0)
        left = self.window.width - width - 24.0
        right = left + width
        bottom = 72.0
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(8, 12, 22, 220),
        )
        _draw_lrtb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        self._title_text.x = left + 20.0
        self._title_text.y = top - 20.0
        self._title_text.draw()
        self._hint_text.x = left + 20.0
        self._hint_text.y = bottom + 24.0
        self._hint_text.draw()

        content_y = top - 52.0
        padding = 20.0
        content_width = width - padding * 1.5
        if not entries:
            optional_arcade.arcade.draw_text(
                "No tracked quests yet.",
                left + padding,
                content_y,
                color=optional_arcade.arcade.color.LIGHT_GRAY,
                font_size=13,
                anchor_y="top",
                width=content_width,
            )
            return

        left_width = max(180.0, content_width * 0.45)
        right_left = left + padding + left_width + 16.0
        right_width = right - right_left - padding
        entries = entries[:50]
        self._selection_index = min(max(0, self._selection_index), max(0, len(entries) - 1))

        y = content_y
        for idx, entry in enumerate(entries):
            if y < bottom + 60.0:
                break
            title_color = optional_arcade.arcade.color.YELLOW if idx == self._selection_index else optional_arcade.arcade.color.WHITE
            if entry.get("completed"):
                title_color = optional_arcade.arcade.color.GRAY
            optional_arcade.arcade.draw_text(
                entry.get("title", "<quest>"),
                left + padding,
                y,
                color=title_color,
                font_size=14,
                width=left_width,
                anchor_y="top",
            )
            y -= 18.0

        if entries:
            selected = entries[self._selection_index]
            detail_color = optional_arcade.arcade.color.LIGHT_GRAY
            status = "Complete" if selected.get("completed") else "Active"
            optional_arcade.arcade.draw_text(
                f"Status: {status}",
                right_left,
                content_y,
                color=detail_color,
                font_size=12,
                width=right_width,
                anchor_y="top",
            )
            objective = selected.get("current_objective") or selected.get("text") or ""
            if objective:
                optional_arcade.arcade.draw_text(
                    f"Objective: {objective}",
                    right_left,
                    content_y - 20.0,
                    color=detail_color,
                    font_size=12,
                    width=right_width,
                    anchor_y="top",
                    multiline=True,
                )
            else:
                optional_arcade.arcade.draw_text(
                    "Objective: -",
                    right_left,
                    content_y - 20.0,
                    color=detail_color,
                    font_size=12,
                    width=right_width,
                    anchor_y="top",
                )

    def _collect_entries(self) -> list[dict[str, Any]]:
        from ..quest_ui import get_active_quests  # noqa: PLC0415

        entries: list[dict[str, Any]] = []
        for summary in get_active_quests(self.window):
            entries.append(
                {
                    "id": summary.quest_id,
                    "title": summary.title,
                    "current_objective": summary.current_objective,
                    "completed": bool(summary.is_complete),
                }
            )
        return entries

    def _move_selection(self, delta: int) -> None:
        entries = self._collect_entries()
        if not entries:
            self._selection_index = 0
            return
        next_index = self._selection_index + int(delta)
        if next_index < 0:
            next_index = 0
        if next_index >= len(entries):
            next_index = len(entries) - 1
        self._selection_index = next_index


@dataclass(slots=True)
class ToastQueue:
    current_text: str = ""
    _seconds_remaining: float = 0.0
    _queue: deque[tuple[str, float]] = field(default_factory=deque)

    def enqueue(self, message: str, *, seconds: float = 4.0) -> None:
        text = str(message or "").strip()
        if not text:
            return
        duration = float(seconds)
        if duration <= 0.0:
            duration = 0.1
        self._queue.append((text, duration))
        if not self.current_text:
            self._pop_next()

    def update(self, dt: float) -> None:
        if not self.current_text:
            if self._queue:
                self._pop_next()
            return
        self._seconds_remaining = max(0.0, self._seconds_remaining - float(dt))
        if self._seconds_remaining <= 0.0:
            self._pop_next()

    def _pop_next(self) -> None:
        if not self._queue:
            self.current_text = ""
            self._seconds_remaining = 0.0
            return
        text, duration = self._queue.popleft()
        self.current_text = text
        self._seconds_remaining = duration

    def clear(self) -> None:
        self._queue.clear()
        self.current_text = ""
        self._seconds_remaining = 0.0


class PlayerHUD(UIElement):
    """Heads-up display for the player (Health, etc)."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        from ..ui_toasts import ToastManager  # noqa: PLC0415

        self._toast_manager: ToastManager = ToastManager()
        self._hud_frame: int = 0
        self._latest_view_model: HudViewModel | None = None
        self._health_text = optional_arcade.arcade.Text(
            text="",
            x=20,
            y=window.height - 20,
            color=optional_arcade.arcade.color.WHITE,
            font_size=14,
            anchor_y="top",
        )

    def clear_toasts(self) -> None:
        self._toast_manager.clear()
        self._xp_text = optional_arcade.arcade.Text(
            text="",
            x=20,
            y=self.window.height - 60,
            color=optional_arcade.arcade.color.WHITE,
            font_size=12,
            anchor_y="top",
        )
        self._level_text = optional_arcade.arcade.Text(
            text="",
            x=20,
            y=self.window.height - 80,
            color=optional_arcade.arcade.color.WHITE,
            font_size=12,
            anchor_y="top",
        )
        self._quest_text = optional_arcade.arcade.Text(
            text="",
            x=self.window.width - 20,
            y=self.window.height - 20,
            color=optional_arcade.arcade.color.YELLOW,
            font_size=12,
            anchor_x="right",
            anchor_y="top",
            multiline=True,
            width=300
        )
        self._toast_text = optional_arcade.arcade.Text(
            text="",
            x=20,
            y=self.window.height - 110,
            color=optional_arcade.arcade.color.LIGHT_GRAY,
            font_size=12,
            anchor_y="top",
            multiline=True,
            width=360,
        )

    @staticmethod
    def build_pinned_objective_text(quest_manager: Any, *, max_chars: int = 220) -> str | None:
        if quest_manager is None or not hasattr(quest_manager, "list_active_quests"):
            return None
        entries = _read_active_quest_entries(
            quest_manager,
            once_key="ui_pinned_objective",
            context="Error reading active quests for pinned objective",
        )
        if not entries:
            return None

        picked: dict[str, Any] | None = None
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            status = str(entry.get("status") or "").strip().lower()
            if status in {"active", "in_progress", "started"}:
                picked = entry
                break
        if picked is None:
            picked = next((entry for entry in entries if isinstance(entry, dict)), None)
        if picked is None:
            return None

        stage_title = str(picked.get("stage_title") or "").strip()
        stage_text = str(picked.get("stage_text") or picked.get("description") or "").strip()
        if not stage_title:
            stage_title = str(picked.get("title") or "Objective").strip() or "Objective"

        stage_text = " ".join(stage_text.split())
        if stage_text and len(stage_text) > max_chars:
            stage_text = stage_text[: max(0, max_chars - 3)].rstrip() + "..."

        if stage_text:
            return f"Objective: {stage_title}\n{stage_text}"
        return f"Objective: {stage_title}"

    @staticmethod
    def maybe_show_quest_log_hint(window: Any, quest_manager: Any = None, scene_id: str | None = None) -> str | None:
        """
        Return the quest log hint text if it should be shown now, otherwise None.

        Persists the shown state via the game state's flags when available.
        """
        flag_name = "hint_shown_quest_log"
        getter = getattr(window, "get_flag", None)
        if callable(getter) and getter(flag_name, False):
            return None
        if getattr(window, "_mesh_hint_shown_quest_log", False):
            return None

        qm = quest_manager or getattr(window, "quest_manager", None)
        if qm is None:
            gs = getattr(window, "game_state_controller", None)
            qm = getattr(gs, "quest_manager", None) if gs is not None else None

        if qm is None:
            return None

        entries = _read_active_quest_entries(
            qm,
            once_key="ui_quest_log_hint",
            context="Error reading active quests for quest log hint",
        )
        if entries is None:
            return None
        active_statuses = {"active", "in_progress", "started"}
        has_active = False
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            status = str(entry.get("status") or "").strip().lower()
            if status in active_statuses:
                has_active = True
                break
        if not has_active:
            return None

        hint = "Press Q to open Quest Log"
        setter = getattr(window, "set_flag", None)
        if callable(setter):
            setter(flag_name, True)
        else:
            setattr(window, "_mesh_hint_shown_quest_log", True)
        return hint

    @staticmethod
    def maybe_show_controls_hint(window: Any, *, scene_id: str | None = None) -> str | None:
        """
        Return a one-time controls hint banner for hub scenes, otherwise None.

        Persists the shown state via the game state's flags when available.
        """
        flag_name = "hint_shown_controls"
        getter = getattr(window, "get_flag", None)
        if callable(getter) and getter(flag_name, False):
            return None
        if getattr(window, "_mesh_hint_shown_controls", False):
            return None

        sid = scene_id or getattr(getattr(window, "scene_controller", None), "current_scene_path", None)
        sid_text = str(sid or "").replace("\\", "/")

        cfg = getattr(window, "engine_config", None)
        hub_scene = getattr(cfg, "start_scene", None) if cfg is not None else None
        hub_text = str(hub_scene or "").replace("\\", "/")
        if hub_text:
            if sid_text != hub_text:
                return None
        else:
            filename = sid_text.rsplit("/", 1)[-1].lower()
            if "hub" not in filename:
                return None

        hint = "Q: Quest Log  Tab: Inventory  I: Inspector  C: Character  F2: Editor  H: Help"
        setter = getattr(window, "set_flag", None)
        if callable(setter):
            setter(flag_name, True)
        else:
            setattr(window, "_mesh_hint_shown_controls", True)
        return hint

    def enqueue_toast(self, message: str, *, seconds: float = 4.0) -> None:
        self._toast_manager.push_toast(message, ttl_s=seconds)

    def update(self, dt: float) -> None:
        self._hud_frame += 1
        self._toast_manager.tick(float(dt))

        if getattr(getattr(self.window, "editor_controller", None), "active", False):
            return

        hint = self.maybe_show_quest_log_hint(
            self.window,
            quest_manager=getattr(self.window, "quest_manager", None),
            scene_id=getattr(getattr(self.window, "scene_controller", None), "current_scene_path", None),
        )
        if hint:
            self.enqueue_toast(hint, seconds=4.0)

    def draw(self) -> None:
        if getattr(getattr(self.window, "editor_controller", None), "active", False):
            return
        player = getattr(self.window, "player", None)
        if not player:
            return

        self._latest_view_model = build_hud_view_model(
            player,
            self._collect_hud_history(limit=200),
            now_frame_or_time=float(self._hud_frame),
        )
        health_state = self._latest_view_model.health_state
        if health_state.max_hp <= 0:
            return

        # Draw Health Bar
        bar_x = 20
        bar_y = self.window.height - 30
        bar_width = 200
        bar_height = 20

        # Background
        _draw_rectangle_filled(
            center_x=bar_x + bar_width / 2,
            center_y=bar_y - bar_height / 2,
            width=bar_width + 4,
            height=bar_height + 4,
            color=optional_arcade.arcade.color.BLACK
        )

        # Fill
        ratio = max(0.0, min(1.0, health_state.hp / health_state.max_hp)) if health_state.max_hp > 0 else 0
        if ratio > 0:
            fill_width = bar_width * ratio
            _draw_rectangle_filled(
                center_x=bar_x + fill_width / 2,
                center_y=bar_y - bar_height / 2,
                width=fill_width,
                height=bar_height,
                color=optional_arcade.arcade.color.RED
            )

        # Text overlay
        self._health_text.text = f"{int(health_state.hp)} / {int(health_state.max_hp)}"
        self._health_text.x = bar_x + bar_width / 2
        self._health_text.y = bar_y - bar_height / 2
        self._health_text.anchor_x = "center"
        self._health_text.anchor_y = "center"
        self._health_text.draw()

        cfg = getattr(self.window, "engine_config", None)
        if cfg is None or getattr(cfg, "hud_show_objective", True):
            show_objective = True
            ui = getattr(self.window, "ui_controller", None)
            if ui is not None:
                is_visible = getattr(ui, "is_quest_log_visible", None)
                if callable(is_visible) and is_visible():
                    show_objective = False
            if show_objective:
                objective = self.build_pinned_objective_text(getattr(self.window, "quest_manager", None))
                if objective:
                    self._quest_text.text = objective
                    self._quest_text.x = self.window.width - 20
                    self._quest_text.y = self.window.height - 20
                    self._quest_text.draw()

        toasts = self._toast_manager.get_active_entries()
        if toasts:
            from ..text_draw import draw_text_cached  # noqa: PLC0415

            start_x = 20.0
            start_y = self.window.height - 110.0
            line_height = 22.0
            padding_x = 12.0
            padding_y = 6.0
            cache = getattr(self.window, "text_cache", None)
            for idx, (toast_text, alpha) in enumerate(toasts):
                if not toast_text:
                    continue
                fade = max(0.0, min(1.0, float(alpha)))
                if fade <= 0.0:
                    continue
                width = min(360.0, max(180.0, 24.0 + (len(toast_text) * 7.5)))
                height = line_height + padding_y * 2
                left = start_x
                top = start_y - (idx * (height + 6.0))
                right = left + width
                bottom = top - height
                bg_alpha = int(round(170 * fade))
                text_alpha = int(round(255 * fade))
                _draw_rectangle_filled(
                    center_x=(left + right) / 2.0,
                    center_y=(top + bottom) / 2.0,
                    width=width,
                    height=height,
                    color=(0, 0, 0, bg_alpha),
                )
                _draw_lrtb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)
                draw_text_cached(
                    toast_text,
                    left + padding_x,
                    top - padding_y,
                    color=(255, 255, 255, text_alpha),
                    font_size=12,
                    anchor_y="top",
                    font_name="Consolas",
                    cache=cache,
                )

        if cfg is not None and not getattr(cfg, "hud_show_xp_bar", True):
            return

        gs = getattr(self.window, "game_state_controller", None)
        if gs is None:
            return

        stats = gs.get_player_stats()
        xp = float(stats.get("xp", 0) or 0)
        xp_to_next = float(stats.get("xp_to_next", 0) or 0)
        xp_needed = max(1.0, xp + max(0.0, xp_to_next))
        xp_ratio = max(0.0, min(1.0, xp / xp_needed))

        xp_bar_width = 200
        xp_bar_height = 10
        xp_bar_x = 20
        xp_bar_y = bar_y - bar_height - 12

        _draw_rectangle_filled(
            center_x=xp_bar_x + xp_bar_width / 2,
            center_y=xp_bar_y - xp_bar_height / 2,
            width=xp_bar_width + 2,
            height=xp_bar_height + 2,
            color=optional_arcade.arcade.color.BLACK,
        )
        if xp_ratio > 0:
            fill_width = xp_bar_width * xp_ratio
            _draw_rectangle_filled(
                center_x=xp_bar_x + fill_width / 2,
                center_y=xp_bar_y - xp_bar_height / 2,
                width=fill_width,
                height=xp_bar_height,
                color=optional_arcade.arcade.color.SKY_BLUE,
            )
        self._xp_text.text = f"XP: {int(xp)}/{int(xp_needed)}"
        self._xp_text.x = xp_bar_x + xp_bar_width / 2
        self._xp_text.y = xp_bar_y - xp_bar_height / 2
        self._xp_text.anchor_x = "center"
        self._xp_text.anchor_y = "center"
        self._xp_text.draw()

        self._level_text.text = f"Lv {int(stats.get('level', 1))}"
        self._level_text.x = xp_bar_x + xp_bar_width + 12
        self._level_text.y = xp_bar_y - xp_bar_height / 2
        self._level_text.anchor_x = "left"
        self._level_text.anchor_y = "center"
        self._level_text.draw()

    def get_hud_view_model(self) -> HudViewModel | None:
        return self._latest_view_model

    def _collect_hud_history(self, *, limit: int) -> tuple[Any, ...]:
        gameplay_history: list[Any] = []
        gameplay_bus = getattr(self.window, "gameplay_event_bus", None)
        gameplay_getter = getattr(gameplay_bus, "get_history", None) if gameplay_bus is not None else None
        if callable(gameplay_getter):
            gameplay_history = _collect_hud_history_entries(
                gameplay_getter,
                limit=limit,
                tag="HUD-003",
                source="engine.ui_overlays.hud.PlayerHUD._collect_hud_history gameplay_history",
            )

        mesh_history: list[Any] = []
        event_bus = getattr(self.window, "event_bus", None)
        mesh_getter = getattr(event_bus, "get_recent_events", None) if event_bus is not None else None
        if callable(mesh_getter):
            mesh_history = _collect_hud_history_entries(
                mesh_getter,
                limit=limit,
                tag="HUD-004",
                source="engine.ui_overlays.hud.PlayerHUD._collect_hud_history mesh_history",
            )

        return tuple(merge_event_histories(gameplay_history, mesh_history))


def maybe_enqueue_controls_hint_toast(
    window: Any,
    *,
    scene_id: str | None = None,
    seconds: float = 4.0,
) -> bool:
    hud = getattr(window, "player_hud", None)
    enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if not callable(enqueue):
        return False
    hint = PlayerHUD.maybe_show_controls_hint(window, scene_id=scene_id)
    if not hint:
        return False
    enqueue(hint, seconds=float(seconds))
    return True


def maybe_enqueue_quest_progress_toast(
    window: Any,
    quest_manager: Any = None,
    *,
    seconds: float = 4.0,
) -> bool:
    hud = getattr(window, "player_hud", None)
    enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if not callable(enqueue):
        return False

    qm = quest_manager or getattr(window, "quest_manager", None)
    if qm is None:
        gs = getattr(window, "game_state_controller", None)
        qm = getattr(gs, "quest_manager", None) if gs is not None else None

    if qm is None:
        return False

    entries = _read_active_quest_entries(
        qm,
        once_key="ui_quest_progress_toast",
        context="Error reading active quests for progress toast",
    )
    if entries is None:
        return False

    key = "hud_last_quest_progress"
    get_var = getattr(window, "get_var", None)
    set_var = getattr(window, "set_var", None)
    if not callable(get_var) or not callable(set_var):
        gs = getattr(window, "game_state_controller", None)
        get_var = getattr(gs, "get_var", None) if gs is not None else None
        set_var = getattr(gs, "set_var", None) if gs is not None else None

    last_map = get_var(key, {}) if callable(get_var) else {}
    if not isinstance(last_map, dict):
        last_map = {}
    new_map = dict(last_map)

    active_statuses = {"active", "in_progress", "started"}
    interesting_statuses = set(active_statuses) | {"completed"}
    did_toast = False
    # Deterministic toast ordering: emit completion toasts before new objective/start toasts
    # so chained quests (complete -> next quest starts on same event) read naturally regardless
    # of quest definition ordering.
    ordered_entries = sorted(
        entries,
        key=lambda e: 0 if isinstance(e, dict) and (e.get("completed") or str(e.get("status") or "").lower() == "completed") else 1,
    )

    for entry in ordered_entries:
        if not isinstance(entry, dict):
            continue
        quest_id = str(entry.get("id") or "").strip()
        if not quest_id:
            continue
        status = str(entry.get("status") or "").strip().lower()
        if status not in interesting_statuses:
            continue

        stage_id_raw = entry.get("stage_id") or entry.get("current_stage") or entry.get("awaiting_stage")
        stage_id = str(stage_id_raw).strip() if stage_id_raw is not None else None
        completed = bool(entry.get("completed")) or status == "completed"

        previous = last_map.get(quest_id)
        prev_completed = bool(previous.get("completed")) if isinstance(previous, dict) else False
        prev_stage_id = (
            str(previous.get("stage_id")).strip()
            if isinstance(previous, dict) and previous.get("stage_id") is not None
            else None
        )

        quest_title = str(entry.get("title") or quest_id).strip() or quest_id
        stage_title = str(entry.get("stage_title") or "").strip()
        complete_toast = entry.get("complete_toast")

        if completed:
            if previous is not None and not prev_completed:
                if isinstance(complete_toast, str) and complete_toast.strip():
                    enqueue(complete_toast.strip(), seconds=float(seconds))
                else:
                    enqueue(f"Quest complete: {quest_title}", seconds=float(seconds))
                did_toast = True
        elif status in active_statuses:
            if stage_title and (previous is None or stage_id != prev_stage_id):
                start_toast = entry.get("start_toast")
                if previous is None and isinstance(start_toast, str) and start_toast.strip():
                    enqueue(start_toast.strip(), seconds=float(seconds))
                else:
                    enqueue(f"Objective updated: {stage_title}", seconds=float(seconds))
                did_toast = True

        new_map[quest_id] = {"stage_id": stage_id, "completed": completed}

    if new_map != last_map and callable(set_var):
        set_var(key, new_map)
    return did_toast


def maybe_auto_open_quest_log(window: Any, quest_manager: Any = None) -> bool:
    """
    Auto-open the Quest Log once when the first quest becomes active.

    Uses the same action dispatch path as pressing Q ("show_quests").
    Persists the shown state via the game state's flags when available.
    """
    flag_name = "auto_opened_quest_log"
    getter = getattr(window, "get_flag", None)
    if callable(getter) and getter(flag_name, False):
        return False
    if getattr(window, "_mesh_auto_opened_quest_log", False):
        return False

    is_visible = getattr(window, "is_quest_log_visible", None)
    if callable(is_visible) and is_visible():
        setter = getattr(window, "set_flag", None)
        if callable(setter):
            setter(flag_name, True)
        else:
            setattr(window, "_mesh_auto_opened_quest_log", True)
        return False

    qm = quest_manager or getattr(window, "quest_manager", None)
    if qm is None:
        gs = getattr(window, "game_state_controller", None)
        qm = getattr(gs, "quest_manager", None) if gs is not None else None

    if qm is None:
        return False

    entries = _read_active_quest_entries(
        qm,
        once_key="ui_auto_open_quest_log",
        context="Error reading active quests for auto-open",
    )
    if entries is None:
        return False
    if not isinstance(entries, list) or not entries:
        return False

    active_statuses = {"active", "in_progress", "started"}
    has_active = False
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status") or "").strip().lower()
        if status in active_statuses and not bool(entry.get("completed")):
            has_active = True
            break
    if not has_active:
        return False

    from ..actions import dispatch_action  # noqa: PLC0415

    if not dispatch_action(window, "show_quests"):
        return False

    setter = getattr(window, "set_flag", None)
    if callable(setter):
        setter(flag_name, True)
    else:
        setattr(window, "_mesh_auto_opened_quest_log", True)
    return True


def _boss_toast_scene_store(window: Any, scene_id: str | None) -> tuple[set[str], str]:
    sid = str(scene_id or "").strip() or "<unknown>"
    prev = getattr(window, "_mesh_boss_toast_scene_id", None)
    if prev != sid:
        setattr(window, "_mesh_boss_toast_scene_id", sid)
        setattr(window, "_mesh_boss_toast_seen", set())
    store = getattr(window, "_mesh_boss_toast_seen", None)
    if not isinstance(store, set):
        store = set()
        setattr(window, "_mesh_boss_toast_seen", store)
    return store, sid


def _boss_toast_entity_id(entity: Any, payload: dict[str, Any]) -> str:
    for key in ("id", "entity_id", "mesh_id", "uuid", "guid", "mesh_name", "prefab_id", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
    for attr_key in ("id", "entity_id", "mesh_id"):
        attr = getattr(entity, attr_key, None)
        if isinstance(attr, str) and attr.strip():
            return attr.strip()
        if isinstance(attr, (int, float)):
            return str(attr)
    attr = getattr(entity, "mesh_name", None)
    if isinstance(attr, str) and attr.strip():
        return attr.strip()
    return "boss"


def maybe_enqueue_boss_spawn_toast(
    window: Any,
    entity_dict_or_resolved: Any,
    scene_id: str | None,
    *,
    seconds: float = 3.0,
) -> bool:
    """Enqueue a one-time per boss per scene-load spawn toast."""

    hud = getattr(window, "player_hud", None)
    enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if not callable(enqueue):
        return False

    payload = getattr(entity_dict_or_resolved, "mesh_entity_data", None) if entity_dict_or_resolved is not None else None
    if not isinstance(payload, dict):
        payload = entity_dict_or_resolved if isinstance(entity_dict_or_resolved, dict) else None
    if payload is None:
        return False

    from ..elite_labeling import is_boss_entity  # noqa: PLC0415

    if not is_boss_entity(payload):
        return False

    store, sid = _boss_toast_scene_store(window, scene_id)
    boss_id = _boss_toast_entity_id(entity_dict_or_resolved, payload)
    key = f"boss_toast_spawned:{sid}:{boss_id}"
    if key in store:
        return False
    store.add(key)

    name = str(payload.get("name") or getattr(entity_dict_or_resolved, "mesh_name", "") or "Boss").strip() or "Boss"
    enqueue(f"BOSS: {name}", seconds=float(seconds))
    return True


def maybe_enqueue_boss_defeat_toast(
    window: Any,
    entity_name_or_resolved: Any,
    scene_id: str | None,
    *,
    seconds: float = 3.0,
) -> bool:
    """Enqueue a one-time per boss per scene-load defeat toast."""

    hud = getattr(window, "player_hud", None)
    enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if not callable(enqueue):
        return False

    payload = getattr(entity_name_or_resolved, "mesh_entity_data", None) if entity_name_or_resolved is not None else None
    if not isinstance(payload, dict):
        payload = entity_name_or_resolved if isinstance(entity_name_or_resolved, dict) else None
    if payload is None:
        return False

    from ..elite_labeling import is_boss_entity  # noqa: PLC0415

    if not is_boss_entity(payload):
        return False

    store, sid = _boss_toast_scene_store(window, scene_id)
    boss_id = _boss_toast_entity_id(entity_name_or_resolved, payload)
    key = f"boss_toast_defeated:{sid}:{boss_id}"
    if key in store:
        return False
    store.add(key)

    name = str(payload.get("name") or getattr(entity_name_or_resolved, "mesh_name", "") or "Boss").strip() or "Boss"
    enqueue("Boss defeated!", seconds=float(seconds))
    return True


def maybe_enqueue_miniboss_spawn_toast(
    window: Any,
    entity_dict_or_resolved: Any,
    scene_id: str | None,
    *,
    seconds: float = 3.0,
) -> bool:
    """Enqueue a one-time per mini-boss per scene-load spawn toast."""

    hud = getattr(window, "player_hud", None)
    enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if not callable(enqueue):
        return False

    payload = getattr(entity_dict_or_resolved, "mesh_entity_data", None) if entity_dict_or_resolved is not None else None
    if not isinstance(payload, dict):
        payload = entity_dict_or_resolved if isinstance(entity_dict_or_resolved, dict) else None
    if payload is None:
        return False

    from ..elite_labeling import is_boss_entity, is_mini_boss_entity  # noqa: PLC0415

    if is_boss_entity(payload):
        return False
    if not is_mini_boss_entity(payload):
        return False

    store, sid = _boss_toast_scene_store(window, scene_id)
    entity_id = _boss_toast_entity_id(entity_dict_or_resolved, payload)
    key = f"miniboss_toast_spawned:{sid}:{entity_id}"
    if key in store:
        return False
    store.add(key)

    name = str(payload.get("name") or getattr(entity_dict_or_resolved, "mesh_name", "") or "Mini-boss").strip() or "Mini-boss"
    enqueue(f"MINI-BOSS: {name}", seconds=float(seconds))
    return True


def maybe_enqueue_miniboss_defeat_toast(
    window: Any,
    entity_name_or_resolved: Any,
    scene_id: str | None,
    *,
    seconds: float = 3.0,
) -> bool:
    """Enqueue a one-time per mini-boss per scene-load defeat toast."""

    hud = getattr(window, "player_hud", None)
    enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if not callable(enqueue):
        return False

    payload = getattr(entity_name_or_resolved, "mesh_entity_data", None) if entity_name_or_resolved is not None else None
    if not isinstance(payload, dict):
        payload = entity_name_or_resolved if isinstance(entity_name_or_resolved, dict) else None
    if payload is None:
        return False

    from ..elite_labeling import is_boss_entity, is_mini_boss_entity  # noqa: PLC0415

    if is_boss_entity(payload):
        return False
    if not is_mini_boss_entity(payload):
        return False

    store, sid = _boss_toast_scene_store(window, scene_id)
    entity_id = _boss_toast_entity_id(entity_name_or_resolved, payload)
    key = f"miniboss_toast_defeated:{sid}:{entity_id}"
    if key in store:
        return False
    store.add(key)

    enqueue("Mini-boss defeated!", seconds=float(seconds))
    return True


DEMO_INTERIOR_HINT_SECONDS = 45.0
DEMO_INTERIOR_HINT_TOAST = "Hint: Head inside the building."


def maybe_enqueue_demo_interior_hint(
    window: Any,
    *,
    dt: float,
    seconds: float = DEMO_INTERIOR_HINT_SECONDS,
    toast: str = DEMO_INTERIOR_HINT_TOAST,
) -> bool:
    """Enqueue a one-time hint toast if the player starts the demo objective but doesn't reach the interior."""

    getter = getattr(window, "get_flag", None)
    setter = getattr(window, "set_flag", None)
    if not callable(getter):
        return False

    started = bool(getter("demo.objective_started", False))
    reached_interior = bool(getter("demo.reached_interior", False))
    already_shown = bool(getter("demo.interior_hint_shown", False)) or bool(
        getattr(window, "_mesh_demo_interior_hint_shown", False)
    )

    if already_shown:
        return False

    if not started or reached_interior:
        setattr(window, "_mesh_demo_interior_hint_remaining", None)
        setattr(window, "_mesh_demo_interior_hint_started", False)
        return False

    if not bool(getattr(window, "_mesh_demo_interior_hint_started", False)):
        setattr(window, "_mesh_demo_interior_hint_started", True)
        setattr(window, "_mesh_demo_interior_hint_remaining", float(seconds))

    remaining = getattr(window, "_mesh_demo_interior_hint_remaining", None)
    if not isinstance(remaining, (int, float)) or isinstance(remaining, bool):
        remaining = float(seconds)
    remaining = float(remaining) - float(dt)
    setattr(window, "_mesh_demo_interior_hint_remaining", remaining)

    if remaining > 0.0:
        return False

    hud = getattr(window, "player_hud", None)
    enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if not callable(enqueue):
        return False

    enqueue(str(toast), seconds=4.0)
    setattr(window, "_mesh_demo_interior_hint_shown", True)
    if callable(setter):
        setter("demo.interior_hint_shown", True)
    return True


def maybe_enqueue_preset_mode_toast(
    window: Any,
    scene_id: str | None,
    *,
    seconds: float = 4.0,
) -> bool:
    """Enqueue a one-time mode tag toast when entering the dungeon in a variant preset."""
    import os

    preset = os.environ.get("MESH_ACTIVE_PRESET")
    if not preset or preset == "golden_slice":
        return False

    # Check if scene is a dungeon scene
    sid = str(scene_id or "").strip()
    if "Ridge Outpost_dungeon" not in sid:
        return False

    # Check persistence (once per run)
    store_attr = "_mesh_preset_mode_toasts_seen"
    store = getattr(window, store_attr, None)
    if not isinstance(store, set):
        store = set()
        setattr(window, store_attr, store)

    key = f"{preset}:{sid}"
    if key in store:
        return False
    store.add(key)

    desc = os.environ.get("MESH_PRESET_DESCRIPTION", "")
    notes = os.environ.get("MESH_PRESET_NOTES", "")

    # Extract variant letter
    variant_letter = preset
    if "variant_b" in preset:
        variant_letter = "Variant B"
    elif "variant_c" in preset:
        variant_letter = "Variant C"
    elif "variant_d" in preset:
        variant_letter = "Variant D"

    # Extract short info
    info = notes if notes else desc
    if len(info) > 30:
        info = info[:27] + "..."

    msg = f"Mode: {variant_letter} ({info})"

    hud = getattr(window, "player_hud", None)
    enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if callable(enqueue):
        enqueue(msg, seconds=float(seconds))
        return True
    return False


def maybe_enqueue_shadowmask_enabled_toast(
    window: Any,
    *,
    seconds: float = 4.0,
) -> bool:
    """Enqueue a one-time toast if shadow mask is enabled."""
    import os

    if os.environ.get("MESH_SHADOWCAST_MASK") != "1":
        return False

    # Check persistence (once per run)
    store_attr = "_mesh_shadowmask_toast_seen"
    if getattr(window, store_attr, False):
        return False
    setattr(window, store_attr, True)

    hud = getattr(window, "player_hud", None)
    enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if callable(enqueue):
        enqueue("Lighting: Shadow mask enabled", seconds=float(seconds))
        return True
    return False


def maybe_enqueue_lighting_toggle_tip(
    window: Any,
    *,
    seconds: float = 4.0,
) -> bool:
    """Enqueue a one-time hint about lighting toggles."""
    # Check persistence (once per run)
    store_attr = "_mesh_lighting_toggle_tip_seen"
    if getattr(window, store_attr, False):
        return False
    setattr(window, store_attr, True)

    hud = getattr(window, "player_hud", None)
    enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if callable(enqueue):
        enqueue("Tip: F6 Shadow mask, F7 Debug rays", seconds=float(seconds))
        return True
    return False


def begin_boss_gold_reward_tracking(
    window: Any,
    entity_name_or_resolved: Any,
    scene_id: str | None,
) -> bool:
    """Capture the gold counter before a boss reward is applied.

    Intended to be called from the boss 'died' handler before other listeners
    (like DropTable) apply rewards.
    """

    payload = getattr(entity_name_or_resolved, "mesh_entity_data", None) if entity_name_or_resolved is not None else None
    if not isinstance(payload, dict):
        payload = entity_name_or_resolved if isinstance(entity_name_or_resolved, dict) else None
    if payload is None:
        return False

    from ..elite_labeling import is_boss_entity  # noqa: PLC0415

    if not is_boss_entity(payload):
        return False

    _, sid = _boss_toast_scene_store(window, scene_id)
    boss_id = _boss_toast_entity_id(entity_name_or_resolved, payload)
    pending_key = f"boss_reward_gold_pending:{sid}:{boss_id}"

    pending = getattr(window, "_mesh_boss_reward_pending", None)
    if not isinstance(pending, dict):
        pending = {}

    if pending_key in pending:
        return False

    getter = getattr(window, "get_counter", None)
    if callable(getter):
        gold_before = float(getter("gold", 0.0))
    else:
        gs = getattr(window, "game_state_controller", None)
        gold_before = float(getattr(gs, "get_counter", lambda *_a, **_k: 0.0)("gold", 0.0)) if gs is not None else 0.0

    pending[pending_key] = gold_before
    setattr(window, "_mesh_boss_reward_pending", pending)
    return True


def maybe_enqueue_exit_unlocked_toast(
    window: Any,
    scene_id: str | None,
    boss_entity: Any,
    *,
    seconds: float = 2.5,
) -> bool:
    """Enqueue 'Exit unlocked' if boss defeat unlocks a forward exit."""
    
    hud = getattr(window, "player_hud", None)
    enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if not callable(enqueue):
        return False

    # Check idempotency
    store, sid = _boss_toast_scene_store(window, scene_id)
    key = f"exit_unlocked:{sid}"
    if key in store:
        return False

    # Resolve boss position
    boss_x = getattr(boss_entity, "center_x", None)
    if boss_x is None:
        # Fallback to payload x if available
        payload = getattr(boss_entity, "mesh_entity_data", {}) or {}
        boss_x = payload.get("x")
    
    if boss_x is None:
        return False

    # Find exit in current scene
    # We need access to scene entities. Try scene_controller.
    scene_ctrl = getattr(window, "scene_controller", None)
    if not scene_ctrl:
        return False
    
    # Try to find Exit entity in loaded scene data or entities layer
    # Prefer loaded_scene_data for raw config, or entities layer for runtime
    # Let's look at _loaded_scene_data first as it's the source of truth for "Exit" name usually
    scene_data = getattr(scene_ctrl, "_loaded_scene_data", {})
    entities = scene_data.get("entities", [])
    
    exit_found = False
    for ent in entities:
        if ent.get("name") == "Exit":
            ex = ent.get("x")
            if ex is not None and ex > boss_x:
                exit_found = True
                break
    
    if not exit_found:
        return False

    store.add(key)
    enqueue("Exit unlocked", seconds=float(seconds))
    return True


def maybe_finish_boss_gold_reward_toast(
    window: Any,
    entity_name_or_resolved: Any,
    scene_id: str | None,
    *,
    seconds: float = 3.0,
) -> bool:
    """If gold increased due to boss rewards, enqueue a "+<N>g" toast."""

    hud = getattr(window, "player_hud", None)
    enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if not callable(enqueue):
        return False

    payload = getattr(entity_name_or_resolved, "mesh_entity_data", None) if entity_name_or_resolved is not None else None
    if not isinstance(payload, dict):
        payload = entity_name_or_resolved if isinstance(entity_name_or_resolved, dict) else None
    if payload is None:
        return False

    from ..elite_labeling import is_boss_entity  # noqa: PLC0415

    if not is_boss_entity(payload):
        return False

    store, sid = _boss_toast_scene_store(window, scene_id)
    boss_id = _boss_toast_entity_id(entity_name_or_resolved, payload)
    toast_key = f"boss_reward_gold:{sid}:{boss_id}"
    if toast_key in store:
        return False

    pending_key = f"boss_reward_gold_pending:{sid}:{boss_id}"
    pending = getattr(window, "_mesh_boss_reward_pending", None)
    if not isinstance(pending, dict) or pending_key not in pending:
        return False
    try:
        gold_before = float(pending.pop(pending_key))
    except (TypeError, ValueError):
        return False

    getter = getattr(window, "get_counter", None)
    if callable(getter):
        gold_after = float(getter("gold", 0.0))
    else:
        gs = getattr(window, "game_state_controller", None)
        gold_after = float(getattr(gs, "get_counter", lambda *_a, **_k: 0.0)("gold", 0.0)) if gs is not None else 0.0

    delta = int(gold_after - gold_before)
    if delta > 0:
        store.add(toast_key)
        enqueue(f"+{delta}g", seconds=float(seconds))
    
    # Check for exit unlock (after rewards)
    maybe_enqueue_exit_unlocked_toast(window, scene_id, entity_name_or_resolved, seconds=2.5)
    
    return delta > 0
