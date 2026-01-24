import json
from pathlib import Path


def _extract_run_preset_step_names(preset: dict) -> list[str]:
    steps = preset.get("steps", [])
    assert isinstance(steps, list)
    names: list[str] = []
    for step in steps:
        assert isinstance(step, dict)
        assert step.get("cmd") == "run-preset"
        args = step.get("args", [])
        assert isinstance(args, list)
        assert len(args) == 1
        assert isinstance(args[0], str)
        names.append(args[0])
    return names


def test_preset_golden_slice_showcase_all_exists_and_is_sorted() -> None:
    config_path = Path("config.json")
    assert config_path.exists()
    config = json.loads(config_path.read_text(encoding="utf-8"))

    presets = config.get("presets") or {}
    assert isinstance(presets, dict)

    preset = presets.get("golden_slice_showcase_all")
    assert isinstance(preset, dict)

    names = _extract_run_preset_step_names(preset)
    assert names == [
        "golden_slice_variant_g",
        "golden_slice_variant_h",
        "golden_slice_variant_i",
        "golden_slice_variant_j",
        "golden_slice_variant_k",
        "golden_slice_variant_l",
    ]
    assert names == sorted(names)
    for name in names:
        assert name in presets


def test_preset_golden_slice2_showcase_all_exists_and_is_sorted() -> None:
    config_path = Path("config.json")
    assert config_path.exists()
    config = json.loads(config_path.read_text(encoding="utf-8"))

    presets = config.get("presets") or {}
    assert isinstance(presets, dict)

    preset = presets.get("golden_slice2_showcase_all")
    assert isinstance(preset, dict)

    names = _extract_run_preset_step_names(preset)
    assert names == [
        "golden_slice2_variant_g",
        "golden_slice2_variant_j",
        "golden_slice2_variant_k",
        "golden_slice2_variant_m",
        "golden_slice2_variant_n",
    ]
    assert names == sorted(names)
    for name in names:
        assert name in presets

