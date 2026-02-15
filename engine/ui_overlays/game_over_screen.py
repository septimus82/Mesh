"""Game-over screen overlay."""

from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade

from .common import UIElement, _draw_rectangle_filled

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


class GameOverScreen(UIElement):
    """Screen displayed when the player dies."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self.visible = False
        self._title = optional_arcade.arcade.Text(
            text="YOU DIED",
            x=window.width / 2,
            y=window.height / 2 + 50,
            color=optional_arcade.arcade.color.RED,
            font_size=40,
            anchor_x="center",
            anchor_y="center",
            bold=True
        )
        self._subtitle = optional_arcade.arcade.Text(
            text="Press SPACE to Retry",
            x=window.width / 2,
            y=window.height / 2 - 20,
            color=optional_arcade.arcade.color.WHITE,
            font_size=20,
            anchor_x="center",
            anchor_y="center"
        )

    @property
    def blocks_input(self) -> bool:
        return self.visible

    def draw(self) -> None:
        if not self.visible:
            return

        _draw_rectangle_filled(
            center_x=self.window.width / 2,
            center_y=self.window.height / 2,
            width=self.window.width,
            height=self.window.height,
            color=(0, 0, 0, 200)
        )

        self._title.x = self.window.width / 2
        self._title.y = self.window.height / 2 + 50
        self._title.draw()

        self._subtitle.x = self.window.width / 2
        self._subtitle.y = self.window.height / 2 - 20
        self._subtitle.draw()
