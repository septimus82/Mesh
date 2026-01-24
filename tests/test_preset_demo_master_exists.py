import json
from pathlib import Path


def test_preset_demo_master_exists_and_is_stable() -> None:
    config_path = Path("config.json")
    assert config_path.exists()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert isinstance(config, dict)

    presets = config.get("presets") or {}
    assert isinstance(presets, dict)

    preset = presets.get("demo_master")
    assert isinstance(preset, dict)

    steps = preset.get("steps", [])
    assert isinstance(steps, list)
    assert steps == [
        {"cmd": "run-preset", "args": ["golden_slice_demo_all"]},
        {"cmd": "run-preset", "args": ["act1_full_demo"]},
    ]

    assert "golden_slice_demo_all" in presets
    assert "act1_full_demo" in presets
