from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from engine.input import InputManager
from engine.input_controller import InputController

pytestmark = [pytest.mark.fast]


class _Backend:
    def __init__(self) -> None:
        self.calls: list[tuple[float, float]] = []

    def rumble(self, intensity: float, duration_s: float) -> None:
        self.calls.append((float(intensity), float(duration_s)))


@dataclass
class _Config:
    input_bindings: dict[str, list[str]] | None = None
    input: dict[str, object] = field(default_factory=dict)


@dataclass
class _Window:
    engine_config: _Config


def test_rumble_env_override_takes_precedence_over_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = InputManager()
    backend = _Backend()
    manager.set_rumble_backend(backend)
    manager.set_rumble_config(enabled=False, strength=1.0)

    monkeypatch.setenv("MESH_RUMBLE", "1")
    manager.rumble(0.7, 0.08)
    assert backend.calls == [(0.7, 0.08)]

    backend.calls.clear()
    manager.set_rumble_config(enabled=True, strength=1.0)
    monkeypatch.setenv("MESH_RUMBLE", "0")
    manager.rumble(0.7, 0.08)
    assert backend.calls == []


def test_rumble_uses_config_and_strength_scaling_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MESH_RUMBLE", raising=False)
    manager = InputManager()
    backend = _Backend()
    manager.set_rumble_backend(backend)
    manager.set_rumble_config(enabled=True, strength=0.5)

    manager.rumble(0.8, 0.1)
    assert backend.calls == [(0.4, 0.1)]


def test_rumble_strength_clamps_to_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MESH_RUMBLE", raising=False)
    manager = InputManager()
    backend = _Backend()
    manager.set_rumble_backend(backend)

    manager.set_rumble_config(enabled=True, strength=5.0)
    manager.rumble(2.0, 0.1)
    assert backend.calls == [(1.0, 0.1)]

    backend.calls.clear()
    manager.set_rumble_config(enabled=True, strength=-3.0)
    manager.rumble(0.9, 0.1)
    assert backend.calls == []


def test_input_controller_applies_persisted_rumble_config_on_init(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MESH_RUMBLE", raising=False)
    window = _Window(
        engine_config=_Config(
            input={"rumble_enabled": True, "rumble_strength": 0.25},
        )
    )
    controller = InputController(window)
    backend = _Backend()
    controller.manager.set_rumble_backend(backend)
    controller.manager.rumble(1.0, 0.2)
    assert backend.calls == [(0.25, 0.2)]


def test_rumble_config_missing_backend_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MESH_RUMBLE", raising=False)
    manager = InputManager()
    manager.set_rumble_config(enabled=True, strength=1.0)
    manager.set_rumble_backend(None)
    manager.rumble(0.8, 0.1)
