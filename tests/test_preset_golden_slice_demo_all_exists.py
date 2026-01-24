import json
from pathlib import Path


def test_preset_golden_slice_demo_all_exists_and_is_stable() -> None:
    config_path = Path("config.json")
    assert config_path.exists()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert isinstance(config, dict)

    presets = config.get("presets") or {}
    assert isinstance(presets, dict)

    preset = presets.get("golden_slice_demo_all")
    assert isinstance(preset, dict)

    steps = preset.get("steps", [])
    assert isinstance(steps, list)
    assert steps == [
        {"cmd": "run-preset", "args": ["golden_slice_index"]},
        {"cmd": "run-preset", "args": ["golden_slice2_index"]},
    ]

    assert "golden_slice_index" in presets
    assert "golden_slice2_index" in presets
