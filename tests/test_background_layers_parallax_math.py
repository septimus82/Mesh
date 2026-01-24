from engine.background_layers import compute_background_offset_px


def test_background_layers_parallax_math_scales_by_zoom():
    assert compute_background_offset_px(camera_x=100.0, camera_y=50.0, parallax=0.5, zoom=1.0) == (-50.0, -25.0)
    assert compute_background_offset_px(camera_x=10.0, camera_y=-8.0, parallax=0.25, zoom=2.0) == (-5.0, 4.0)
