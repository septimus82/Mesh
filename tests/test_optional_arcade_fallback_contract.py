from __future__ import annotations

import engine.optional_arcade as optional_arcade
from engine import arcade_fallback


def test_optional_arcade_always_available() -> None:
    arcade = optional_arcade.arcade
    assert arcade is not None

    assert hasattr(arcade, "Window")
    assert hasattr(arcade, "Sprite")
    assert hasattr(arcade, "key")
    assert hasattr(arcade, "MOUSE_BUTTON_LEFT")

    if not optional_arcade.HAS_ARCADE:
        window = arcade.Window()
        sprite = arcade.Sprite()
        assert window is not None
        assert sprite is not None
        assert arcade is arcade_fallback
