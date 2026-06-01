"""Read-only Quest Editor overlay for the editor right dock."""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.ui_overlays.common import UIElement
from engine.ui_overlays.editor_database_form_helpers import (
    FormColors,
    add_form_buttons,
    collect_button_rects,
    compute_database_form_layout,
    draw_text_input,
    draw_text_input_rows,
    scalar_rows_for_mode,
    sync_text_inputs,
    try_click_text_widget,
)
from engine.ui_overlays.widgets import Rect, TextInput

if TYPE_CHECKING:  # pragma: no cover
    from engine.game import GameWindow


QUEST_EDITOR_TEXT_COLOR = (220, 220, 230, 255)
QUEST_EDITOR_DIM_COLOR = (150, 150, 160, 255)
QUEST_EDITOR_SELECTED_BG = (90, 140, 200, 140)
QUEST_EDITOR_BUTTON_COLOR = (100, 200, 255, 255)
QUEST_EDITOR_ROW_HEIGHT = 18.0
QUEST_EDITOR_ROW_PADDING_X = 6.0
QUEST_EDITOR_PANEL_GAP = 8.0
QUEST_EDITOR_ERROR_COLOR = (255, 120, 120, 255)
QUEST_EDITOR_EDITABLE_SCALAR_FIELDS = {"id", "title", "description", "type", "start_toast", "complete_toast"}
_QUEST_FORM_COLORS = FormColors(
    text=QUEST_EDITOR_TEXT_COLOR,
    dim=QUEST_EDITOR_DIM_COLOR,
    button=QUEST_EDITOR_BUTTON_COLOR,
)
QUEST_EDITOR_READ_ONLY_COMPLEX_FIELDS = frozenset(
    {"stages", "steps", "reward", "requires_flags", "blocks_flags"}
)


class QuestEditorOverlay(UIElement):
    """Read-only quest database view hosted in the editor right dock."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._model: object | None = None
        self._load_error: str | None = None
        self._row_hits: list[tuple[int, object]] = []
        self._widget_rows: dict[str, object] = {}

    def _get_controller(self) -> object | None:
        return getattr(self.window, "editor_controller", None)

    def _is_visible_for_controller(self, controller: object | None) -> bool:
        if controller is None or not getattr(controller, "active", False):
            return False
        dock = getattr(controller, "dock", None)
        snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
        right_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
        return right_tab == "Quests"

    def _get_model(self) -> object | None:
        if self._model is not None:
            return self._model
        try:
            from engine.editor.quest_editor_model import QuestEditorModel

            self._model = QuestEditorModel.load()
            self._load_error = None
        except Exception as exc:  # pragma: no cover - defensive runtime path
            self._model = None
            self._load_error = str(exc)
        return self._model

    def reload_model(self) -> None:
        self._model = None
        self._get_model()

    def selected_quest_dict(self) -> dict[str, object] | None:
        model = self._get_model()
        quest = model.selected_quest() if model is not None and hasattr(model, "selected_quest") else None
        return dict(quest) if isinstance(quest, dict) else None

    def all_quest_dicts(self) -> list[dict[str, object]]:
        model = self._get_model()
        quests = model.quests() if model is not None and hasattr(model, "quests") else []
        return [dict(quest) for quest in quests if isinstance(quest, dict)]

    def draw(self) -> None:
        controller = self._get_controller()
        if not self._is_visible_for_controller(controller):
            return

        from engine.editor.widgets.panel_primitives import EditorPanelBase, PanelField, PanelHeader, PanelRow

        list_rect, detail_rect = compute_database_form_layout(self.window, controller, QUEST_EDITOR_PANEL_GAP)

        model = self._get_model()
        quest_editor = getattr(controller, "quest_editor", None)
        edit_mode = bool(quest_editor is not None and quest_editor.is_edit_mode_active())
        dirty_marker = " *" if quest_editor is not None and quest_editor.is_dirty() else ""
        list_panel = EditorPanelBase(
            list_rect,
            panel_bg=(0, 0, 0, 0),
            panel_border=(0, 0, 0, 0),
            item_spacing=0.0,
            inner_padding_x=0.0,
            inner_padding_y=0.0,
        )
        list_panel.add_header(PanelHeader("Quests", str(model.quest_count) if model is not None else "0"))
        self._row_hits = []

        if model is None:
            list_panel.add_row(
                PanelRow(
                    PanelField("Unable to load quests", self._load_error, label_color=QUEST_EDITOR_DIM_COLOR),
                    height=QUEST_EDITOR_ROW_HEIGHT,
                    padding_x=QUEST_EDITOR_ROW_PADDING_X,
                )
            )
        elif not model.quests():
            list_panel.add_row(
                PanelRow(
                    PanelField("No quests found", None, label_color=QUEST_EDITOR_DIM_COLOR),
                    height=QUEST_EDITOR_ROW_HEIGHT,
                    padding_x=QUEST_EDITOR_ROW_PADDING_X,
                )
            )
        else:
            selected_index = model.selected_index()
            for index, (title, quest_id) in enumerate(model.list_rows()):
                row = PanelRow(
                    PanelField(title, quest_id, label_color=QUEST_EDITOR_TEXT_COLOR, value_color=QUEST_EDITOR_DIM_COLOR),
                    height=QUEST_EDITOR_ROW_HEIGHT,
                    padding_x=QUEST_EDITOR_ROW_PADDING_X,
                    selected_bg=QUEST_EDITOR_SELECTED_BG,
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
        quest = model.selected_quest() if model is not None else None
        button_rows: dict[str, object] = {}
        self._widget_rows = {}
        if quest is None:
            detail_panel.add_header(PanelHeader(f"Quests{dirty_marker}", "No quest"))
        else:
            if edit_mode and quest_editor is not None:
                self._sync_edit_widgets(quest_editor)
            quest_id = str(quest.get("id", "") or "")
            title = str(quest.get("title", "") or quest_id)
            detail_panel.add_header(PanelHeader(f"{title}{dirty_marker}", quest_id))
            if quest_editor is not None and quest_editor.last_error_message():
                detail_panel.add_row(
                    PanelRow(
                        PanelField("Error", quest_editor.last_error_message(), label_color=QUEST_EDITOR_ERROR_COLOR),
                        height=QUEST_EDITOR_ROW_HEIGHT,
                        padding_x=QUEST_EDITOR_ROW_PADDING_X,
                    )
                )
            from engine.editor.quest_editor_model import QUEST_SCALAR_FIELD_ORDER  # noqa: PLC0415

            for label, value, field_path in scalar_rows_for_mode(
                model=model,
                edit_mode=edit_mode,
                scalar_field_order=QUEST_SCALAR_FIELD_ORDER,
                selected_record=model.selected_quest,
                value_for_field=lambda record, field: record.get(field) if isinstance(record, dict) else None,
                label_for_field=_label_for_field,
            ):
                if edit_mode and field_path in QUEST_EDITOR_EDITABLE_SCALAR_FIELDS:
                    self._widget_rows[field_path] = detail_panel.add_row(
                        PanelRow(
                            PanelField(label, "", label_color=QUEST_EDITOR_TEXT_COLOR, value_color=QUEST_EDITOR_DIM_COLOR),
                            height=QUEST_EDITOR_ROW_HEIGHT,
                            padding_x=QUEST_EDITOR_ROW_PADDING_X,
                        )
                    )
                    continue
                detail_panel.add_row(
                    PanelRow(
                        PanelField(label, value, label_color=QUEST_EDITOR_TEXT_COLOR, value_color=QUEST_EDITOR_DIM_COLOR),
                        height=QUEST_EDITOR_ROW_HEIGHT,
                        padding_x=QUEST_EDITOR_ROW_PADDING_X,
                    )
                )
            complex_rows = model.complex_detail_rows()
            if complex_rows:
                from engine.editor.quest_editor_model import stage_rows  # noqa: PLC0415

                detail_panel.add_header(PanelHeader("Complex fields (read-only)", None, title_color=QUEST_EDITOR_DIM_COLOR))
                for label, value in complex_rows:
                    detail_panel.add_row(
                        PanelRow(
                            PanelField(label, value, label_color=QUEST_EDITOR_TEXT_COLOR, value_color=QUEST_EDITOR_DIM_COLOR),
                            height=QUEST_EDITOR_ROW_HEIGHT,
                            padding_x=QUEST_EDITOR_ROW_PADDING_X,
                        )
                    )
                    if label == "Stages":
                        for stage_id, summary in stage_rows(quest):
                            detail_panel.add_row(
                                PanelRow(
                                    PanelField(
                                        stage_id,
                                        summary,
                                        label_color=QUEST_EDITOR_TEXT_COLOR,
                                        value_color=QUEST_EDITOR_DIM_COLOR,
                                    ),
                                    height=QUEST_EDITOR_ROW_HEIGHT,
                                    padding_x=QUEST_EDITOR_ROW_PADDING_X,
                                )
                            )
            button_rows = add_form_buttons(
                detail_panel,
                edit_mode=edit_mode,
                button_color=QUEST_EDITOR_BUTTON_COLOR,
                row_height=QUEST_EDITOR_ROW_HEIGHT,
                padding_x=QUEST_EDITOR_ROW_PADDING_X,
            )
        detail_panel.draw()
        if quest_editor is not None:
            quest_editor.set_button_rects(collect_button_rects(button_rows))
        if edit_mode and quest_editor is not None:
            self._draw_edit_widgets(quest_editor)

    def row_index_at(self, x: float, y: float) -> int | None:
        for index, row in self._row_hits:
            if row.hit_test(float(x), float(y)):
                return index
        return None

    def set_selected_index(self, index: int) -> bool:
        model = self._get_model()
        setter = getattr(model, "set_selected_index", None)
        return bool(setter(int(index))) if callable(setter) else False

    def _draw_text_input(self, text_input: TextInput, rect: Rect) -> None:
        draw_text_input(text_input, rect, _QUEST_FORM_COLORS)

    def _sync_edit_widgets(self, quest_editor: object) -> None:
        edit_buffer = getattr(quest_editor, "edit_buffer", None)
        if not isinstance(edit_buffer, dict):
            return
        focused = getattr(quest_editor, "focused_field", lambda: None)
        focused_field = focused() if callable(focused) else None
        text_inputs = getattr(quest_editor, "text_inputs", lambda: {})()
        if isinstance(text_inputs, dict):
            sync_text_inputs(
                text_inputs,
                focused_field,
                lambda field: edit_buffer.get(str(field)),
            )

    def _draw_edit_widgets(self, quest_editor: object) -> None:
        text_inputs = getattr(quest_editor, "text_inputs", lambda: {})()
        if isinstance(text_inputs, dict):
            draw_text_input_rows(self._widget_rows, text_inputs, self._draw_text_input)

    def try_click_widget(self, x: float, y: float) -> str | None:
        controller = self._get_controller()
        quest_editor = getattr(controller, "quest_editor", None) if controller is not None else None
        if quest_editor is None:
            return None
        return try_click_text_widget(self._widget_rows, quest_editor, x, y)


def _label_for_field(field_path: str) -> str:
    return {
        "id": "ID",
        "title": "Title",
        "description": "Description",
        "type": "Type",
        "start_toast": "Start toast",
        "complete_toast": "Complete toast",
    }.get(field_path, field_path)
