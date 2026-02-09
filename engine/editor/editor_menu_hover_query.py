from __future__ import annotations

from typing import Any, Tuple


def get_menu_hover_title(controller: Any) -> str | None:
    hover = getattr(controller, "hover", None)
    getter = getattr(hover, "get_hover_menu_title", None) if hover is not None else None
    return getter() if callable(getter) else None


def get_menu_hover_title_rect(
    controller: Any,
) -> Tuple[float, float, float, float] | None:
    hover = getattr(controller, "hover", None)
    getter = getattr(hover, "get_hover_menu_title_rect", None) if hover is not None else None
    return getter() if callable(getter) else None


def get_menu_hover_item_id(controller: Any) -> str | None:
    return getattr(controller, "_menu_hover_item_id", None)


def get_menu_hover_item_rect(
    controller: Any,
) -> Tuple[float, float, float, float] | None:
    hover = getattr(controller, "hover", None)
    getter = getattr(hover, "get_hover_menu_item_rect", None) if hover is not None else None
    return getter() if callable(getter) else None


def get_context_menu_hover_id(controller: Any) -> str | None:
    return getattr(controller, "_context_menu_hover_id", None)


def get_context_menu_hover_rect(
    controller: Any,
) -> Tuple[float, float, float, float] | None:
    hover = getattr(controller, "hover", None)
    getter = getattr(hover, "get_hover_context_item_rect", None) if hover is not None else None
    return getter() if callable(getter) else None
