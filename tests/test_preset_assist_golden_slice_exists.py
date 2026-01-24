import json
import pytest
from pathlib import Path

def test_preset_assist_golden_slice_exists():
    """Verify assist-golden-slice-dryrun preset exists and is correct."""
    config_path = Path("config.json")
    assert config_path.exists(), "config.json not found"
    
    config = json.loads(config_path.read_text(encoding="utf-8"))
    presets = config.get("presets", {})
    
    preset_id = "assist-golden-slice-dryrun"
    assert preset_id in presets, f"Preset '{preset_id}' missing from config.json"
    
    preset = presets[preset_id]
    assert preset["description"] == "Agent dry-run summary (no writes) for Golden Slice"
    
    steps = preset.get("steps", [])
    assert len(steps) == 1, "Expected exactly one step"
    
    step = steps[0]
    assert step["cmd"] == "assist"
    
    args = step.get("args", [])
    assert "--dry-run" in args
    assert "--summary-json" in args
    
    # Check world argument
    assert "--world" in args
    world_idx = args.index("--world")
    assert world_idx + 1 < len(args)
    world_path = args[world_idx + 1]
    
    # Verify world file exists
    assert Path(world_path).exists(), f"Referenced world file '{world_path}' does not exist"
