from pathlib import Path

from tests._variant_contracts import get_golden_slice_variant_case


def test_variant_g_dungeon_scene_validates_strict():
    case = get_golden_slice_variant_case("g")
    assert case.scene == "packs/core_regions/scenes/Ridge Outpost_dungeon_variant_g.json"
    assert Path(case.scene).exists()
