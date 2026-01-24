def test_variant_h_quest_progression_zone_to_zone():
    from tests._variant_contracts import get_golden_slice_variant_case

    case = get_golden_slice_variant_case("h")
    assert case.quest_id == "ridge_variant_h_relay"
    assert case.stage_id == "reactivate_relay"
    assert case.start_zone == "VariantHStartZone"
    assert case.goal_zone == "VariantHGoalZone"
