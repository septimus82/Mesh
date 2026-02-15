"""Pause menu overlay with save/load and settings sub-menus."""

from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade
from engine.logging_tools import get_logger

from .common import UIElement, _draw_rectangle_filled
from ..text_draw import TextCache, draw_text_cached
from ._settings_data import SETTINGS_ROWS

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow

logger = get_logger(__name__)


class PauseMenu(UIElement):
    """Menu displayed when the game is paused."""

    _SETTINGS_ROWS = SETTINGS_ROWS

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible = False
        self.options = ["Resume", "Settings", "Save Game", "Load Game", "Quit"]
        self.selected_index = 0
        self.state = "main"  # main, save, load, settings
        self.save_slots: list[str] = []
        self.selected_save_index = 0
        self._settings_index = 0
        self._text_cache = TextCache()

        self._title = optional_arcade.arcade.Text(
            text="PAUSED",
            x=window.width / 2,
            y=window.height / 2 + 80,
            color=optional_arcade.arcade.color.WHITE,
            font_size=30,
            anchor_x="center",
            anchor_y="center",
            bold=True
        )

    def toggle(self) -> bool:
        self.visible = not self.visible
        if self.visible:
            self.selected_index = 0
            self.state = "main"
            self._settings_index = 0
        return self.visible

    @property
    def blocks_input(self) -> bool:
        return self.visible

    def _play_ui_sound(self, path: str) -> None:
        if hasattr(self.window, "audio"):
            self.window.audio.play_sound(path)

    def _runtime_settings(self):
        from ..runtime_settings import ensure_runtime_settings  # noqa: PLC0415

        return ensure_runtime_settings(self.window)

    def _apply_runtime_settings(self) -> None:
        settings = self._runtime_settings()
        settings.apply(self.window)
        saver = getattr(self, "_save_runtime_settings", None)
        if callable(saver):
            saver()

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

        _draw_rectangle_filled(
            center_x=self.window.width / 2,
            center_y=self.window.height / 2,
            width=self.window.width,
            height=self.window.height,
            color=(0, 0, 0, 150)
        )

        if self.state == "main":
            self._draw_main_menu()
        elif self.state == "save":
            self._draw_save_menu()
        elif self.state == "load":
            self._draw_load_menu()
        elif self.state == "settings":
            self._draw_settings_menu()

    def _draw_main_menu(self) -> None:
        self._title.text = "PAUSED"
        self._title.x = self.window.width / 2
        self._title.y = self.window.height / 2 + 100
        self._title.draw()

        start_y = self.window.height / 2 + 20
        for i, option in enumerate(self.options):
            color = optional_arcade.arcade.color.YELLOW if i == self.selected_index else optional_arcade.arcade.color.GRAY
            draw_text_cached(
                option,
                self.window.width / 2,
                start_y - i * 40,
                color=color,
                font_size=20,
                anchor_x="center",
                anchor_y="center",
                cache=self._text_cache,
            )

    def _draw_save_menu(self) -> None:
        self._title.text = "SAVE GAME"
        self._title.x = self.window.width / 2
        self._title.y = self.window.height / 2 + 100
        self._title.draw()

        start_y = self.window.height / 2 + 20
        slots_to_show = self.save_slots + ["<New Save>"]

        for i, slot in enumerate(slots_to_show):
            color = optional_arcade.arcade.color.YELLOW if i == self.selected_save_index else optional_arcade.arcade.color.GRAY
            draw_text_cached(
                slot,
                self.window.width / 2,
                start_y - i * 40,
                color=color,
                font_size=20,
                anchor_x="center",
                anchor_y="center",
                cache=self._text_cache,
            )

        draw_text_cached("Press ESC to return", self.window.width / 2, 50, color=optional_arcade.arcade.color.GRAY, font_size=14, anchor_x="center", cache=self._text_cache)

    def _draw_load_menu(self) -> None:
        self._title.text = "LOAD GAME"
        self._title.x = self.window.width / 2
        self._title.y = self.window.height / 2 + 100
        self._title.draw()

        if not self.save_slots:
            draw_text_cached("No saves found", self.window.width / 2, self.window.height / 2, color=optional_arcade.arcade.color.GRAY, font_size=20, anchor_x="center", cache=self._text_cache)
            draw_text_cached("Press ESC to return", self.window.width / 2, 50, color=optional_arcade.arcade.color.GRAY, font_size=14, anchor_x="center", cache=self._text_cache)
            return

        start_y = self.window.height / 2 + 20
        for i, slot in enumerate(self.save_slots):
            color = optional_arcade.arcade.color.YELLOW if i == self.selected_save_index else optional_arcade.arcade.color.GRAY
            draw_text_cached(
                slot,
                self.window.width / 2,
                start_y - i * 40,
                color=color,
                font_size=20,
                anchor_x="center",
                anchor_y="center",
                cache=self._text_cache,
            )

        draw_text_cached("Press ESC to return", self.window.width / 2, 50, color=optional_arcade.arcade.color.GRAY, font_size=14, anchor_x="center", cache=self._text_cache)

    def _draw_settings_menu(self) -> None:
        self._title.text = "SETTINGS"
        self._title.x = self.window.width / 2
        self._title.y = self.window.height / 2 + 120
        self._title.draw()

        settings = self._runtime_settings()
        start_y = self.window.height / 2 + 40
        for i, (key, label, kind) in enumerate(self._SETTINGS_ROWS):
            color = optional_arcade.arcade.color.YELLOW if i == self._settings_index else optional_arcade.arcade.color.GRAY
            value = ""
            if kind == "slider":
                if key == "music_volume":
                    value = f"{int(round(settings.music_volume * 100.0))}%"
                elif key == "sfx_volume":
                    value = f"{int(round(settings.sfx_volume * 100.0))}%"
            elif kind == "toggle":
                enabled = bool(getattr(settings, key, False))
                value = "ON" if enabled else "OFF"
            text = f"{label}: {value}" if value else label
            draw_text_cached(
                text,
                self.window.width / 2,
                start_y - i * 36,
                color=color,
                font_size=18,
                anchor_x="center",
                anchor_y="center",
                cache=self._text_cache,
            )

        draw_text_cached(
            "Enter/A: Toggle   Left/Right: Adjust   Esc/B: Back",
            self.window.width / 2,
            50,
            color=optional_arcade.arcade.color.GRAY,
            font_size=14,
            anchor_x="center",
            cache=self._text_cache,
        )

    def _handle_action(self, action: str, *, large_step: bool = False) -> bool:
        action = str(action)
        if self.state == "main":
            if action == "up":
                self.selected_index = (self.selected_index - 1) % len(self.options)
                self._play_ui_sound("assets/sounds/ui_hover.wav")
                return True
            if action == "down":
                self.selected_index = (self.selected_index + 1) % len(self.options)
                self._play_ui_sound("assets/sounds/ui_hover.wav")
                return True
            if action == "confirm":
                return self._confirm_main()
            if action == "back":
                self._play_ui_sound("assets/sounds/ui_close.wav")
                self.window.paused = False
                self.visible = False
                return True
            return False

        if self.state == "save":
            slots_to_show = self.save_slots + ["<New Save>"]
            if action == "up":
                self.selected_save_index = (self.selected_save_index - 1) % len(slots_to_show)
                self._play_ui_sound("assets/sounds/ui_hover.wav")
                return True
            if action == "down":
                self.selected_save_index = (self.selected_save_index + 1) % len(slots_to_show)
                self._play_ui_sound("assets/sounds/ui_hover.wav")
                return True
            if action == "confirm":
                self._play_ui_sound("assets/sounds/ui_click.wav")
                return self._confirm_save(slots_to_show)
            if action == "back":
                self.state = "main"
                return True
            return False

        if self.state == "load":
            if not self.save_slots:
                if action in ("back", "confirm"):
                    self.state = "main"
                return True
            if action == "up":
                self.selected_save_index = (self.selected_save_index - 1) % len(self.save_slots)
                self._play_ui_sound("assets/sounds/ui_hover.wav")
                return True
            if action == "down":
                self.selected_save_index = (self.selected_save_index + 1) % len(self.save_slots)
                self._play_ui_sound("assets/sounds/ui_hover.wav")
                return True
            if action == "confirm":
                self._play_ui_sound("assets/sounds/ui_click.wav")
                slot_name = self.save_slots[self.selected_save_index]
                if self._confirm_unsaved_action("Load Game", lambda: self.window.save_manager.load_game(slot_name)):
                    return True
                self.window.save_manager.load_game(slot_name)
                self.window.paused = False
                self.visible = False
                return True
            if action == "back":
                self.state = "main"
                return True
            return False

        if self.state == "settings":
            if action == "up":
                self._settings_index = (self._settings_index - 1) % len(self._SETTINGS_ROWS)
                self._play_ui_sound("assets/sounds/ui_hover.wav")
                return True
            if action == "down":
                self._settings_index = (self._settings_index + 1) % len(self._SETTINGS_ROWS)
                self._play_ui_sound("assets/sounds/ui_hover.wav")
                return True
            if action in ("left", "right"):
                delta = 0.1 if large_step else 0.05
                if action == "left":
                    delta = -delta
                return self._adjust_setting(delta)
            if action == "confirm":
                return self._confirm_setting()
            if action == "back":
                self.state = "main"
                return True
            return False

        return False

    def _confirm_unsaved_action(self, reason: str, action) -> bool:
        editor = getattr(self.window, "editor_controller", None)
        if editor is None or not getattr(editor, "active", False):
            return False
        blocker = getattr(editor, "confirm_unsaved_changes", None)
        if callable(blocker):
            blocked = blocker(reason, action)
            return isinstance(blocked, bool) and blocked
        return False

    def _confirm_main(self) -> bool:
        self._play_ui_sound("assets/sounds/ui_click.wav")
        option = self.options[self.selected_index]
        if option == "Resume":
            self.window.paused = False
            self.visible = False
            return True
        if option == "Settings":
            self.state = "settings"
            self._settings_index = 0
            return True
        if option == "Save Game":
            self.state = "save"
            self.save_slots = self.window.save_manager.list_saves()
            self.selected_save_index = 0
            return True
        if option == "Load Game":
            self.state = "load"
            self.save_slots = self.window.save_manager.list_saves()
            self.selected_save_index = 0
            return True
        if option == "Quit":
            optional_arcade.arcade.close_window()
            return True
        return True

    def _confirm_save(self, slots_to_show: list[str]) -> bool:
        slot_name = slots_to_show[self.selected_save_index]
        if slot_name == "<New Save>":
            import datetime

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            slot_name = f"save_{timestamp}"

        self.window.save_manager.save_game(slot_name)
        logger.info("Saved game to '%s'", slot_name)
        self.state = "main"
        return True

    def _adjust_setting(self, delta: float) -> bool:
        key, _label, kind = self._SETTINGS_ROWS[self._settings_index]
        settings = self._runtime_settings()
        if kind != "slider":
            return False
        if key == "music_volume":
            settings.music_volume = max(0.0, min(1.0, float(settings.music_volume) + delta))
        elif key == "sfx_volume":
            settings.sfx_volume = max(0.0, min(1.0, float(settings.sfx_volume) + delta))
        else:
            return False
        self._apply_runtime_settings()
        return True

    def _confirm_setting(self) -> bool:
        key, _label, kind = self._SETTINGS_ROWS[self._settings_index]
        settings = self._runtime_settings()
        if kind == "toggle":
            current = bool(getattr(settings, key, False))
            setattr(settings, key, not current)
            self._apply_runtime_settings()
            return True
        if kind == "action" and key == "back":
            self.state = "main"
            return True
        return False

    def on_key_press(self, key: int, modifiers: int = 0) -> bool:
        if not self.visible:
            return False

        if self.state == "main":
            if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.W):
                return self._handle_action("up")
            if key in (optional_arcade.arcade.key.DOWN, optional_arcade.arcade.key.S):
                return self._handle_action("down")
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
                return self._handle_action("confirm")
            if key == optional_arcade.arcade.key.ESCAPE:
                return self._handle_action("back")

        elif self.state == "save":
            if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.W):
                return self._handle_action("up")
            if key in (optional_arcade.arcade.key.DOWN, optional_arcade.arcade.key.S):
                return self._handle_action("down")
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
                return self._handle_action("confirm")
            if key == optional_arcade.arcade.key.ESCAPE:
                return self._handle_action("back")

        elif self.state == "load":
            if not self.save_slots:
                if key in (optional_arcade.arcade.key.ESCAPE, optional_arcade.arcade.key.ENTER):
                    self.state = "main"
                return True

            if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.W):
                return self._handle_action("up")
            if key in (optional_arcade.arcade.key.DOWN, optional_arcade.arcade.key.S):
                return self._handle_action("down")
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
                return self._handle_action("confirm")
            if key == optional_arcade.arcade.key.ESCAPE:
                return self._handle_action("back")

        elif self.state == "settings":
            if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.W):
                return self._handle_action("up")
            if key in (optional_arcade.arcade.key.DOWN, optional_arcade.arcade.key.S):
                return self._handle_action("down")
            if key in (optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.MINUS):
                return self._handle_action("left", large_step=bool(modifiers & optional_arcade.arcade.key.MOD_SHIFT))
            if key in (optional_arcade.arcade.key.RIGHT, optional_arcade.arcade.key.EQUAL):
                return self._handle_action("right", large_step=bool(modifiers & optional_arcade.arcade.key.MOD_SHIFT))
            if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
                return self._handle_action("confirm")
            if key == optional_arcade.arcade.key.ESCAPE:
                return self._handle_action("back")

        return True  # Block other input while paused
