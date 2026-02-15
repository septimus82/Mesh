"""
Cached text drawing wrapper to avoid Arcade PerformanceWarning on hot paths.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, NamedTuple, OrderedDict
from collections import OrderedDict

import engine.optional_arcade

if TYPE_CHECKING:
    from arcade import Text

_DEFAULT_FONT_NAME: tuple[str, ...] = ("calibri", "arial")

# Global text scale multiplier (set via RuntimeSettings.apply)
_text_scale: float = 1.0


def set_text_scale(scale: float) -> None:
    """Set the global text scale multiplier (clamped to 0.5–3.0)."""
    global _text_scale
    _text_scale = max(0.5, min(3.0, float(scale)))


def get_text_scale() -> float:
    """Return the current global text scale multiplier."""
    return _text_scale

class TextCacheKey(NamedTuple):
    text: str
    font_name: Optional[str | tuple[str, ...]]
    font_size: float
    color: Tuple[int, int, int, int]
    anchor_x: str
    anchor_y: str
    width: int
    align: str
    multiline: bool
    bold: bool
    italic: bool

class TextCache:
    def __init__(self, max_size: int = 512):
        self._cache: OrderedDict[TextCacheKey, "Text"] = OrderedDict()
        self._max_size = max_size

    def get(self, key: TextCacheKey) -> Optional["Text"]:
        if key in self._cache:
            # Move to end (LRU behavior)
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: TextCacheKey, text_obj: "Text"):
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            self._cache[key] = text_obj
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

def draw_text_cached(
    text: str,
    x: float,
    y: float,
    *,
    color: Tuple[int, int, int, int] | Tuple[int, int, int] = (255, 255, 255, 255),
    font_size: float = 12.0,
    font_name: Optional[str | tuple[str, ...]] = None,
    anchor_x: str = "left",
    anchor_y: str = "baseline",
    rotation: float = 0.0,
    width: int = 0,
    align: str = "left",
    multiline: bool = False,
    bold: bool = False,
    italic: bool = False,
    cache: Optional[TextCache] = None,
) -> None:
    if engine.optional_arcade.arcade is None:
        return

    # Apply global text scale
    font_size = font_size * _text_scale

    if font_name is None:
        font_name = _DEFAULT_FONT_NAME

    # Normalize color to 4 components
    normalized_color: Tuple[int, int, int, int]
    if len(color) == 3:
        normalized_color = (*color, 255)
    else:
        normalized_color = color
    
    if cache is None or not hasattr(engine.optional_arcade.arcade, "Text"):
        # Fallback if no cache provided or Text class not available
        engine.optional_arcade.arcade.draw_text(
            text, 
            x, 
            y, 
            normalized_color,
            font_size,
            width=width,
            align=align,
            font_name=font_name,
            bold=bold,
            italic=italic,
            anchor_x=anchor_x,
            anchor_y=anchor_y,
            rotation=rotation,
            multiline=multiline
        )
        return

    # Key excludes x, y, rotation as they are mutable
    key = TextCacheKey(
        text=text,
        font_name=font_name,
        font_size=font_size,
        color=normalized_color,
        anchor_x=anchor_x,
        anchor_y=anchor_y,
        width=width,
        align=align,
        multiline=multiline,
        bold=bold,
        italic=italic
    )
    
    text_obj = cache.get(key)
    if text_obj is None:
        text_obj = engine.optional_arcade.arcade.Text(
            text,
            x,
            y,
            normalized_color,
            font_size,
            width=width,
            align=align,
            font_name=font_name,
            bold=bold,
            italic=italic,
            anchor_x=anchor_x,
            anchor_y=anchor_y,
            rotation=rotation,
            multiline=multiline
        )
        cache.put(key, text_obj)
    
    text_obj.position = (x, y)
    text_obj.rotation = rotation
    text_obj.draw()
