"""Demo-complete end-cap overlay and trigger helper."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade

from .common import (
    UIElement,
    _draw_lrtb_rectangle_outline,
    _draw_rectangle_filled,
)
from ..text_draw import TextCache, draw_text_cached

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow

DEMO_COMPLETE_ENDCAP_SECONDS = 4.0


class DemoCompleteOverlay(UIElement):
    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible = False
        self._remaining_seconds = 0.0
        self._text_cache = TextCache()

    def show(self, *, seconds: float = DEMO_COMPLETE_ENDCAP_SECONDS) -> None:
        self.visible = True
        self._remaining_seconds = max(0.0, float(seconds))

    def update(self, dt: float) -> None:
        if not self.visible:
            return
        self._remaining_seconds -= float(dt)
        if self._remaining_seconds <= 0.0:
            self.visible = False
            self._remaining_seconds = 0.0

    def draw(self) -> None:
        if not self.visible:
            return

        width = min(560.0, max(320.0, self.window.width - 80.0))
        height = 100.0
        left = (self.window.width - width) / 2.0
        right = left + width
        top = self.window.height - 70.0
        bottom = top - height

        _draw_rectangle_filled(
            center_x=(left + right) / 2.0,
            center_y=(top + bottom) / 2.0,
            width=width,
            height=height,
            color=(0, 0, 0, 190),
        )
        _draw_lrtb_rectangle_outline(left, right, top, bottom, optional_arcade.arcade.color.GOLD, 2)

        draw_text_cached(
            "DEMO COMPLETE",
            (left + right) / 2.0,
            (top + bottom) / 2.0 + 6.0,
            color=optional_arcade.arcade.color.GOLD,
            font_size=20,
            anchor_x="center",
            anchor_y="center",
            bold=True,
            font_name=("Consolas", "Courier New", "Courier"),
            cache=self._text_cache,
        )
        draw_text_cached(
            "Thanks for playing!",
            (left + right) / 2.0,
            (top + bottom) / 2.0 - 18.0,
            color=optional_arcade.arcade.color.LIGHT_GRAY,
            font_size=12,
            anchor_x="center",
            anchor_y="center",
            font_name=("Consolas", "Courier New", "Courier"),
            cache=self._text_cache,
        )


def maybe_trigger_demo_complete_endcap(
    window: Any,
    *,
    previous: bool,
    current: bool,
    seconds: float = DEMO_COMPLETE_ENDCAP_SECONDS,
) -> bool:
    """
    Trigger a one-shot "Demo Complete" end-cap on a false->true transition.

    This is intentionally UI-only and safe to call from stub windows in tests.
    """

    if bool(previous):
        return False
    if not bool(current):
        return False

    if bool(getattr(window, "_mesh_demo_complete_endcap_seen", False)):
        return False
    setattr(window, "_mesh_demo_complete_endcap_seen", True)

    overlay = getattr(window, "demo_complete_overlay", None)
    show = getattr(overlay, "show", None) if overlay is not None else None
    if callable(show):
        show(seconds=float(seconds))
        return True
    return False
