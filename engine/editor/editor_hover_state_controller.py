from __future__ import annotations

from typing import Any, Tuple


class EditorHoverStateController:
    """Owns hover state for editor UI highlights/tooltips."""

    def __init__(self, dock_controller: Any) -> None:
        self._dock = dock_controller
        self._menu_title: str | None = None
        self._menu_title_rect: Tuple[float, float, float, float] | None = None
        self._menu_item_rect: Tuple[float, float, float, float] | None = None
        self._top_bar_control_id: str | None = None
        self._splitter: str | None = None
        self._splitter_rect: Tuple[float, float, float, float] | None = None
        self._context_item_rect: Tuple[float, float, float, float] | None = None
        self._inspector_field_key: str | None = None
        self._inspector_field_rect: Tuple[float, float, float, float] | None = None
        self._entity_id: str | None = None
        self._entity_rect: Tuple[float, float, float, float] | None = None

    def set_hover_dock_tab(
        self,
        dock: str | None,
        tab: str | None,
        rect: Tuple[float, float, float, float] | None,
    ) -> None:
        setter = getattr(self._dock, "set_hover_tab", None) if self._dock is not None else None
        if callable(setter):
            setter(dock, tab, rect)

    def set_hover_splitter(self, which: str | None, rect: Tuple[float, float, float, float] | None) -> None:
        self._splitter = which
        self._splitter_rect = rect

    def set_hover_menu_title(self, title: str | None, rect: Tuple[float, float, float, float] | None) -> None:
        self._menu_title = title
        self._menu_title_rect = rect

    def set_hover_menu_item_rect(self, rect: Tuple[float, float, float, float] | None) -> None:
        self._menu_item_rect = rect

    def set_hover_top_bar_control(self, control_id: str | None) -> None:
        self._top_bar_control_id = control_id

    def get_hover_top_bar_control_id(self) -> str | None:
        return self._top_bar_control_id

    def set_hover_context_item_rect(self, rect: Tuple[float, float, float, float] | None) -> None:
        self._context_item_rect = rect

    def set_hover_inspector_field(self, key: str | None, rect: Tuple[float, float, float, float] | None) -> None:
        self._inspector_field_key = key
        self._inspector_field_rect = rect

    def set_hover_entity(self, entity_id: str | None, rect: Tuple[float, float, float, float] | None) -> None:
        self._entity_id = entity_id
        self._entity_rect = rect

    def clear_hover_state(self) -> None:
        self._menu_title = None
        self._menu_title_rect = None
        self._menu_item_rect = None
        self._top_bar_control_id = None
        self._splitter = None
        self._splitter_rect = None
        self._context_item_rect = None
        self._inspector_field_key = None
        self._inspector_field_rect = None
        self._entity_id = None
        self._entity_rect = None
        setter = getattr(self._dock, "set_hover_tab", None) if self._dock is not None else None
        if callable(setter):
            setter(None, None, None)

    def get_hover_menu_title(self) -> str | None:
        return self._menu_title

    def get_hover_menu_title_rect(self) -> Tuple[float, float, float, float] | None:
        return self._menu_title_rect

    def get_hover_menu_item_rect(self) -> Tuple[float, float, float, float] | None:
        return self._menu_item_rect

    def get_hover_splitter(self) -> str | None:
        return self._splitter

    def get_hover_splitter_rect(self) -> Tuple[float, float, float, float] | None:
        return self._splitter_rect

    def get_hover_context_item_rect(self) -> Tuple[float, float, float, float] | None:
        return self._context_item_rect

    def get_hover_inspector_field_key(self) -> str | None:
        return self._inspector_field_key

    def get_hover_inspector_field_rect(self) -> Tuple[float, float, float, float] | None:
        return self._inspector_field_rect

    def get_hover_entity_id(self) -> str | None:
        return self._entity_id

    def get_hover_entity_rect(self) -> Tuple[float, float, float, float] | None:
        return self._entity_rect
