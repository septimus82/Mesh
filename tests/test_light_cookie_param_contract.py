from __future__ import annotations

from engine.lighting import DynamicLightHandle, LightManager


class _StubLight:
    def __init__(self, position: tuple[float, float], radius: float) -> None:
        self.position = position
        self.radius = radius


def _make_manager() -> LightManager:
    manager = object.__new__(LightManager)
    manager._static_configs = []
    manager._dynamic_handles = []
    return manager


def test_light_cookie_params_static_and_dynamic() -> None:
    manager = _make_manager()
    manager._static_configs = [
        {
            "x": 10.0,
            "y": 20.0,
            "radius": 30.0,
            "cookie_id": "packs/core/fx/cookie.png",
            "cookie_scale": 1.5,
            "cookie_rotation_deg": 45.0,
            "cookie_offset_px": (2.0, -3.0),
        }
    ]
    dyn_light = _StubLight((100.0, 50.0), 60.0)
    handle = DynamicLightHandle(
        owner=object(),
        light=dyn_light,
        base_radius=60.0,
        base_color=(255, 255, 255, 255),
        cookie_id="packs/core/fx/dyn_cookie.png",
        cookie_scale=0.75,
        cookie_rotation_deg=90.0,
        cookie_offset_px=(1.0, 2.0),
    )
    manager._dynamic_handles = [handle]
    specs = LightManager._collect_cookie_draw_specs(manager, offset=(0.0, 0.0))
    assert len(specs) == 2
    static_spec = specs[0]
    assert static_spec["cookie_id"] == "packs/core/fx/cookie.png"
    assert static_spec["center_x"] == 12.0
    assert static_spec["center_y"] == 17.0
    assert static_spec["cookie_scale"] == 1.5
    assert static_spec["cookie_rotation_deg"] == 45.0
    dynamic_spec = specs[1]
    assert dynamic_spec["cookie_id"] == "packs/core/fx/dyn_cookie.png"
    assert dynamic_spec["center_x"] == 101.0
    assert dynamic_spec["center_y"] == 52.0
    assert dynamic_spec["cookie_scale"] == 0.75
    assert dynamic_spec["cookie_rotation_deg"] == 90.0


def test_light_cookie_missing_defaults_to_no_specs() -> None:
    manager = _make_manager()
    manager._static_configs = [{"x": 0.0, "y": 0.0, "radius": 10.0}]
    manager._dynamic_handles = [
        DynamicLightHandle(
            owner=object(),
            light=_StubLight((0.0, 0.0), 10.0),
            base_radius=10.0,
            base_color=(255, 255, 255, 255),
        )
    ]
    specs = LightManager._collect_cookie_draw_specs(manager, offset=(0.0, 0.0))
    assert specs == []
