from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from engine.lighting import LightManager
from engine.lighting.shadow_soften import expand_polygon

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


def _build_manager(soft_enabled: bool) -> LightManager:
    manager = object.__new__(LightManager)
    manager.window = SimpleNamespace(
        width=100,
        height=100,
        camera=None,
        ctx=None,
        engine_config=SimpleNamespace(
            soft_shadows_enabled=soft_enabled,
            soft_shadows_expand_px=4.0,
            soft_shadows_alpha_scale=0.25,
        ),
    )
    manager._layer = _StubLayer()
    manager._static_occluders = [{"type": "rect", "x": 0, "y": 0, "width": 10, "height": 10}]
    manager.shadows_mode = "hard"
    manager.ambient_color = (0, 0, 0, 255)
    manager._select_shadow_light = lambda: ("static", (5.0, 5.0), 20.0, object())
    return manager


def test_soft_shadows_enabled_renders_soft_and_hard_polys() -> None:
    manager = _build_manager(True)
    targets = SimpleNamespace(
        light_fbo=_StubFbo(),
        mask_fbo=_StubFbo(),
        mask_tex=object(),
        light_tex=object(),
    )
    hard_polys = [[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]]
    captured: list[list[list[tuple[float, float]]]] = []

    def _render_shadow_mask(_window, polys, *_args, **_kwargs):  # noqa: ANN001
        captured.append(list(polys))
        return targets.mask_tex

    with patch("engine.lighting.hard_shadows_backend.ensure_render_targets", return_value=targets), patch(
        "engine.lighting.hard_shadows_backend.composite_to_window", return_value=True
    ), patch("engine.lighting.shadows.build_shadow_polygons", return_value=hard_polys), patch(
        "engine.lighting.shadows.render_shadow_mask", _render_shadow_mask
    ):
        ok = LightManager._end_hard_shadows_composite(manager)

    assert ok is True
    assert captured[0] == hard_polys
    assert captured[1] == [expand_polygon(poly, 4.0) for poly in hard_polys]


def test_soft_shadows_disabled_renders_only_hard_polys() -> None:
    manager = _build_manager(False)
    targets = SimpleNamespace(
        light_fbo=_StubFbo(),
        mask_fbo=_StubFbo(),
        mask_tex=object(),
        light_tex=object(),
    )
    hard_polys = [[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]]
    captured: list[list[list[tuple[float, float]]]] = []

    def _render_shadow_mask(_window, polys, *_args, **_kwargs):  # noqa: ANN001
        captured.append(list(polys))
        return targets.mask_tex

    with patch("engine.lighting.hard_shadows_backend.ensure_render_targets", return_value=targets), patch(
        "engine.lighting.hard_shadows_backend.composite_to_window", return_value=True
    ), patch("engine.lighting.shadows.build_shadow_polygons", return_value=hard_polys), patch(
        "engine.lighting.shadows.render_shadow_mask", _render_shadow_mask
    ):
        ok = LightManager._end_hard_shadows_composite(manager)

    assert ok is True
    assert captured == [hard_polys]
