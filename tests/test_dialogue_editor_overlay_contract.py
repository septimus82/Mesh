from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import engine.editor.widgets.panel_primitives as panel_primitives
from engine.editor.dialogue_editor_model import DialogueEditorModel
from engine.editor.dock_tab_registry import DOCK_TAB_TOOLTIPS, RIGHT_DOCK_TABS
from engine.ui_overlays.dialogue_editor_overlay import (
    DIALOGUE_EDITOR_EDITABLE_SCALAR_FIELDS,
    DialogueEditorOverlay,
)
from engine.ui_overlays.widgets import TextInput
from tests._dock_stub import make_dock_stub

pytestmark = [pytest.mark.fast]


class _DialogueEditorStub:
    def __init__(self, *, edit_mode: bool = False, dirty: bool = False, error: str | None = None) -> None:
        self._edit_mode = edit_mode
        self._dirty = dirty
        self._error = error
        self.edit_buffer: dict[str, object] = {
            "id": "ep02_intro",
            "schema_version": 1,
            "start_node": "start",
        }
        self._focused_field: str | None = "id" if edit_mode else None
        self._text_inputs = {
            "id": TextInput(text="ep02_intro", focused=edit_mode, font_size=12, height=18.0),
            "schema_version": TextInput(text="1", focused=False, font_size=12, height=18.0),
            "start_node": TextInput(text="start", focused=False, font_size=12, height=18.0),
        }
        self.button_rects: dict[str, object] = {}

    def is_edit_mode_active(self) -> bool:
        return self._edit_mode

    def is_dirty(self) -> bool:
        return self._dirty

    def last_error_message(self) -> str | None:
        return self._error

    def text_input(self, field: str) -> TextInput:
        return self._text_inputs[field]

    def text_inputs(self) -> dict[str, TextInput]:
        return dict(self._text_inputs)

    def field_value(self, field: str) -> object:
        current: object = self.edit_buffer
        for part in str(field).split("."):
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                idx = int(part)
                current = current[idx] if 0 <= idx < len(current) else None
            else:
                return None
        return current

    def focused_field(self) -> str | None:
        return self._focused_field

    def set_button_rects(self, rects: dict[str, object]) -> None:
        self.button_rects = dict(rects)


def _window_for_tab(right_tab: str, dialogue_editor: object | None = None) -> SimpleNamespace:
    controller = SimpleNamespace(active=True, dock=make_dock_stub(right_tab=right_tab), dialogue_editor=dialogue_editor)
    return SimpleNamespace(width=1280, height=720, editor_controller=controller)


def _dialogue_path(tmp_path: Path, dialogues: list[dict[str, object]] | None = None) -> Path:
    path = tmp_path / "assets" / "data" / "dialogues.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "dialogues": dialogues
                if dialogues is not None
                else [
                    {
                        "id": "ep02_intro",
                        "schema_version": 1,
                        "start_node": "start",
                        "script": {
                            "start": {
                                "speaker": "Mentor",
                                "text": "Hello.",
                                "choices": [{"next": "end", "text": "OK"}],
                            },
                            "end": {"speaker": "Mentor", "text": "Bye.", "next": None},
                        },
                    },
                    {
                        "id": "ep03_intro",
                        "schema_version": 1,
                        "start_node": "start",
                        "script": {"start": {"speaker": "Mentor", "text": "Go.", "next": None}},
                    },
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _model(tmp_path: Path, dialogues: list[dict[str, object]] | None = None) -> DialogueEditorModel:
    return DialogueEditorModel.load(_dialogue_path(tmp_path, dialogues))


def _capture_panel_text(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(panel_primitives, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(panel_primitives, "_draw_tb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(panel_primitives, "draw_text_cached", lambda text, *args, **kwargs: captured.append(str(text)))
    return captured


def test_dialogue_editor_overlay_constructs() -> None:
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))

    assert overlay is not None


def test_dialogue_editor_overlay_uses_layout_primitives() -> None:
    source = DialogueEditorOverlay.draw.__code__.co_names

    assert "EditorPanelBase" in source
    assert "PanelRow" in source
    assert "PanelField" in source
    assert "PanelHeader" in source


def test_dialogue_editor_overlay_visibility_is_dialogue_tab_only() -> None:
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))
    assert overlay._is_visible_for_controller(overlay.window.editor_controller) is True

    other = DialogueEditorOverlay(_window_for_tab("Quests"))
    assert other._is_visible_for_controller(other.window.editor_controller) is False


def test_dialogue_tab_is_registered_after_quests() -> None:
    assert "Dialogue" in RIGHT_DOCK_TABS
    assert RIGHT_DOCK_TABS.index("Dialogue") == RIGHT_DOCK_TABS.index("Quests") + 1
    assert DOCK_TAB_TOOLTIPS["Dialogue"] == "Dialogue -- Browse dialogue database"


def test_dialogue_editor_overlay_renders_selected_dialogue_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert "Dialogue" in captured
    assert "ep02_intro" in captured
    assert "ep03_intro" in captured
    assert "ID" in captured
    assert "Schema version" in captured
    assert "Start node" in captured


def test_dialogue_editor_overlay_renders_script_section(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert "Script (read-only)" in captured
    assert "0 errors" in captured
    assert "Node count" in captured
    assert "Choice count" in captured


def test_dialogue_editor_overlay_renders_script_node_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert "start (start)" in captured
    assert "1 choice" in captured
    assert "end" in captured
    assert "end (start)" not in captured
    assert "(end)" in captured


def test_dialogue_editor_overlay_node_id_at_returns_matching_node() -> None:
    from engine.editor.widgets.panel_primitives import PanelField, PanelRow
    from engine.ui.widgets import Rect

    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))
    start_row = PanelRow(PanelField("start", None), height=18.0, padding_x=6.0)
    end_row = PanelRow(PanelField("end", None), height=18.0, padding_x=6.0)
    start_row.layout(Rect(0, 100, 200, 18))
    end_row.layout(Rect(0, 82, 200, 18))
    overlay._node_row_hits = [("start", start_row), ("end", end_row)]

    assert overlay.node_id_at(10.0, 109.0) == "start"
    assert overlay.node_id_at(10.0, 91.0) == "end"
    assert overlay.node_id_at(500.0, 500.0) is None


def test_dialogue_editor_overlay_set_selected_node_id_stores_id() -> None:
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))

    overlay.set_selected_node_id("end")
    assert overlay._selected_node_id == "end"
    assert overlay.selected_node_id() == "end"

    overlay.set_selected_node_id(None)
    assert overlay._selected_node_id is None
    assert overlay.selected_node_id() is None


def test_dialogue_editor_overlay_draw_highlights_selected_node(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _capture_panel_text(monkeypatch)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))
    overlay._model = _model(tmp_path)
    overlay._selected_dialogue_id_for_node = "ep02_intro"
    overlay._selected_node_id = "end"

    overlay.draw()

    selected = [node_id for node_id, row in overlay._node_row_hits if row.is_selected]
    assert selected == ["end"]


def test_dialogue_editor_overlay_defaults_node_selection_to_start_node(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _capture_panel_text(monkeypatch)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert overlay._selected_node_id == "start"
    selected = [node_id for node_id, row in overlay._node_row_hits if row.is_selected]
    assert selected == ["start"]


def test_dialogue_editor_overlay_switching_dialogue_redefaults_node_selection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _capture_panel_text(monkeypatch)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))
    overlay._model = _model(
        tmp_path,
        [
            {
                "id": "first",
                "schema_version": 1,
                "start_node": "start",
                "script": {"start": {"speaker": "A", "text": "One.", "next": None}},
            },
            {
                "id": "second",
                "schema_version": 1,
                "start_node": "begin",
                "script": {"begin": {"speaker": "B", "text": "Two.", "next": None}},
            },
        ],
    )
    overlay.draw()
    overlay._model.set_selected_index(1)

    overlay.draw()

    assert overlay._selected_dialogue_id_for_node == "second"
    assert overlay._selected_node_id == "begin"


def test_dialogue_editor_overlay_renders_selected_node_detail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))
    overlay._model = _model(tmp_path)
    overlay._selected_dialogue_id_for_node = "ep02_intro"
    overlay._selected_node_id = "end"

    overlay.draw()

    assert "Selected node" in captured
    assert "Speaker" in captured
    assert "Text" in captured
    assert "Bye." in captured


def test_dialogue_editor_overlay_view_mode_selected_node_detail_is_read_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))
    overlay._model = _model(tmp_path)
    overlay._selected_dialogue_id_for_node = "ep02_intro"
    overlay._selected_node_id = "end"

    overlay.draw()

    assert "Speaker" in captured
    assert "Text" in captured
    assert "script.end.speaker" not in overlay._widget_rows
    assert "script.end.text" not in overlay._widget_rows


def test_dialogue_editor_overlay_view_mode_renders_choice_rows_read_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))
    overlay._model = _model(tmp_path)
    overlay._selected_dialogue_id_for_node = "ep02_intro"
    overlay._selected_node_id = "start"

    overlay.draw()

    assert "Choice 0 text" in captured
    assert "OK" in captured
    assert "Choice 0 next" in captured
    assert "end" in captured
    assert "script.start.choices.0.text" not in overlay._widget_rows
    assert "script.start.choices.0.next" not in overlay._widget_rows


def test_dialogue_editor_overlay_edit_mode_selected_node_detail_registers_widgets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _capture_panel_text(monkeypatch)
    dialogue_editor = _DialogueEditorStub(edit_mode=True)
    dialogue_editor.edit_buffer["script"] = {
        "start": {"speaker": "Mentor", "text": "Hello.", "choices": [{"next": "end", "text": "OK"}]},
        "end": {"speaker": "Mentor", "text": "Bye.", "next": None},
    }
    dialogue_editor._text_inputs["script.end.speaker"] = TextInput(text="", focused=False, font_size=12, height=18.0)
    dialogue_editor._text_inputs["script.end.text"] = TextInput(text="", focused=False, font_size=12, height=18.0)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue", dialogue_editor))
    overlay._model = _model(tmp_path)
    overlay._selected_dialogue_id_for_node = "ep02_intro"
    overlay._selected_node_id = "end"

    overlay.draw()

    assert "script.end.speaker" in overlay._widget_rows
    assert "script.end.text" in overlay._widget_rows
    assert dialogue_editor.text_input("script.end.speaker").text == "Mentor"
    assert dialogue_editor.text_input("script.end.text").text == "Bye."


def test_dialogue_editor_overlay_edit_mode_choice_rows_register_widgets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _capture_panel_text(monkeypatch)
    dialogue_editor = _DialogueEditorStub(edit_mode=True)
    dialogue_editor.edit_buffer["script"] = {
        "start": {"speaker": "Mentor", "text": "Hello.", "choices": [{"next": "end", "text": "OK"}]},
        "end": {"speaker": "Mentor", "text": "Bye.", "next": None},
    }
    for field in (
        "script.start.speaker",
        "script.start.text",
        "script.start.choices.0.text",
        "script.start.choices.0.next",
    ):
        dialogue_editor._text_inputs[field] = TextInput(text="", focused=False, font_size=12, height=18.0)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue", dialogue_editor))
    overlay._model = _model(tmp_path)
    overlay._selected_dialogue_id_for_node = "ep02_intro"
    overlay._selected_node_id = "start"

    overlay.draw()

    assert "script.start.choices.0.text" in overlay._widget_rows
    assert "script.start.choices.0.next" in overlay._widget_rows
    assert dialogue_editor.text_input("script.start.choices.0.text").text == "OK"
    assert dialogue_editor.text_input("script.start.choices.0.next").text == "end"


def test_dialogue_editor_overlay_edit_mode_branch_node_renders_add_choice_action(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    dialogue_editor = _DialogueEditorStub(edit_mode=True)
    dialogue_editor.edit_buffer["script"] = {
        "start": {"speaker": "Mentor", "text": "Hello.", "choices": [{"next": "end", "text": "OK"}]},
        "end": {"speaker": "Mentor", "text": "Bye.", "next": None},
    }
    for field in (
        "script.start.speaker",
        "script.start.text",
        "script.start.choices.0.text",
        "script.start.choices.0.next",
    ):
        dialogue_editor._text_inputs[field] = TextInput(text="", focused=False, font_size=12, height=18.0)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue", dialogue_editor))
    overlay._model = _model(tmp_path)
    overlay._selected_dialogue_id_for_node = "ep02_intro"
    overlay._selected_node_id = "start"

    overlay.draw()

    assert "Add choice" in captured
    assert "choice.add" not in overlay._widget_rows
    action, row = overlay._choice_action_hits[0]
    assert action == "choice.add"
    rect = row.last_rect
    assert rect is not None
    assert overlay.choice_action_at(rect.left + 1.0, rect.center_y) == "choice.add"


def test_dialogue_editor_overlay_no_add_choice_action_in_view_or_linear_edit_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    view_overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))
    view_overlay._model = _model(tmp_path)
    view_overlay._selected_dialogue_id_for_node = "ep02_intro"
    view_overlay._selected_node_id = "start"

    view_overlay.draw()

    assert "Add choice" not in captured
    assert view_overlay.choice_action_at(0.0, 0.0) is None

    dialogue_editor = _DialogueEditorStub(edit_mode=True)
    dialogue_editor.edit_buffer["script"] = {
        "start": {"speaker": "Mentor", "text": "Hello.", "choices": [{"next": "end", "text": "OK"}]},
        "end": {"speaker": "Mentor", "text": "Bye.", "next": None},
    }
    dialogue_editor._text_inputs["script.end.speaker"] = TextInput(text="", focused=False, font_size=12, height=18.0)
    dialogue_editor._text_inputs["script.end.text"] = TextInput(text="", focused=False, font_size=12, height=18.0)
    edit_overlay = DialogueEditorOverlay(_window_for_tab("Dialogue", dialogue_editor))
    edit_overlay._model = _model(tmp_path)
    edit_overlay._selected_dialogue_id_for_node = "ep02_intro"
    edit_overlay._selected_node_id = "end"

    edit_overlay.draw()

    assert "choice.add" not in edit_overlay._widget_rows
    assert edit_overlay.choice_action_at(0.0, 0.0) is None


def test_dialogue_editor_overlay_edit_mode_renders_delete_choice_actions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    dialogue_editor = _DialogueEditorStub(edit_mode=True)
    dialogue_editor.edit_buffer["script"] = {
        "start": {
            "speaker": "Mentor",
            "text": "Hello.",
            "choices": [{"next": "a", "text": "First"}, "bad", {"next": "c", "text": "Third"}],
        },
        "a": {"speaker": "Mentor", "text": "A.", "next": None},
        "c": {"speaker": "Mentor", "text": "C.", "next": None},
    }
    for field in (
        "script.start.speaker",
        "script.start.text",
        "script.start.choices.0.text",
        "script.start.choices.0.next",
        "script.start.choices.2.text",
        "script.start.choices.2.next",
    ):
        dialogue_editor._text_inputs[field] = TextInput(text="", focused=False, font_size=12, height=18.0)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue", dialogue_editor))
    overlay._model = _model(
        tmp_path,
        [
            {
                "id": "branching",
                "schema_version": 1,
                "start_node": "start",
                "script": dialogue_editor.edit_buffer["script"],
            }
        ],
    )
    overlay._selected_dialogue_id_for_node = "branching"
    overlay._selected_node_id = "start"

    overlay.draw()

    assert "Delete choice 0" in captured
    assert "Delete choice 1" not in captured
    assert "Delete choice 2" in captured
    assert "choice.0.delete" not in overlay._widget_rows
    assert "choice.2.delete" not in overlay._widget_rows
    hit_rows = dict(overlay._choice_action_hits)
    for action in ("choice.0.delete", "choice.2.delete"):
        rect = hit_rows[action].last_rect
        assert rect is not None
        assert overlay.choice_action_at(rect.left + 1.0, rect.center_y) == action


def test_dialogue_editor_overlay_no_delete_choice_actions_in_view_or_linear_edit_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    view_overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))
    view_overlay._model = _model(tmp_path)
    view_overlay._selected_dialogue_id_for_node = "ep02_intro"
    view_overlay._selected_node_id = "start"

    view_overlay.draw()

    assert "Delete choice 0" not in captured
    assert view_overlay.choice_action_at(0.0, 0.0) is None

    dialogue_editor = _DialogueEditorStub(edit_mode=True)
    dialogue_editor.edit_buffer["script"] = {
        "start": {"speaker": "Mentor", "text": "Hello.", "choices": [{"next": "end", "text": "OK"}]},
        "end": {"speaker": "Mentor", "text": "Bye.", "next": None},
    }
    dialogue_editor._text_inputs["script.end.speaker"] = TextInput(text="", focused=False, font_size=12, height=18.0)
    dialogue_editor._text_inputs["script.end.text"] = TextInput(text="", focused=False, font_size=12, height=18.0)
    edit_overlay = DialogueEditorOverlay(_window_for_tab("Dialogue", dialogue_editor))
    edit_overlay._model = _model(tmp_path)
    edit_overlay._selected_dialogue_id_for_node = "ep02_intro"
    edit_overlay._selected_node_id = "end"

    edit_overlay.draw()

    assert not any(action.endswith(".delete") for action, _row in edit_overlay._choice_action_hits)


def test_dialogue_editor_overlay_selected_node_fields_skip_non_dict_choices(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dialogues = [
        {
            "id": "branching",
            "schema_version": 1,
            "start_node": "start",
            "script": {
                "start": {
                    "speaker": "Mentor",
                    "text": "Choose.",
                    "choices": [
                        {"text": "First", "next": "a"},
                        "not-a-choice",
                        {"text": "Third", "next": "c"},
                    ],
                },
                "a": {"speaker": "Mentor", "text": "A.", "next": None},
                "c": {"speaker": "Mentor", "text": "C.", "next": None},
            },
        }
    ]
    captured = _capture_panel_text(monkeypatch)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))
    overlay._model = _model(tmp_path, dialogues)
    overlay._selected_dialogue_id_for_node = "branching"
    overlay._selected_node_id = "start"

    overlay.draw()

    ordered_labels = ["Speaker", "Text", "Choice 0 text", "Choice 0 next", "Choice 2 text", "Choice 2 next"]
    label_positions = [captured.index(label) for label in ordered_labels]
    assert label_positions == sorted(label_positions)
    assert "Choice 1 text" not in captured
    assert "Choice 1 next" not in captured
    assert "First" in captured
    assert "a" in captured
    assert "Third" in captured
    assert "c" in captured

    dialogue_editor = _DialogueEditorStub(edit_mode=True)
    dialogue_editor.edit_buffer = dict(dialogues[0])
    edit_overlay = DialogueEditorOverlay(_window_for_tab("Dialogue", dialogue_editor))
    edit_overlay._model = _model(tmp_path, dialogues)
    edit_overlay._selected_dialogue_id_for_node = "branching"
    edit_overlay._selected_node_id = "start"

    edit_overlay.draw()

    assert {
        "script.start.speaker",
        "script.start.text",
        "script.start.choices.0.text",
        "script.start.choices.0.next",
        "script.start.choices.2.text",
        "script.start.choices.2.next",
    } <= set(edit_overlay._widget_rows)
    assert not any(".choices.1." in field for field in edit_overlay._widget_rows)


def test_dialogue_editor_overlay_linear_node_renders_no_choice_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    dialogue_editor = _DialogueEditorStub(edit_mode=True)
    dialogue_editor.edit_buffer["script"] = {
        "start": {"speaker": "Mentor", "text": "Hello.", "choices": [{"next": "end", "text": "OK"}]},
        "end": {"speaker": "Mentor", "text": "Bye.", "next": None},
    }
    dialogue_editor._text_inputs["script.end.speaker"] = TextInput(text="", focused=False, font_size=12, height=18.0)
    dialogue_editor._text_inputs["script.end.text"] = TextInput(text="", focused=False, font_size=12, height=18.0)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue", dialogue_editor))
    overlay._model = _model(tmp_path)
    overlay._selected_dialogue_id_for_node = "ep02_intro"
    overlay._selected_node_id = "end"

    overlay.draw()

    assert "Choice 0 text" not in captured
    assert "Choice 0 next" not in captured
    assert not any(".choices." in field for field in overlay._widget_rows)


def test_dialogue_editor_overlay_renders_single_reference_error_badge(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))
    overlay._model = _model(
        tmp_path,
        [
            {
                "id": "bad_ref",
                "schema_version": 1,
                "start_node": "start",
                "script": {"start": {"text": "Broken.", "next": "missing"}},
            }
        ],
    )

    overlay.draw()

    assert "Script (read-only)" in captured
    assert "1 error" in captured


def test_dialogue_editor_overlay_renders_plural_reference_error_badge(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))
    overlay._model = _model(
        tmp_path,
        [
            {
                "id": "bad_refs",
                "schema_version": 1,
                "start_node": "start",
                "script": {
                    "start": {
                        "text": "Broken.",
                        "next": "missing",
                        "choices": [{"next": "also_missing", "text": ""}],
                    }
                },
            }
        ],
    )

    overlay.draw()

    assert "Script (read-only)" in captured
    assert "3 errors" in captured


def test_dialogue_editor_overlay_view_mode_shows_edit_button(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    dialogue_editor = _DialogueEditorStub(edit_mode=False)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue", dialogue_editor))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert "Edit" in captured
    assert "Save" not in captured
    assert "Cancel" not in captured
    assert "edit" in dialogue_editor.button_rects


def test_dialogue_editor_overlay_edit_mode_shows_save_cancel_and_scalar_widgets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    dialogue_editor = _DialogueEditorStub(edit_mode=True)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue", dialogue_editor))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert "Save" in captured
    assert "Cancel" in captured
    assert "Edit" not in captured
    assert DIALOGUE_EDITOR_EDITABLE_SCALAR_FIELDS <= set(overlay._widget_rows)
    assert {"save", "cancel"} <= set(dialogue_editor.button_rects)
    assert "Script (read-only)" in captured


def test_dialogue_editor_overlay_edit_mode_shows_optional_fields_when_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _capture_panel_text(monkeypatch)
    dialogue_editor = _DialogueEditorStub(edit_mode=True)
    dialogue_editor.edit_buffer = {"id": "minimal"}
    dialogue_editor._text_inputs["schema_version"].text = ""
    dialogue_editor._text_inputs["start_node"].text = ""
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue", dialogue_editor))
    overlay._model = _model(tmp_path, [{"id": "minimal", "script": {}}])

    overlay.draw()

    assert DIALOGUE_EDITOR_EDITABLE_SCALAR_FIELDS <= set(overlay._widget_rows)
    assert dialogue_editor.text_input("schema_version").text == ""
    assert dialogue_editor.text_input("start_node").text == ""


def test_dialogue_editor_overlay_syncs_scalar_widget_values_from_buffer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _capture_panel_text(monkeypatch)
    dialogue_editor = _DialogueEditorStub(edit_mode=True)
    dialogue_editor.edit_buffer["start_node"] = "changed_node"
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue", dialogue_editor))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert dialogue_editor.text_input("id").text == "ep02_intro"
    assert dialogue_editor.text_input("start_node").text == "changed_node"


def test_dialogue_editor_overlay_dirty_marker_and_error_row(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    dialogue_editor = _DialogueEditorStub(edit_mode=True, dirty=True, error="id is required")
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue", dialogue_editor))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert "ep02_intro *" in captured
    assert "Error" in captured
    assert "id is required" in captured


def test_dialogue_editor_overlay_click_text_widget_returns_field_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _capture_panel_text(monkeypatch)
    dialogue_editor = _DialogueEditorStub(edit_mode=True)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue", dialogue_editor))
    overlay._model = _model(tmp_path)
    overlay.draw()

    for field in ("id", "schema_version", "start_node"):
        row = overlay._widget_rows[field]
        rect = row.last_rect
        assert rect is not None

        assert overlay.try_click_widget(rect.left + 100.0, rect.center_y) == field


def test_dialogue_editor_overlay_script_not_in_widget_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _capture_panel_text(monkeypatch)
    dialogue_editor = _DialogueEditorStub(edit_mode=True)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue", dialogue_editor))
    overlay._model = _model(tmp_path)

    overlay.draw()

    assert "script" not in overlay._widget_rows
    assert "node_count" not in overlay._widget_rows


def test_dialogue_editor_overlay_renders_empty_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured = _capture_panel_text(monkeypatch)
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))
    overlay._model = _model(tmp_path, [])

    overlay.draw()

    assert "No dialogue entries found" in captured
    assert "No entry" in captured


def test_dialogue_editor_overlay_selected_dialogue_dict_and_all_dialogue_dicts(tmp_path: Path) -> None:
    overlay = DialogueEditorOverlay(_window_for_tab("Dialogue"))
    overlay._model = _model(tmp_path)

    selected = overlay.selected_dialogue_dict()
    all_dicts = overlay.all_dialogue_dicts()

    assert isinstance(selected, dict)
    assert selected["id"] == "ep02_intro"
    assert len(all_dicts) == 2
    assert all_dicts[0]["id"] == "ep02_intro"
    assert all_dicts[1]["id"] == "ep03_intro"
