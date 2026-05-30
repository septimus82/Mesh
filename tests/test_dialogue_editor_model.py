from __future__ import annotations

from pathlib import Path

import pytest

from engine.editor.dialogue_editor_model import DialogueEditorModel, script_rows


pytestmark = [pytest.mark.fast]


def _dialogue_path(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "dialogues.json"
    import json

    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_dialogue_editor_model_loads_rows_and_detail_counts(tmp_path: Path) -> None:
    path = _dialogue_path(
        tmp_path,
        {
            "dialogues": [
                {
                    "id": "intro",
                    "schema_version": 1,
                    "start_node": "start",
                    "script": {
                        "start": {"text": "Hello", "choices": [{"text": "Continue", "next": "end"}]},
                        "end": {"text": "Done", "next": None},
                    },
                }
            ]
        },
    )

    model = DialogueEditorModel.load(path)

    assert model.dialogue_count == 1
    assert model.list_rows() == [("intro", "start", "2")]
    assert model.detail_rows() == [
        ("ID", "intro"),
        ("Schema version", "1"),
        ("Start node", "start"),
        ("Node count", "2"),
        ("Choice count", "1"),
    ]


def test_dialogue_editor_model_selection_clamps_and_returns_copy(tmp_path: Path) -> None:
    path = _dialogue_path(
        tmp_path,
        {
            "dialogues": [
                {"id": "a", "start_node": "start", "script": {}},
                {"id": "b", "start_node": "start", "script": {}},
            ]
        },
    )
    model = DialogueEditorModel.load(path)

    assert model.set_selected_index(99) is True
    assert model.selected_index() == 1
    selected = model.selected_dialogue()
    assert selected == {"id": "b", "start_node": "start", "script": {}}
    assert selected is not model.dialogues()[1]


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"dialogues": "not-a-list"},
        {"dialogues": [None, "bad"]},
    ],
)
def test_dialogue_editor_model_malformed_payloads_are_empty(tmp_path: Path, payload: object) -> None:
    model = DialogueEditorModel.load(_dialogue_path(tmp_path, payload))

    assert model.dialogues() == []
    assert model.list_rows() == []
    assert model.detail_rows() == []


def test_dialogue_editor_model_missing_file_is_empty(tmp_path: Path) -> None:
    model = DialogueEditorModel.load(tmp_path / "missing.json")

    assert model.dialogue_count == 0
    assert model.selected_dialogue() is None


def test_script_rows_preserves_natural_order_and_summarizes_edges() -> None:
    dialogue = {
        "script": {
            "start": {"text": "Start", "next": "middle"},
            "middle": {"text": "Middle", "choices": [{"text": "End", "next": "end"}, {"text": "Loop", "next": "start"}]},
            "end": {"text": "End", "next": None},
        }
    }

    assert script_rows(dialogue) == [
        ("start", "-> middle"),
        ("middle", "2 choices"),
        ("end", "(end)"),
    ]


def test_script_rows_singular_and_empty_choices() -> None:
    dialogue = {
        "script": {
            "single": {"text": "One", "choices": [{"text": "Go", "next": "end"}]},
            "empty": {"text": "None", "choices": []},
        }
    }

    assert script_rows(dialogue) == [
        ("single", "1 choice"),
        ("empty", "0 choices"),
    ]


def test_script_rows_next_wins_over_choices() -> None:
    dialogue = {"script": {"mixed": {"text": "Mixed", "next": "end", "choices": [{"text": "Ignored"}]}}}

    assert script_rows(dialogue) == [("mixed", "-> end")]


def test_script_rows_skips_non_dict_nodes_and_non_dict_script() -> None:
    assert script_rows({"script": {"start": "bad", "end": {"text": "End"}}}) == [("end", "(end)")]
    assert script_rows({"script": []}) == []
