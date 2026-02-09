from engine.scene_lifecycle_model import SceneLoadInputs, build_scene_load_plan, compute_state_resets


def test_scene_load_plan_deterministic() -> None:
    inputs = SceneLoadInputs(
        scene_path="scenes/a.json",
        current_scene_path="scenes/a.json",
        preserved_camera_state={"x": 1.0, "y": 2.0, "zoom": 1.5},
        clear_assets_on_next_load=True,
        has_assets=True,
        has_audio=True,
        camera_center=(5.0, 6.0),
        camera_zoom=2.0,
    )
    plan1 = build_scene_load_plan(inputs)
    plan2 = build_scene_load_plan(inputs)
    assert plan1 == plan2
    assert plan1.is_reload is True
    assert plan1.saved_camera_pos == (1.0, 2.0)
    assert plan1.saved_zoom == 1.5
    assert plan1.should_clear_assets is True


def test_scene_load_plan_fallback_camera() -> None:
    inputs = SceneLoadInputs(
        scene_path="scenes/a.json",
        current_scene_path="scenes/a.json",
        preserved_camera_state=None,
        clear_assets_on_next_load=False,
        has_assets=True,
        has_audio=True,
        camera_center=(10.0, 11.0),
        camera_zoom=3.0,
    )
    plan = build_scene_load_plan(inputs)
    assert plan.is_reload is True
    assert plan.saved_camera_pos == (10.0, 11.0)
    assert plan.saved_zoom == 3.0
    effects = compute_state_resets(plan)
    assert effects.restore_camera is True
    assert effects.restore_zoom is True


def test_scene_load_plan_not_reload() -> None:
    inputs = SceneLoadInputs(
        scene_path="scenes/b.json",
        current_scene_path="scenes/a.json",
        preserved_camera_state={"x": 1.0, "y": 2.0, "zoom": 1.5},
        clear_assets_on_next_load=True,
        has_assets=True,
        has_audio=True,
        camera_center=(0.0, 0.0),
        camera_zoom=1.0,
    )
    plan = build_scene_load_plan(inputs)
    assert plan.is_reload is False
    assert plan.saved_camera_pos is None
    assert plan.saved_zoom is None
    effects = compute_state_resets(plan)
    assert effects.restore_camera is False
    assert effects.restore_zoom is False
