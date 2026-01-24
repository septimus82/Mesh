from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def test_hard_shadows_fallback_draw_calls_draw_polygon_filled(monkeypatch) -> None:
    import arcade

    from engine.lighting import LightManager

    calls: list[int] = []

    def _draw_polygon_filled(points, color):  # noqa: ANN001,ARG001
        calls.append(len(points))

    monkeypatch.setattr(arcade, "draw_polygon_filled", _draw_polygon_filled, raising=False)
    import engine.lighting.shadows
    # Make sure shadows module sees the patch regardless of how it imported it
    # We must patch the reference that shadows module is holding
    monkeypatch.setattr(engine.lighting.shadows.optional_arcade.arcade, "draw_polygon_filled", _draw_polygon_filled, raising=False)
    monkeypatch.setattr(engine.lighting.shadows.optional_arcade.arcade, "get_window", lambda: None, raising=False)

    class _Layer:
        diffuse_texture = object()
        light_texture = object()

        def draw(self, *_args, **_kwargs):  # noqa: ANN003
            return None

    manager = object.__new__(LightManager)
    manager.window = SimpleNamespace(width=800, height=600, camera=None, ctx=None, scene_controller=None)
    manager._layer = _Layer()
    manager.enabled = True
    manager.ambient_color = (10, 10, 10, 255)
    manager._static_occluders = [{"id": "o1", "type": "rect", "x": 0, "y": 0, "width": 10, "height": 10}]
    manager._dynamic_handles = []
    manager._static_lights = []
    manager._static_configs = []
    manager.shadows_mode = "hard"
    manager.debug_geometry_enabled = False

    # Hard shadows are implemented as an overlay pass: LightLayer draw + polygon fills.
    with patch("engine.lighting.shadows.build_shadow_polygons", return_value=[[(0.0, 0.0), (16.0, 0.0), (0.0, 16.0)]]), patch.object(
        LightManager, "_select_shadow_light", return_value=("dynamic", (0.0, 0.0), 100.0, object())
        ), patch("arcade.get_window", return_value=None):
            manager.end()

    assert calls
