from __future__ import annotations

import json
from pathlib import Path
from engine.behaviours.drop_table import DropTable
from engine.events import MeshEvent, MeshEventBus
from engine.game_state_controller import GameStateController
from engine.ui import begin_boss_gold_reward_tracking, maybe_finish_boss_gold_reward_toast

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

    def get_counter(self, name: str, default: float = 0.0) -> float:
        return self.game_state_controller.get_counter(name, default)

class StubActor:
    def __init__(self, entity_data: dict) -> None:
        self.mesh_name = entity_data.get("name", "Boss")
        self.mesh_entity_data = entity_data
        self.center_x = 0
        self.center_y = 0

def test_variant_e_boss_reward_clarity() -> None:
    scene_path = "packs/core_regions/scenes/Ridge Outpost_dungeon_variant_e.json"
    real_path = Path(scene_path)
    if not real_path.exists():
        real_path = Path("d:/Games/Mesh") / scene_path
    
    with open(real_path, "r") as f:
        scene_data = json.load(f)
        
    boss_entity = next(e for e in scene_data["entities"] if e["name"] == "Boss")
    
    # Verify preconditions from JSON
    tags = boss_entity.get("tags", [])
    assert "boss" in tags, "Boss entity must have 'boss' tag for toast logic"
    
    drop_config = boss_entity["behaviour_config"]["DropTable"]
    assert drop_config["drops"][0].get("gold") == 10, "Boss must drop 10 gold"

    window = StubWindow(scene_id=scene_path)
    actor = StubActor(boss_entity)

    # Pre: boss handler captures gold before rewards apply.
    def pre_died_handler(event: MeshEvent) -> None:
        begin_boss_gold_reward_tracking(window, event.payload.get("actor"), window.scene_controller.current_scene_path)

    # Post: wildcard handler runs after all type listeners
    def post_any_handler(event: MeshEvent) -> None:
        if event.type != "died":
            return
        maybe_finish_boss_gold_reward_toast(window, event.payload.get("actor"), window.scene_controller.current_scene_path, seconds=1.0)

    window.event_bus.subscribe("died", pre_died_handler)

    # Instantiate DropTable with config from JSON
    DropTable(
        actor,
        window,
        **drop_config
    )

    window.event_bus.subscribe_all(post_any_handler)

    assert window.get_counter("gold", 0.0) == 0.0
    window.event_bus.emit("died", actor=actor, name="Boss")

    assert window.get_counter("gold", 0.0) == 10.0
    assert window.player_hud.toasts == ["+10g"]
