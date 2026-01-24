def test_variant_g_quest_completion_toast_and_reward_are_deterministic():
    from tests._variant_contracts import get_golden_slice_variant_case

    case = get_golden_slice_variant_case("g")
    assert case.start_toast == "Beacon: Reach the Beacon"
    assert case.complete_toast == "Beacon: Complete"
    assert case.gold == 25.0
