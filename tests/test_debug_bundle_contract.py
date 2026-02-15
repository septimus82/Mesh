"""Contract tests for debug bundle snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from engine.editor.debug_bundle import build_debug_bundle
from engine.save_runtime.io import record_load_attempt
from engine.save_runtime.save_diagnostics import SaveDiagnosticsAggregator


@dataclass
class _StubEvent:
    sequence: int
    event_type: str
    source_entity: str
    source_behaviour: str
    payload: dict


class _StubEventBus:
    def __init__(self, events: list[_StubEvent]) -> None:
        self._events = list(events)

    def get_history(self, _limit: int) -> list[_StubEvent]:
        return list(self._events)


class _StubQuestManager:
    def get_inspector_state(self) -> dict:
        return {
            "total_quests": 2,
            "active_count": 1,
            "completed_count": 0,
            "inactive_count": 1,
            "quests": [
                {
                    "id": "bQuest",
                    "title": "B Quest",
                    "status": "active",
                    "progress": "1/3",
                    "completed_stages": ["s2", "s1"],
                    "current_stage": {
                        "id": "s2",
                        "title": "Stage 2",
                        "text": "B",
                        "has_complete_trigger": True,
                        "has_requirements": False,
                    },
                },
                {
                    "id": "aQuest",
                    "title": "A Quest",
                    "status": "inactive",
                    "progress": "",
                    "completed_stages": [],
                    "awaiting_stage": "s1",
                },
            ],
        }


class _StubQuestRunner:
    def get_diagnostics(self) -> list[dict]:
        return [
            {
                "quest_id": "bQuest",
                "step_id": "s2",
                "event_type": "hit",
                "matched": False,
                "reason": "missing flag",
            },
            {
                "quest_id": "aQuest",
                "step_id": "s1",
                "event_type": "start",
                "matched": True,
                "reason": "ok",
            },
        ]


class _StubCutsceneRunner:
    def get_inspector_state(self) -> dict:
        return {
            "script_id": "cutscene_a",
            "is_running": True,
            "command_index": 1,
            "command_count": 2,
            "wait_remaining": 0.5,
            "current_command_type": "wait",
        }

    def get_command_list(self) -> list[dict]:
        return [
            {"index": 1, "type": "wait", "duration": 1.0},
            {"index": 0, "type": "label", "name": "start"},
        ]


class _StubDigestTracker:
    def __init__(self, digests: dict[int, str]) -> None:
        self.digests = digests


class _StubWindow:
    def __init__(self, event_bus: _StubEventBus) -> None:
        self.gameplay_event_bus = event_bus
        self.quest_manager = _StubQuestManager()
        self.quest_runner = _StubQuestRunner()
        self.cutscene_runner = _StubCutsceneRunner()
        self.digest_tracker = _StubDigestTracker({2: "bbb", 1: "aaa"})


def test_debug_bundle_deterministic_output() -> None:
    events = [
        _StubEvent(sequence=2, event_type="beta", source_entity="npc", source_behaviour="AI", payload={"b": 2}),
        _StubEvent(sequence=1, event_type="alpha", source_entity="hero", source_behaviour="Player", payload={"a": 1}),
    ]
    window = _StubWindow(_StubEventBus(events))

    bundle_a = build_debug_bundle(window, None, deterministic=True)
    bundle_b = build_debug_bundle(window, None, deterministic=True)
    assert bundle_a.to_json(deterministic=True) == bundle_b.to_json(deterministic=True)

    payload = bundle_a.to_dict(deterministic=True)
    assert payload["world"]["recent"] == [
        {"frame": 1, "digest": "aaa"},
        {"frame": 2, "digest": "bbb"},
    ]
    quests = payload["quests"]["inspector_state"]["quests"]
    assert [q["id"] for q in quests] == ["aQuest", "bQuest"]
    diagnostics = payload["quests"]["diagnostics"]
    assert [d["quest_id"] for d in diagnostics] == ["aQuest", "bQuest"]
    commands = payload["cutscene"]["commands"]
    assert [cmd["index"] for cmd in commands] == [0, 1]
    event_rows = payload["events"]["rows"]
    assert [row["sequence"] for row in event_rows] == [1, 2]
    assert payload["hud"]["health"]["hp"] == 0.0
    assert payload["hud"]["feed"] == []


def test_debug_bundle_missing_subsystems_safe() -> None:
    bundle = build_debug_bundle(None, None, deterministic=True)
    payload = bundle.to_dict(deterministic=True)

    assert payload["render"] is None
    assert payload["quests"]["inspector_state"] is None
    assert payload["quests"]["diagnostics"] == []
    assert payload["events"]["rows"] == []
    assert payload["hud"]["feed"] == []
    assert payload["selected_entity"]["behaviours"] == []


def test_debug_bundle_includes_combat_summary_from_event_history() -> None:
    events = [
        _StubEvent(
            sequence=1,
            event_type="combat_damage",
            source_entity="archer",
            source_behaviour="Projectile",
            payload={"source": "archer", "target": "hero", "amount": 2.5},
        ),
        _StubEvent(
            sequence=2,
            event_type="died",
            source_entity="",
            source_behaviour="Health",
            payload={"name": "hero"},
        ),
    ]
    bundle = build_debug_bundle(_StubWindow(_StubEventBus(events)), None, deterministic=True)
    payload = bundle.to_dict(deterministic=True)
    summary = payload["events"]["combat_summary"]

    assert summary["damage_event_count"] == 1
    assert summary["death_event_count"] == 1
    assert summary["damage_taken"]["hero"] == 2.5
    assert summary["damage_dealt"]["archer"] == 2.5
    hud_feed = payload["hud"]["feed"]
    assert hud_feed[-1]["event_type"] == "combat_death"


def test_debug_bundle_includes_save_runtime_diagnostics_summary() -> None:
    aggregator = SaveDiagnosticsAggregator()
    record_load_attempt(kind="slot", path=None, ok=True, aggregator=aggregator)
    bundle = build_debug_bundle(None, None, deterministic=True)
    payload = bundle.to_dict(deterministic=True)
    summary = payload["world"]["save_runtime_diagnostics"]
    assert "last_save_attempt" in summary
    assert "last_load_attempt" in summary
    assert isinstance(summary["last_load_attempt"]["counts"], dict)
