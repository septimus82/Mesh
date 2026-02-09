from __future__ import annotations

from typing import Any, Tuple, cast


def get_hovered_dock_tab(controller: Any) -> Tuple[str, str] | None:
    dock = getattr(controller, "dock", None)
    if dock is not None:
        getter = getattr(dock, "get_hover_tab", None)
        if callable(getter):
            result = getter()
            return cast(Tuple[str, str] | None, result)
    return None


def get_hovered_dock_tab_rect(controller: Any) -> Tuple[float, float, float, float] | None:
    dock = getattr(controller, "dock", None)
    if dock is not None:
        getter = getattr(dock, "get_hover_tab_rect", None)
        if callable(getter):
            result = getter()
            return cast(Tuple[float, float, float, float] | None, result)
    return None
