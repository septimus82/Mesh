"""Standalone settings overlay (keyboard-only keybinding editor)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade

from .common import (
    UIElement,
    _draw_lrtb_rectangle_outline,
    _draw_rectangle_filled,
)
from ..text_draw import TextCache, draw_text_cached

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


class SettingsOverlay(UIElement):
    """
    Minimal settings UI (keyboard-only).

    - ESC: open/close
    - Up/Down: navigate
    - Enter: remap keybind / activate close
    - Left/Right: adjust volume
    """

    _ACTIONS: tuple[str, ...] = (
        "move_up",
        "move_down",
        "move_left",
        "move_right",
        "interact",
        "attack",
    )

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible = False
        self._paused_before_open: bool = False
        self._selection_index: int = 0
        self._capture_action: str | None = None
        self._dirty: bool = False
        self._text_cache = TextCache()

        from ..settings import load_settings, resolve_settings_path  # noqa: PLC0415

        self._settings_path = resolve_settings_path()
        self.settings = load_settings(self._settings_path)

        self._rows: list[tuple[str, str]] = []
        self._rebuild_rows()

    def _rebuild_rows(self) -> None:
        self._rows = [(f"Keybind: {action}", action) for action in self._ACTIONS]
        self._rows.extend(
            [
                ("Audio: SFX Volume", "sfx_volume"),
                ("Audio: Music Volume", "music_volume"),
                ("Save & Close", "close"),
            ]
        )

    @property
    def blocks_input(self) -> bool:
        return bool(self.visible)

    def toggle(self) -> bool:
        if self.visible:
            self.close()
        else:
            self.open()
        return self.visible

    def open(self) -> None:
        self.visible = True
        self._paused_before_open = bool(getattr(self.window, "paused", False))
        setattr(self.window, "paused", True)
        self._selection_index = 0
        self._capture_action = None
        self._dirty = False

    def close(self) -> None:
        self.visible = False
        self._capture_action = None
        if not self._paused_before_open:
            setattr(self.window, "paused", False)
        self._paused_before_open = False
        if self._dirty:
            self.save()
        self._dirty = False

    def save(self) -> None:
        from ..settings import save_settings  # noqa: PLC0415

        save_settings(self._settings_path, self.settings)

    def apply(self) -> None:
        from ..settings import apply_settings  # noqa: PLC0415

        apply_settings(self.window, self.settings)

    def _key_name(self, code: int | None) -> str:
        if code is None:
            return "-"
        try:
            return str(optional_arcade.arcade.key.key_string(int(code)))
        except Exception:
            return str(code)

    def get_lines(self) -> list[str]:
        from ..settings import resolve_settings_path  # noqa: PLC0415

        rows: list[str] = ["Settings (ESC)"]
        rows.append(f"path: {resolve_settings_path(self._settings_path).as_posix()}")
        rows.append("")
        for idx, (label, key) in enumerate(self._rows):
            prefix = ">" if idx == self._selection_index else " "
            suffix = ""
            if key in self._ACTIONS:
                code = self.settings.keybinds.get(key)
                if code is None:
                    manager = getattr(getattr(self.window, "input_controller", None), "manager", None)
                    get_bindings = getattr(manager, "get_bindings", None) if manager is not None else None
                    bindings = get_bindings() if callable(get_bindings) else {}
                    codes = bindings.get(key, []) if isinstance(bindings, dict) else []
                    code = int(codes[0]) if codes else None
                suffix = f": {self._key_name(code)}"
                if self._capture_action == key:
                    suffix = ": [press a key...]"
            elif key == "sfx_volume":
                suffix = f": {int(round(float(self.settings.sfx_volume) * 100.0)):d}%"
            elif key == "music_volume":
                suffix = f": {int(round(float(self.settings.music_volume) * 100.0)):d}%"
            rows.append(f"{prefix} {label}{suffix}")
        return rows

    def on_key_press(self, key: int, modifiers: int = 0) -> bool:  # noqa: ARG002
        if not self.visible:
            return False

        if self._capture_action is not None:
            if key == optional_arcade.arcade.key.ESCAPE:
                self._capture_action = None
                return True

            action = self._capture_action
            self._capture_action = None
            self.settings.keybinds[str(action)] = int(key)
            self.apply()
            self._dirty = True
            return True

        if key == optional_arcade.arcade.key.ESCAPE:
            self.close()
            return True

        if key in (optional_arcade.arcade.key.UP, optional_arcade.arcade.key.W):
            self._selection_index = (self._selection_index - 1) % len(self._rows)
            return True
        if key in (optional_arcade.arcade.key.DOWN, optional_arcade.arcade.key.S):
            self._selection_index = (self._selection_index + 1) % len(self._rows)
            return True

        _, row_key = self._rows[self._selection_index]
        if row_key in ("sfx_volume", "music_volume") and key in (optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.RIGHT, optional_arcade.arcade.key.MINUS, optional_arcade.arcade.key.EQUAL):
            delta = 0.05 if key in (optional_arcade.arcade.key.RIGHT, optional_arcade.arcade.key.EQUAL) else -0.05
            if row_key == "sfx_volume":
                self.settings.sfx_volume = max(0.0, min(1.0, float(self.settings.sfx_volume) + delta))
            else:
                self.settings.music_volume = max(0.0, min(1.0, float(self.settings.music_volume) + delta))
            self.apply()
            self._dirty = True
            return True

        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.SPACE):
            if row_key in self._ACTIONS:
                self._capture_action = str(row_key)
                return True
            if row_key == "close":
                self.close()
                return True

        return True

    def draw(self) -> None:
        if not self.visible:
            return

        lines = self.get_lines()
        text = "\n".join(lines)

        width = min(680.0, max(440.0, self.window.width - 80.0))
        height = min(520.0, max(280.0, self.window.height - 140.0))
        left = (self.window.width - width) / 2.0
        right = left + width
        bottom = (self.window.height - height) / 2.0
        top = bottom + height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 210),
        )
        _draw_lrtb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        draw_text_cached(
            text,
            left + 20.0,
            top - 20.0,
            color=optional_arcade.arcade.color.LIGHT_GRAY,
            font_size=14,
            anchor_y="top",
            font_name=("Consolas", "Courier New", "Courier"),
            cache=self._text_cache,
        )
