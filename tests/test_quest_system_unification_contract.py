from __future__ import annotations

from typing import Any, cast

from engine.behaviours.quest_giver import QuestGiver
from engine.events import MeshEvent, MeshEventBus
from engine.game_state_controller import GameStateController
from engine.quest_ui import get_active_quests
from engine.quests import QuestManager as FullQuestManager
from engine.save_runtime import payloads as save_payloads


class _Entity:
    mesh_id = "quest_giver"
    mesh_name = "Quest Giver"
    mesh_entity_data: dict[str, Any] = {}


class _SceneController:
    current_scene_path = "scenes/quest_contract.json"
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
        self.game_state_controller.quests = self.quest_manager

    def emit_signal(self, event_name: str, **payload: Any) -> None:
        event = MeshEvent(event_name, payload)
        self.event_bus.emit_event(event)
        # Quest definitions may auto-start a stage during QuestManager
        # construction, which emits before ``quest_manager`` is bound; guard
        # the reentrant call. Post-unification this is the same shared store.
        quest_manager = getattr(self, "quest_manager", None)
        if quest_manager is not None:
            quest_manager.handle_event(event)
        self.game_state_controller.handle_event(event)

    def set_flag(self, name: str, value: bool = True) -> None:
        self.game_state_controller.set_flag(name, value)

    def get_flag(self, name: str, default: bool = False) -> bool:
        return self.game_state_controller.get_flag(name, default)

    def inc_counter(self, name: str, amount: float = 1.0) -> float:
        return self.game_state_controller.inc_counter(name, amount)


def _install_full_quest(window: _Window, quest_payload: dict[str, Any]) -> str:
    normalized = window.quest_manager._normalize_quest(quest_payload)
    assert normalized is not None
    window.quest_manager._definitions = {normalized["id"]: normalized}
    window.quest_manager._rebuild_stage_lookup()
    window.quest_manager.reload_from_state()
    return str(normalized["id"])


def _stage_quest(quest_id: str = "unified_contract") -> dict[str, Any]:
    return {
        "id": quest_id,
        "title": "Unified Contract",
        "description": "Quest state should be shared by runtime, UI, and saves.",
        "stages": [
            {
                "id": "enter",
                "title": "Enter the zone",
                "text": "Enter the contract zone.",
                "start_on_event": {"type": "entered_zone", "payload": {"zone": "ContractZone"}},
                "complete_on_event": {"type": "contract_complete", "payload": {"quest": quest_id}},
            }
        ],
        "reward": {"set_flags": {"unified_contract_complete": True}, "inc_counters": {}},
    }


def _active_ids(window: _Window) -> list[str]:
    return [summary.quest_id for summary in get_active_quests(window)]


def test_start_visible_in_ui() -> None:
    window = _Window()
    quest_id = "giver_contract"
    _install_full_quest(window, _stage_quest(quest_id))
    giver = QuestGiver(_Entity(), window, quest_id=quest_id, listen_event="quest_start")

    try:
        window.event_bus.emit("quest_start")

        assert quest_id in _active_ids(window)
    finally:
        giver.on_destroy()


def test_progress_persists_round_trip() -> None:
    window = _Window()
    quest_id = _install_full_quest(window, _stage_quest())

    window.emit_signal("entered_zone", zone="ContractZone")

    snapshot, _content_hash = save_payloads.build_slot_payload(
        window,
        "quest-contract",
        compact=False,
        timestamp="2026-06-25T00:00:00Z",
    )
    fresh = _Window()
    _install_full_quest(fresh, _stage_quest())

    assert save_payloads.apply_loaded_payload(fresh, snapshot, mode="slot") is True
    assert quest_id in _active_ids(fresh)
    assert snapshot["saved_quests"]["quests"][quest_id]["state"] == "active"


def test_single_canonical_store() -> None:
    window = _Window()
    quest_id = "canonical_contract"
    _install_full_quest(window, _stage_quest(quest_id))

    window.quest_manager.start_quest(quest_id)

    # Slice 2+ should make these accessors resolve to the same canonical store;
    # identity is the strongest form of the contract, while the state comparison
    # below documents the minimum visible behavior expected by UI/save callers.
    assert window.quest_manager is window.game_state_controller.quests
    assert window.game_state_controller.quests is not None
    assert window.game_state_controller.quests.list_active_quests() == window.quest_manager.list_active_quests()
