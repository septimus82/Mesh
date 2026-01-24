from engine.tilemap import compute_parallax_camera_position


def test_tilemap_multilayer_parallax_math():
    assert compute_parallax_camera_position((100.0, 50.0), 1.0) == (100.0, 50.0)
    assert compute_parallax_camera_position((100.0, 50.0), 0.5) == (50.0, 25.0)
    assert compute_parallax_camera_position((-10.0, 8.0), 2.0) == (-20.0, 16.0)

