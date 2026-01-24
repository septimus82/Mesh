from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from engine.lighting import LightManager

pytestmark = pytest.mark.fast


class _StubFbo:
    def use(self) -> None:
        return

    def clear(self) -> None:
        return


class _StubLayer:
    def __init__(self) -> None:
        self.diffuse_texture = object()

    def draw(self, *args, **kwargs) -> None:  # noqa: ANN001
        return


def test_ambient_tint_defaults_to_neutral_in_composite() -> None:
    manager = object.__new__(LightManager)
    manager.window = SimpleNamespace(width=100, height=100, camera=None, ctx=None)
    manager._layer = _StubLayer()
    manager._static_occluders = [{"type": "rect", "x": 0, "y": 0, "width": 10, "height": 10}]
    manager.shadows_mode = "hard"
    manager.ambient_color = (10, 20, 30, 200)
    manager.ambient_tint = (255, 255, 255, 255)
    manager.ambient_darkness_alpha = None
    manager._select_shadow_light = lambda: ("static", (5.0, 5.0), 20.0, object())

    targets = SimpleNamespace(
        light_fbo=_StubFbo(),
        mask_fbo=_StubFbo(),
        mask_tex=object(),
        light_tex=object(),
    )
    captured: list[tuple[int, int, int, int]] = []

    def _composite_to_window(_window, *, diffuse_tex, light_tex, mask_tex, ambient_color):  # noqa: ANN001
        captured.append(tuple(ambient_color))
        return True

    with patch("engine.lighting.hard_shadows_backend.ensure_render_targets", return_value=targets), patch(
        "engine.lighting.hard_shadows_backend.composite_to_window", _composite_to_window
    ), patch("engine.lighting.shadows.render_shadow_mask", return_value=targets.mask_tex):
        ok = LightManager._end_hard_shadows_composite(manager)

    assert ok is True
    assert captured == [(10, 20, 30, 200)]
