from __future__ import annotations

from typing import Any, Tuple


def get_hovered_top_bar_control_id(controller: Any) -> str | None:
    hover = getattr(controller, "hover", None)
    getter = getattr(hover, "get_hover_top_bar_control_id", None) if hover is not None else None
    return getter() if callable(getter) else None


def get_hovered_splitter(controller: Any) -> str | None:
    hover = getattr(controller, "hover", None)
    getter = getattr(hover, "get_hover_splitter", None) if hover is not None else None
    return getter() if callable(getter) else None


def get_hovered_splitter_rect(
    controller: Any,
) -> Tuple[float, float, float, float] | None:
    hover = getattr(controller, "hover", None)
    getter = getattr(hover, "get_hover_splitter_rect", None) if hover is not None else None
    return getter() if callable(getter) else None


def get_hovered_inspector_field_key(controller: Any) -> str | None:
    hover = getattr(controller, "hover", None)
    getter = getattr(hover, "get_hover_inspector_field_key", None) if hover is not None else None
    return getter() if callable(getter) else None


def get_hovered_inspector_field_rect(
    controller: Any,
) -> Tuple[float, float, float, float] | None:
    hover = getattr(controller, "hover", None)
    getter = getattr(hover, "get_hover_inspector_field_rect", None) if hover is not None else None
    return getter() if callable(getter) else None


def get_hovered_entity_id(controller: Any) -> str | None:
    hover = getattr(controller, "hover", None)
    getter = getattr(hover, "get_hover_entity_id", None) if hover is not None else None
    return getter() if callable(getter) else None


def get_hovered_entity_rect(
    controller: Any,
) -> Tuple[float, float, float, float] | None:
    hover = getattr(controller, "hover", None)
    getter = getattr(hover, "get_hover_entity_rect", None) if hover is not None else None
    return getter() if callable(getter) else None
