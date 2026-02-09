from engine.scene_update_model import UpdateInputs, UpdateStep, build_update_plan


def test_update_plan_pending_load_priority() -> None:
    plan = build_update_plan(UpdateInputs(pending_scene_load=True, pending_scene_change=True, paused=False))
    assert plan.steps == (UpdateStep.PENDING_SCENE_LOAD,)


def test_update_plan_pending_change() -> None:
    plan = build_update_plan(UpdateInputs(pending_scene_load=False, pending_scene_change=True, paused=False))
    assert plan.steps == (UpdateStep.PENDING_SCENE_CHANGE,)


def test_update_plan_paused() -> None:
    plan = build_update_plan(UpdateInputs(pending_scene_load=False, pending_scene_change=False, paused=True))
    assert plan.steps == ()


def test_update_plan_running_order() -> None:
    plan = build_update_plan(UpdateInputs(pending_scene_load=False, pending_scene_change=False, paused=False))
    assert plan.steps == (
        UpdateStep.PRE_UPDATE,
        UpdateStep.UPDATE_BEHAVIOUR,
        UpdateStep.UPDATE_MOVEMENT,
        UpdateStep.UPDATE_ANIMATION,
        UpdateStep.LATE_UPDATE,
    )
