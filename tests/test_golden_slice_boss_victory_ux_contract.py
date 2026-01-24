from __future__ import annotations

import json
import pytest
from pathlib import Path
from engine.config import load_config
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
    def __init__(self, entity_data: dict) -> None:
        self.mesh_name = entity_data.get("name", "Boss")
        self.mesh_entity_data = entity_data
        self.center_x = entity_data.get("x", 0)
        self.center_y = entity_data.get("y", 0)

def _get_dungeon_scene_path(preset_name: str) -> Path:
    config = load_config()
    preset = config.presets.get(preset_name)
    if not preset:
        pytest.fail(f"Preset {preset_name} not found")
    
    # Find world file in pipeline steps
    steps = preset.get("steps", [])
    world_path_str = None
    for step in steps:
        args = step.get("args", [])
        if "--world" in args:
            idx = args.index("--world")
            if idx + 1 < len(args):
                world_path_str = args[idx + 1]
                break
    
    if not world_path_str:
        # Fallback for simple presets or if not found in args (e.g. implicit)
        # But Golden Slice variants usually have explicit world args.
        # If not, check config.profiles or similar? 
        # For this test, we assume standard Golden Slice structure.
        pytest.fail(f"Could not find world file for preset {preset_name}")

    world_path = Path(world_path_str)
    if not world_path.exists():
        # Try relative to workspace root if test running from elsewhere?
        # But standard paths are relative to root.
        pass

    with open(world_path, "r") as f:
        world_data = json.load(f)
    
    # Find dungeon scene
    # Convention: "Ridge Outpost_dungeon" key in scenes map
    scenes = world_data.get("scenes", {})
    dungeon_entry = scenes.get("Ridge Outpost_dungeon")
    if not dungeon_entry:
        pytest.fail(f"Ridge Outpost_dungeon not found in world {world_path}")
        
    return Path(dungeon_entry["path"])

@pytest.mark.parametrize("preset_name", [
    "golden_slice",
    "golden_slice_variant_b",
    "golden_slice_variant_c",
    "golden_slice_variant_d",
    "golden_slice_variant_e",
    "golden_slice_variant_f",
    "golden_slice_variant_g",
])
def test_golden_slice_boss_victory_ux_contract(preset_name: str) -> None:
    """
    Verify that for all Golden Slice variants:
    1. Boss drops exactly 10 gold.
    2. Boss defeat triggers toasts in order: "Boss defeated!", "+10g", "Exit unlocked".
    """
    scene_path = _get_dungeon_scene_path(preset_name)
    if not scene_path.exists():
        pytest.fail(f"Scene file {scene_path} does not exist")

    with open(scene_path, "r") as f:
        scene_data = json.load(f)

    # 1. Find Boss and Exit
    entities = scene_data.get("entities", [])
    boss_entity = next((e for e in entities if "Boss" in e.get("name", "") or "boss" in e.get("variant_id", "")), None)
    exit_entity = next((e for e in entities if e.get("name") == "Exit"), None)

    assert boss_entity, f"Boss missing in {preset_name}"
    assert exit_entity, f"Exit missing in {preset_name}"

    # 2. Verify Boss Config (Gold = 10)
    # Check DropTable config
    behaviour_config = boss_entity.get("behaviour_config", {})
    drop_table_config = behaviour_config.get("DropTable", {})
    drops = drop_table_config.get("drops", [])
    
    gold_drop = next((d for d in drops if d.get("gold") is not None), None)
    assert gold_drop, f"Boss in {preset_name} has no gold drop configured"
    
    # Normalize drop config (handle min/max quantity if present, though usually just 'gold': 10 implies quantity 1 of 10 gold? 
    # No, DropTable logic: gold value is per unit. 
    # Let's check how DropTable parses it. 
    # If 'gold': 10, and no quantity, it's 10 gold.
    # If 'gold': 1, and min_quantity: 10, it's 10 gold.
    # We want total guaranteed gold to be 10.
    
    gold_val = gold_drop.get("gold", 0)
    min_q = gold_drop.get("min_quantity", 1)
    max_q = gold_drop.get("max_quantity", 1)
    chance = gold_drop.get("chance", 1.0)
    
    assert chance == 1.0, f"Boss gold drop in {preset_name} is not guaranteed (chance={chance})"
    
    # Calculate expected total. 
    # If min_q != max_q, it's not deterministic 10g.
    assert min_q == max_q, f"Boss gold drop in {preset_name} is variable ({min_q}-{max_q})"
    
    total_gold = gold_val * min_q
    assert total_gold == 10, f"Boss in {preset_name} drops {total_gold}g, expected 10g"

    # 3. Verify Exit Position
    boss_x = boss_entity.get("x", 0)
    exit_x = exit_entity.get("x", 0)
    assert exit_x > boss_x, f"Exit (x={exit_x}) is not after Boss (x={boss_x}) in {preset_name}"

    # 4. Simulate Runtime UX
    window = StubWindow(scene_id=str(scene_path).replace("\\", "/"), scene_data=scene_data)
    actor = StubActor(boss_entity)

    # Wire up listeners exactly as in game.py
    def on_entity_died(event: MeshEvent) -> None:
        actor = event.payload.get("actor")
        scene_id = window.scene_controller.current_scene_path
        begin_boss_gold_reward_tracking(window, actor, scene_id)
        maybe_enqueue_boss_defeat_toast(window, actor, scene_id, seconds=3.0)

    window.event_bus.subscribe("died", on_entity_died)

    # Instantiate DropTable
    DropTable(
        actor,
        window,
        **drop_table_config
    )

    def on_any_event(event: MeshEvent) -> None:
        if event.type != "died":
            return
        actor = event.payload.get("actor")
        scene_id = window.scene_controller.current_scene_path
        maybe_finish_boss_gold_reward_toast(window, actor, scene_id, seconds=3.0)
        # Note: maybe_finish_boss_gold_reward_toast calls maybe_enqueue_exit_unlocked_toast internally now

    window.event_bus.subscribe_all(on_any_event)

    # Act
    window.event_bus.emit("died", actor=actor, name="Boss")

    # Assert Toasts
    expected_toasts = ["Boss defeated!", "+10g", "Exit unlocked"]
    assert window.player_hud.toasts == expected_toasts, \
        f"Toast sequence mismatch in {preset_name}. Got: {window.player_hud.toasts}"
