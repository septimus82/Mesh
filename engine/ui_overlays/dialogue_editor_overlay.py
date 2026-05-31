"""Dialogue Editor overlay for the editor right dock."""

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


DIALOGUE_EDITOR_TEXT_COLOR = (220, 220, 230, 255)
DIALOGUE_EDITOR_DIM_COLOR = (150, 150, 160, 255)
DIALOGUE_EDITOR_SELECTED_BG = (90, 140, 200, 140)
DIALOGUE_EDITOR_BUTTON_COLOR = (100, 200, 255, 255)
DIALOGUE_EDITOR_ERROR_COLOR = (255, 120, 120, 255)
DIALOGUE_EDITOR_ROW_HEIGHT = 18.0
DIALOGUE_EDITOR_ROW_PADDING_X = 6.0
DIALOGUE_EDITOR_PANEL_GAP = 8.0
DIALOGUE_EDITOR_EDITABLE_SCALAR_FIELDS = {"id", "schema_version", "start_node"}
DIALOGUE_EDITOR_CHOICE_ADD_ACTION = "choice.add"
_DIALOGUE_FORM_COLORS = FormColors(
    text=DIALOGUE_EDITOR_TEXT_COLOR,
    dim=DIALOGUE_EDITOR_DIM_COLOR,
    button=DIALOGUE_EDITOR_BUTTON_COLOR,
)

_SelectedNodeFieldRow = tuple[str, str, str]


def _selected_node_choice_field_rows(node_id: str, choices: object) -> list[_SelectedNodeFieldRow]:
    """Return editable/display choice rows in the same order as the dialogue data."""
    if not isinstance(choices, list):
        return []
    rows: list[_SelectedNodeFieldRow] = []
    for i, choice in enumerate(choices):
        if not isinstance(choice, dict):
            continue
        choice_prefix = f"script.{node_id}.choices.{i}"
        choice_text_path = f"{choice_prefix}.text"
        choice_next_path = f"{choice_prefix}.next"
        choice_text_value = str(choice.get("text") or "")
        choice_next_value = str(choice.get("next") or "")
        rows.extend(
            [
                (f"Choice {i} text", choice_text_path, choice_text_value),
                (f"Choice {i} next", choice_next_path, choice_next_value),
            ]
        )
    return rows


def _selected_node_field_rows(node_id: str, selected_node: dict) -> list[_SelectedNodeFieldRow]:
    """Return the selected-node fields shared by read-only rows and edit widgets."""
    speaker_path = f"script.{node_id}.speaker"
    text_path = f"script.{node_id}.text"
    speaker_value = str(selected_node.get("speaker") or "")
    text_value = str(selected_node.get("text") or "")
    rows = [
        ("Speaker", speaker_path, speaker_value),
        ("Text", text_path, text_value),
    ]
    if not selected_node.get("choices"):
        rows.append(("Next", f"script.{node_id}.next", str(selected_node.get("next") or "")))
    rows.extend(_selected_node_choice_field_rows(node_id, selected_node.get("choices")))
    return rows


class DialogueEditorOverlay(UIElement):
    """Dialogue database view hosted in the editor right dock."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._model: object | None = None
        self._row_hits: list[tuple[int, object]] = []
        self._node_row_hits: list[tuple[str, object]] = []
        self._node_action_hits: list[tuple[str, object]] = []
        self._choice_action_hits: list[tuple[str, object]] = []
        self._selected_node_id: str | None = None
        self._selected_dialogue_id_for_node: str | None = None
        self._widget_rows: dict[str, object] = {}

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

        from engine.editor.dialogue_editor_model import (  # noqa: PLC0415
            DIALOGUE_SCALAR_FIELD_ORDER,
            dialogue_reference_problem_count,
            script_rows,
        )
        from engine.editor.widgets.panel_primitives import EditorPanelBase, PanelField, PanelHeader, PanelRow

        list_rect, detail_rect = compute_database_form_layout(self.window, controller, DIALOGUE_EDITOR_PANEL_GAP)
        model = self._get_model()
        dialogue_editor = getattr(controller, "dialogue_editor", None)
        edit_mode = bool(dialogue_editor is not None and dialogue_editor.is_edit_mode_active())
        dirty_marker = " *" if dialogue_editor is not None and dialogue_editor.is_dirty() else ""

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
        button_rows: dict[str, object] = {}
        self._widget_rows = {}
        self._node_row_hits = []
        self._node_action_hits = []
        self._choice_action_hits = []
        if dialogue is None:
            detail_panel.add_header(PanelHeader("Dialogue", "No entry"))
        else:
            if edit_mode and dialogue_editor is not None:
                self._sync_edit_widgets(dialogue_editor)
            dialogue_id = str(dialogue.get("id", "") or "")
            detail_panel.add_header(PanelHeader(f"{dialogue_id}{dirty_marker}", dialogue_id))
            if dialogue_editor is not None and dialogue_editor.last_error_message():
                detail_panel.add_row(
                    PanelRow(
                        PanelField("Error", dialogue_editor.last_error_message(), label_color=DIALOGUE_EDITOR_ERROR_COLOR),
                        height=DIALOGUE_EDITOR_ROW_HEIGHT,
                        padding_x=DIALOGUE_EDITOR_ROW_PADDING_X,
                    )
                )
            for label, value, field_path in scalar_rows_for_mode(
                model=model,
                edit_mode=edit_mode,
                scalar_field_order=DIALOGUE_SCALAR_FIELD_ORDER,
                selected_record=model.selected_dialogue,
                value_for_field=lambda record, field: record.get(field) if isinstance(record, dict) else None,
                label_for_field=_label_for_field,
            ):
                if edit_mode and field_path in DIALOGUE_EDITOR_EDITABLE_SCALAR_FIELDS:
                    self._widget_rows[field_path] = detail_panel.add_row(
                        PanelRow(
                            PanelField(label, "", label_color=DIALOGUE_EDITOR_TEXT_COLOR, value_color=DIALOGUE_EDITOR_DIM_COLOR),
                            height=DIALOGUE_EDITOR_ROW_HEIGHT,
                            padding_x=DIALOGUE_EDITOR_ROW_PADDING_X,
                        )
                    )
                    continue
                detail_panel.add_row(
                    PanelRow(
                        PanelField(label, value, label_color=DIALOGUE_EDITOR_TEXT_COLOR, value_color=DIALOGUE_EDITOR_DIM_COLOR),
                        height=DIALOGUE_EDITOR_ROW_HEIGHT,
                        padding_x=DIALOGUE_EDITOR_ROW_PADDING_X,
                    )
                )
            script = dialogue.get("script")
            node_count = str(len(script) if isinstance(script, dict) else 0)
            choice_count = str(
                sum(len(n.get("choices", [])) for n in script.values() if isinstance(n, dict))
                if isinstance(script, dict)
                else 0
            )
            reference_count = dialogue_reference_problem_count(dialogue)
            script_badge = "1 error" if reference_count == 1 else f"{reference_count} errors"
            script_badge_color = DIALOGUE_EDITOR_ERROR_COLOR if reference_count else DIALOGUE_EDITOR_DIM_COLOR
            detail_panel.add_header(
                PanelHeader(
                    "Script (read-only)",
                    script_badge,
                    title_color=DIALOGUE_EDITOR_DIM_COLOR,
                    subtitle_color=script_badge_color,
                )
            )
            detail_panel.add_row(
                PanelRow(
                    PanelField("Node count", node_count, label_color=DIALOGUE_EDITOR_TEXT_COLOR, value_color=DIALOGUE_EDITOR_DIM_COLOR),
                    height=DIALOGUE_EDITOR_ROW_HEIGHT,
                    padding_x=DIALOGUE_EDITOR_ROW_PADDING_X,
                )
            )
            detail_panel.add_row(
                PanelRow(
                    PanelField("Choice count", choice_count, label_color=DIALOGUE_EDITOR_TEXT_COLOR, value_color=DIALOGUE_EDITOR_DIM_COLOR),
                    height=DIALOGUE_EDITOR_ROW_HEIGHT,
                    padding_x=DIALOGUE_EDITOR_ROW_PADDING_X,
                )
            )
            current_dialogue_id = str(dialogue.get("id") or "")
            start_node_id = str(dialogue.get("start_node") or "").strip()
            node_rows = script_rows(dialogue)
            node_ids = [node_id for node_id, _summary in node_rows]
            if current_dialogue_id != self._selected_dialogue_id_for_node or self._selected_node_id not in node_ids:
                self._selected_node_id = start_node_id if start_node_id in node_ids else (node_ids[0] if node_ids else None)
                self._selected_dialogue_id_for_node = current_dialogue_id
            for node_id, summary in node_rows:
                label = f"{node_id} (start)" if node_id == start_node_id else node_id
                row = PanelRow(
                    PanelField(label, summary, label_color=DIALOGUE_EDITOR_TEXT_COLOR, value_color=DIALOGUE_EDITOR_DIM_COLOR),
                    height=DIALOGUE_EDITOR_ROW_HEIGHT,
                    padding_x=DIALOGUE_EDITOR_ROW_PADDING_X,
                    selected_bg=DIALOGUE_EDITOR_SELECTED_BG,
                )
                row.set_selected(node_id == self._selected_node_id)
                self._node_row_hits.append((node_id, row))
                detail_panel.add_row(row)
            if edit_mode:
                self._node_action_hits.append(
                    (
                        "node.add",
                        detail_panel.add_row(
                            PanelRow(
                                PanelField(
                                    "Add node",
                                    "",
                                    label_color=DIALOGUE_EDITOR_BUTTON_COLOR,
                                    value_color=DIALOGUE_EDITOR_DIM_COLOR,
                                ),
                                height=DIALOGUE_EDITOR_ROW_HEIGHT,
                                padding_x=DIALOGUE_EDITOR_ROW_PADDING_X,
                            )
                        ),
                    )
                )
            script_dict = dialogue.get("script")
            selected_node = script_dict.get(self._selected_node_id) if isinstance(script_dict, dict) else None
            if isinstance(selected_node, dict):
                detail_panel.add_header(
                    PanelHeader("Selected node", self._selected_node_id, title_color=DIALOGUE_EDITOR_DIM_COLOR)
                )
                choices = selected_node.get("choices")
                selected_node_fields = _selected_node_field_rows(self._selected_node_id, selected_node)
                if edit_mode and dialogue_editor is not None:
                    for label, field_path, _current_value in selected_node_fields:
                        self._widget_rows[field_path] = detail_panel.add_row(
                            PanelRow(
                                PanelField(label, "", label_color=DIALOGUE_EDITOR_TEXT_COLOR, value_color=DIALOGUE_EDITOR_DIM_COLOR),
                                height=DIALOGUE_EDITOR_ROW_HEIGHT,
                                padding_x=DIALOGUE_EDITOR_ROW_PADDING_X,
                            )
                        )
                    if isinstance(choices, list):
                        for i, choice in enumerate(choices):
                            if not isinstance(choice, dict):
                                continue
                            self._choice_action_hits.append(
                                (
                                    f"choice.{i}.delete",
                                    detail_panel.add_row(
                                        PanelRow(
                                            PanelField(
                                                f"Delete choice {i}",
                                                "",
                                                label_color=DIALOGUE_EDITOR_BUTTON_COLOR,
                                                value_color=DIALOGUE_EDITOR_DIM_COLOR,
                                            ),
                                            height=DIALOGUE_EDITOR_ROW_HEIGHT,
                                            padding_x=DIALOGUE_EDITOR_ROW_PADDING_X,
                                        )
                                    ),
                                )
                            )
                        self._choice_action_hits.insert(
                            0,
                            (
                                DIALOGUE_EDITOR_CHOICE_ADD_ACTION,
                                detail_panel.add_row(
                                    PanelRow(
                                        PanelField(
                                            "Add choice",
                                            "",
                                            label_color=DIALOGUE_EDITOR_BUTTON_COLOR,
                                            value_color=DIALOGUE_EDITOR_DIM_COLOR,
                                        ),
                                        height=DIALOGUE_EDITOR_ROW_HEIGHT,
                                        padding_x=DIALOGUE_EDITOR_ROW_PADDING_X,
                                    )
                                ),
                            )
                        )
                    self._node_action_hits.append(
                        (
                            "node.delete",
                            detail_panel.add_row(
                                PanelRow(
                                    PanelField(
                                        "Delete node",
                                        "",
                                        label_color=DIALOGUE_EDITOR_BUTTON_COLOR,
                                        value_color=DIALOGUE_EDITOR_DIM_COLOR,
                                    ),
                                    height=DIALOGUE_EDITOR_ROW_HEIGHT,
                                    padding_x=DIALOGUE_EDITOR_ROW_PADDING_X,
                                )
                            ),
                        )
                    )
                else:
                    for label, _field_path, value in selected_node_fields:
                        detail_panel.add_row(
                            PanelRow(
                                PanelField(label, value, label_color=DIALOGUE_EDITOR_TEXT_COLOR, value_color=DIALOGUE_EDITOR_DIM_COLOR),
                                height=DIALOGUE_EDITOR_ROW_HEIGHT,
                                padding_x=DIALOGUE_EDITOR_ROW_PADDING_X,
                            )
                        )
            button_rows = add_form_buttons(
                detail_panel,
                edit_mode=edit_mode,
                button_color=DIALOGUE_EDITOR_BUTTON_COLOR,
                row_height=DIALOGUE_EDITOR_ROW_HEIGHT,
                padding_x=DIALOGUE_EDITOR_ROW_PADDING_X,
            )
        detail_panel.draw()
        if dialogue_editor is not None:
            dialogue_editor.set_button_rects(collect_button_rects(button_rows))
        if edit_mode and dialogue_editor is not None:
            self._draw_edit_widgets(dialogue_editor)

    def row_index_at(self, x: float, y: float) -> int | None:
        for index, row in self._row_hits:
            if row.hit_test(float(x), float(y)):
                return index
        return None

    def node_id_at(self, x: float, y: float) -> str | None:
        for node_id, row in self._node_row_hits:
            if row.hit_test(float(x), float(y)):
                return node_id
        return None

    def choice_action_at(self, x: float, y: float) -> str | None:
        for action, row in self._choice_action_hits:
            if row.hit_test(float(x), float(y)):
                return action
        return None

    def node_action_at(self, x: float, y: float) -> str | None:
        for action, row in self._node_action_hits:
            if row.hit_test(float(x), float(y)):
                return action
        return None

    def set_selected_index(self, index: int) -> bool:
        model = self._get_model()
        setter = getattr(model, "set_selected_index", None)
        return bool(setter(int(index))) if callable(setter) else False

    def set_selected_node_id(self, node_id: str | None) -> None:
        self._selected_node_id = str(node_id) if node_id else None

    def selected_node_id(self) -> str | None:
        return self._selected_node_id

    def selected_dialogue_dict(self) -> dict[str, object] | None:
        model = self._get_model()
        dialogue = model.selected_dialogue() if model is not None and hasattr(model, "selected_dialogue") else None
        return dict(dialogue) if isinstance(dialogue, dict) else None

    def all_dialogue_dicts(self) -> list[dict[str, object]]:
        model = self._get_model()
        dialogues = model.dialogues() if model is not None and hasattr(model, "dialogues") else []
        return [dict(d) for d in dialogues if isinstance(d, dict)]

    def _draw_text_input(self, text_input: TextInput, rect: Rect) -> None:
        draw_text_input(text_input, rect, _DIALOGUE_FORM_COLORS)

    def _sync_edit_widgets(self, dialogue_editor: object) -> None:
        edit_buffer = getattr(dialogue_editor, "edit_buffer", None)
        if not isinstance(edit_buffer, dict):
            return
        focused = getattr(dialogue_editor, "focused_field", lambda: None)
        focused_field = focused() if callable(focused) else None
        text_inputs = getattr(dialogue_editor, "text_inputs", lambda: {})()
        if isinstance(text_inputs, dict):
            sync_text_inputs(
                text_inputs,
                focused_field,
                lambda field: _field_value(dialogue_editor, edit_buffer, str(field)),
            )

    def _draw_edit_widgets(self, dialogue_editor: object) -> None:
        text_inputs = getattr(dialogue_editor, "text_inputs", lambda: {})()
        if isinstance(text_inputs, dict):
            draw_text_input_rows(self._widget_rows, text_inputs, self._draw_text_input)

    def try_click_widget(self, x: float, y: float) -> str | None:
        controller = self._get_controller()
        dialogue_editor = getattr(controller, "dialogue_editor", None) if controller is not None else None
        if dialogue_editor is None:
            return None
        return try_click_text_widget(self._widget_rows, dialogue_editor, x, y)


def _label_for_field(field_path: str) -> str:
    return {
        "id": "ID",
        "schema_version": "Schema version",
        "start_node": "Start node",
    }.get(field_path, field_path)


def _field_value(dialogue_editor: object, edit_buffer: dict[str, object], field_path: str) -> object:
    getter = getattr(dialogue_editor, "field_value", None)
    if callable(getter):
        try:
            return getter(field_path)
        except Exception:  # noqa: BLE001  # REASON: overlay sync must fall back for lightweight editor stubs
            pass
    return edit_buffer.get(field_path)
