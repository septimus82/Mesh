"""Read-only Dialogue Editor overlay for the editor right dock."""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.ui_overlays.common import UIElement
from engine.ui_overlays.editor_database_form_helpers import compute_database_form_layout

if TYPE_CHECKING:  # pragma: no cover
    from engine.game import GameWindow


DIALOGUE_EDITOR_TEXT_COLOR = (220, 220, 230, 255)
DIALOGUE_EDITOR_DIM_COLOR = (150, 150, 160, 255)
DIALOGUE_EDITOR_SELECTED_BG = (90, 140, 200, 140)
DIALOGUE_EDITOR_ROW_HEIGHT = 18.0
DIALOGUE_EDITOR_ROW_PADDING_X = 6.0
DIALOGUE_EDITOR_PANEL_GAP = 8.0


class DialogueEditorOverlay(UIElement):
    """Read-only dialogue database view hosted in the editor right dock."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._model: object | None = None
        self._row_hits: list[tuple[int, object]] = []

    def _get_controller(self) -> object | None:
        return getattr(self.window, "editor_controller", None)

    def _is_visible_for_controller(self, controller: object | None) -> bool:
        if controller is None or not getattr(controller, "active", False):
            return False
        dock = getattr(controller, "dock", None)
        snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
        right_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
        return right_tab == "Dialogue"

    def _get_model(self) -> object | None:
        if self._model is not None:
            return self._model
        from engine.editor.dialogue_editor_model import DialogueEditorModel

        self._model = DialogueEditorModel.load()
        return self._model

    def reload_model(self) -> None:
        self._model = None
        self._get_model()

    def draw(self) -> None:
        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            return

        from engine.editor.widgets.panel_primitives import EditorPanelBase, PanelField, PanelHeader, PanelRow

        list_rect, detail_rect = compute_database_form_layout(self.window, controller, DIALOGUE_EDITOR_PANEL_GAP)
        model = self._get_model()

        list_panel = EditorPanelBase(
            list_rect,
            panel_bg=(0, 0, 0, 0),
            panel_border=(0, 0, 0, 0),
            item_spacing=0.0,
            inner_padding_x=0.0,
            inner_padding_y=0.0,
        )
        list_panel.add_header(PanelHeader("Dialogue", str(model.dialogue_count) if model is not None else "0"))
        self._row_hits = []
        if model is None or not model.dialogues():
            list_panel.add_row(
                PanelRow(
                    PanelField("No dialogue entries found", None, label_color=DIALOGUE_EDITOR_DIM_COLOR),
                    height=DIALOGUE_EDITOR_ROW_HEIGHT,
                    padding_x=DIALOGUE_EDITOR_ROW_PADDING_X,
                )
            )
        else:
            selected_index = model.selected_index()
            for index, (dialogue_id, start_node, node_count) in enumerate(model.list_rows()):
                row = PanelRow(
                    PanelField(
                        dialogue_id,
                        f"{start_node} | {node_count} nodes",
                        label_color=DIALOGUE_EDITOR_TEXT_COLOR,
                        value_color=DIALOGUE_EDITOR_DIM_COLOR,
                    ),
                    height=DIALOGUE_EDITOR_ROW_HEIGHT,
                    padding_x=DIALOGUE_EDITOR_ROW_PADDING_X,
                    selected_bg=DIALOGUE_EDITOR_SELECTED_BG,
                )
                row.set_selected(index == selected_index)
                self._row_hits.append((index, row))
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
        dialogue = model.selected_dialogue() if model is not None else None
        if dialogue is None:
            detail_panel.add_header(PanelHeader("Dialogue", "No entry"))
        else:
            dialogue_id = str(dialogue.get("id", "") or "")
            detail_panel.add_header(PanelHeader(dialogue_id, "Read-only"))
            for label, value in model.detail_rows():
                detail_panel.add_row(
                    PanelRow(
                        PanelField(label, value, label_color=DIALOGUE_EDITOR_TEXT_COLOR, value_color=DIALOGUE_EDITOR_DIM_COLOR),
                        height=DIALOGUE_EDITOR_ROW_HEIGHT,
                        padding_x=DIALOGUE_EDITOR_ROW_PADDING_X,
                    )
                )
        detail_panel.draw()

    def row_index_at(self, x: float, y: float) -> int | None:
        for index, row in self._row_hits:
            if row.hit_test(float(x), float(y)):
                return index
        return None

    def set_selected_index(self, index: int) -> bool:
        model = self._get_model()
        setter = getattr(model, "set_selected_index", None)
        return bool(setter(int(index))) if callable(setter) else False
