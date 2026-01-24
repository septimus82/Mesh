from __future__ import annotations

from engine.behaviours.drop_table import DropTable
from engine.events import MeshEvent, MeshEventBus
from engine.game_state_controller import GameStateController
from engine.ui import begin_boss_gold_reward_tracking, maybe_finish_boss_gold_reward_toast


class StubHUD:
    def __init__(self) -> None:
        self.toasts: list[str] = []

    def enqueue_toast(self, message: str, *, seconds: float = 4.0) -> None:  # noqa: ARG002
        self.toasts.append(str(message))


class StubSceneController:
    def __init__(self, scene_id: str) -> None:
        self.current_scene_path = scene_id


class StubWindow:
    def __init__(self, scene_id: str) -> None:
        self.event_bus = MeshEventBus()
        self.scene_controller = StubSceneController(scene_id)
        self.player_hud = StubHUD()
        self.game_state_controller = GameStateController(self)  # real counter storage

    def get_counter(self, name: str, default: float = 0.0) -> float:
        return self.game_state_controller.get_counter(name, default)


class StubActor:
    def __init__(self) -> None:
        self.mesh_name = "Ridge_Boss"
        self.mesh_entity_data = {
            "mesh_name": "Ridge_Boss",
            "name": "Golden Slice",
            "is_boss": True,
            "tags": ["boss"],
        }


def test_boss_defeat_grants_gold_and_enqueues_reward_toast() -> None:
    window = StubWindow(scene_id="packs/core_regions/scenes/Ridge Outpost_dungeon.json")
    actor = StubActor()

    # Pre: boss handler captures gold before rewards apply.
    def pre_died_handler(event: MeshEvent) -> None:
        begin_boss_gold_reward_tracking(window, event.payload.get("actor"), window.scene_controller.current_scene_path)

    # Post: wildcard handler runs after all type listeners (including DropTable)
    def post_any_handler(event: MeshEvent) -> None:
        if event.type != "died":
            return
        maybe_finish_boss_gold_reward_toast(window, event.payload.get("actor"), window.scene_controller.current_scene_path, seconds=1.0)

    window.event_bus.subscribe("died", pre_died_handler)

    # Reward wiring: existing DropTable behaviour (reused) grants gold on died.
    DropTable(
        actor,
        window,
        listen_event="died",
        match_self=True,
        seed=123,
        drops=[{"gold": 1, "min_quantity": 10, "max_quantity": 10, "chance": 1.0}],
    )

    window.event_bus.subscribe_all(post_any_handler)

    assert window.get_counter("gold", 0.0) == 0.0
    window.event_bus.emit("died", actor=actor, name="Golden Slice")

    assert window.get_counter("gold", 0.0) == 10.0
    assert window.player_hud.toasts == ["+10g"]
