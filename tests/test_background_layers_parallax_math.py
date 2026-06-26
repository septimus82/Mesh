from engine.background_layers import compute_background_offset_px, compute_background_screen_center, compute_background_world_center


def test_background_layers_parallax_math_scales_by_zoom():
    assert compute_background_offset_px(camera_x=100.0, camera_y=50.0, parallax=0.5, zoom=1.0) == (-50.0, -25.0)
    assert compute_background_offset_px(camera_x=10.0, camera_y=-8.0, parallax=0.25, zoom=2.0) == (-5.0, 4.0)


def test_background_world_center_interpolates_between_anchor_and_camera():
    assert compute_background_world_center(camera_x=100.0, camera_y=50.0, parallax=0.0) == (100.0, 50.0)
    assert compute_background_world_center(camera_x=100.0, camera_y=50.0, parallax=1.0) == (0.0, 0.0)
    assert compute_background_world_center(camera_x=100.0, camera_y=50.0, parallax=0.5) == (50.0, 25.0)


def test_background_screen_center_locks_parallax_zero_to_viewport_center():
    assert compute_background_screen_center(
        camera_x=500.0, camera_y=300.0, parallax=0.0, viewport_w=640.0, viewport_h=480.0
    ) == (320.0, 240.0)
