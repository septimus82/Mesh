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
    assert "Node count" in captured
    assert "Choice count" in captured


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
