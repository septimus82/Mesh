from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import engine.optional_arcade as optional_arcade
from engine.behaviours.combat import Combat
from engine.behaviours.hitbox import Hitbox
from engine.behaviours.projectile import Projectile
from engine.input import InputManager

pytestmark = [pytest.mark.fast]


class _RumbleBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[float, float]] = []

    def rumble(self, intensity: float, duration_s: float) -> None:
        self.calls.append((float(intensity), float(duration_s)))


class _DamageReceiver:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def apply_damage(self, *args: object, **kwargs: object) -> None:
        self.calls.append((args, kwargs))


def _make_sprite(name: str, *, tag: str, x: float, y: float) -> optional_arcade.arcade.Sprite:
    sprite = optional_arcade.arcade.Sprite()
    sprite.mesh_name = name
    sprite.mesh_tag = tag
    sprite.center_x = float(x)
    sprite.center_y = float(y)
    sprite.mesh_behaviours_runtime = []
    return sprite


def _manager_with_backend(monkeypatch: pytest.MonkeyPatch, enabled: bool) -> tuple[InputManager, _RumbleBackend]:
    monkeypatch.setenv("MESH_RUMBLE", "1" if enabled else "0")
    manager = InputManager()
    backend = _RumbleBackend()
    manager.set_rumble_backend(backend)
    return manager, backend


def test_input_manager_rumble_enabled_and_disabled_gating(monkeypatch: pytest.MonkeyPatch) -> None:
    manager_enabled, backend_enabled = _manager_with_backend(monkeypatch, enabled=True)
    manager_enabled.rumble(0.75, 0.05)
    assert backend_enabled.calls == [(0.75, 0.05)]

    manager_disabled, backend_disabled = _manager_with_backend(monkeypatch, enabled=False)
    manager_disabled.rumble(0.75, 0.05)
    assert backend_disabled.calls == []


def test_input_manager_rumble_no_backend_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESH_RUMBLE", "1")
    manager = InputManager()
    manager.set_rumble_backend(None)
    manager.rumble(0.8, 0.1)


def test_world_impact_events_trigger_expected_rumble_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, backend = _manager_with_backend(monkeypatch, enabled=True)
    input_controller = SimpleNamespace(manager=manager)

    projectile_window = SimpleNamespace(
        input_controller=input_controller,
        audio=MagicMock(),
        particle_manager=MagicMock(),
    )
    projectile_entity = _make_sprite("Arrow", tag="projectile", x=0.0, y=0.0)
    projectile = Projectile(
        projectile_entity,
        projectile_window,
        speed=0.0,
        damage=2.0,
        target_tag="player",
        lifetime=1.0,
        direction=0.0,
    )
    projectile_target = _make_sprite("Hero", tag="player", x=10.0, y=20.0)
    projectile_target.mesh_behaviours_runtime = [_DamageReceiver()]
    projectile._apply_damage(projectile_target)
    assert backend.calls[-1] == pytest.approx((0.7, 0.08))

    hitbox_window = SimpleNamespace(
        input_controller=input_controller,
        audio=MagicMock(),
    )
    hitbox_entity = _make_sprite("Slash", tag="player", x=0.0, y=0.0)
    hitbox = Hitbox(hitbox_entity, hitbox_window, damage=2.0, target_tag="enemy", duration=1.0)
    hitbox_target = _make_sprite("Enemy", tag="enemy", x=7.0, y=-3.0)
    hitbox_target.mesh_behaviours_runtime = [_DamageReceiver()]
    hitbox._apply_damage(hitbox_target)
    assert backend.calls[-1] == pytest.approx((0.5, 0.06))

    combat_window = SimpleNamespace(
        input_controller=input_controller,
        audio=MagicMock(),
        scene_controller=SimpleNamespace(_create_sprite=lambda _payload: None),
        engine_config=SimpleNamespace(player_stats_enabled=False),
    )
    attacker = _make_sprite("Player", tag="player", x=3.0, y=4.0)
    combat = Combat(attacker, combat_window, cooldown=0.0, attack_sound="assets/sounds/attack.wav")
    monkeypatch.setattr(combat, "_spawn_hitbox", lambda: None)
    assert combat.attack() is True
    assert backend.calls[-1] == pytest.approx((0.2, 0.03))


def test_world_impact_events_do_not_rumble_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, backend = _manager_with_backend(monkeypatch, enabled=False)
    input_controller = SimpleNamespace(manager=manager)
    window = SimpleNamespace(
        input_controller=input_controller,
        audio=MagicMock(),
        particle_manager=MagicMock(),
    )
    projectile_entity = _make_sprite("Arrow", tag="projectile", x=0.0, y=0.0)
    projectile = Projectile(
        projectile_entity,
        window,
        speed=0.0,
        damage=2.0,
        target_tag="player",
        lifetime=1.0,
        direction=0.0,
    )
    target = _make_sprite("Hero", tag="player", x=10.0, y=20.0)
    target.mesh_behaviours_runtime = [_DamageReceiver()]
    projectile._apply_damage(target)
    assert backend.calls == []
