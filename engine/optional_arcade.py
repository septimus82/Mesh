from __future__ import annotations

from typing import Any

from . import arcade_fallback

_arcade: Any = None
_arcade_gl: Any = None
HAS_ARCADE = False

try:  # pragma: no cover - exercised in headless tests
    import arcade as _arcade
    HAS_ARCADE = True
except Exception:  # noqa: BLE001 - optional dependency
    _arcade = arcade_fallback
    HAS_ARCADE = False

if HAS_ARCADE:
    try:
        import arcade.gl as _arcade_gl
    except ImportError:
        _arcade_gl = None

arcade: Any = _arcade
arcade_gl: Any = _arcade_gl


def has_arcade() -> bool:
    return HAS_ARCADE


def has_arcade_gl() -> bool:
    return arcade_gl is not None


__all__ = ["arcade", "arcade_gl", "has_arcade", "has_arcade_gl", "HAS_ARCADE"]
