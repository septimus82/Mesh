import json
from pathlib import Path


def test_preset_golden_slice_showcase_exists_and_lists_variants_sorted():
    config_path = Path("config.json")
    assert config_path.exists()
    config = json.loads(config_path.read_text(encoding="utf-8"))

    presets = config.get("presets") or {}
    assert isinstance(presets, dict)

    preset = presets.get("golden_slice_showcase")
    assert isinstance(preset, dict)

    steps = preset.get("steps", [])
    assert isinstance(steps, list)
    assert len(steps) == 5

    names: list[str] = []
    for step in steps:
        assert isinstance(step, dict)
        assert step.get("cmd") == "run-preset"
        args = step.get("args", [])
        assert isinstance(args, list)
        assert len(args) == 1
        assert isinstance(args[0], str)
        names.append(args[0])

    assert names == [
        "golden_slice_variant_g",
        "golden_slice_variant_h",
        "golden_slice_variant_i",
        "golden_slice_variant_j",
        "golden_slice_variant_k",
    ]
    assert names == sorted(names)
    for name in names:
        assert name in presets
