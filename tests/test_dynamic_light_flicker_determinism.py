from __future__ import annotations

import engine.lighting as lighting


class _StubLight:
    def __init__(self, radius: float, color: tuple[int, int, int, int]) -> None:
        self.radius = radius
        self.color = color
        self.position = (0.0, 0.0)


def _make_manager(monkeypatch) -> lighting.LightManager:
    manager = object.__new__(lighting.LightManager)
    manager.enabled = True
    manager._layer = object()
    manager._max_dynamic_lights = None
    manager._dynamic_handles = []
    manager._flicker_lights = []
    manager._flicker_time = 0.0

    def _create_light(self, x: float, y: float, radius: float, color: tuple[int, int, int, int], mode: str) -> _StubLight:
        return _StubLight(radius, color)

    manager._create_light = _create_light.__get__(manager, lighting.LightManager)
    manager._add_light = (lambda self, light: None).__get__(manager, lighting.LightManager)
    monkeypatch.setattr(lighting, "_Light", object())
    monkeypatch.setattr(lighting, "_LightLayer", object())
    return manager


def test_dynamic_light_flicker_deterministic(monkeypatch) -> None:
    manager_a = _make_manager(monkeypatch)
    manager_b = _make_manager(monkeypatch)
    handle_a = lighting.LightManager.register_dynamic_light(
        manager_a,
        owner=object(),
        radius=100.0,
        color=(200, 200, 200, 255),
        flicker_enabled=True,
        flicker_seed=123,
        flicker_speed=2.5,
        flicker_amount=0.4,
    )
    handle_b = lighting.LightManager.register_dynamic_light(
        manager_b,
        owner=object(),
        radius=100.0,
        color=(200, 200, 200, 255),
        flicker_enabled=True,
        flicker_seed=123,
        flicker_speed=2.5,
        flicker_amount=0.4,
    )
    assert handle_a is not None and handle_b is not None
    manager_a.update(0.25)
    manager_b.update(0.25)
    assert handle_a.light.radius == handle_b.light.radius
    assert handle_a.light.color == handle_b.light.color


def test_dynamic_light_flicker_disabled_no_change(monkeypatch) -> None:
    manager = _make_manager(monkeypatch)
    handle = lighting.LightManager.register_dynamic_light(
        manager,
        owner=object(),
        radius=80.0,
        color=(50, 60, 70, 255),
        flicker_enabled=False,
    )
    assert handle is not None
    initial_radius = handle.light.radius
    initial_color = handle.light.color
    manager.update(0.5)
    assert handle.light.radius == initial_radius
    assert handle.light.color == initial_color
