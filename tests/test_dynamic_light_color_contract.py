from __future__ import annotations

from typing import Any

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

    def _create_light(self, x: float, y: float, radius: float, color: Any, mode: str) -> _StubLight:
        return _StubLight(radius, color)

    manager._create_light = _create_light.__get__(manager, lighting.LightManager)
    manager._add_light = (lambda self, light: None).__get__(manager, lighting.LightManager)
    monkeypatch.setattr(lighting, "_Light", object())
    monkeypatch.setattr(lighting, "_LightLayer", object())
    return manager


def test_dynamic_light_color_rgba_overrides(monkeypatch) -> None:
    manager = _make_manager(monkeypatch)
    handle = lighting.LightManager.register_dynamic_light(
        manager,
        owner=object(),
        radius=42.0,
        color="#ffffff",
        color_rgba=(10, 20, 30, 40),
    )
    assert handle is not None
    assert handle.light.color == (10, 20, 30, 40)


def test_dynamic_light_color_default_white(monkeypatch) -> None:
    manager = _make_manager(monkeypatch)
    handle = lighting.LightManager.register_dynamic_light(
        manager,
        owner=object(),
        radius=12.0,
        color=None,
        color_rgba=None,
    )
    assert handle is not None
    assert handle.light.color == (255, 255, 255, 255)
