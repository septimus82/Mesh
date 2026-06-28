from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from engine.behaviours.emit_event_on_event import EmitEventOnEvent
from engine.behaviours.encounter_cleared import EncounterCleared
from engine.behaviours.health import Health
from engine.behaviours.set_game_state_on_event import SetGameStateOnEvent
from engine.events import MeshEvent, MeshEventBus
from engine.game_runtime import events as game_events
from engine.game_state_controller import GameStateController

pytestmark = pytest.mark.fast


class _SceneController:
    def __init__(self) -> None:
        self.all_sprites: list[_Sprite] = []
        self.current_scene_path = "scenes/game1a_combat_room.json"


class _Sprite:
    def __init__(self, name: str, tag: str, scene: _SceneController) -> None:
        self.mesh_id = name
        self.mesh_name = name
        self.mesh_tag = tag
        self.mesh_entity_data: dict[str, Any] = {}
        self.mesh_behaviours_runtime: list[Any] = []
        self.center_x = 0.0
        self.center_y = 0.0
        self.width = 32.0
        self.height = 32.0
        self._scene = scene

    def remove_from_sprite_lists(self) -> None:
        if self in self._scene.all_sprites:
            self._scene.all_sprites.remove(self)


class _Window:
    def __init__(self) -> None:
        self.scene_controller = _SceneController()
        self.event_bus = MeshEventBus()
        self._events: list[MeshEvent] = []
        self.event_bus.subscribe_all(self._events.append)
        self.engine_config = SimpleNamespace(player_stats_enabled=False)
        self.game_state_controller = GameStateController(self)
        self.game_state = self.game_state_controller.state
        self.player_hud = SimpleNamespace(enqueue_toast=lambda *_args, **_kwargs: None)
        self.particle_manager = SimpleNamespace(emit_death_effect=lambda *_args, **_kwargs: None)
        self.game_over = False
        self.game_over_screen = SimpleNamespace(visible=False)
        self.paused = False
        self.console_lines: list[str] = []

    def console_log(self, message: str) -> None:
        self.console_lines.append(str(message))

    def emit_signal(self, event_type: str, **payload: Any) -> None:
        self.event_bus.emit(event_type, **payload)

    def set_flag(self, name: str, value: bool = True) -> None:
        self.game_state_controller.set_flag(name, value)

    def get_flag(self, name: str, default: bool = False) -> bool:
        return self.game_state_controller.get_flag(name, default)

    def inc_counter(self, name: str, amount: float = 1.0) -> float:
        return self.game_state_controller.inc_counter(name, amount)


def _make_enemy(window: _Window, name: str, *, hp: float = 5.0) -> tuple[_Sprite, Health]:
    enemy = _Sprite(name, "enemy", window.scene_controller)
    health = Health(enemy, window, max_hp=hp, hp=hp)
    enemy.mesh_behaviours_runtime.append(health)
    window.scene_controller.all_sprites.append(enemy)
    return enemy, health


def _make_player(window: _Window, *, hp: float = 5.0) -> tuple[_Sprite, Health]:
    player = _Sprite("Player", "player", window.scene_controller)
    health = Health(player, window, max_hp=hp, hp=hp)
    player.mesh_behaviours_runtime.append(health)
    window.scene_controller.all_sprites.append(player)
    return player, health


def _make_controller(window: _Window) -> tuple[_Sprite, EncounterCleared]:
    controller = _Sprite("EncounterController", "controller", window.scene_controller)
    watcher = EncounterCleared(controller, window)
    controller.mesh_behaviours_runtime.append(watcher)
    window.scene_controller.all_sprites.append(controller)
    return controller, watcher


def _deliver_events(window: _Window, *behaviours: Any) -> list[MeshEvent]:
    delivered: list[MeshEvent] = []
    while window._events:
        event = window._events.pop(0)
        delivered.append(event)
        for behaviour in behaviours:
            interest_getter = getattr(behaviour, "subscribed_event_types", None)
            interest = interest_getter() if callable(interest_getter) else None
            if interest is not None and event.type not in interest:
                continue
            on_event = getattr(behaviour, "on_event", None)
            if callable(on_event):
                on_event(event)
    return delivered


def test_encounter_cleared_fires_once_when_last_enemy_dies() -> None:
    window = _Window()
    _make_enemy(window, "enemy_a")
    _enemy_b, health_b = _make_enemy(window, "enemy_b")
    _controller, watcher = _make_controller(window)
    watcher.update(0.0)

    health_b.apply_damage(10)
    delivered = _deliver_events(window, watcher)

    assert "encounter_cleared" not in [event.type for event in delivered]
    assert window.event_bus.get_recent_event_names(20).count("encounter_cleared") == 0

    enemy_a_health = next(
        behaviour
        for sprite in window.scene_controller.all_sprites
        if getattr(sprite, "mesh_name", "") == "enemy_a"
        for behaviour in sprite.mesh_behaviours_runtime
        if isinstance(behaviour, Health)
    )
    enemy_a_health.apply_damage(10)
    _deliver_events(window, watcher)

    assert window.event_bus.get_recent_event_names(40).count("encounter_cleared") == 1

    watcher.update(0.0)
    watcher.on_event(MeshEvent("died", {"actor": _enemy_b, "name": "enemy_b"}))

    assert window.event_bus.get_recent_event_names(60).count("encounter_cleared") == 1


def test_encounter_cleared_never_fires_when_scene_started_with_zero_enemies() -> None:
    window = _Window()
    _controller, watcher = _make_controller(window)

    watcher.update(0.0)
    watcher.update(0.0)
    watcher.on_event(MeshEvent("died", {"name": "not_enemy"}))

    assert "encounter_cleared" not in window.event_bus.get_recent_event_names(10)


def test_encounter_cleared_sets_victory_flag_and_emits_victory_event() -> None:
    window = _Window()
    _enemy, health = _make_enemy(window, "enemy")
    _controller, watcher = _make_controller(window)
    state_hook = SetGameStateOnEvent(
        _Sprite("VictoryFlagHook", "controller", window.scene_controller),
        window,
        event_type="encounter_cleared",
        set_flags={"game1a.victory": True},
        once=True,
    )
    victory_emitter = EmitEventOnEvent(
        _Sprite("VictoryEventHook", "controller", window.scene_controller),
        window,
        listen_event="encounter_cleared",
        emit_event="victory",
    )
    watcher.update(0.0)

    health.apply_damage(10)
    _deliver_events(window, watcher, state_hook, victory_emitter)

    assert window.get_flag("game1a.victory") is True
    assert "victory" in window.event_bus.get_recent_event_names(30)


def test_player_lethal_damage_uses_existing_game_over_path() -> None:
    window = _Window()
    player, health = _make_player(window, hp=5)
    window.event_bus.subscribe("died", lambda event: game_events.on_entity_died(window, event))

    health.apply_damage(10)

    assert health._dead is True
    assert player not in window.scene_controller.all_sprites
    assert window.game_over is True
    assert window.game_over_screen.visible is True
    assert window.paused is True
