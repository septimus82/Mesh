from pathlib import Path

from tests._variant_contracts import get_golden_slice_variant_case


def test_variant_h_dungeon_scene_validates_strict():
    case = get_golden_slice_variant_case("h")
    assert case.scene == "packs/core_regions/scenes/Ridge Outpost_dungeon_variant_h.json"
    assert Path(case.scene).exists()
