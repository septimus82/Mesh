from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engine.editor.quest_editor_model import save_quests, validate_quest_entries

pytestmark = [pytest.mark.fast]


def _quest(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "showcase_tour",
        "title": "Tour of the Mesh",
        "description": "Visit the demonstration rooms.",
        "type": "tour",
        "start_toast": "Tour started",
        "complete_toast": "Tour complete",
        "stages": [{"id": "intro", "title": "Talk", "text": "Talk to the guide."}],
        "reward": {"inc_counters": {"developer_badge": 1}},
        "requires_flags": ["intro_complete"],
        "blocks_flags": ["tour_blocked"],
    }
    payload.update(overrides)
    return payload


def test_save_quests_round_trips_wrapped_entries(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "quests.json"
    entries = [
        _quest(id="showcase_tour", title="Tour of the Mesh"),
        _quest(id="cellar_exterminator", title="Cellar Exterminator"),
    ]

    save_quests(entries, target)

    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert list(loaded) == ["quests"]
    assert [entry["id"] for entry in loaded["quests"]] == ["showcase_tour", "cellar_exterminator"]
    assert loaded["quests"][0]["stages"][0]["id"] == "intro"
    assert loaded["quests"][0]["reward"] == {"inc_counters": {"developer_badge": 1}}
    assert loaded["quests"][0]["requires_flags"] == ["intro_complete"]
    assert target.read_text(encoding="utf-8").endswith("\n")


def test_save_quests_accepts_empty_quest_list(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "quests.json"

    save_quests([], target)

    assert json.loads(target.read_text(encoding="utf-8")) == {"quests": []}


def test_save_quests_missing_id_raises_and_does_not_write(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "quests.json"

    with pytest.raises(ValueError, match="non-empty 'id'"):
        save_quests([_quest(id="")], target)

    assert not target.exists()


def test_save_quests_missing_title_leaves_existing_file_unchanged(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "quests.json"
    target.parent.mkdir(parents=True)
    original = '{"quests": []}\n'
    target.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="non-empty 'title'"):
        save_quests([_quest(title="")], target)

    assert target.read_text(encoding="utf-8") == original


def test_save_quests_rejects_duplicate_ids(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "quests.json"

    with pytest.raises(ValueError, match="Duplicate quest id 'same_id'"):
        save_quests(
            [
                _quest(id="same_id", title="First"),
                _quest(id="same_id", title="Second"),
            ],
            target,
        )

    assert not target.exists()


def test_save_quests_rejects_missing_stages(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "quests.json"
    bad = _quest()
    bad.pop("stages")

    with pytest.raises(ValueError, match="must have a 'stages' array"):
        save_quests([bad], target)

    assert not target.exists()


def test_validate_quest_entries_normalizes_validation_errors_to_strings(tmp_path: Path) -> None:
    target = tmp_path / "assets" / "data" / "quests.json"

    errors = validate_quest_entries([_quest(id="")], target)

    assert errors
    assert all(isinstance(error, str) for error in errors)
    assert any("non-empty 'id'" in error for error in errors)
