"""Help overlay showing controls and common hotkeys."""

from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade

from .common import (
    UIElement,
    _draw_tb_rectangle_outline,
    _draw_rectangle_filled,
)
from ..input_hints import get_action_hint, set_keyboard_hints
from ..text_draw import TextCache, draw_text_cached

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


class HelpOverlay(UIElement):
    """Simple overlay that lists controls and common hotkeys."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible: bool = False
        self._body_text = self._build_body_text()
        self._text_cache = TextCache()

    def _build_body_text(self) -> str:
        lines = [
            "Movement: W A S D",
            "Interact: E",
            "Attack: Space",
            "",
            "Q: Quest Log",
            "Tab: Inventory",
            "I: Inspector",
            "C: Character",
            "F2: Editor",
            "H: Help",
            "V: Golden Slice Variants",
            "",
            "F1: Command Palette (Debug)",
            "~ / Insert: Dev Console (Debug)",
            "F3: Toggle Debug Mode",
            "Esc: Pause",
            "",
            "Lighting demos:",
            "mesh run-preset lighting-shadowmask-demo",
            "mesh run-preset lighting-shadowmask-demo-debug",
        ]
        return "\n".join(lines)

    def toggle(self) -> bool:
        self.visible = not self.visible
        if hasattr(self.window, "audio"):
            sound = "assets/sounds/ui_open.wav" if self.visible else "assets/sounds/ui_close.wav"
            self.window.audio.play_sound(sound)
        return self.visible

    def set_visible(self, value: bool) -> None:
        self.visible = bool(value)

    @property
    def blocks_input(self) -> bool:
        return self.visible

    def on_key_press(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        if not self.visible:
            return False
        if key in (optional_arcade.arcade.key.H, optional_arcade.arcade.key.ESCAPE):
            self.toggle() if key == optional_arcade.arcade.key.H else self.set_visible(False)
            return True
        return True

    def draw(self) -> None:
        if not self.visible:
            return

        width = min(620.0, max(360.0, self.window.width - 120.0))
        height = min(420.0, max(240.0, self.window.height - 160.0))
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
        _draw_tb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.SKY_BLUE, 2)

        text_left = left + 40.0
        title_y = top - 20.0
        draw_text_cached(
            "Help / Controls",
            text_left,
            title_y,
            color=optional_arcade.arcade.color.WHITE,
            font_size=20,
            anchor_y="top",
            cache=self._text_cache,
        )
        input_source = "keyboard_mouse"
        manager = getattr(getattr(self.window, "input_controller", None), "manager", None)
        if manager is not None:
            input_source = str(getattr(manager, "input_source", input_source))
        bindings = getattr(getattr(self.window, "input_controller", None), "get_bindings_as_names", None)
        if callable(bindings):
            set_keyboard_hints(bindings())
        hint_parts = []
        for action, label in (
            ("interact", "Interact"),
            ("toggle_help", "Back"),
            ("attack", "Attack"),
            ("pause_menu", "Pause"),
        ):
            hint = get_action_hint(action, input_source)
            if hint:
                hint_parts.append(f"{hint} {label}")
        if hint_parts:
            draw_text_cached(
                "  ".join(hint_parts),
                text_left,
                title_y - 26.0,
                color=optional_arcade.arcade.color.LIGHT_GRAY,
                font_size=13,
                anchor_y="top",
                cache=self._text_cache,
            )
        draw_text_cached(
            self._body_text,
            text_left,
            title_y - 40.0,
            color=optional_arcade.arcade.color.LIGHT_GRAY,
            font_size=13,
            width=int(width - 80.0),
            multiline=True,
            anchor_y="top",
            cache=self._text_cache,
        )
