from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import engine.optional_arcade as optional_arcade
from engine.behaviours.health import Health
from engine.behaviours.projectile import Projectile
from engine.behaviours.shooter import Shooter
from engine.events import MeshEventBus


class _MockEntity(optional_arcade.arcade.Sprite):
    def __init__(self, name: str, *, tag: str = "", x: float = 0.0, y: float = 0.0) -> None:
        super().__init__()
        self.mesh_name = name
        self.mesh_tag = tag
        self.mesh_behaviours_runtime = []
        self.center_x = float(x)
        self.center_y = float(y)
        self.x = float(x)
        self.y = float(y)


def _make_window() -> MagicMock:
    window = MagicMock()
    window.event_bus = MeshEventBus()
    window.engine_config = MagicMock()
    window.engine_config.player_stats_enabled = False
    window.scene_controller = MagicMock()
    window.scene_controller.all_sprites = []
    window.audio = MagicMock()
    window.particle_manager = MagicMock()
    return window


def test_shooter_emits_projectile_and_attack_events() -> None:
    window = _make_window()
    owner = _MockEntity("Sentry", tag="enemy")
    owner.center_x = 10.0
    owner.center_y = 20.0

    window.scene_controller._create_sprite.return_value = _MockEntity("Projectile")

    shooter = Shooter(owner, window, projectile_speed=250.0, cooldown=0.5, target_tag="player")
    assert shooter.shoot_at(100.0, 75.0) is True

    names = window.event_bus.get_recent_event_names(10)
    assert "projectile_fired" in names
    assert "combat_attack" in names

    events = window.event_bus.get_recent_events(10)
    projectile_event = next(item for item in events if item["name"] == "projectile_fired")
    assert projectile_event["payload"]["source"] == "Sentry"
    assert projectile_event["payload"]["speed"] == pytest.approx(250.0)


def _run_projectile_hit_once() -> tuple[float, list[str]]:
    window = _make_window()
    target = _MockEntity("Hero", tag="player", x=0.0, y=0.0)
    target.mesh_behaviours_runtime = [Health(target, window, max_hp=7.0, hp=7.0)]

    projectile_entity = _MockEntity("Arrow", tag="projectile", x=0.0, y=0.0)
    projectile = Projectile(
        projectile_entity,
        window,
        speed=0.0,
        damage=2.0,
        target_tag="player",
        lifetime=1.0,
        direction=0.0,
    )

    window.scene_controller.all_sprites = [projectile_entity, target]
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            optional_arcade.arcade,
            "check_for_collision_with_list",
            lambda _sprite, _targets: [target],
        )
        projectile.update(0.1)

    health = target.mesh_behaviours_runtime[0]
    names = window.event_bus.get_recent_event_names(20)
    return float(health.hp), names


def test_projectile_hit_handling_is_deterministic() -> None:
    hp_a, events_a = _run_projectile_hit_once()
    hp_b, events_b = _run_projectile_hit_once()

    assert hp_a == hp_b == 5.0
    assert events_a == events_b
    assert "projectile_hit" in events_a
    assert "combat_damage" in events_a
