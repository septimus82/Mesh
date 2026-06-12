import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine.events import MeshEvent
from engine.game_state_controller import GameStateController
from engine.quests import QuestManager
from engine.scene_loader import SceneLoader

pytestmark = pytest.mark.builtin_behaviours

class MockWindow:
    def __init__(self):
        self.listeners = {}
        self.game_state_controller = GameStateController(self)
        self.game_state = self.game_state_controller.state
        # Replace default QuestManager with the event-driven one
        # Clear the old one first to prevent emit_signal from using it during the new one's init
        self.game_state_controller.quests = None
        self.game_state_controller.quests = QuestManager(self)
        self.scene_loader = SceneLoader()
        self.scene_controller = MagicMock()
        self.scene_controller.current_scene_path = None

    def emit_signal(self, event_name, **payload):
        event = MeshEvent(event_name, payload)

        # Propagate to listeners (mocking behaviour system) - Run these FIRST to update state
        if event_name in self.listeners:
            for callback in self.listeners[event_name]:
                callback(event)

        # Propagate to quest manager if it supports event handling
        if self.game_state_controller.quests and hasattr(self.game_state_controller.quests, "handle_event"):
            self.game_state_controller.quests.handle_event(event)

    def on(self, event_name, callback):
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(callback)

    def set_flag(self, name: str, value: bool = True) -> None:
        self.game_state_controller.set_flag(name, value)

    def get_flag(self, name: str, default: bool = False) -> bool:
        return self.game_state_controller.get_flag(name, default)

    def inc_counter(self, name: str, amount: float = 1.0) -> float:
        return self.game_state_controller.inc_counter(name, amount)

    def get_counter(self, name: str, default: float = 0.0) -> float:
        return self.game_state_controller.get_counter(name, default)

def test_vertical_slice_smoke():
    # 1. Load World
    world_path = Path("worlds/main_world.json")
    assert world_path.exists()
    with open(world_path, "r") as f:
        world = json.load(f)

    # 2. Setup Harness
    window = MockWindow()
    # Ensure quest definitions are loaded
    window.game_state_controller.quests.load_definitions()

    # 3. Simulate Quest Start
    # We use field_supplies which is in the core pack

    print("Simulating quest acceptance...")
    window.emit_signal("dialogue_choice", entity="FieldWarden", choice_id="warden_offer_accept")

    # Verify quest started
    qm = window.game_state_controller.quests
    assert qm.is_quest_active("field_supplies"), "Quest should be active after acceptance"
    current_stage = qm.get_current_stage("field_supplies")
    assert current_stage["id"] == "collect_supply_crate"

    # 4. Simulate Item Pickup in Cellar
    # In cellar.json, picking up "Golden Rat Statue" triggers "collectible_picked".
    # The quest stage "find_statue" completes on: { type: "collectible_picked", payload: { collectible_name: "Golden Rat Statue" } }
    # Also, there is a QuestLogic entity in cellar.json that sets flag "has_golden_rat_statue" on this event.
    # We need to simulate the QuestLogic behaviour too, or manually check the quest update.
    # Since we don't have the full behaviour system running, we'll manually attach a listener
    # that mimics the SetGameStateOnEvent behaviour for the smoke test.

    def mock_quest_logic(event):
        if event.payload.get("collectible_name") == "SupplyCrate":
            window.game_state.flags["has_supply_crate"] = True

    window.on("collectible_picked", mock_quest_logic)

    print("Simulating item pickup...")
    window.emit_signal("collectible_picked", collectible_name="SupplyCrate", collector="Player", position=(0,0))

    # Verify quest updated
    # "collect_supply_crate" should be complete, "return_to_warden" should be active.
    assert qm.is_stage_completed("field_supplies", "collect_supply_crate"), "Stage 'collect_supply_crate' should be complete"
    current_stage = qm.get_current_stage("field_supplies")
    assert current_stage["id"] == "return_to_warden"

    # Verify flag set (by our mock logic, confirming event flow)
    assert window.game_state.flags.get("has_supply_crate"), "Flag should be set"

    # 5. Simulate Turn-in
    print("Simulating quest turn-in...")
    window.emit_signal("dialogue_choice", entity="FieldWarden", choice_id="warden_turnin")

    # Verify completion
    assert qm.is_quest_completed("field_supplies"), "Quest should be completed"
    assert window.game_state.counters.get("quests_completed", 0) == 1, "Reward counter should be incremented"

    # 6. Simulate Kill-Count Quest
    # Start "cellar_exterminator"
    print("Simulating kill-count quest...")
    qm.start_quest("cellar_exterminator")
    assert qm.is_quest_active("cellar_exterminator")

    # Simulate 5 rat kills
    # The scene has IncrementCounterOnEvent listening for "died" with name="Rat1"
    # We need to register the listener that the scene WOULD have registered.
    # Updated to use scoped counter logic

    def mock_kill_counter(event):
        if event.payload.get("name") == "Rat1":
            # Simulate scoped increment
            window.game_state_controller.inc_quest_counter("cellar_exterminator", "rats_killed", 1.0)

    window.on("died", mock_kill_counter)

    for i in range(5):
        window.emit_signal("died", actor="Rat1", name="Rat1")

    # Verify scoped counter
    assert window.game_state_controller.get_quest_counter("cellar_exterminator", "rats_killed") == 5.0

    # Verify global counter is NOT affected (scoping check)
    assert window.get_counter("rats_killed") == 0.0

    # Verify stage completion (QuestManager checks requirements on update/event)
    assert qm.is_stage_completed("cellar_exterminator", "kill_rats"), "Stage 'kill_rats' should be complete"
    current_stage = qm.get_current_stage("cellar_exterminator")
    assert current_stage["id"] == "report_success"

    # Complete quest
    window.emit_signal("dialogue_choice", entity="Guard", choice_id="guard_exterminator_complete")
    assert qm.is_quest_completed("cellar_exterminator")
    assert window.game_state.counters.get("gold") == 100, "Total gold should be 100 (from cellar_exterminator)"

    # 7. Simulate Core Region Quest (Ridge Outpost)
    print("Simulating Ridge Outpost quest...")
    qm.start_quest("ridge_fetch_supplies")
    assert qm.is_quest_active("ridge_fetch_supplies")

    # Simulate picking up supplies
    def mock_ridge_logic(event):
        if event.payload.get("collectible_name") == "RidgeSupplies":
            window.game_state.flags["has_ridge_supplies"] = True

    window.on("collectible_picked", mock_ridge_logic)
    window.emit_signal("collectible_picked", collectible_name="RidgeSupplies", collector="Player", position=(0,0))

    assert qm.is_stage_completed("ridge_fetch_supplies", "collect_supplies")
    assert qm.get_current_stage("ridge_fetch_supplies")["id"] == "return_supplies"

    # Complete quest
    window.emit_signal("dialogue_choice", entity="RidgeMerchant", choice_id="ridge_turnin")
    assert qm.is_quest_completed("ridge_fetch_supplies")

def test_ashen_quest_flow():
    window = MockWindow()
    qm = window.game_state_controller.quests

    # Load quests
    # QuestManager loads from packs automatically
    qm.load_definitions()

    # Start quest
    qm.start_quest("Ashen_fetch_quest")
    assert qm.is_quest_active("Ashen_fetch_quest")

    # Simulate picking up relic
    window.emit_signal("collectible_picked", collectible_name="AshenRelic", collector="Player", position=(0,0))

    assert qm.is_stage_completed("Ashen_fetch_quest", "collect_relics")
    assert qm.get_current_stage("Ashen_fetch_quest")["id"] == "return_relic"

    # Complete quest
    window.emit_signal("dialogue_choice", entity="Ashen_Elder", choice_id="ashen_relic_turnin")
    assert qm.is_quest_completed("Ashen_fetch_quest")
