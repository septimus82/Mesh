import json
import pytest
from pathlib import Path
from engine.config import load_config
from engine.prefabs import PrefabManager

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
        pytest.fail(f"Could not find world file for preset {preset_name}")

    world_path = Path(world_path_str)
    if not world_path.exists():
        pytest.fail(f"World file {world_path} does not exist")

    with open(world_path, "r") as f:
        world_data = json.load(f)
    
    # Find dungeon scene
    # Convention: "Ridge Outpost_dungeon" key in scenes map
    scenes = world_data.get("scenes", {})
    dungeon_entry = scenes.get("Ridge Outpost_dungeon")
    if not dungeon_entry:
        pytest.fail(f"Ridge Outpost_dungeon not found in world {world_path}")
        
    return Path(dungeon_entry["path"])

def test_prefab_variant_consistency_gate():
    """
    Gate test to prevent silent drift in prefab/variant references.
    
    Validates that for all Golden Slice variants:
    1. Any entity with 'prefab_id' references a valid prefab.
    2. Any entity with 'variant_id' references a valid variant patch.
    3. Any entity with 'variant_id' MUST also have a valid 'prefab_id' (base).
    """
    # 1. Load Registry
    pm = PrefabManager()
    pm.load()
    
    known_prefabs = set(pm.prefabs.keys())
    # Accessing private _variants for validation purposes as per "Reuse-first" 
    # (using the manager's loaded state rather than re-parsing files)
    known_variants = set(pm._variants.keys())
    
    # 2. Identify Presets
    config = load_config()
    presets = getattr(config, "presets", {})
    golden_slice_presets = [
        name for name in presets.keys() 
        if name == "golden_slice" or name.startswith("golden_slice_variant_")
    ]
    
    assert golden_slice_presets, "No Golden Slice presets found"

    # 3. Validate Scenes
    for preset_name in golden_slice_presets:
        scene_path = _get_dungeon_scene_path(preset_name)
        if not scene_path.exists():
            pytest.fail(f"Scene file {scene_path} missing for {preset_name}")
            
        with open(scene_path, "r") as f:
            scene_data = json.load(f)
            
        entities = scene_data.get("entities", [])
        
        for i, entity in enumerate(entities):
            name = entity.get("name") or entity.get("mesh_name") or f"Entity_{i}"
            prefab_id = entity.get("prefab_id")
            variant_id = entity.get("variant_id")
            
            # Context for failure messages
            ctx = f"Preset: {preset_name}, Scene: {scene_path.name}, Entity: {name}"
            
            if prefab_id:
                assert prefab_id in known_prefabs, \
                    f"{ctx}: References unknown prefab_id '{prefab_id}'"
            
            if variant_id:
                assert variant_id in known_variants, \
                    f"{ctx}: References unknown variant_id '{variant_id}'"
                
                assert prefab_id, \
                    f"{ctx}: Has variant_id '{variant_id}' but missing base prefab_id"
                
                # We already checked prefab_id validity above if it exists, 
                # so we know we have a valid base + valid variant.

