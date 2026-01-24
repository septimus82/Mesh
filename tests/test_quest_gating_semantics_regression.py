from __future__ import annotations

from unittest.mock import MagicMock

from engine.events import MeshEvent
from engine.game_state_controller import GameStateController
from engine.quest_runtime.gating import can_activate_quest
from engine.quests import QuestManager


class _StubWindow:
    def __init__(self) -> None:
        self.game_state_controller = GameStateController(self)
        self.game_state = self.game_state_controller.state
        self.scene_controller = MagicMock()
        self.scene_controller.current_scene_path = None
        self.game_state_controller.quests = None
        self.game_state_controller.quests = QuestManager(self)

    def emit_signal(self, event_name: str, **payload) -> None:
        event = MeshEvent(event_name, payload)
        qm = self.game_state_controller.quests
        if qm and hasattr(qm, "handle_event"):
            qm.handle_event(event)

    def set_flag(self, name: str, value: bool = True) -> None:
        self.game_state_controller.set_flag(name, value)

    def get_flag(self, name: str, default: bool = False) -> bool:
        return self.game_state_controller.get_flag(name, default)


def _install_single_quest(qm: QuestManager, quest_payload: dict) -> str:
    normalized = qm._normalize_quest(quest_payload)
    assert normalized is not None
    qm._definitions = {normalized["id"]: normalized}
    qm._rebuild_stage_lookup()
    qm.reload_from_state()
    return normalized["id"]


def test_can_activate_quest_semantics_and_edge_cases() -> None:
    quest_def = {"requires_flags": ["a"], "blocks_flags": ["b"]}
    assert can_activate_quest({"a": False, "b": False}, quest_def) is False
    assert can_activate_quest({"a": True, "b": True}, quest_def) is False
    assert can_activate_quest({"a": True, "b": False}, quest_def) is True
    assert can_activate_quest({}, {"requires_flags": [], "blocks_flags": []}) is True
    assert can_activate_quest({}, {}) is True


def test_missing_requires_blocks_allows_start() -> None:
    window = _StubWindow()
    qm = window.game_state_controller.quests

    quest_id = _install_single_quest(
        qm,
        {
            "id": "no_gates",
            "title": "No Gates",
            "stages": [{"id": "s1", "start_on_event": {"type": "ping"}}],
            "reward": {"set_flags": {}, "inc_counters": {}},
        },
    )

    window.emit_signal("ping")
    assert qm.is_quest_active(quest_id)


def test_empty_requires_blocks_lists_allow_start() -> None:
    window = _StubWindow()
    qm = window.game_state_controller.quests

    quest_id = _install_single_quest(
        qm,
        {
            "id": "empty_gates",
            "title": "Empty Gates",
            "requires_flags": [],
            "blocks_flags": [],
            "stages": [{"id": "s1", "start_on_event": {"type": "ping"}}],
            "reward": {"set_flags": {}, "inc_counters": {}},
        },
    )

    window.emit_signal("ping")
    assert qm.is_quest_active(quest_id)

