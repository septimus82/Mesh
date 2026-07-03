from __future__ import annotations

from typing import Any

from .dpi_bootstrap import set_process_dpi_unaware

# Must run before ``import arcade`` (pyglet sets per-monitor DPI awareness at import).
set_process_dpi_unaware()

from . import arcade_fallback

_arcade: Any = None
_arcade_gl: Any = None
HAS_ARCADE = False

try:  # pragma: no cover - exercised in headless tests
    import arcade as _arcade
    HAS_ARCADE = True
except Exception:  # noqa: BLE001  # REASON: arcade import failures should fall back to the headless arcade shim
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


def draw_texture_rect_compat(
    center_x: float,
    center_y: float,
    width: float,
    height: float,
    texture: Any,
    *,
    angle: float = 0.0,
    alpha: int = 255,
) -> None:
    """Draw ``texture`` centered at ``(center_x, center_y)`` with the given size.

    Arcade 3 removed ``arcade.draw_texture_rectangle`` in favour of
    ``draw_texture_rect(texture, rect)`` (rect via ``arcade.XYWH``). This shim
    prefers the Arcade-3 API and falls back to the legacy call (still defined by
    the headless arcade stub) so headless render paths keep working. Centralising
    the getattr dance keeps every call site off the removed bare attribute.
    """
    backend = arcade
    if backend is None:
        return
    draw_rect = getattr(backend, "draw_texture_rect", None)
    xywh = getattr(backend, "XYWH", None)
    if callable(draw_rect) and callable(xywh):
        draw_rect(
            texture,
            xywh(float(center_x), float(center_y), float(width), float(height)),
            angle=float(angle),
            alpha=int(alpha),
        )
        return
    legacy = getattr(backend, "draw_texture_rectangle", None)
    if callable(legacy):
        legacy(
            float(center_x),
            float(center_y),
            float(width),
            float(height),
            texture,
            angle=float(angle),
            alpha=int(alpha),
        )


__all__ = [
    "arcade",
    "arcade_gl",
    "has_arcade",
    "has_arcade_gl",
    "HAS_ARCADE",
    "draw_texture_rect_compat",
]
