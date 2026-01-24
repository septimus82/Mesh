from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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


def test_hard_shadows_composite_includes_polygon_occluders() -> None:
    manager = object.__new__(LightManager)
    manager.window = SimpleNamespace(width=100, height=100, camera=None, ctx=None)
    manager._layer = _StubLayer()
    manager._static_occluders = [
        {"type": "rect", "x": 0, "y": 0, "width": 10, "height": 10},
        {"type": "poly", "points": [[0, 0], [10, 0], [10, 10], [0, 10]]},
    ]
    manager.shadows_mode = "hard"
    manager.ambient_color = (0, 0, 0, 255)
    manager._select_shadow_light = lambda: ("static", (5.0, 5.0), 20.0, object())

    targets = SimpleNamespace(
        light_fbo=_StubFbo(),
        mask_fbo=_StubFbo(),
        mask_tex=object(),
        light_tex=object(),
    )
    captured: list[list[tuple[float, float]]] = []

    rect_polys = [[(1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (1.0, 2.0)]]
    poly_polys = [[(3.0, 3.0), (4.0, 3.0), (4.0, 4.0), (3.0, 4.0)]]

    rect_builder = MagicMock(return_value=rect_polys)
    poly_builder = MagicMock(return_value=poly_polys)

    def _render_shadow_mask(_window, polys, *_args, **_kwargs):  # noqa: ANN001
        captured.extend(polys)
        return targets.mask_tex

    with patch("engine.lighting.hard_shadows_backend.ensure_render_targets", return_value=targets), patch(
        "engine.lighting.hard_shadows_backend.composite_to_window", return_value=True
    ), patch("engine.lighting.shadows.build_shadow_polygons", rect_builder), patch(
        "engine.lighting.shadows_v1.build_shadow_polygons_v1", poly_builder
    ), patch("engine.lighting.shadows.render_shadow_mask", _render_shadow_mask):
        ok = LightManager._end_hard_shadows_composite(manager)

    assert ok is True
    assert rect_builder.called is True
    assert poly_builder.called is True
    assert captured == rect_polys + poly_polys
