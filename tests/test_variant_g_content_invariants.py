def test_variant_g_scene_zones_exist_exactly_once_and_match_quest():
    from tests._variant_contracts import get_golden_slice_variant_case

    case = get_golden_slice_variant_case("g")
    assert case.on_trigger_start == "variant_g_start"
    assert case.on_trigger_goal == "variant_g_goal"
    assert case.complete_flag == "ridge_variant_g_beacon_complete"
