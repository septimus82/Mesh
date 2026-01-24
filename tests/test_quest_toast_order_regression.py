from __future__ import annotations

from unittest.mock import MagicMock

from engine.events import MeshEvent
from engine.game_state_controller import GameStateController
from engine.quests import QuestManager


class _StubWindow:
    def __init__(self) -> None:
        self.emitted: list[str] = []
        self.game_state_controller = GameStateController(self)
        self.game_state = self.game_state_controller.state
        self.scene_controller = MagicMock()
        self.scene_controller.current_scene_path = None
        self.game_state_controller.quests = None
        self.game_state_controller.quests = QuestManager(self)

    def emit_signal(self, event_name: str, **payload) -> None:
        self.emitted.append(event_name)

    def set_flag(self, name: str, value: bool = True) -> None:
        self.game_state_controller.set_flag(name, value)

    def get_flag(self, name: str, default: bool = False) -> bool:
        return self.game_state_controller.get_flag(name, default)

    def inc_counter(self, name: str, amount: float) -> None:
        self.game_state_controller.inc_counter(name, amount)

    def get_counter(self, name: str, default: float = 0.0) -> float:
        return self.game_state_controller.get_counter(name, default)


def _install_two_quests(qm: QuestManager, first: dict, second: dict) -> tuple[str, str]:
    a = qm._normalize_quest(first)
    b = qm._normalize_quest(second)
    assert a is not None
    assert b is not None
    qm._definitions = {a["id"]: a, b["id"]: b}
    qm._rebuild_stage_lookup()
    qm.reload_from_state()
    return a["id"], b["id"]


def test_completion_happens_before_dependent_start_deterministically() -> None:
    window = _StubWindow()
    qm = window.game_state_controller.quests

    quest2, quest1 = _install_two_quests(
        qm,
        {
            "id": "quest2",
            "title": "Quest 2",
            "requires_flags": ["unlock_q2"],
            "stages": [{"id": "s1", "start_on_event": {"type": "tick"}}],
            "reward": {"set_flags": {}, "inc_counters": {}},
        },
        {
            "id": "quest1",
            "title": "Quest 1",
            "auto_start": True,
            "stages": [{"id": "s1", "complete_on": {"type": "tick"}}],
            "reward": {"set_flags": {"unlock_q2": True}, "inc_counters": {}},
        },
    )

    window.emitted.clear()
    qm.handle_event(MeshEvent("tick", {}))

    completed_idx = window.emitted.index("quest_completed")
    started_idx = window.emitted.index("quest_stage_started")
    assert completed_idx < started_idx
    assert qm.is_quest_completed(quest1)
    assert qm.is_quest_active(quest2)

