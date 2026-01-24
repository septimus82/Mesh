from __future__ import annotations

import pytest

from engine.lighting import LightManager

pytestmark = pytest.mark.fast


def test_colored_light_resolves_rgba_and_defaults_to_white() -> None:
    manager = object.__new__(LightManager)
    color = manager._resolve_light_color({"color_rgba": [10, 20, 30, 40]})
    assert color == (10, 20, 30, 40)

    default_color = manager._resolve_light_color({})
    assert default_color == (255, 255, 255, 255)
