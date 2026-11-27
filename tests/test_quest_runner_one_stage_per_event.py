"""#621: one event advances at most one stage of a quest in QuestRunner (episodes, campaign replays).

The live QuestManager got the same guard in #681 (``quest_runtime/progress.py``).
"""
from __future__ import annotations

from typing import Any

import pytest

from engine.gameplay_event_bus import GameplayEvent
from engine.quest_runtime.runner import QuestRunner

pytestmark = pytest.mark.fast

_WOLF = {"type": "enemy_killed", "payload": {"kind": "wolf"}}


def _wolf_quests() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "quests": [
            {
                "id": "wolves",
                "title": "Wolves",
                "stages": [
                    {"id": "first_wolf", "title": "first_wolf", "complete_on": _WOLF},
                    {"id": "second_wolf", "title": "second_wolf", "complete_on": _WOLF},
                    {"id": "third_wolf", "title": "third_wolf", "complete_on": _WOLF},
                ],
                "reward": {"inc_counters": {"gold": 100}},
            },
            {
                # A quest whose stages listen to different events still advances on each of them.
                "id": "errand",
                "title": "Errand",
                "stages": [
                    {"id": "talk", "title": "talk", "complete_on": {"type": "talked", "payload": {"npc": "elder"}}},
                    {"id": "fetch", "title": "fetch", "complete_on": {"type": "item_picked", "payload": {"item": "herb"}}},
                ],
            },
        ],
    }


def _runner() -> QuestRunner:
    runner = QuestRunner()
    assert runner.load_definitions(_wolf_quests()) == []
    assert runner.start_quest("wolves") and runner.start_quest("errand")
    return runner


def _event(seq: int, event_type: str = "enemy_killed", **payload: Any) -> GameplayEvent:
    if not payload and event_type == "enemy_killed":
        payload = {"kind": "wolf"}
    return GameplayEvent(event_type=event_type, payload=payload, sequence=seq)


def _completed_stages(emitted: list[GameplayEvent], quest_id: str = "wolves") -> list[str]:
    return [e.payload["stage_id"] for e in emitted
            if e.event_type == "quest_stage_completed" and e.payload["quest_id"] == quest_id]


def _rewarded(emitted: list[GameplayEvent]) -> list[str]:
    return [e.payload["quest_id"] for e in emitted if e.event_type == "quest_completed"]


def test_one_event_completes_one_stage_and_reward_waits_for_the_last_stage() -> None:
    runner = _runner()
    seen: list[list[str]] = []
    for seq in (1, 2):
        emitted = runner.process_events([_event(seq)])
        seen.append(_completed_stages(emitted))
        assert _rewarded(emitted) == [], f"reward paid early, after wolf {seq}"
    assert seen == [["first_wolf"], ["second_wolf"]]
    state = runner.get_quest_state("wolves")
    assert state is not None and state.status == "active" and state.current_stage == "third_wolf"

    emitted = runner.process_events([_event(3)])
    assert _completed_stages(emitted) == ["third_wolf"]
    assert _rewarded(emitted) == ["wolves"]
    assert emitted[-1].payload["reward"]["inc_counters"] == {"gold": 100}
    # The reward is paid once: later wolves do nothing.
    assert runner.process_events([_event(4)]) == []


def test_a_batch_of_events_counts_one_stage_per_event() -> None:
    # QuestRunner has no counter of its own: "kill 3 wolves" is three stages, and each wolf counts once.
    emitted = _runner().process_events([_event(2), _event(1)])
    assert _completed_stages(emitted) == ["first_wolf", "second_wolf"]
    assert _rewarded(emitted) == []

    emitted = _runner().process_events([_event(seq) for seq in (4, 3, 2, 1)])
    assert _completed_stages(emitted) == ["first_wolf", "second_wolf", "third_wolf"]
    assert _rewarded(emitted) == ["wolves"]


def test_stages_on_different_events_still_advance() -> None:
    runner = _runner()
    emitted = runner.process_events([_event(1, "talked", npc="elder"), _event(2, "item_picked", item="herb")])
    assert _completed_stages(emitted, "errand") == ["talk", "fetch"]
    assert _rewarded(emitted) == ["errand"]


def test_next_stage_started_by_the_same_event_completes_on_a_later_one() -> None:
    runner = QuestRunner()
    assert runner.load_definitions({"schema_version": 1, "quests": [{"id": "gate", "title": "Gate", "stages": [
        {"id": "open", "title": "open", "complete_on": {"type": "lever"}},
        {"id": "hold", "title": "hold", "start_on": {"type": "lever"}, "complete_on": {"type": "lever"}},
    ]}]}) == []
    runner.start_quest("gate")
    first = runner.process_events([_event(1, "lever")])
    assert [e.event_type for e in first] == ["quest_stage_completed", "quest_stage_started"]
    second = runner.process_events([_event(2, "lever")])
    assert _completed_stages(second, "gate") == ["hold"] and _rewarded(second) == ["gate"]


def test_save_and_load_between_the_two_events() -> None:
    runner = _runner()
    runner.process_events([_event(1)])
    saved = runner.saveable_state()

    loaded = QuestRunner()
    assert loaded.load_definitions(_wolf_quests()) == []
    loaded.restore_state(saved)
    state = loaded.get_quest_state("wolves")
    assert state is not None and state.current_stage == "second_wolf" and state.completed_stages == ["first_wolf"]

    emitted = loaded.process_events([_event(2)])
    assert _completed_stages(emitted) == ["second_wolf"] and _rewarded(emitted) == []
    emitted = loaded.process_events([_event(3)])
    assert _completed_stages(emitted) == ["third_wolf"] and _rewarded(emitted) == ["wolves"]
