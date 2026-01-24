from __future__ import annotations

from engine.lighting import LightManager
from engine.lighting.occluders import Rect
from engine.lighting.shadows import build_shadow_polygons, cull_occluders_for_light


def test_hard_shadows_selects_dynamic_light_when_present() -> None:
    manager = object.__new__(LightManager)
    manager.window = object()
    manager._dynamic_handles = [type("H", (), {"owner": object(), "light": type("L", (), {"x": 100.0, "y": 200.0, "radius": 300.0})()})()]
    manager._static_lights = []
    manager._static_configs = []
    manager.debug_geometry_enabled = False
    manager.shadowcast_debug_enabled = False

    selected = LightManager._select_shadow_light(manager)
    assert selected is not None
    kind, (lx, ly), radius, _light = selected
    assert kind == "dynamic"
    assert (lx, ly, radius) == (100.0, 200.0, 300.0)

    rects = [Rect(x=120.0, y=180.0, width=40.0, height=40.0)]
    culled = cull_occluders_for_light(lx, ly, radius, rects)
    polys = build_shadow_polygons((lx, ly), radius, culled)
    assert len(polys) > 0


def test_hard_shadows_falls_back_to_static_light() -> None:
    manager = object.__new__(LightManager)
    manager.window = object()
    manager._dynamic_handles = []
    manager._static_lights = []
    manager._static_configs = [{"enabled": True, "x": 10.0, "y": 20.0, "radius": 200.0}]
    manager.debug_geometry_enabled = False
    manager.shadowcast_debug_enabled = False

    selected = LightManager._select_shadow_light(manager)
    assert selected is not None
    kind, (lx, ly), radius, _light = selected
    assert kind == "static"
    assert (lx, ly, radius) == (10.0, 20.0, 200.0)


def test_hard_shadows_extracts_vec2_like_position_objects() -> None:
    class _Vec2Like:
        def __init__(self, x: float, y: float) -> None:
            self.x = x
            self.y = y

        def __iter__(self):
            yield self.x
            yield self.y

    class _Light:
        def __init__(self) -> None:
            self.position = _Vec2Like(12.5, 33.25)
            self.radius = 99.0

    manager = object.__new__(LightManager)
    posrad = LightManager._extract_light_pos_radius(manager, _Light())
    assert posrad == (12.5, 33.25, 99.0)
