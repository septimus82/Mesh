import logging

import pytest

import engine.swallowed_exceptions as swallowed_exceptions
from engine.lighting import LightManager

pytestmark = [pytest.mark.fast]


class _Camera:
    position = {"x": 12.0, "y": 34.0}


class _Window:
    camera = _Camera()
    show_debug = False


def test_end_uses_zero_camera_offset_for_bad_position_shape(caplog: pytest.LogCaptureFixture) -> None:
    manager = object.__new__(LightManager)
    manager.enabled = True
    manager._layer = object()
    manager.shadows_mode = "none"
    manager.debug_geometry_enabled = False
    manager.window = _Window()

    seen_offsets: list[tuple[float, float]] = []
    manager._draw_layer_safe = lambda: True
    manager._apply_light_cookies = lambda *, target_fbo, offset: seen_offsets.append(offset)
    manager._apply_light_shafts = lambda *, target_fbo, offset: seen_offsets.append(offset)

    swallowed_exceptions._SWALLOW_ONCE_TAGS.clear()
    try:
        with caplog.at_level(logging.DEBUG, logger="engine.lighting"):
            manager.end()
            manager.end()
        swallow_tags = set(swallowed_exceptions._SWALLOW_ONCE_TAGS)
    finally:
        swallowed_exceptions._SWALLOW_ONCE_TAGS.clear()

    assert seen_offsets == [(0.0, 0.0), (0.0, 0.0), (0.0, 0.0), (0.0, 0.0)]
    assert swallow_tags == {"LGIN-008"}
