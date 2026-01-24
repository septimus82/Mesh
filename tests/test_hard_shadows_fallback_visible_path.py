from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def test_hard_shadows_fallback_visible_path_returns_true_and_draws(monkeypatch) -> None:
    import arcade

    from engine.lighting import LightManager

    os.environ["MESH_SHADOWS_FALLBACK_DRAW"] = "1"

    calls: list[int] = []

    def _draw_polygon_filled(points, _color):  # noqa: ANN001
        calls.append(len(points))

    monkeypatch.setattr(arcade, "draw_polygon_filled", _draw_polygon_filled, raising=False)
    # Also patch engine.optional_arcade.arcade just to be safe
    import engine.optional_arcade
    monkeypatch.setattr(engine.optional_arcade.arcade, "draw_polygon_filled", _draw_polygon_filled, raising=False)

    class _Layer:
        diffuse_texture = object()

        def __init__(self) -> None:
            self.screen_draw_calls = 0

        def draw(self, *_args, **kwargs):  # noqa: ANN003
            # Count screen draws (no target kwarg means screen draw).
            if kwargs.get("target") is None:
                self.screen_draw_calls += 1
            return None

    class _Fbo:
        def use(self) -> None:
            return None

        def clear(self, *args, **kwargs):  # noqa: ANN002,ARG002
            return None

    targets = SimpleNamespace(light_fbo=_Fbo(), mask_fbo=_Fbo(), mask_tex=object(), light_tex=object())

    manager = object.__new__(LightManager)
    manager.window = SimpleNamespace(width=800, height=600, camera=SimpleNamespace(position=(0.0, 0.0)), ctx=None, scene_controller=None)
    manager._layer = _Layer()
    manager.enabled = True
    manager.ambient_color = (10, 10, 10, 255)
    manager._static_occluders = [{"id": "o1", "type": "rect", "x": 0, "y": 0, "width": 10, "height": 10}]
    manager._dynamic_handles = []
    manager._static_lights = []
    manager._static_configs = []
    manager.shadows_mode = "hard"
    manager.debug_geometry_enabled = False
    manager._last_lighting_stats = {}

    # Force composite failure so we exercise the visible fallback path.
    with patch("engine.lighting.hard_shadows_backend.ensure_render_targets", return_value=targets), patch(
        "engine.lighting.shadows.render_shadow_mask", return_value=None
    ), patch(
        "engine.lighting.hard_shadows_backend.composite_to_window", return_value=False
    ), patch.object(LightManager, "_select_shadow_light", return_value=("dynamic", (0.0, 0.0), 100.0, object())), patch(
        "engine.lighting.shadows.build_shadow_polygons",
        return_value=[[(10.0, 10.0), (20.0, 10.0), (20.0, 20.0), (10.0, 20.0)]],
    ):
        ok = LightManager._end_hard_shadows_composite(manager)

    assert ok is True
    assert calls
    stats = manager.get_lighting_stats()
    assert stats.get("fallback_drawn") is True
    assert stats.get("composite_ok") is False
