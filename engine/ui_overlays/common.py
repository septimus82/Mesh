from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arcade import Sprite

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow

def _get_arcade() -> Any:
    return importlib.import_module("engine.optional_arcade").arcade


class UIElement:
    """Base class for overlay elements that can update and draw."""

    def __init__(self, window: "GameWindow") -> None:
        self.window = window

    def update(self, dt: float) -> None:  # pragma: no cover - default no-op
        return

    def on_resize(self, width: int, height: int) -> None:  # pragma: no cover - default no-op
        """Resize hook for overlays; override when caching geometry."""
        return

    def draw(self) -> None:  # pragma: no cover - default no-op
        return

    @property
    def blocks_input(self) -> bool:
        """Return True if this element captures gameplay input."""
        return False


def load_config_json(config_path: str = "config.json") -> dict[str, Any]:
    path = Path(str(config_path or "config.json"))
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


INSPECTOR_MAX_LINES = 8
INSPECTOR_MAX_LINE_CHARS = 96
INSPECTOR_MAX_LIST_ITEMS = 6


def _safe_truncate(value: str, max_len: int) -> str:
    text = str(value or "")
    limit = max(1, int(max_len))
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3] + "..."



def _draw_rectangle_filled(
    center_x: float,
    center_y: float,
    width: float,
    height: float,
    color: Any,
) -> None:
    arcade = _get_arcade()
    fn = getattr(arcade, "draw_rectangle_filled", None)
    if callable(fn):
        fn(center_x, center_y, width, height, color)
    else:
        # Fallback for newer arcade that might only have lrbt bounds drawing.
        half_w = width / 2
        half_h = height / 2
        arcade.draw_lrbt_rectangle_filled(
            center_x - half_w,
            center_x + half_w,
            center_y - half_h,
            center_y + half_h,
            color
        )

def _draw_tb_rectangle_filled(
    left: float,
    right: float,
    top: float,
    bottom: float,
    color: Any,
) -> None:
    arcade = _get_arcade()
    arcade.draw_lrbt_rectangle_filled(left, right, bottom, top, color)

def _draw_rectangle_outline(
    left: float,
    right: float,
    top: float,
    bottom: float,
    color: Any,
    border_width: float = 1,
) -> None:
    arcade = _get_arcade()
    arcade.draw_lrbt_rectangle_outline(left, right, bottom, top, color, border_width)

def _draw_rectangle_filled_centered(
    center_x: float,
    center_y: float,
    width: float,
    height: float,
    color: Any,
) -> None:
    arcade = _get_arcade()
    fn = getattr(arcade, "draw_rectangle_filled", None)
    if callable(fn):
        fn(center_x, center_y, width, height, color)
        return
    half_w = width / 2
    half_h = height / 2
    left = center_x - half_w
    right = center_x + half_w
    bottom = center_y - half_h
    top = center_y + half_h
    arcade.draw_lrbt_rectangle_filled(left, right, bottom, top, color)



def _draw_tb_rectangle_outline(
    left: float,
    right: float,
    top: float,
    bottom: float,
    color: Any,
    border_width: float = 1.0,
) -> None:
    arcade = _get_arcade()
    arcade.draw_lrbt_rectangle_outline(left, right, bottom, top, color, border_width)


def _sprite_under_cursor(window: "GameWindow") -> "Sprite | None":
    if not getattr(window, "show_debug", False):
        return None

    world_x, world_y = window.screen_to_world(window._mouse_x, window._mouse_y)

    candidates: list["Sprite"] = []
    layers = getattr(window.scene_controller, "layers", {})
    arcade = _get_arcade()
    for layer in layers.values():
        hits = arcade.get_sprites_at_point((world_x, world_y), layer)
        if hits:
            candidates.extend(hits)

    if not candidates:
        return None
    return candidates[-1]


def draw_panel_bg(left: float, right: float, bottom: float, top: float, color: Any = (0, 0, 0, 200)) -> None:
    """Draw a filled rectangle using lrbt ordering with safety."""
    lo_y, hi_y = (bottom, top) if bottom <= top else (top, bottom)
    arcade = _get_arcade()
    arcade.draw_lrbt_rectangle_filled(left, right, lo_y, hi_y, color)


def draw_outline_centered(cx: float, cy: float, width: float, height: float, color: Any, border: float = 2) -> None:
    half_w = width / 2.0
    half_h = height / 2.0
    arcade = _get_arcade()
    arcade.draw_lrbt_rectangle_outline(
        cx - half_w,
        cx + half_w,
        cy - half_h,
        cy + half_h,
        color,
        border,
    )
