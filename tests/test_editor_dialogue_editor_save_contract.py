from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine.editor.dialogue_editor_model import (
    dialogue_reference_problem_count,
    dialogue_unreachable_nodes,
    save_dialogues,
    validate_dialogue_entries,
)

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


def test_validate_dialogue_entries_flags_dangling_node_next(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"
    entry = _dialogue()
    entry["script"]["path_a"]["next"] = "missing_node"

    errors = validate_dialogue_entries([entry], target)

    assert (
        "entry 'ep02_dialogue_intro': node 'path_a' next 'missing_node' does not exist in script"
        in errors
    )


def test_validate_dialogue_entries_accepts_node_next_to_sibling(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"
    entry = _dialogue()
    entry["script"]["path_a"]["next"] = "path_b"

    errors = validate_dialogue_entries([entry], target)

    assert not any("node 'path_a' next" in error for error in errors)


def test_validate_dialogue_entries_accepts_null_node_next(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"

    errors = validate_dialogue_entries([_dialogue()], target)

    assert not any("next 'None'" in error for error in errors)


def test_validate_dialogue_entries_flags_dangling_choice_next(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"
    entry = _dialogue()
    entry["script"]["start"]["choices"][1]["next"] = "missing_choice_node"

    errors = validate_dialogue_entries([entry], target)

    assert (
        "entry 'ep02_dialogue_intro': node 'start' choice 1 next 'missing_choice_node' does not exist in script"
        in errors
    )


def test_validate_dialogue_entries_accepts_choice_next_to_sibling(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"

    errors = validate_dialogue_entries([_dialogue()], target)

    assert not any("choice 0 next 'path_a' does not exist" in error for error in errors)
    assert not any("choice 1 next 'path_b' does not exist" in error for error in errors)


def test_validate_dialogue_entries_flags_empty_choice_text(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"
    entry = _dialogue()
    entry["script"]["start"]["choices"][0]["text"] = ""

    errors = validate_dialogue_entries([entry], target)

    assert "entry 'ep02_dialogue_intro': node 'start' choice 0 text is empty" in errors


def test_validate_dialogue_entries_flags_missing_choice_text(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"
    entry = _dialogue()
    entry["script"]["start"]["choices"][1].pop("text")

    errors = validate_dialogue_entries([entry], target)

    assert "entry 'ep02_dialogue_intro': node 'start' choice 1 text is empty" in errors


def test_validate_dialogue_entries_accepts_real_dialogue_database() -> None:
    payload = json.loads(Path("assets/data/dialogues.json").read_text(encoding="utf-8"))

    errors = validate_dialogue_entries(payload["dialogues"], Path("assets/data/dialogues.json"))

    assert errors == []


def test_dialogue_reference_problem_count_clean_dialogue_is_zero() -> None:
    assert dialogue_reference_problem_count(_dialogue()) == 0


def test_dialogue_reference_problem_count_dangling_node_next() -> None:
    entry = _dialogue()
    entry["script"]["path_a"]["next"] = "missing_node"

    assert dialogue_reference_problem_count(entry) == 1


def test_dialogue_reference_problem_count_dangling_choice_next() -> None:
    entry = _dialogue()
    entry["script"]["start"]["choices"][0]["next"] = "missing_choice_node"

    assert dialogue_reference_problem_count(entry) == 1


def test_dialogue_reference_problem_count_empty_choice_text() -> None:
    entry = _dialogue()
    entry["script"]["start"]["choices"][1]["text"] = ""

    assert dialogue_reference_problem_count(entry) == 1


def test_dialogue_reference_problem_count_combined_multiplicity() -> None:
    entry = _dialogue()
    entry["script"]["path_a"]["next"] = "missing_node"
    entry["script"]["start"]["choices"][0]["next"] = "missing_choice_node"
    entry["script"]["start"]["choices"][1].pop("text")

    assert dialogue_reference_problem_count(entry) == 3


def test_validate_dialogue_entries_reference_messages_unchanged(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "dialogues.json"
    entry = _dialogue()
    entry["script"]["path_a"]["next"] = "missing_node"
    entry["script"]["start"]["choices"][0]["next"] = "missing_choice_node"
    entry["script"]["start"]["choices"][1].pop("text")

    errors = validate_dialogue_entries([entry], target)

    assert "entry 'ep02_dialogue_intro': node 'path_a' next 'missing_node' does not exist in script" in errors
    assert (
        "entry 'ep02_dialogue_intro': node 'start' choice 0 next 'missing_choice_node' does not exist in script"
        in errors
    )
    assert "entry 'ep02_dialogue_intro': node 'start' choice 1 text is empty" in errors


# ---------------------------------------------------------------------------
# dialogue_unreachable_nodes
# ---------------------------------------------------------------------------


def test_dialogue_unreachable_nodes_all_reachable_returns_empty() -> None:
    entry: dict = {
        "start_node": "a",
        "script": {
            "a": {"next": "b"},
            "b": {"next": "c"},
            "c": {"next": None},
        },
    }
    assert dialogue_unreachable_nodes(entry) == []


def test_dialogue_unreachable_nodes_one_orphan() -> None:
    # orphan's own next points to a non-existent id — dangling out-edge safety check
    entry: dict = {
        "start_node": "a",
        "script": {
            "a": {"next": "b"},
            "b": {"next": None},
            "orphan": {"next": "nonexistent"},
        },
    }
    assert dialogue_unreachable_nodes(entry) == ["orphan"]


def test_dialogue_unreachable_nodes_cycle_among_reachable_returns_empty() -> None:
    entry: dict = {
        "start_node": "a",
        "script": {
            "a": {"next": "b"},
            "b": {"next": "a"},
        },
    }
    assert dialogue_unreachable_nodes(entry) == []


def test_dialogue_unreachable_nodes_orphaned_cycle() -> None:
    entry: dict = {
        "start_node": "a",
        "script": {
            "a": {"next": None},
            "b": {"next": "c"},
            "c": {"next": "b"},
        },
    }
    assert dialogue_unreachable_nodes(entry) == ["b", "c"]


def test_dialogue_unreachable_nodes_missing_start_node_returns_empty() -> None:
    entry: dict = {
        "script": {
            "a": {"next": "b"},
            "b": {"next": None},
        },
    }
    assert dialogue_unreachable_nodes(entry) == []
    entry_empty: dict = {"start_node": "", "script": {"a": {"next": None}}}
    assert dialogue_unreachable_nodes(entry_empty) == []


def test_dialogue_unreachable_nodes_start_node_not_in_script_returns_empty() -> None:
    entry: dict = {
        "start_node": "nonexistent",
        "script": {
            "a": {"next": "b"},
            "b": {"next": None},
        },
    }
    assert dialogue_unreachable_nodes(entry) == []


def test_dialogue_unreachable_nodes_reachable_only_via_choice_next() -> None:
    entry: dict = {
        "start_node": "start",
        "script": {
            "start": {"choices": [{"next": "branch", "text": "Go."}, {"next": "end", "text": "Stop."}]},
            "branch": {"next": None},
            "end": {"next": None},
        },
    }
    assert dialogue_unreachable_nodes(entry) == []


def test_dialogue_unreachable_nodes_reachable_only_via_node_next() -> None:
    entry: dict = {
        "start_node": "start",
        "script": {
            "start": {"next": "middle"},
            "middle": {"next": "end"},
            "end": {"next": None},
        },
    }
    assert dialogue_unreachable_nodes(entry) == []
