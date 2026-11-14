from __future__ import annotations

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def test_the_legacy_overlay_path_is_still_selectable(monkeypatch) -> None:
    import arcade

    import engine.lighting as lighting
    import engine.lighting.shadows as shadows
    import engine.optional_arcade

    calls: list[int] = []

    def _draw_polygon_filled(points, _color):  # noqa: ANN001
        calls.append(len(points))

    # The pre-Milestone-12 overlay, kept selectable for comparison: these tests pin that code path.
    monkeypatch.setenv("MESH_SHADOWS_RENDERER", "legacy")
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


def test_hard_shadows_without_a_gpu_light_the_room_and_paint_no_black(monkeypatch) -> None:
    """Milestone 12: when the per-light renderer can't run (here: no GL context at all), the room is drawn
    lit by its LightLayer as with shadows off, the stats say why, and no shadow polygon is painted over it."""
    import arcade

    import engine.lighting as lighting
    import engine.optional_arcade

    monkeypatch.delenv("MESH_SHADOWS_RENDERER", raising=False)
    calls: list[int] = []

    def _draw_polygon_filled(points, _color):  # noqa: ANN001
        calls.append(len(points))

    monkeypatch.setattr(arcade, "draw_polygon_filled", _draw_polygon_filled, raising=False)
    monkeypatch.setattr(engine.optional_arcade.arcade, "draw_polygon_filled", _draw_polygon_filled, raising=False)

    class _Layer:
        def __init__(self) -> None:
            self.draws = 0
            self.diffuse_texture = object()

        def draw(self, *args, **kwargs):  # noqa: ANN002, ANN003, ARG002
            self.draws += 1

        def __iter__(self):
            return iter([])

    class _Camera:
        position = (0.0, 0.0)

        def use(self) -> None:
            return

    class _Window:  # no ctx: no GL context
        width = 320
        height = 200
        camera = _Camera()

    monkeypatch.setattr(lighting, "_LightLayer", None, raising=True)
    monkeypatch.setattr(lighting, "_Light", None, raising=True)
    lm = lighting.LightManager(_Window(), enabled=False)
    lm.enabled = True
    lm.available = True
    lm._layer = _Layer()
    lm.shadows_mode = "hard"
    lm._static_occluders = [{"id": "wall", "x": 0, "y": 0, "width": 32, "height": 32}]

    lm.end()
    assert lm._layer.draws == 1, "the room is drawn lit, without shadows"
    assert not calls, "no black shadow polygons over the scene"
    assert lm._last_lighting_stats.get("shadows_unavailable"), lm._last_lighting_stats
