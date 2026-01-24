import json
from pathlib import Path

from engine.ui import build_golden_slice_variant_picker_presets, build_golden_slice_variant_picker_source, load_config_json


def _extract_showcase_preset_names(showcase: dict) -> list[str]:
    steps = showcase.get("steps", [])
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


def test_golden_slice_variant_picker_list_source_includes_both_locations_in_stable_order() -> None:
    config_path = Path("config.json")
    assert config_path.exists()
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)

    presets = raw.get("presets") or {}
    assert isinstance(presets, dict)
    index1 = presets.get("golden_slice_index")
    assert isinstance(index1, dict)
    index2 = presets.get("golden_slice2_index")
    assert isinstance(index2, dict)

    index1_targets = _extract_showcase_preset_names(index1)
    index2_targets = _extract_showcase_preset_names(index2)
    assert index1_targets == ["golden_slice_showcase_all"]
    assert index2_targets == ["golden_slice2_showcase_all"]

    showcase1 = presets.get(index1_targets[0])
    assert isinstance(showcase1, dict)
    showcase2 = presets.get(index2_targets[0])
    assert isinstance(showcase2, dict)

    names1 = _extract_showcase_preset_names(showcase1)
    names2 = _extract_showcase_preset_names(showcase2)

    assert names1 == sorted(names1)
    assert names2 == sorted(names2)

    picker_names = build_golden_slice_variant_picker_presets(load_config_json("config.json"))
    assert picker_names == names1 + names2

    source = build_golden_slice_variant_picker_source(load_config_json("config.json"))
    categories = source.get("categories")
    assert isinstance(categories, list)
    act1 = [c for c in categories if isinstance(c, dict) and c.get("id") == "act1"]
    assert len(act1) == 1
    assert act1[0].get("label") == "Act 1"
    assert act1[0].get("ok") is True
    assert act1[0].get("names") == ["act1_index", "act1_prologue", "act1_chapter1", "act1_demo"]
