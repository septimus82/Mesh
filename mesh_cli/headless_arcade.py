from __future__ import annotations

import sys
import types
from typing import Any, cast


def install_arcade_stub_if_missing() -> None:
    """Best-effort `arcade` stub so headless CLI tooling can import engine modules.

    This is intentionally minimal and only intended to support import-time wiring
    and validation paths (verify-all, validators, etc). Gameplay still requires
    the real `arcade` package.
    """
    existing = sys.modules.get("arcade")
    if existing is not None:
        return
    if existing is None and "arcade" in sys.modules:
        sys.modules.pop("arcade", None)
    try:
        __import__("arcade")
        return
    except ModuleNotFoundError:
        pass

    arcade_stub = types.ModuleType("arcade")

    class Sprite:  # noqa: D401
        """Stub for arcade.Sprite."""

    class SpriteList(list):  # noqa: D401
        """Stub for arcade.SpriteList."""

    class Texture:  # noqa: D401
        """Stub for arcade.Texture."""

    class Text:  # noqa: D401
        """Stub for arcade.Text."""

        def __init__(self, *args: object, **kwargs: object) -> None:
            return

        def draw(self) -> None:
            return

    key_mod = types.ModuleType("arcade.key")

    def symbol_string(code: int) -> str:
        return f"KEY_{int(code)}"

    key_any = cast(Any, key_mod)
    key_any.symbol_string = symbol_string

    color_mod = types.SimpleNamespace(
        BLACK=(0, 0, 0),
        WHITE=(255, 255, 255),
        RED=(255, 0, 0),
        GREEN=(0, 255, 0),
        BLUE=(0, 0, 255),
    )

    def get_window() -> None:
        return None

    arcade_any = cast(Any, arcade_stub)
    arcade_any.Sprite = Sprite
    arcade_any.SpriteList = SpriteList
    arcade_any.Texture = Texture
    arcade_any.Text = Text
    arcade_any.key = key_mod
    arcade_any.color = color_mod
    arcade_any.get_window = get_window
    arcade_any.__mesh_headless_stub__ = True

    sys.modules["arcade"] = arcade_stub
    sys.modules["arcade.key"] = key_mod
