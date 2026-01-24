def test_variant_h_quest_toast_and_reward_are_idempotent():
    from tests._variant_contracts import get_golden_slice_variant_case

    case = get_golden_slice_variant_case("h")
    assert case.start_toast == "Relay: Reactivate the Relay"
    assert case.complete_toast == "Relay: Complete"
    assert case.gold == 30.0
