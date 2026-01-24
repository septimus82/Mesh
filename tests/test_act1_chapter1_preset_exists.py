from engine.config import load_config


def test_act1_chapter1_preset_exists_and_targets_world() -> None:
    config = load_config()
    presets = getattr(config, "presets", {})
    assert "act1_chapter1" in presets

    preset = presets["act1_chapter1"]
    assert isinstance(preset, dict)
    assert preset.get("description")

    steps = preset.get("steps")
    assert isinstance(steps, list)
    assert len(steps) >= 1

    first = steps[0]
    assert isinstance(first, dict)
    assert first.get("cmd") == "pipeline"

    args = first.get("args")
    assert isinstance(args, list)
    assert "--world" in args
    world_idx = args.index("--world")
    assert args[world_idx + 1] == "worlds/act1_chapter1.json"
