from __future__ import annotations

from engine.behaviours.drop_table import DropTable
from engine.events import MeshEvent, MeshEventBus
from engine.game_state_controller import GameStateController
from engine.ui import (
    begin_boss_gold_reward_tracking,
    maybe_enqueue_boss_defeat_toast,
    maybe_finish_boss_gold_reward_toast,
)


class StubHUD:
    def __init__(self) -> None:
        self.toasts: list[str] = []

    def enqueue_toast(self, message: str, *, seconds: float = 4.0) -> None:
        self.toasts.append(str(message))

class StubSceneController:
    def __init__(self, scene_id: str, scene_data: dict) -> None:
        self.current_scene_path = scene_id
        self._loaded_scene_data = scene_data

class StubWindow:
    def __init__(self, scene_id: str, scene_data: dict) -> None:
        self.event_bus = MeshEventBus()
        self.scene_controller = StubSceneController(scene_id, scene_data)
        self.player_hud = StubHUD()
        self.game_state_controller = GameStateController(self)
        self._mesh_boss_reward_pending = {}
        self._mesh_boss_toast_store = {}

    def get_counter(self, name: str, default: float = 0.0) -> float:
        return self.game_state_controller.get_counter(name, default)

class StubActor:
    def __init__(self, x: int) -> None:
        self.mesh_name = "Boss"
        self.mesh_entity_data = {
            "name": "Boss",
            "is_boss": True,
            "tags": ["boss"],
            "x": x
        }
        self.center_x = x
        self.center_y = 0

def test_boss_defeat_exit_unlocked_toast_order() -> None:
    """
    Verify that 'Exit unlocked' appears after 'Boss defeated!' and '+Xg'.
    Requires Exit entity to be positioned after Boss (x_exit > x_boss).
    """
    boss_x = 600
    exit_x = 700

    scene_data = {
        "entities": [
            {"name": "Boss", "x": boss_x, "is_boss": True},
            {"name": "Exit", "x": exit_x}
        ]
    }

    window = StubWindow(scene_id="packs/core_regions/scenes/Ridge Outpost_dungeon.json", scene_data=scene_data)
    actor = StubActor(x=boss_x)

    # 1. System Listener: _on_entity_died
    def on_entity_died(event: MeshEvent) -> None:
        actor = event.payload.get("actor")
        scene_id = window.scene_controller.current_scene_path
        begin_boss_gold_reward_tracking(window, actor, scene_id)
        maybe_enqueue_boss_defeat_toast(window, actor, scene_id, seconds=3.0)

    window.event_bus.subscribe("died", on_entity_died)

    # 2. Behaviour Listener: DropTable
    DropTable(
        actor,
        window,
        listen_event="died",
        match_self=True,
        drops=[{"gold": 10, "chance": 1.0}]
    )

    # 3. Wildcard Listener: _on_any_event_boss_reward_clarity
    def on_any_event(event: MeshEvent) -> None:
        if event.type != "died":
            return
        actor = event.payload.get("actor")
        scene_id = window.scene_controller.current_scene_path
        # This single call should handle both gold and exit toasts
        maybe_finish_boss_gold_reward_toast(window, actor, scene_id, seconds=3.0)

    window.event_bus.subscribe_all(on_any_event)

    # Act
    window.event_bus.emit("died", actor=actor, name="Boss")

    # Assert
    assert len(window.player_hud.toasts) == 3
    assert window.player_hud.toasts[0] == "Boss defeated!"
    assert window.player_hud.toasts[1] == "+10g"
    assert window.player_hud.toasts[2] == "Exit unlocked"

def test_boss_defeat_no_exit_unlocked_if_exit_before_boss() -> None:
    """Verify 'Exit unlocked' does NOT appear if Exit is before Boss."""
    boss_x = 600
    exit_x = 100 # Exit is before boss (e.g. entrance)

    scene_data = {
        "entities": [
            {"name": "Boss", "x": boss_x, "is_boss": True},
            {"name": "Exit", "x": exit_x}
        ]
    }

    window = StubWindow(scene_id="packs/core_regions/scenes/Ridge Outpost_dungeon.json", scene_data=scene_data)
    actor = StubActor(x=boss_x)

    # Minimal wiring for this test
    def on_any_event(event: MeshEvent) -> None:
        if event.type != "died":
            return
        actor = event.payload.get("actor")
        scene_id = window.scene_controller.current_scene_path
        # This single call should handle both gold and exit toasts
        maybe_finish_boss_gold_reward_toast(window, actor, scene_id, seconds=3.0)

    window.event_bus.subscribe_all(on_any_event)

    # Act
    window.event_bus.emit("died", actor=actor, name="Boss")

    # Assert
    assert "Exit unlocked" not in window.player_hud.toasts
