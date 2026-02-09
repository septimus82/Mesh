from __future__ import annotations

from typing import Any, Mapping


def _get_attr(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def panels_is_open(source: Any, layer_id: str) -> bool:
    if layer_id == "unsaved_confirm":
        confirm = _get_attr(source, "unsaved_confirm")
        if confirm is not None:
            return bool(_get_attr(confirm, "is_open", False))
        return False
    panels = _get_attr(source, "panels")
    if panels is not None:
        if layer_id == "command_palette":
            fn = getattr(panels, "is_command_palette_open", None)
        elif layer_id == "context_menu":
            fn = getattr(panels, "is_context_menu_open", None)
        elif layer_id == "project_context_menu":
            fn = getattr(panels, "is_project_context_menu_open", None)
        elif layer_id == "keybinds":
            fn = getattr(panels, "is_keybinds_visible", None)
        elif layer_id == "confirm_modal":
            fn = getattr(panels, "is_confirm_modal_visible", None)
        else:
            fn = getattr(panels, "ui_layers", None)
            if fn is not None and hasattr(fn, "is_visible"):
                return bool(fn.is_visible(layer_id))
            fn = None
        if callable(fn):
            return bool(fn())

    ui_layers = _get_attr(source, "ui_layers")
    if ui_layers is not None and hasattr(ui_layers, "is_visible"):
        return bool(ui_layers.is_visible(layer_id))
    return False


def panels_active_modal(source: Any) -> str | None:
    panels = _get_attr(source, "panels")
    ui_layers = None
    if panels is not None:
        ui_layers = getattr(panels, "ui_layers", None)
    if ui_layers is None:
        ui_layers = _get_attr(source, "ui_layers")
    if ui_layers is not None:
        return getattr(getattr(ui_layers, "_state", None), "active_modal_id", None)
    return None
