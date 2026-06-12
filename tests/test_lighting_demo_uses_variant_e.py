import json
from pathlib import Path

import pytest

from engine.config import load_config


def test_lighting_demo_uses_variant_e():
    """
    Verify that lighting demo presets use Variant E and that the variant content is valid for the demo.
    """
    config = load_config()

    demo_presets = [
        "lighting-shadowmask-demo",
        "lighting-shadowmask-demo-debug"
    ]

    for preset_name in demo_presets:
        assert preset_name in config.presets, f"Preset {preset_name} missing"
        preset = config.presets[preset_name]

        # 1. Check World File Reference
        steps = preset.get("steps", [])
        assert steps, f"Preset {preset_name} has no steps"

        pipeline_step = steps[0]
        args = pipeline_step.get("args", [])

        world_arg_idx = -1
        try:
            world_arg_idx = args.index("--world")
        except ValueError:
            pytest.fail(f"Preset {preset_name} missing --world argument")

        world_path_str = args[world_arg_idx + 1]
        assert world_path_str == "worlds/golden_slice_variant_e.json", \
            f"Preset {preset_name} should use Variant E world, found {world_path_str}"

        # 2. Verify World File Exists
        world_path = Path(world_path_str)
        assert world_path.exists(), f"World file {world_path} does not exist"

        # 3. Verify Dungeon Scene Content (Occluders)
        with open(world_path, "r") as f:
            world_data = json.load(f)

        # Find the dungeon scene path from the world file
        scenes = world_data.get("scenes", {})
        dungeon_entry = scenes.get("Ridge Outpost_dungeon")
        assert dungeon_entry, "Ridge Outpost_dungeon missing from world file"

        dungeon_scene_path = Path(dungeon_entry["path"])
        assert dungeon_scene_path.exists(), f"Dungeon scene {dungeon_scene_path} does not exist"

        with open(dungeon_scene_path, "r") as f:
            scene_data = json.load(f)

        occluders = scene_data.get("occluders", [])
        assert len(occluders) >= 3, \
            f"Preset {preset_name} points to a scene with insufficient occluders ({len(occluders)}). Demo requires >= 3."
