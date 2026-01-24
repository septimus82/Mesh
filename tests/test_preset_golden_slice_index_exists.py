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


def test_preset_golden_slice_indices_exist_and_are_stable() -> None:
    config_path = Path("config.json")
    assert config_path.exists()
    config = json.loads(config_path.read_text(encoding="utf-8"))

    presets = config.get("presets") or {}
    assert isinstance(presets, dict)

    index1 = presets.get("golden_slice_index")
    assert isinstance(index1, dict)
    index2 = presets.get("golden_slice2_index")
    assert isinstance(index2, dict)

    assert _extract_run_preset_step_names(index1) == ["golden_slice_showcase_all"]
    assert _extract_run_preset_step_names(index2) == ["golden_slice2_showcase_all"]

    assert "golden_slice_showcase_all" in presets
    assert "golden_slice2_showcase_all" in presets

