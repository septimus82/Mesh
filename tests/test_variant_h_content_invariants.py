def test_variant_h_scene_zones_exist_exactly_once_and_match_quest():
    from tests._variant_contracts import get_golden_slice_variant_case

    case = get_golden_slice_variant_case("h")
    assert case.on_trigger_start == "variant_h_start"
    assert case.on_trigger_goal == "variant_h_goal"
    assert case.complete_flag == "ridge_variant_h_relay_complete"
