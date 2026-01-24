from __future__ import annotations

import pytest
from engine.behaviours.drop_table import DropTable
from engine.events import MeshEvent, MeshEventBus
from engine.game_state_controller import GameStateController
from engine.ui import (
    begin_boss_gold_reward_tracking,
    maybe_finish_boss_gold_reward_toast,
    maybe_enqueue_boss_defeat_toast,
)

class StubHUD:
    def __init__(self) -> None:
        self.toasts: list[str] = []

    def enqueue_toast(self, message: str, *, seconds: float = 4.0) -> None:
        self.toasts.append(str(message))

class StubSceneController:
    def __init__(self, scene_id: str) -> None:
        self.current_scene_path = scene_id

class StubWindow:
    def __init__(self, scene_id: str) -> None:
        self.event_bus = MeshEventBus()
        self.scene_controller = StubSceneController(scene_id)
        self.player_hud = StubHUD()
        self.game_state_controller = GameStateController(self)
        self._mesh_boss_reward_pending = {}
        self._mesh_boss_toast_store = {}

    def get_counter(self, name: str, default: float = 0.0) -> float:
        return self.game_state_controller.get_counter(name, default)

class StubActor:
    def __init__(self) -> None:
        self.mesh_name = "Boss"
        self.mesh_entity_data = {
            "name": "Boss",
            "is_boss": True,
            "tags": ["boss"],
        }
        self.center_x = 0
        self.center_y = 0

def test_boss_defeat_reward_toast_order() -> None:
    """
    Verify that 'Boss defeated!' appears before '+Xg' reward toast.
    
    Order relies on:
    1. _on_entity_died (specific listener, registered first) -> Enqueues 'Boss defeated!'
    2. DropTable (specific listener, registered later) -> Grants gold
    3. _on_any_event_boss_reward_clarity (wildcard listener) -> Enqueues '+Xg'
    """
    window = StubWindow(scene_id="packs/core_regions/scenes/Ridge Outpost_dungeon.json")
    actor = StubActor()

    # 1. System Listener: _on_entity_died (Simulated)
    # This runs first because it's a specific listener registered before behaviours.
    def on_entity_died(event: MeshEvent) -> None:
        actor = event.payload.get("actor")
        scene_id = window.scene_controller.current_scene_path
        
        # Snapshot gold
        begin_boss_gold_reward_tracking(window, actor, scene_id)
        
        # Enqueue defeat toast
        maybe_enqueue_boss_defeat_toast(window, actor, scene_id, seconds=3.0)

    window.event_bus.subscribe("died", on_entity_died)

    # 2. Behaviour Listener: DropTable
    # Registered after system listener (simulating scene load after game init)
    DropTable(
        actor,
        window,
        listen_event="died",
        match_self=True,
        drops=[{"gold": 10, "chance": 1.0}]
    )

    # 3. Wildcard Listener: _on_any_event_boss_reward_clarity (Simulated)
    # Runs after specific listeners
    def on_any_event(event: MeshEvent) -> None:
        if event.type != "died":
            return
        actor = event.payload.get("actor")
        scene_id = window.scene_controller.current_scene_path
        maybe_finish_boss_gold_reward_toast(window, actor, scene_id, seconds=3.0)

    window.event_bus.subscribe_all(on_any_event)

    # Act
    window.event_bus.emit("died", actor=actor, name="Boss")

    # Assert
    # 1. Gold was granted
    assert window.get_counter("gold") == 10.0
    
    # 2. Toasts are in correct order
    assert len(window.player_hud.toasts) == 2
    assert window.player_hud.toasts[0] == "Boss defeated!"
    assert window.player_hud.toasts[1] == "+10g"
