"""Spec'd fakes (S1 5.6 (c)): a fake window, sprite or player can only have what the real one has.

A bare ``MagicMock()`` window answers every attribute, so a test passes against an API the game doesn't have (#622 B,
#636, #641, #643). ``fake_window()`` is a MagicMock whose ``spec_set`` is the real GameWindow's attribute names
(``tests/fixtures/game_window_attributes.txt``: what a real hidden window has after loading a room, plus the names
production creates on a window lazily). Reading or setting any other name raises AttributeError, and ``hasattr`` is
False, exactly as on the real window. ``fake_sprite()`` is spec'd on the engine's entity sprite class the same way.

tests/test_fake_only_window_attributes.py regenerates the manifest from a real window and fails when it drifts.
"""
from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

MANIFEST = Path(__file__).resolve().parent / "fixtures" / "game_window_attributes.txt"


@cache
def window_attributes() -> tuple[str, ...]:
    return tuple(line for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#"))


def fake_window(**attributes: Any) -> MagicMock:
    """A stand-in GameWindow with only the real window's attributes; ``attributes`` are set on it."""
    window = MagicMock(spec_set=list(window_attributes()))
    for name, value in attributes.items():
        setattr(window, name, value)
    return window


def fake_sprite(**attributes: Any) -> MagicMock:
    """A stand-in entity sprite (arcade's Sprite: what the scene builds entities from). The ``mesh_*`` fields the scene
    adds, and any other per-entity data, are given as ``attributes``; nothing else is invented."""
    import engine.optional_arcade as optional_arcade

    sprite = MagicMock(spec=optional_arcade.arcade.Sprite)
    for name, value in attributes.items():
        setattr(sprite, name, value)
    return sprite
