from __future__ import annotations

from unittest.mock import MagicMock

from engine.events import MeshEvent
from engine.game_state_controller import GameStateController
from engine.quests import QuestManager


class _StubWindow:
    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}
        self.game_state_controller = GameStateController(self)
        self.game_state = self.game_state_controller.state
        self.scene_controller = MagicMock()
        self.scene_controller.current_scene_path = None

        self.game_state_controller.quests = None
        self.game_state_controller.quests = QuestManager(self)

    def emit_signal(self, event_name: str, **payload) -> None:
        event = MeshEvent(event_name, payload)
        if event_name in self.listeners:
            for callback in list(self.listeners[event_name]):
                callback(event)

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


def test_requires_flags_blocks_start_until_flag_set() -> None:
    window = _StubWindow()
    qm = window.game_state_controller.quests

    quest_id = _install_single_quest(
        qm,
        {
            "id": "gated_requires",
            "title": "Gated Requires",
            "requires_flags": ["unlock_me"],
            "stages": [
                {
                    "id": "s1",
                    "title": "Enter Zone",
                    "start_on_event": {"type": "entered_zone", "payload": {"zone": "GateZone"}},
                }
            ],
            "reward": {"set_flags": {"gated_requires_complete": True}, "inc_counters": {}},
        },
    )

    window.emit_signal("entered_zone", zone="GateZone", actor="Player", position=(0.0, 0.0))
    assert not qm.is_quest_active(quest_id)

    window.set_flag("unlock_me", True)
    window.emit_signal("entered_zone", zone="GateZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(quest_id)


def test_blocks_flags_prevents_start_when_flag_present() -> None:
    window = _StubWindow()
    qm = window.game_state_controller.quests

    quest_id = _install_single_quest(
        qm,
        {
            "id": "gated_blocks",
            "title": "Gated Blocks",
            "blocks_flags": ["already_done"],
            "stages": [
                {
                    "id": "s1",
                    "title": "Enter Zone",
                    "start_on_event": {"type": "entered_zone", "payload": {"zone": "BlockZone"}},
                }
            ],
            "reward": {"set_flags": {"gated_blocks_complete": True}, "inc_counters": {}},
        },
    )

    window.set_flag("already_done", True)
    window.emit_signal("entered_zone", zone="BlockZone", actor="Player", position=(0.0, 0.0))
    assert not qm.is_quest_active(quest_id)

    window.set_flag("already_done", False)
    window.emit_signal("entered_zone", zone="BlockZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(quest_id)

