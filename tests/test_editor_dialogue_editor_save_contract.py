from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine.editor.dialogue_editor_model import save_dialogues, validate_dialogue_entries

pytestmark = [pytest.mark.fast]


def _dialogue(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "ep02_dialogue_intro",
        "schema_version": 1,
        "script": {
            "start": {
                "speaker": "Mentor",
                "text": "Choose your approach.",
                "choices": [
                    {"next": "path_a", "text": "Option A."},
                    {"next": "path_b", "text": "Option B."},
                ],
            },
            "path_a": {"speaker": "Mentor", "text": "Path A chosen.", "next": None},
            "path_b": {"speaker": "Mentor", "text": "Path B chosen.", "next": None},
        },
        "start_node": "start",
    }
    payload.update(overrides)
    return payload


def test_save_dialogues_round_trips_wrapped_entries(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"
    entries = [
        _dialogue(id="ep02_dialogue_intro"),
        _dialogue(id="ep03_dialogue_intro"),
    ]

    save_dialogues(entries, target)

    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert list(loaded) == ["dialogues"]
    assert [e["id"] for e in loaded["dialogues"]] == ["ep02_dialogue_intro", "ep03_dialogue_intro"]
    assert loaded["dialogues"][0]["script"]["start"]["text"] == "Choose your approach."
    assert loaded["dialogues"][0]["schema_version"] == 1
    assert target.read_text(encoding="utf-8").endswith("\n")


def test_save_dialogues_accepts_empty_list(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"

    save_dialogues([], target)

    assert json.loads(target.read_text(encoding="utf-8")) == {"dialogues": []}


def test_save_dialogues_missing_id_raises_and_does_not_write(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"

    with pytest.raises(ValueError, match="id must be a non-empty string"):
        save_dialogues([_dialogue(id="")], target)

    assert not target.exists()


def test_save_dialogues_rejects_duplicate_ids(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"

    with pytest.raises(ValueError, match="duplicate dialogue id"):
        save_dialogues(
            [
                _dialogue(id="same_id"),
                _dialogue(id="same_id"),
            ],
            target,
        )

    assert not target.exists()


@pytest.mark.parametrize("bad_version", ["1", 0, -1, 1.5])
def test_save_dialogues_rejects_invalid_schema_version(
    tmp_path: Path, bad_version: Any
) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"

    with pytest.raises(ValueError, match="schema_version must be a positive integer"):
        save_dialogues([_dialogue(schema_version=bad_version)], target)

    assert not target.exists()


def test_save_dialogues_rejects_start_node_not_in_script(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"

    with pytest.raises(ValueError, match="start_node 'nonexistent_node' does not exist in script"):
        save_dialogues([_dialogue(start_node="nonexistent_node")], target)

    assert not target.exists()


def test_save_dialogues_accepts_valid_integer_schema_version(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"

    save_dialogues([_dialogue(schema_version=2)], target)

    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded["dialogues"][0]["schema_version"] == 2


def test_save_dialogues_accepts_absent_start_node(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"
    entry = _dialogue()
    entry.pop("start_node")

    save_dialogues([entry], target)

    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert "start_node" not in loaded["dialogues"][0]


def test_save_dialogues_accepts_start_node_referencing_real_node(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"

    save_dialogues([_dialogue(start_node="path_a")], target)

    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded["dialogues"][0]["start_node"] == "path_a"


def test_save_dialogues_invalid_leaves_existing_file_unchanged(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"
    target.parent.mkdir(parents=True)
    original = '{"dialogues": []}\n'
    target.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate dialogue id"):
        save_dialogues([_dialogue(id="dup"), _dialogue(id="dup")], target)

    assert target.read_text(encoding="utf-8") == original


def test_validate_dialogue_entries_returns_list_of_strings(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"

    errors = validate_dialogue_entries([_dialogue(id="")], target)

    assert errors
    assert all(isinstance(error, str) for error in errors)
    assert any("id must be a non-empty string" in error for error in errors)
