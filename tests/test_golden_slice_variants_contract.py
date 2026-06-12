import pytest

from tests._variant_contracts import (
    GOLDEN_SLICE_VARIANT_CASES,
    assert_branching_choice_content_invariants,
    assert_branching_choice_paths,
    assert_content_invariants,
    assert_preset_targets_world,
    assert_puzzle_lite_content_invariants,
    assert_puzzle_lite_paths,
    assert_reward_toast_idempotent,
    drive_zone_to_zone_quest,
    load_scene_and_assert_valid,
)

pytestmark = pytest.mark.builtin_behaviours

LINEAR_VARIANT_CASES = [case for case in GOLDEN_SLICE_VARIANT_CASES if case.kind == "linear"]


@pytest.mark.parametrize("case", GOLDEN_SLICE_VARIANT_CASES, ids=lambda c: f"variant_{c.variant}")
def test_golden_slice_variant_scene_load_contract(case) -> None:
    load_scene_and_assert_valid(case.scene)


@pytest.mark.parametrize("case", GOLDEN_SLICE_VARIANT_CASES, ids=lambda c: f"variant_{c.variant}")
def test_golden_slice_variant_quest_progression_contract(case) -> None:
    if case.kind == "linear":
        assert case.quest_id is not None
        assert case.stage_id is not None
        assert case.start_zone is not None
        assert case.goal_zone is not None
        assert case.complete_flag is not None
        assert case.gold is not None
        drive_zone_to_zone_quest(
            quest_id=case.quest_id,
            stage_id=case.stage_id,
            start_zone_id=case.start_zone,
            goal_zone_id=case.goal_zone,
            expected_flag=case.complete_flag,
            expected_gold=case.gold,
        )
        return

    if case.kind == "branching_choice":
        assert case.start_zone is not None
        assert case.intro_quest_id is not None
        assert case.intro_flag is not None
        assert case.choice_a_quest_id is not None
        assert case.choice_b_quest_id is not None
        assert case.choice_a_start_zone is not None
        assert case.choice_b_start_zone is not None
        assert case.choice_a_goal_zone is not None
        assert case.choice_b_goal_zone is not None
        assert case.choice_a_complete_flag is not None
        assert case.choice_b_complete_flag is not None
        assert case.choice_gold is not None
        assert case.choice_a_start_toast is not None
        assert case.choice_b_start_toast is not None
        assert case.choice_a_complete_toast is not None
        assert case.choice_b_complete_toast is not None
        assert_branching_choice_paths(
            intro_quest_id=case.intro_quest_id,
            intro_flag=case.intro_flag,
            start_zone_id=case.start_zone,
            choice_a_quest_id=case.choice_a_quest_id,
            choice_b_quest_id=case.choice_b_quest_id,
            choice_a_start_zone=case.choice_a_start_zone,
            choice_b_start_zone=case.choice_b_start_zone,
            choice_a_goal_zone=case.choice_a_goal_zone,
            choice_b_goal_zone=case.choice_b_goal_zone,
            choice_a_complete_flag=case.choice_a_complete_flag,
            choice_b_complete_flag=case.choice_b_complete_flag,
            choice_gold=case.choice_gold,
            choice_a_start_toast=case.choice_a_start_toast,
            choice_b_start_toast=case.choice_b_start_toast,
            choice_a_complete_toast=case.choice_a_complete_toast,
            choice_b_complete_toast=case.choice_b_complete_toast,
        )
        return

    assert case.kind == "puzzle_lite"
    assert case.start_zone is not None
    assert case.goal_zone is not None
    assert case.puzzle_unlock_event is not None
    assert case.puzzle_unlocked_flag is not None
    assert case.puzzle_quest_id is not None
    assert case.puzzle_start_toast is not None
    assert case.puzzle_complete_toast is not None
    assert case.goal_quest_id is not None
    assert case.goal_complete_flag is not None
    assert case.goal_start_toast is not None
    assert case.goal_complete_toast is not None
    assert case.goal_gold is not None
    assert_puzzle_lite_paths(
        start_zone_id=case.start_zone,
        goal_zone_id=case.goal_zone,
        unlock_event=case.puzzle_unlock_event,
        unlocked_flag=case.puzzle_unlocked_flag,
        puzzle_quest_id=case.puzzle_quest_id,
        puzzle_start_toast=case.puzzle_start_toast,
        puzzle_complete_toast=case.puzzle_complete_toast,
        goal_quest_id=case.goal_quest_id,
        goal_complete_flag=case.goal_complete_flag,
        goal_start_toast=case.goal_start_toast,
        goal_complete_toast=case.goal_complete_toast,
        goal_gold=case.goal_gold,
    )


@pytest.mark.parametrize("case", LINEAR_VARIANT_CASES, ids=lambda c: f"variant_{c.variant}")
def test_golden_slice_variant_reward_toast_idempotency_contract(case) -> None:
    assert case.quest_id is not None
    assert case.start_zone is not None
    assert case.goal_zone is not None
    assert case.start_toast is not None
    assert case.complete_toast is not None
    assert case.gold is not None
    assert_reward_toast_idempotent(
        quest_id=case.quest_id,
        start_zone_id=case.start_zone,
        goal_zone_id=case.goal_zone,
        start_toast=case.start_toast,
        complete_toast=case.complete_toast,
        expected_gold=case.gold,
    )


@pytest.mark.parametrize("case", GOLDEN_SLICE_VARIANT_CASES, ids=lambda c: f"variant_{c.variant}")
def test_golden_slice_variant_content_invariants_contract(case) -> None:
    if case.kind == "linear":
        assert case.quest_id is not None
        assert case.start_zone is not None
        assert case.goal_zone is not None
        assert case.gold is not None
        assert case.complete_flag is not None
        assert case.start_toast is not None
        assert case.complete_toast is not None
        assert case.on_trigger_start is not None
        assert case.on_trigger_goal is not None
        assert_content_invariants(
            scene_json_path=case.scene,
            quest_id=case.quest_id,
            start_zone_id=case.start_zone,
            goal_zone_id=case.goal_zone,
            expected_gold=case.gold,
            expected_flag=case.complete_flag,
            expected_start_toast=case.start_toast,
            expected_complete_toast=case.complete_toast,
            on_trigger_start=case.on_trigger_start,
            on_trigger_goal=case.on_trigger_goal,
        )
        return

    if case.kind == "branching_choice":
        assert case.start_zone is not None
        assert case.intro_quest_id is not None
        assert case.intro_flag is not None
        assert case.choice_a_quest_id is not None
        assert case.choice_b_quest_id is not None
        assert case.choice_a_start_zone is not None
        assert case.choice_b_start_zone is not None
        assert case.choice_a_goal_zone is not None
        assert case.choice_b_goal_zone is not None
        assert case.choice_a_complete_flag is not None
        assert case.choice_b_complete_flag is not None
        assert case.choice_gold is not None
        assert case.choice_a_start_toast is not None
        assert case.choice_b_start_toast is not None
        assert case.choice_a_complete_toast is not None
        assert case.choice_b_complete_toast is not None
        assert_branching_choice_content_invariants(
            scene_json_path=case.scene,
            start_zone_id=case.start_zone,
            intro_quest_id=case.intro_quest_id,
            intro_flag=case.intro_flag,
            choice_a_quest_id=case.choice_a_quest_id,
            choice_b_quest_id=case.choice_b_quest_id,
            choice_a_start_zone=case.choice_a_start_zone,
            choice_b_start_zone=case.choice_b_start_zone,
            choice_a_goal_zone=case.choice_a_goal_zone,
            choice_b_goal_zone=case.choice_b_goal_zone,
            choice_a_complete_flag=case.choice_a_complete_flag,
            choice_b_complete_flag=case.choice_b_complete_flag,
            choice_gold=case.choice_gold,
            choice_a_start_toast=case.choice_a_start_toast,
            choice_b_start_toast=case.choice_b_start_toast,
            choice_a_complete_toast=case.choice_a_complete_toast,
            choice_b_complete_toast=case.choice_b_complete_toast,
        )
        return

    assert case.kind == "puzzle_lite"
    assert case.start_zone is not None
    assert case.goal_zone is not None
    assert case.on_trigger_start is not None
    assert case.on_trigger_goal is not None
    assert case.puzzle_unlock_event is not None
    assert case.puzzle_unlocked_flag is not None
    assert case.puzzle_quest_id is not None
    assert case.puzzle_start_toast is not None
    assert case.puzzle_complete_toast is not None
    assert case.goal_quest_id is not None
    assert case.goal_start_toast is not None
    assert case.goal_complete_toast is not None
    assert case.goal_complete_flag is not None
    assert case.goal_gold is not None
    assert_puzzle_lite_content_invariants(
        scene_json_path=case.scene,
        start_zone_id=case.start_zone,
        goal_zone_id=case.goal_zone,
        on_trigger_start=case.on_trigger_start,
        on_trigger_goal=case.on_trigger_goal,
        unlock_event=case.puzzle_unlock_event,
        unlocked_flag=case.puzzle_unlocked_flag,
        puzzle_quest_id=case.puzzle_quest_id,
        puzzle_start_toast=case.puzzle_start_toast,
        puzzle_complete_toast=case.puzzle_complete_toast,
        goal_quest_id=case.goal_quest_id,
        goal_start_toast=case.goal_start_toast,
        goal_complete_toast=case.goal_complete_toast,
        goal_complete_flag=case.goal_complete_flag,
        goal_gold=case.goal_gold,
    )


@pytest.mark.parametrize("case", GOLDEN_SLICE_VARIANT_CASES, ids=lambda c: f"variant_{c.variant}")
def test_golden_slice_variant_preset_targets_world_contract(case) -> None:
    assert_preset_targets_world(case.preset, case.world)
