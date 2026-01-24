def test_preset_golden_slice_variant_g_exists_and_targets_world():
    from pathlib import Path

    from tests._variant_contracts import get_golden_slice_variant_case

    case = get_golden_slice_variant_case("g")
    assert case.preset == "golden_slice_variant_g"
    assert case.world == "worlds/golden_slice_variant_g.json"
    assert Path(case.world).exists()
