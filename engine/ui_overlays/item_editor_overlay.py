"""Read-only Item Editor overlay for the editor right dock."""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.ui_overlays.common import UIElement
from engine.ui_overlays.widgets import Rect

if TYPE_CHECKING:  # pragma: no cover
    from engine.game import GameWindow


ITEM_EDITOR_TEXT_COLOR = (220, 220, 230, 255)
ITEM_EDITOR_DIM_COLOR = (150, 150, 160, 255)
ITEM_EDITOR_SELECTED_BG = (90, 140, 200, 140)
ITEM_EDITOR_ROW_HEIGHT = 18.0
ITEM_EDITOR_ROW_PADDING_X = 6.0
ITEM_EDITOR_PANEL_GAP = 8.0


class ItemEditorOverlay(UIElement):
    """Read-only item database view hosted in the editor right dock."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._model: object | None = None
        self._load_error: str | None = None

    def _get_controller(self) -> object | None:
        return getattr(self.window, "editor_controller", None)

    def _is_visible_for_controller(self, controller: object | None) -> bool:
        if controller is None or not getattr(controller, "active", False):
            return False
        dock = getattr(controller, "dock", None)
        snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
        right_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
        return right_tab == "Items"

    def _get_model(self) -> object | None:
        if self._model is not None:
            return self._model
        try:
            from engine.editor.item_editor_model import ItemEditorModel

            self._model = ItemEditorModel.load()
            self._load_error = None
        except Exception as exc:  # pragma: no cover - defensive runtime path
            self._model = None
            self._load_error = str(exc)
        return self._model

    def draw(self) -> None:
        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            return

        from engine.editor.editor_dock_query import get_effective_dock_widths
        from engine.editor.editor_shell_layout import compute_editor_shell_layout
        from engine.editor.widgets.panel_primitives import EditorPanelBase, PanelField, PanelHeader, PanelRow

        window_w = int(getattr(self.window, "width", 1280) or 1280)
        window_h = int(getattr(self.window, "height", 720) or 720)
        left_w, right_w = get_effective_dock_widths(controller, window_w)
        layout = compute_editor_shell_layout(window_w, window_h, left_w, right_w)

        dock = layout.right_dock
        content_top = dock.top - 38.0
        content_bottom = dock.bottom + 10.0
        content_left = dock.left + 8.0
        content_right = dock.right - 8.0
        content_width = max(0.0, content_right - content_left)
        split_x = content_left + max(112.0, content_width * 0.44)
        list_rect = Rect(
            x=float(content_left),
            y=float(content_bottom),
            width=max(0.0, float(split_x - content_left - (ITEM_EDITOR_PANEL_GAP * 0.5))),
            height=max(0.0, float(content_top - content_bottom)),
        )
        detail_rect = Rect(
            x=float(split_x + (ITEM_EDITOR_PANEL_GAP * 0.5)),
            y=float(content_bottom),
            width=max(0.0, float(content_right - split_x - (ITEM_EDITOR_PANEL_GAP * 0.5))),
            height=max(0.0, float(content_top - content_bottom)),
        )

        model = self._get_model()
        list_panel = EditorPanelBase(
            list_rect,
            panel_bg=(0, 0, 0, 0),
            panel_border=(0, 0, 0, 0),
            item_spacing=0.0,
            inner_padding_x=0.0,
            inner_padding_y=0.0,
        )
        list_panel.add_header(PanelHeader("Items", str(model.item_count) if model is not None else "0"))

        if model is None:
            list_panel.add_row(
                PanelRow(
                    PanelField("Unable to load items", self._load_error, label_color=ITEM_EDITOR_DIM_COLOR),
                    height=ITEM_EDITOR_ROW_HEIGHT,
                    padding_x=ITEM_EDITOR_ROW_PADDING_X,
                )
            )
        elif not model.items:
            list_panel.add_row(
                PanelRow(
                    PanelField("No items found", None, label_color=ITEM_EDITOR_DIM_COLOR),
                    height=ITEM_EDITOR_ROW_HEIGHT,
                    padding_x=ITEM_EDITOR_ROW_PADDING_X,
                )
            )
        else:
            selected_index = model._clamp_index(model.selected_index)
            for index, label in enumerate(model.list_rows()):
                row = PanelRow(
                    PanelField(label, None, label_color=ITEM_EDITOR_TEXT_COLOR),
                    height=ITEM_EDITOR_ROW_HEIGHT,
                    padding_x=ITEM_EDITOR_ROW_PADDING_X,
                    selected_bg=ITEM_EDITOR_SELECTED_BG,
                )
                row.set_selected(index == selected_index)
                list_panel.add_row(row)
        list_panel.draw()

        detail_panel = EditorPanelBase(
            detail_rect,
            panel_bg=(0, 0, 0, 0),
            panel_border=(0, 0, 0, 0),
            item_spacing=2.0,
            inner_padding_x=0.0,
            inner_padding_y=0.0,
        )
        item = model.selected_item if model is not None else None
        if item is None:
            detail_panel.add_header(PanelHeader("No item", None))
        else:
            detail_panel.add_header(PanelHeader(item.name, item.id))
            for label, value in model.selected_detail_rows():
                detail_panel.add_row(
                    PanelRow(
                        PanelField(label, value, label_color=ITEM_EDITOR_TEXT_COLOR, value_color=ITEM_EDITOR_DIM_COLOR),
                        height=ITEM_EDITOR_ROW_HEIGHT,
                        padding_x=ITEM_EDITOR_ROW_PADDING_X,
                    )
                )
        detail_panel.draw()
