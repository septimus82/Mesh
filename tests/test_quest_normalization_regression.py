from __future__ import annotations

from engine.quests import QuestManager


def test_quest_normalization_preserves_toast_fields_and_fallbacks() -> None:
    qm = QuestManager.__new__(QuestManager)

    quest = qm._normalize_quest(
        {
            "id": "Q1",
            "start_toast": "  Hello  ",
            "complete_toast": "",
            "stages": [{"title": "Stage One"}],
            "reward": {"set_flags": {}, "inc_counters": {}},
        },
    )
    assert quest is not None
    assert quest["id"] == "Q1"
    assert quest["title"] == "Q1"
    assert quest["start_toast"] == "Hello"
    assert quest["complete_toast"] is None
    assert quest["stages"][0]["id"] == "stage_0"
    assert quest["stages"][0]["title"] == "Stage One"
    assert quest["stages"][0]["text"] == "Stage One"

