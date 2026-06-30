from __future__ import annotations

from typing import Any


def dispose_game_window(window: Any) -> None:
    """Close a live GameWindow and clear arcade's global window singleton."""
    import engine.optional_arcade as optional_arcade

    try:
        close = getattr(window, "close", None)
        if callable(close):
            close()
    finally:
        arcade = optional_arcade.arcade
        close_window = getattr(arcade, "close_window", None)
        if callable(close_window):
            try:
                close_window()
            except Exception:
                pass
