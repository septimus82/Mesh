import json
from pathlib import Path


def test_preset_act1_full_demo_exists_and_is_stable() -> None:
    config_path = Path("config.json")
    assert config_path.exists()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert isinstance(config, dict)

    presets = config.get("presets") or {}
    assert isinstance(presets, dict)

    preset = presets.get("act1_full_demo")
    assert isinstance(preset, dict)

    steps = preset.get("steps", [])
    assert isinstance(steps, list)
    assert steps == [
        {"cmd": "run-preset", "args": ["act1_prologue"]},
        {"cmd": "run-preset", "args": ["act1_chapter1"]},
        {"cmd": "run-preset", "args": ["act1_chapter2"]},
        {"cmd": "run-preset", "args": ["act1_chapter3"]},
        {"cmd": "run-preset", "args": ["act1_chapter4"]},
        {"cmd": "run-preset", "args": ["act1_chapter5"]},
    ]

    assert "act1_prologue" in presets
    assert "act1_chapter1" in presets
    assert "act1_chapter2" in presets
    assert "act1_chapter3" in presets
    assert "act1_chapter4" in presets
    assert "act1_chapter5" in presets

    act1_index = presets.get("act1_index")
    assert isinstance(act1_index, dict)
    index_steps = act1_index.get("steps", [])
    assert isinstance(index_steps, list)
    assert index_steps == [{"cmd": "run-preset", "args": ["act1_full_demo"]}]
