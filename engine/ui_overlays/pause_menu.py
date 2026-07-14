"""Pause menu overlay with save/load and settings sub-menus."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade
from engine.logging_tools import get_logger

from ..text_draw import TextCache, draw_text_cached
from ._settings_data import SETTINGS_ROWS
from .common import UIElement, _draw_rectangle_filled
from .widgets import Button, DrawInstruction, Label, Padding, Panel, Rect, ScrollList, Slider, Toggle, VStack

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow

logger = get_logger(__name__)

_MAIN_ACTIONS: tuple[tuple[str, str], ...] = (
    ("pause.main.resume", "Resume"),
    ("pause.main.settings", "Settings"),
    ("pause.main.save", "Save Game"),
    ("pause.main.load", "Load Game"),
    ("pause.main.quit", "Quit"),
)


@dataclass(frozen=True)
class PauseHitTarget:
    action_id: str
    rect: Rect
    index: int
    widget: Any | None = None


@dataclass(frozen=True)
class PauseMenuLayout:
    state: str
    selected_index: int
    selected_save_index: int
    settings_index: int
    window_size: tuple[int, int]
    instructions: list[DrawInstruction] = field(default_factory=list)
    hit_targets: list[PauseHitTarget] = field(default_factory=list)

    def target_at(self, x: float, y: float) -> PauseHitTarget | None:
        for target in self.hit_targets:
            if target.rect.contains(float(x), float(y)):
                return target
        return None

    @property
    def action_ids(self) -> tuple[str, ...]:
        return tuple(target.action_id for target in self.hit_targets)


class PauseMenu(UIElement):
    """Menu displayed when the game is paused."""

    _SETTINGS_ROWS = SETTINGS_ROWS

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible = False
        self.options = [label for _action_id, label in _MAIN_ACTIONS]
        self.selected_index = 0
        self.state = "main"
        self.save_slots: list[str] = []
        self.selected_save_index = 0
        self._settings_index = 0
        self._text_cache = TextCache()
        self._main_menu_buttons: list[Button] = []
        self._last_layout: PauseMenuLayout | None = None
        self._layout_dirty = True
        self._last_window_size: tuple[int, int] | None = None

        self._save_scroll = ScrollList(items=[], row_height=34, selected_index=0)
        self._load_scroll = ScrollList(items=[], row_height=34, selected_index=0)
        self._settings_widgets: dict[str, Slider | Toggle | Button] = {
            "music_volume": Slider(label="Music Volume", value=1.0, step=0.01, height=34.0),
            "sfx_volume": Slider(label="SFX Volume", value=1.0, step=0.01, height=34.0),
            "fog_enabled": Toggle(label="Fog", value=False, height=30.0),
            "soft_shadows_enabled": Toggle(label="Soft Shadows", value=False, height=30.0),
            "back": Button(text="Back", action_id="pause.settings.back", font_size=18, height=34.0),
        }

    @property
    def blocks_input(self) -> bool:
        return bool(self.visible)

    def toggle(self) -> bool:
        self.visible = not self.visible
        if self.visible:
            self.selected_index = 0
            self.state = "main"
            self._settings_index = 0
        self._invalidate_layout()
        return self.visible

    def on_resize(self, _width: int, _height: int) -> None:
        self._invalidate_layout()

    def _invalidate_layout(self) -> None:
        self._layout_dirty = True
        self._last_layout = None
        self._main_menu_buttons = []

    def _play_ui_sound(self, path: str) -> None:
        audio = getattr(self.window, "audio", None)
        if audio is not None:
            audio.play_sound(path)

    def _runtime_settings(self):
        from ..runtime_settings import ensure_runtime_settings  # noqa: PLC0415

        return ensure_runtime_settings(self.window)

    def _apply_runtime_settings(self) -> None:
        settings = self._runtime_settings()
        settings.apply(self.window)
        saver = getattr(self, "_save_runtime_settings", None)
        if callable(saver):
            saver()
        self._invalidate_layout()

    def _save_runtime_settings(self) -> None:
        from ..i18n import tr  # noqa: PLC0415

        editor = getattr(self.window, "editor", None)
        if editor is not None and hasattr(editor, "workspace"):
            editor.workspace.save_user_settings()
        else:
            from ..runtime_settings_storage import save_runtime_settings  # noqa: PLC0415

            path = getattr(self.window, "runtime_settings_path", None)
            settings = self._runtime_settings()
            save_runtime_settings(path, settings)
        hud = getattr(self.window, "player_hud", None)
        enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
        if callable(enqueue):
            enqueue(tr("UI_SETTINGS_SAVED"), seconds=2.0)

    def _window_size(self) -> tuple[int, int]:
        return (int(getattr(self.window, "width", 800) or 800), int(getattr(self.window, "height", 600) or 600))

    def _panel_bounds(self, *, height_scale: float = 0.58, min_height: float = 300.0, max_height: float = 460.0) -> Rect:
        width, height = self._window_size()
        panel_width = min(600.0, max(360.0, float(width) * 0.52))
        panel_height = min(max_height, max(min_height, float(height) * height_scale))
        return Rect(
            x=(float(width) - panel_width) / 2.0,
            y=(float(height) - panel_height) / 2.0,
            width=panel_width,
            height=panel_height,
        )

    def layout_current_state(self) -> PauseMenuLayout:
        size = self._window_size()
        if not self._layout_dirty and self._last_layout is not None and self._last_window_size == size:
            return self._last_layout
        if self.state == "save":
            layout = self._layout_save()
        elif self.state == "load":
            layout = self._layout_load()
        elif self.state == "settings":
            layout = self._layout_settings()
        else:
            layout = self._layout_main()
        self._last_layout = layout
        self._last_window_size = size
        self._layout_dirty = False
        return layout

    def _layout_main(self) -> PauseMenuLayout:
        panel_bounds = self._panel_bounds()
        title = Label(text="PAUSED", font_size=30, color_token="white", height=48.0)
        buttons: list[Button] = []
        hit_targets: list[PauseHitTarget] = []
        for index, (action_id, label) in enumerate(_MAIN_ACTIONS):
            selected = index == self.selected_index
            button = Button(
                text=label,
                action_id=action_id,
                font_size=20,
                height=36.0,
                text_color_token="yellow" if selected else "gray",
                bg_style_token="selected" if selected else "idle",
            )
            buttons.append(button)
        stack = VStack(children=[title, *buttons], spacing=8.0, align="stretch")
        result = Panel(children=[stack], padding=Padding.uniform(16.0), bg_style_token="pause_panel").layout(panel_bounds)
        self._main_menu_buttons = buttons
        for index, button in enumerate(buttons):
            if button.last_rect is not None:
                hit_targets.append(PauseHitTarget(_MAIN_ACTIONS[index][0], button.last_rect, index, button))
        return PauseMenuLayout(
            state="main",
            selected_index=self.selected_index,
            selected_save_index=self.selected_save_index,
            settings_index=self._settings_index,
            window_size=self._window_size(),
            instructions=result.instructions,
            hit_targets=hit_targets,
        )

    def _layout_save(self) -> PauseMenuLayout:
        panel_bounds = self._panel_bounds(height_scale=0.64, min_height=330.0, max_height=500.0)
        inner = panel_bounds.inset(Padding.uniform(18.0))
        title_bounds = Rect(inner.x, inner.top - 44.0, inner.width, 44.0)
        footer_bounds = Rect(inner.x, inner.y, inner.width, 34.0)
        list_bounds = Rect(inner.x, footer_bounds.top + 12.0, inner.width, max(80.0, title_bounds.bottom - footer_bounds.top - 24.0))
        items = [*self.save_slots, "<New Save>", "Back"]
        self.selected_save_index = self._clamp_index(self.selected_save_index, len(items))
        self._save_scroll.items = items
        self._save_scroll.selected_index = self.selected_save_index
        self._save_scroll.ensure_visible(self.selected_save_index)
        list_layout = self._save_scroll.layout(list_bounds)
        instructions = [
            DrawInstruction("panel_bg", {"rect": panel_bounds, "style_token": "pause_panel"}),
            *Label(text="SAVE GAME", font_size=28, height=44.0).layout(title_bounds).instructions,
            *list_layout.instructions,
            *Label(text="Esc/B: Back", font_size=14, color_token="gray", height=34.0).layout(footer_bounds).instructions,
        ]
        hit_targets: list[PauseHitTarget] = []
        for row_index, _text, rect, _selected in self._save_scroll.visible_rows:
            hit_targets.append(PauseHitTarget(self._save_action_id(row_index), rect, row_index, self._save_scroll))
        return PauseMenuLayout(
            state="save",
            selected_index=self.selected_index,
            selected_save_index=self.selected_save_index,
            settings_index=self._settings_index,
            window_size=self._window_size(),
            instructions=instructions,
            hit_targets=hit_targets,
        )

    def _layout_load(self) -> PauseMenuLayout:
        panel_bounds = self._panel_bounds(height_scale=0.64, min_height=330.0, max_height=500.0)
        inner = panel_bounds.inset(Padding.uniform(18.0))
        title_bounds = Rect(inner.x, inner.top - 44.0, inner.width, 44.0)
        footer_bounds = Rect(inner.x, inner.y, inner.width, 34.0)
        list_bounds = Rect(inner.x, footer_bounds.top + 12.0, inner.width, max(80.0, title_bounds.bottom - footer_bounds.top - 24.0))
        content_items = self.save_slots if self.save_slots else ["No saves found"]
        items = [*content_items, "Back"]
        back_index = len(items) - 1
        if not self.save_slots and self.selected_save_index == 0:
            self.selected_save_index = back_index
        self.selected_save_index = self._clamp_index(self.selected_save_index, len(items))
        self._load_scroll.items = items
        self._load_scroll.selected_index = self.selected_save_index
        self._load_scroll.ensure_visible(self.selected_save_index)
        list_layout = self._load_scroll.layout(list_bounds)
        instructions = [
            DrawInstruction("panel_bg", {"rect": panel_bounds, "style_token": "pause_panel"}),
            *Label(text="LOAD GAME", font_size=28, height=44.0).layout(title_bounds).instructions,
            *list_layout.instructions,
            *Label(text="Esc/B: Back", font_size=14, color_token="gray", height=34.0).layout(footer_bounds).instructions,
        ]
        hit_targets: list[PauseHitTarget] = []
        for row_index, _text, rect, _selected in self._load_scroll.visible_rows:
            if not self.save_slots and row_index == 0:
                continue
            hit_targets.append(PauseHitTarget(self._load_action_id(row_index), rect, row_index, self._load_scroll))
        return PauseMenuLayout(
            state="load",
            selected_index=self.selected_index,
            selected_save_index=self.selected_save_index,
            settings_index=self._settings_index,
            window_size=self._window_size(),
            instructions=instructions,
            hit_targets=hit_targets,
        )

    def _layout_settings(self) -> PauseMenuLayout:
        panel_bounds = self._panel_bounds(height_scale=0.66, min_height=350.0, max_height=520.0)
        settings = self._runtime_settings()
        self._sync_settings_widgets(settings)
        title = Label(text="SETTINGS", font_size=28, color_token="white", height=44.0)
        rows: list[Any] = [title]
        hit_targets: list[PauseHitTarget] = []
        for index, (key, _label, kind) in enumerate(self._SETTINGS_ROWS):
            widget = self._settings_widgets[key]
            if isinstance(widget, Button):
                widget.text_color_token = "yellow" if index == self._settings_index else "gray"
                widget.bg_style_token = "selected" if index == self._settings_index else "idle"
            rows.append(widget)
        stack = VStack(children=rows, spacing=10.0, align="stretch")
        result = Panel(children=[stack], padding=Padding.uniform(18.0), bg_style_token="pause_panel").layout(panel_bounds)
        for index, (key, _label, _kind) in enumerate(self._SETTINGS_ROWS):
            widget = self._settings_widgets[key]
            rect = getattr(widget, "last_rect", None)
            if isinstance(rect, Rect):
                hit_targets.append(PauseHitTarget(self._settings_action_id(key), rect, index, widget))
        return PauseMenuLayout(
            state="settings",
            selected_index=self.selected_index,
            selected_save_index=self.selected_save_index,
            settings_index=self._settings_index,
            window_size=self._window_size(),
            instructions=result.instructions,
            hit_targets=hit_targets,
        )

    def _sync_settings_widgets(self, settings: Any) -> None:
        music = self._settings_widgets["music_volume"]
        sfx = self._settings_widgets["sfx_volume"]
        fog = self._settings_widgets["fog_enabled"]
        shadows = self._settings_widgets["soft_shadows_enabled"]
        if isinstance(music, Slider):
            music.value = float(settings.music_volume)
        if isinstance(sfx, Slider):
            sfx.value = float(settings.sfx_volume)
        if isinstance(fog, Toggle):
            fog.value = bool(settings.fog_enabled)
        if isinstance(shadows, Toggle):
            shadows.value = bool(settings.soft_shadows_enabled)

    def _save_action_id(self, row_index: int) -> str:
        if row_index < len(self.save_slots):
            return f"pause.save.slot.{row_index}"
        if row_index == len(self.save_slots):
            return "pause.save.new"
        return "pause.save.back"

    def _load_action_id(self, row_index: int) -> str:
        if row_index < len(self.save_slots):
            return f"pause.load.slot.{row_index}"
        return "pause.load.back"

    def _settings_action_id(self, key: str) -> str:
        return f"pause.settings.{key}"

    def _current_action_id(self) -> str | None:
        if self.state == "main":
            return _MAIN_ACTIONS[self._clamp_index(self.selected_index, len(_MAIN_ACTIONS))][0]
        if self.state == "save":
            count = len(self.save_slots) + 2
            return self._save_action_id(self._clamp_index(self.selected_save_index, count))
        if self.state == "load":
            count = len(self.save_slots) + 1 if self.save_slots else 2
            return self._load_action_id(self._clamp_index(self.selected_save_index, count))
        if self.state == "settings":
            key, _label, _kind = self._SETTINGS_ROWS[self._clamp_index(self._settings_index, len(self._SETTINGS_ROWS))]
            return self._settings_action_id(key)
        return None

    @staticmethod
    def _clamp_index(index: int, count: int) -> int:
        if count <= 0:
            return 0
        return max(0, min(int(index), count - 1))

    def _resolve_widget_color(self, token: str, *, selected: bool = False) -> tuple[int, int, int] | tuple[int, int, int, int]:
        normalized = str(token or "").strip().lower()
        if selected:
            return (255, 255, 0)
        if normalized == "yellow":
            return (255, 255, 0)
        if normalized == "gray":
            return (170, 170, 170)
        if normalized == "light_gray":
            return (211, 211, 211)
        if normalized == "black":
            return (0, 0, 0)
        return (255, 255, 255)

    def _safe_draw_rectangle_filled(
        self,
        center_x: float,
        center_y: float,
        width: float,
        height: float,
        color: Any,
    ) -> None:
        try:
            _draw_rectangle_filled(center_x, center_y, width, height, color)
        except (AttributeError, RuntimeError):
            return

    def _safe_draw_text(
        self,
        text: str,
        x: float,
        y: float,
        *,
        color: Any,
        font_size: int,
        anchor_x: str,
        anchor_y: str,
    ) -> None:
        try:
            draw_text_cached(
                text,
                x,
                y,
                color=color,
                font_size=font_size,
                anchor_x=anchor_x,
                anchor_y=anchor_y,
                cache=self._text_cache,
            )
        except (AttributeError, RuntimeError):
            return

    def _draw_widget_instructions(self, instructions: list[DrawInstruction]) -> None:
        for instruction in instructions:
            kind = str(getattr(instruction, "kind", "") or "")
            payload = instruction.payload if isinstance(instruction.payload, dict) else {}
            rect = payload.get("rect")
            if kind == "panel_bg" and isinstance(rect, Rect):
                self._safe_draw_rectangle_filled(rect.center_x, rect.center_y, rect.width, rect.height, (0, 0, 0, 170))
                continue
            if kind == "button_bg" and isinstance(rect, Rect):
                style_token = str(payload.get("style_token", "") or "").strip().lower()
                color = (255, 255, 255, 34) if style_token == "selected" else (0, 0, 0, 0)
                self._safe_draw_rectangle_filled(rect.center_x, rect.center_y, rect.width, rect.height, color)
                continue
            if kind == "scroll_row_bg" and isinstance(rect, Rect):
                color = (255, 255, 255, 34) if bool(payload.get("selected", False)) else (255, 255, 255, 10)
                self._safe_draw_rectangle_filled(rect.center_x, rect.center_y, rect.width, rect.height, color)
                continue
            if kind in {"slider_track", "slider_fill", "slider_knob"} and isinstance(rect, Rect):
                if kind == "slider_track":
                    color = (72, 72, 82, 230)
                elif kind == "slider_fill":
                    color = (255, 220, 90, 230)
                else:
                    color = (240, 240, 245, 255)
                self._safe_draw_rectangle_filled(rect.center_x, rect.center_y, rect.width, rect.height, color)
                continue
            if kind in {"text", "button_text", "slider_label_text", "slider_value_text", "toggle_text", "scroll_row_text"}:
                selected = bool(payload.get("selected", False))
                text = str(payload.get("text", "") or "")
                if kind == "scroll_row_text" and isinstance(rect, Rect):
                    x = rect.left + 14.0
                    y = rect.center_y
                    anchor_x = "left"
                    anchor_y = "center"
                    font_size = 18
                else:
                    x = float(payload.get("x", 0.0) or 0.0)
                    y = float(payload.get("y", 0.0) or 0.0)
                    anchor_x = str(payload.get("anchor_x", "center") or "center")
                    anchor_y = str(payload.get("anchor_y", "center") or "center")
                    font_size = int(payload.get("font_size", 16) or 16)
                self._safe_draw_text(
                    text,
                    x,
                    y,
                    color=self._resolve_widget_color(str(payload.get("color_token", "white") or "white"), selected=selected),
                    font_size=font_size,
                    anchor_x=anchor_x,
                    anchor_y=anchor_y,
                )

    def update(self, dt: float) -> None:  # noqa: ARG002
        if not self.visible:
            return
        manager = getattr(self.window, "input", None)
        if manager is None:
            return
        if getattr(manager, "input_source", "keyboard_mouse") != "gamepad":
            return
        if manager.was_action_pressed("move_up"):
            self._handle_action("up")
        if manager.was_action_pressed("move_down"):
            self._handle_action("down")
        if manager.was_action_pressed("move_left"):
            self._handle_action("left")
        if manager.was_action_pressed("move_right"):
            self._handle_action("right")
        if manager.was_action_pressed("interact"):
            self._handle_action("confirm")
        if manager.was_action_pressed("toggle_help"):
            self._handle_action("back")

    def draw(self) -> None:
        if not self.visible:
            return
        width, height = self._window_size()
        self._safe_draw_rectangle_filled(width / 2.0, height / 2.0, width, height, (0, 0, 0, 150))
        layout = self.layout_current_state()
        self._draw_widget_instructions(layout.instructions)

    def _handle_action(self, action: str, *, large_step: bool = False) -> bool:
        action = str(action)
        if action == "up":
            return self._move_selection(-1)
        if action == "down":
            return self._move_selection(1)
        if action in ("left", "right"):
            if self.state != "settings":
                return True
            delta = 0.1 if large_step else 0.05
            if action == "left":
                delta = -delta
            return self._adjust_setting(delta)
        if action == "confirm":
            action_id = self._current_action_id()
            return self._activate_action(action_id) if action_id is not None else True
        if action == "back":
            return self._activate_back()
        return False

    def _move_selection(self, delta: int) -> bool:
        if self.state == "main":
            self.selected_index = (self.selected_index + int(delta)) % len(_MAIN_ACTIONS)
        elif self.state == "save":
            count = len(self.save_slots) + 2
            self.selected_save_index = (self.selected_save_index + int(delta)) % count
            self._save_scroll.ensure_visible(self.selected_save_index)
        elif self.state == "load":
            count = len(self.save_slots) + 1 if self.save_slots else 2
            self.selected_save_index = (self.selected_save_index + int(delta)) % count
            self._load_scroll.ensure_visible(self.selected_save_index)
        elif self.state == "settings":
            self._settings_index = (self._settings_index + int(delta)) % len(self._SETTINGS_ROWS)
        else:
            return False
        self._play_ui_sound("assets/sounds/ui_hover.wav")
        self._invalidate_layout()
        return True

    def _activate_back(self) -> bool:
        if self.state == "main":
            self._play_ui_sound("assets/sounds/ui_close.wav")
            self.window.paused = False
            self.visible = False
        else:
            self.state = "main"
        self._invalidate_layout()
        return True

    def _activate_action(self, action_id: str | None, *, value: float | bool | None = None) -> bool:
        if action_id is None:
            return False
        action_id = str(action_id)
        if action_id.startswith("pause.main."):
            self._play_ui_sound("assets/sounds/ui_click.wav")
        if action_id == "pause.main.resume":
            self.window.paused = False
            self.visible = False
        elif action_id == "pause.main.settings":
            self.state = "settings"
            self._settings_index = 0
        elif action_id == "pause.main.save":
            self.state = "save"
            self.save_slots = list(self.window.save_manager.list_saves())
            self.selected_save_index = 0
        elif action_id == "pause.main.load":
            self.state = "load"
            self.save_slots = list(self.window.save_manager.list_saves())
            self.selected_save_index = 0
        elif action_id == "pause.main.quit":
            optional_arcade.arcade.close_window()
        elif action_id.startswith("pause.save.slot."):
            self._play_ui_sound("assets/sounds/ui_click.wav")
            index = int(action_id.rsplit(".", 1)[1])
            self.selected_save_index = self._clamp_index(index, len(self.save_slots) + 2)
            self._save_to_slot(self.save_slots[self.selected_save_index])
        elif action_id == "pause.save.new":
            self._play_ui_sound("assets/sounds/ui_click.wav")
            self.selected_save_index = len(self.save_slots)
            self._save_to_slot(self._new_save_slot_name())
        elif action_id == "pause.save.back":
            self.state = "main"
        elif action_id.startswith("pause.load.slot."):
            self._play_ui_sound("assets/sounds/ui_click.wav")
            index = int(action_id.rsplit(".", 1)[1])
            self.selected_save_index = self._clamp_index(index, len(self.save_slots))
            self._load_slot(self.save_slots[self.selected_save_index])
        elif action_id == "pause.load.back":
            self.state = "main"
        elif action_id.startswith("pause.settings."):
            return self._activate_setting(action_id, value=value)
        else:
            return False
        self._invalidate_layout()
        return True

    def _activate_setting(self, action_id: str, *, value: float | bool | None = None) -> bool:
        key = action_id.removeprefix("pause.settings.")
        if key == "back":
            self.state = "main"
            self._invalidate_layout()
            return True
        row = next((row for row in self._SETTINGS_ROWS if row[0] == key), None)
        if row is None:
            return False
        _key, _label, kind = row
        settings = self._runtime_settings()
        if kind == "slider":
            if value is None:
                return False
            setattr(settings, key, max(0.0, min(1.0, float(value))))
            self._apply_runtime_settings()
            return True
        if kind == "toggle":
            next_value = (not bool(getattr(settings, key, False))) if value is None else bool(value)
            setattr(settings, key, next_value)
            self._apply_runtime_settings()
            return True
        return False

    def _new_save_slot_name(self) -> str:
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"save_{timestamp}"

    def _save_to_slot(self, slot_name: str) -> bool:
        self.window.save_manager.save_game(slot_name)
        logger.info("Saved game to '%s'", slot_name)
        self.state = "main"
        return True

    def _load_slot(self, slot_name: str) -> bool:
        if self._confirm_unsaved_action("Load Game", lambda: self.window.save_manager.load_game(slot_name)):
            return True
        self.window.save_manager.load_game(slot_name)
        self.window.paused = False
        self.visible = False
        return True

    def _confirm_unsaved_action(self, reason: str, action: Any) -> bool:
        editor = getattr(self.window, "editor_controller", None)
        if editor is None or not getattr(editor, "active", False):
            return False
        blocker = getattr(editor, "confirm_unsaved_changes", None)
        if callable(blocker):
            blocked = blocker(reason, action)
            return isinstance(blocked, bool) and blocked
        return False

    def _adjust_setting(self, delta: float) -> bool:
        key, _label, kind = self._SETTINGS_ROWS[self._settings_index]
        if kind != "slider":
            return True
        settings = self._runtime_settings()
        current = float(getattr(settings, key, 0.0))
        return self._activate_action(self._settings_action_id(key), value=current + float(delta))

    def _confirm_setting(self) -> bool:
        action_id = self._current_action_id()
        return self._activate_action(action_id) if action_id is not None else True

    def on_key_press(self, key: int, modifiers: int = 0) -> bool:
        if not self.visible:
            return False
        arcade_key = optional_arcade.arcade.key
        if key in (arcade_key.UP, arcade_key.W):
            return self._handle_action("up")
        if key in (arcade_key.DOWN, arcade_key.S):
            return self._handle_action("down")
        if self.state == "settings" and key in (arcade_key.LEFT, arcade_key.MINUS):
            return self._handle_action("left", large_step=bool(modifiers & arcade_key.MOD_SHIFT))
        if self.state == "settings" and key in (arcade_key.RIGHT, arcade_key.EQUAL):
            return self._handle_action("right", large_step=bool(modifiers & arcade_key.MOD_SHIFT))
        if key in (arcade_key.ENTER, arcade_key.RETURN, arcade_key.SPACE):
            return self._handle_action("confirm")
        if key == arcade_key.ESCAPE:
            return self._handle_action("back")
        return True

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int = 0) -> bool:  # noqa: ARG002
        if not self.visible:
            return False
        if int(button) != int(optional_arcade.arcade.MOUSE_BUTTON_LEFT):
            return True
        layout = self.layout_current_state()
        target = layout.target_at(float(x), float(y))
        if target is None:
            return True
        if self.state == "main":
            self.selected_index = target.index
            return self._activate_action(target.action_id)
        if self.state in {"save", "load"}:
            self.selected_save_index = target.index
            return self._activate_action(target.action_id)
        if self.state == "settings":
            self._settings_index = target.index
            widget = target.widget
            if isinstance(widget, Slider):
                if widget.on_mouse_press(float(x), float(y)):
                    return self._activate_action(target.action_id, value=widget.value)
                return True
            if isinstance(widget, Toggle):
                return self._activate_action(target.action_id)
            return self._activate_action(target.action_id)
        return True
