from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.editor.quest_editor_model import (
    QUEST_COMPLEX_FIELD_ORDER,
    QUEST_SCALAR_FIELD_ORDER,
    QuestEditorModel,
    stage_rows,
)

pytestmark = [pytest.mark.fast]


def _write_quests(path: Path, quests: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"quests": quests}, indent=2), encoding="utf-8")


def _quest_path(tmp_path: Path) -> Path:
    path = tmp_path / "assets" / "data" / "quests.json"
    _write_quests(
        path,
        [
            {
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
            },
            {
                "id": "test_quest",
                "title": "Test Quest",
                "type": None,
                "steps": [],
            },
        ],
    )
    return path


def test_quest_editor_model_loads_real_quests() -> None:
    model = QuestEditorModel.load()

    assert model.quest_count > 0
    assert any(quest.get("id") == "showcase_tour" for quest in model.quests())


def test_quest_editor_model_loads_direct_json_shape(tmp_path: Path) -> None:
    model = QuestEditorModel.load(_quest_path(tmp_path))

    assert model.quest_count == 2
    assert model.list_rows()[0] == ("Tour of the Mesh", "showcase_tour")
    assert model.list_rows()[1] == ("Test Quest", "test_quest")


def test_quest_editor_model_selection_mutation(tmp_path: Path) -> None:
    model = QuestEditorModel.load(_quest_path(tmp_path))

    assert model.selected_index() == 0
    assert model.set_selected_index(1) is True
    assert model.selected_index() == 1
    assert model.selected_quest() is not None
    assert model.selected_quest()["id"] == "test_quest"
    assert model.set_selected_index(999) is False
    assert model.selected_index() == 1


def test_quest_editor_model_detail_rows_split_scalar_and_complex_fields(tmp_path: Path) -> None:
    model = QuestEditorModel.load(_quest_path(tmp_path))

    assert ("ID", "showcase_tour", "id") in model.scalar_detail_rows()
    assert ("Title", "Tour of the Mesh", "title") in model.scalar_detail_rows()
    assert ("Description", "Visit the demonstration rooms.", "description") in model.scalar_detail_rows()
    assert ("Type", "tour", "type") in model.scalar_detail_rows()
    assert ("Start toast", "Tour started", "start_toast") in model.scalar_detail_rows()
    assert ("Complete toast", "Tour complete", "complete_toast") in model.scalar_detail_rows()
    assert any(label == "Stages" for label, _value in model.complex_detail_rows())
    assert ("Reward", '{"inc_counters":{"developer_badge":1}}') in model.complex_detail_rows()
    assert ("Requires flags", "intro_complete") in model.complex_detail_rows()
    assert ("Blocks flags", "tour_blocked") in model.complex_detail_rows()


def test_quest_editor_model_field_orders_are_locked() -> None:
    assert QUEST_SCALAR_FIELD_ORDER == (
        "id",
        "title",
        "description",
        "type",
        "start_toast",
        "complete_toast",
    )
    assert QUEST_COMPLEX_FIELD_ORDER == (
        "stages",
        "steps",
        "reward",
        "requires_flags",
        "blocks_flags",
    )


def test_quest_editor_model_empty_file_has_no_selection(tmp_path: Path) -> None:
    path = tmp_path / "assets" / "data" / "quests.json"
    _write_quests(path, [])
    model = QuestEditorModel.load(path)

    assert model.quest_count == 0
    assert model.selected_index() == 0
    assert model.selected_quest() is None
    assert model.scalar_detail_rows() == []
    assert model.complex_detail_rows() == []


def test_quest_editor_stage_rows_preserve_order_and_summary_fallbacks() -> None:
    quest = {
        "stages": [
            {"id": "intro", "title": "Talk", "text": "Talk to the guide."},
            {"id": "travel", "text": "Walk to the marker."},
            {"id": "done"},
        ]
    }

    assert stage_rows(quest) == [
        ("intro", "Talk"),
        ("travel", "Walk to the marker."),
        ("done", "(untitled)"),
    ]


def test_quest_editor_stage_rows_skip_invalid_entries_and_use_positional_fallback() -> None:
    assert stage_rows({}) == []
    assert stage_rows({"stages": "invalid"}) == []

    quest = {
        "stages": [
            {"id": "intro", "title": "Talk"},
            "invalid",
            {"title": "No ID"},
        ]
    }

    assert stage_rows(quest) == [("intro", "Talk"), ("stage_2", "No ID")]
