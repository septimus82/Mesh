def test_variant_g_quest_progression_zone_to_zone():
    from tests._variant_contracts import get_golden_slice_variant_case

    case = get_golden_slice_variant_case("g")
    assert case.quest_id == "ridge_variant_g_beacon"
    assert case.stage_id == "reach_beacon"
    assert case.start_zone == "VariantGStartZone"
    assert case.goal_zone == "VariantGGoalZone"
