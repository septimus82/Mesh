def test_preset_golden_slice_variant_h_exists_and_targets_world():
    from pathlib import Path

    from tests._variant_contracts import get_golden_slice_variant_case

    case = get_golden_slice_variant_case("h")
    assert case.preset == "golden_slice_variant_h"
    assert case.world == "worlds/golden_slice_variant_h.json"
    assert Path(case.world).exists()
