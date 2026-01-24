from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def test_hard_shadows_overlay_draws_shadow_polygons(monkeypatch) -> None:
    import arcade

    from engine.lighting import LightManager

    os.environ["MESH_SHADOWS_FALLBACK_DRAW"] = "1"

    calls: list[int] = []

    def _draw_polygon_filled(points, _color):  # noqa: ANN001
        calls.append(len(points))

    monkeypatch.setattr(arcade, "draw_polygon_filled", _draw_polygon_filled, raising=False)
    # Ensure shadows module sees the patch - Access via the shadows module to be sure as global state might be polluted
    import engine.lighting.shadows
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
    manager._last_lighting_stats = {}

    with patch(
        "engine.lighting.shadows.build_shadow_polygons",
        return_value=[[(10.0, 10.0), (20.0, 10.0), (20.0, 20.0), (10.0, 20.0)]],
    ), patch.object(LightManager, "_select_shadow_light", return_value=("dynamic", (0.0, 0.0), 100.0, object())), \
       patch("arcade.get_window", return_value=None):
        manager.end()

    assert calls
    assert manager.get_lighting_stats().get("fallback_drawn") is True
