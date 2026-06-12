import json
from pathlib import Path

import pytest

from engine.config import load_config


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

def test_golden_slice_lighting_showcase_intent():
    """
    Enforce lighting showcase intent for Golden Slice variants.
    
    Rule:
    - If preset is 'golden_slice' or starts with 'golden_slice_variant_',
      it must either:
        A) Have >= 3 occluders in its dungeon scene (Showcase), OR
        B) Explicitly opt-out via "lighting_showcase": false in config.json.
    
    Also enforces that variant_e specifically IS a showcase.
    """
    config = load_config()
    presets = getattr(config, "presets", {})

    golden_slice_presets = [
        name for name in presets.keys()
        if name == "golden_slice" or name.startswith("golden_slice_variant_")
    ]

    assert "golden_slice_variant_e" in golden_slice_presets, "Variant E must exist"

    for preset_name in golden_slice_presets:
        preset_data = presets[preset_name]
        is_showcase_flag = preset_data.get("lighting_showcase", None)

        # Specific check for Variant E
        if preset_name == "golden_slice_variant_e":
            assert is_showcase_flag is True, f"{preset_name} must have lighting_showcase=True"

        # Load scene to check occluders
        scene_path = _get_dungeon_scene_path(preset_name)
        if not scene_path.exists():
             pytest.fail(f"Scene file {scene_path} missing for {preset_name}")

        with open(scene_path, "r") as f:
            scene_data = json.load(f)

        occluders = scene_data.get("occluders", [])
        occluder_count = len(occluders)

        is_content_showcase = occluder_count >= 3

        if is_content_showcase:
            # If content qualifies as showcase, flag should ideally be True or unset (defaulting to True? No, default is False usually).
            # Actually, the rule is: If it IS a showcase content-wise, we don't
            # strictly require the flag to be True unless we want to enforce
            # metadata accuracy.
            # But the prompt says: "it must either A) reference a world whose dungeon scene contains occluders >= 3, OR B) have "lighting_showcase": false"
            # This implies: If occluders < 3, THEN lighting_showcase MUST be False.
            pass
        else:
            # Content is NOT a showcase (occluders < 3).
            # Therefore, it MUST explicitly opt-out.
            assert is_showcase_flag is False, (
                f"Preset '{preset_name}' has only {occluder_count} occluders (not a showcase), "
                f"so it must explicitly set 'lighting_showcase': false in config.json."
            )

