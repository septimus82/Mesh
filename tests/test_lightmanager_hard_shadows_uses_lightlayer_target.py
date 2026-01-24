from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def test_lightlayer_overlay_path_is_used_in_hard_mode(monkeypatch) -> None:
    import engine.lighting as lighting
    import engine.lighting.shadows as shadows
    import engine.optional_arcade
    import arcade

    calls: list[int] = []

    def _draw_polygon_filled(points, _color):  # noqa: ANN001
        calls.append(len(points))

    monkeypatch.setattr(arcade, "draw_polygon_filled", _draw_polygon_filled, raising=False)
    monkeypatch.setattr(arcade, "get_window", lambda: None, raising=False)
    monkeypatch.setattr(engine.optional_arcade.arcade, "draw_polygon_filled", _draw_polygon_filled, raising=False)
    monkeypatch.setattr(engine.optional_arcade.arcade, "get_window", lambda: None, raising=False)
    monkeypatch.setattr(shadows.optional_arcade.arcade, "draw_polygon_filled", _draw_polygon_filled, raising=False)
    monkeypatch.setattr(shadows.optional_arcade.arcade, "get_window", lambda: None, raising=False)
    monkeypatch.setattr(
        shadows,
        "build_shadow_polygons",
        lambda *_a, **_k: [[(10.0, 10.0), (20.0, 10.0), (20.0, 20.0), (10.0, 20.0)]],
        raising=True,
    )

    class _Layer:
        def __init__(self) -> None:
            self.called_target = None
            self.diffuse_texture = object()
            self.light_texture = object()

        def draw(self, *, position=(0, 0), target=None, ambient_color=(0, 0, 0)):  # noqa: ARG002
            self.called_target = target

    class _Camera:
        position = (0.0, 0.0)

    class _Window:
        width = 320
        height = 200
        camera = _Camera()

        def use(self) -> None:  # pragma: no cover
            return

    window = _Window()
    monkeypatch.setattr(lighting, "_LightLayer", None, raising=True)
    monkeypatch.setattr(lighting, "_Light", None, raising=True)
    lm = lighting.LightManager(window, enabled=False)
    lm.enabled = True
    lm.available = True
    lm._layer = _Layer()
    lm.shadows_mode = "hard"
    lm._static_occluders = [{"id": "wall", "x": 0, "y": 0, "width": 32, "height": 32}]
    lm._static_configs = [{"enabled": True, "x": 16, "y": 16, "radius": 64}]

    lm.end()
    # Overlay mode draws to the screen (no target framebuffer) and draws shadow polys.
    assert lm._layer.called_target is None
    assert calls
