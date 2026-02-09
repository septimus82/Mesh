"""Typed cached text drawing helpers for UI overlays."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .text_draw import TextCache, draw_text_cached


@dataclass(slots=True)
class UiTextCache:
    cache: TextCache


def draw_text(ui_cache: UiTextCache, *, text: str, x: float, y: float, **kwargs: Any) -> None:
    """Draw cached text with a shared UI cache."""
    draw_text_cached(text, x, y, cache=ui_cache.cache, **kwargs)
