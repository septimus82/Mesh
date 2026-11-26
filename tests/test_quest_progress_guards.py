"""#650 (S1 5.5): quest progress guards, each killing its named mutant in docs/s1/evidence/mutation_probe.py.

The quests are loaded from a quests.json by the real QuestManager; events arrive the way the per-frame update hands
them over (``GameStateController.handle_event``) or through a QuestProgressOnEvent behaviour.
"""

from __future__ import annotations

import json
import types
from pathlib import Path
from typing import Any, cast

import pytest

from engine.behaviours.quest_progress import QuestProgressOnEvent
from engine.events import MeshEvent, MeshEventBus
from engine.game_state_controller import GameStateController
from engine.quest_runtime import progress
from engine.quests import QuestManager

pytestmark = pytest.mark.integration  # (writes a quests.json to a temporary folder)

WOLF = {"type": "enemy_defeated", "payload_field": "kind", "payload_value": "wolf"}
QUESTS = [
    {"id": "hunt", "title": "Hunt", "description": "", "auto_start": True,
     "stages": [{"id": "wolf", "title": "Wolf", "text": "Kill a wolf.", "complete_event": WOLF}],
     "reward": {"inc_counters": {"bounties": 1}}},
    {"id": "trail", "title": "Trail", "description": "", "auto_start": True,
     "stages": [{"id": "s1", "title": "One", "text": "First."}, {"id": "s2", "title": "Two", "text": "Second."}]},
]


class _Window:
    def __init__(self, quests_json: Path) -> None:
        self.signals: list[str] = []
        self.event_bus = MeshEventBus()
        self.game_state_controller = GameStateController(cast(Any, self))
        self.game_state = self.game_state_controller.state
        self.quest_manager = QuestManager(self, data_path=str(quests_json))
        self.game_state_controller.quests = self.quest_manager

    def emit_signal(self, event_name: str, **_payload: Any) -> None:
        self.signals.append(event_name)

    def set_flag(self, name: str, value: bool = True) -> None:
        self.game_state_controller.set_flag(name, value)

    def get_flag(self, name: str, default: bool = False) -> bool:
        return self.game_state_controller.get_flag(name, default)

    def inc_counter(self, name: str, amount: float = 1.0) -> float:
        return self.game_state_controller.inc_counter(name, amount)

    def get_counter(self, name: str, default: float = 0.0) -> float:
        return self.game_state_controller.get_counter(name, default)


@pytest.fixture
def window(tmp_path: Path) -> _Window:
    path = tmp_path / "quests.json"
    path.write_text(json.dumps({"quests": QUESTS}), encoding="utf-8")
    return _Window(path)


def test_a_stage_keyed_on_payload_value_completes_only_for_that_value(window: _Window) -> None:
    """Mutant Q1: killing a boar must not complete "kill a wolf"."""
    window.game_state_controller.handle_event(MeshEvent("enemy_defeated", {"kind": "boar"}))
    assert window.quest_manager.is_quest_active("hunt") and not window.quest_manager.is_stage_completed("hunt", "wolf")
    window.game_state_controller.handle_event(MeshEvent("enemy_defeated", {"kind": "wolf"}))
    assert window.quest_manager.is_quest_completed("hunt")


def test_completing_a_completed_quest_pays_its_reward_once(window: _Window) -> None:
    """Mutant Q3: a "complete quest" trigger firing after the quest is done pays nothing more."""
    window.game_state_controller.handle_event(MeshEvent("enemy_defeated", {"kind": "wolf"}))
    assert window.get_counter("bounties") == 1
    finisher = QuestProgressOnEvent(types.SimpleNamespace(mesh_entity_data={}), window, quest_id="hunt",
                                    action="complete_quest", event_type="boss_slain")
    finisher.on_event(MeshEvent("boss_slain", {}))
    finisher.on_event(MeshEvent("boss_slain", {}))
    assert window.get_counter("bounties") == 1
    assert window.signals.count("quest_completed") == 1


def test_complete_stage_leaves_a_stage_that_is_not_current_alone(window: _Window) -> None:
    """Mutant Q5: completing stage two while stage one is current changes nothing (no skipped stage).

    Every caller in the quest runtime checks the current stage first, so this holds ``complete_stage``'s own guard.
    """
    manager = window.quest_manager
    quest = manager._definitions["trail"]
    state = manager._ensure_state("trail")
    assert state["current_stage"] == "s1"
    progress.complete_stage(manager, quest, quest["stage_lookup"]["s2"], state, source="test")
    assert (state["current_stage"], state["completed_stages"], state["status"]) == ("s1", [], "active")
    assert "quest_stage_completed" not in window.signals
