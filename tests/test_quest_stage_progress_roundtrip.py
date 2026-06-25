"""Regression: Option A preserves STAGE progress across save/reload.

The quest-unification contract proves quest-level status survives a round trip;
this guards the stronger property the design hinges on -- that
``current_stage`` and ``completed_stages`` (the stage-complete truth in
``game_state.values["quests"]``) survive save -> reload into a fresh window,
not just the top-level ``active`` status.
"""

from __future__ import annotations

from typing import Any, cast

from engine.events import MeshEvent, MeshEventBus
from engine.game_state_controller import GameStateController
from engine.quests import QuestManager as FullQuestManager
from engine.save_runtime import payloads as save_payloads


class _SceneController:
    current_scene_path = "scenes/stage_roundtrip.json"
    all_sprites: list[Any] = []

    def build_scene_snapshot(self, *, compact: bool = False) -> dict[str, Any]:  # noqa: ARG002
        return {"scene_path": self.current_scene_path}


class _Window:
    def __init__(self) -> None:
        self.event_bus = MeshEventBus()
        self.scene_controller = _SceneController()
        self.game_state_controller = GameStateController(cast(Any, self))
        self.game_state = self.game_state_controller.state
        self.quest_manager = FullQuestManager(self)

    def emit_signal(self, event_name: str, **payload: Any) -> None:
        event = MeshEvent(event_name, payload)
        self.event_bus.emit_event(event)
        quest_manager = getattr(self, "quest_manager", None)
        if quest_manager is not None:
            quest_manager.handle_event(event)

    def set_flag(self, name: str, value: bool = True) -> None:
        self.game_state_controller.set_flag(name, value)

    def get_flag(self, name: str, default: bool = False) -> bool:
        return self.game_state_controller.get_flag(name, default)

    def inc_counter(self, name: str, amount: float = 1.0) -> float:
        return self.game_state_controller.inc_counter(name, amount)

    def get_counter(self, name: str, default: float = 0.0) -> float:
        return self.game_state_controller.get_counter(name, default)


_QUEST_ID = "stage_roundtrip"


def _two_stage_quest() -> dict[str, Any]:
    return {
        "id": _QUEST_ID,
        "title": "Stage Roundtrip",
        "description": "Two-stage quest used to prove stage progress persists.",
        "stages": [
            {"id": "s1", "title": "First", "text": "Do the first thing."},
            {"id": "s2", "title": "Second", "text": "Do the second thing."},
        ],
        "reward": {"set_flags": {}, "inc_counters": {}},
    }


def _install(window: _Window) -> None:
    qm = window.quest_manager
    normalized = qm._normalize_quest(_two_stage_quest())
    assert normalized is not None
    qm._definitions = {normalized["id"]: normalized}
    qm._rebuild_stage_lookup()
    qm.reload_from_state()


def test_stage_progress_survives_save_reload() -> None:
    window = _Window()
    _install(window)

    # First stage auto-starts (no start trigger); advance past it.
    assert window.quest_manager.is_quest_active(_QUEST_ID)
    assert window.quest_manager.complete_stage(_QUEST_ID) is True

    progress = window.quest_manager.get_state_snapshot(_QUEST_ID)
    assert progress is not None
    assert progress["current_stage"] == "s2"
    assert "s1" in progress["completed_stages"]

    snapshot, _hash = save_payloads.build_slot_payload(
        window,
        "stage-roundtrip",
        compact=False,
        timestamp="2026-06-25T00:00:00Z",
    )

    fresh = _Window()
    _install(fresh)
    assert save_payloads.apply_loaded_payload(fresh, snapshot, mode="slot") is True

    restored = fresh.quest_manager.get_state_snapshot(_QUEST_ID)
    assert restored is not None
    # The whole point of Option A: STAGE progress, not just quest-level status.
    assert restored["status"] == "active"
    assert restored["current_stage"] == "s2"
    assert "s1" in restored["completed_stages"]
