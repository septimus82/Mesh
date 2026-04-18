from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, Iterator

import engine.optional_arcade

from engine.camera_controller import CameraArea
from engine.event_runtime.emit import emit_event as emit_event_normalized
from engine.events import MeshEvent
from engine.game_runtime import events as game_events
from engine.game_state_controller import GameState
from engine.logging_tools import get_logger
from engine.ui import maybe_trigger_demo_complete_endcap

from ._shared import resolve_persistence_service as _resolve_persistence_service
from ._shared import resolve_replay_service as _resolve_replay_service

if TYPE_CHECKING:
    from engine.game import GameWindow


logger = get_logger(__name__)


def _log_swallow(tag: str, context: str, *, once: bool = False) -> None:
    from engine.game import _log_swallow as game_log_swallow  # noqa: PLC0415

    game_log_swallow(tag, context, once=once)


# --- Persistence & reload ---
def should_collide(
    self: "GameWindow",
    sprite_a: engine.optional_arcade.arcade.Sprite,
    sprite_b: engine.optional_arcade.arcade.Sprite,
) -> bool:
    return self.scene_controller.should_collide(sprite_a, sprite_b)


def load_scene(self: "GameWindow", scene_path: str) -> Dict[str, Any]:
    return _resolve_persistence_service(self).load_scene(self, scene_path)


def request_scene_reload(self: "GameWindow", clear_assets: bool = False) -> None:
    _resolve_persistence_service(self).request_scene_reload(self, clear_assets=clear_assets)


def request_reload_current_scene(self: "GameWindow", clear_assets: bool = False) -> None:
    _resolve_persistence_service(self).request_reload_current_scene(self, clear_assets=clear_assets)


def request_scene_change(self: "GameWindow", scene_path: str) -> None:
    _resolve_persistence_service(self).request_scene_change(self, scene_path)


def queue_scene_change(self: "GameWindow", scene_path: str, *, spawn_id: str | None = None) -> None:
    _resolve_persistence_service(self).queue_scene_change(self, scene_path, spawn_id=spawn_id)


def mark_scene_dirty(self: "GameWindow", reason: str) -> None:
    _resolve_persistence_service(self).mark_scene_dirty(self, reason)


def record_recent_scene(self: "GameWindow", scene_path: str) -> None:
    _resolve_persistence_service(self).record_recent_scene(self, scene_path)


def get_recent_scenes(self: "GameWindow") -> list[str]:
    return _resolve_persistence_service(self).get_recent_scenes(self)


def clear_scene_dirty(self: "GameWindow") -> None:
    _resolve_persistence_service(self).clear_scene_dirty(self)


def set_hot_reload_error(self: "GameWindow", message: str, scene_path: str | None = None) -> None:
    self.hot_reload_error_message = str(message or "").strip()
    self.hot_reload_error_scene_path = str(scene_path or "").strip()
    self.hot_reload_error_visible = bool(self.hot_reload_error_message)


def clear_hot_reload_error(self: "GameWindow") -> None:
    self.hot_reload_error_message = ""
    self.hot_reload_error_scene_path = ""
    self.hot_reload_error_visible = False


def _undo_enabled(self: "GameWindow") -> bool:
    return _resolve_persistence_service(self).undo_enabled(self)


def _snapshot_current_authored_scene_payload(self: "GameWindow") -> Any:
    return _resolve_persistence_service(self).snapshot_current_authored_scene_payload(self)


def push_undo_frame(self: "GameWindow", reason: str) -> bool:
    return _resolve_persistence_service(self).push_undo_frame(self, reason)


def undo(self: "GameWindow") -> bool:
    return _resolve_persistence_service(self).undo(self)


def redo(self: "GameWindow") -> bool:
    return _resolve_persistence_service(self).redo(self)


def reload_scene_from_disk(self: "GameWindow") -> bool:
    return _resolve_persistence_service(self).reload_scene_from_disk(self)


def persist_scene_to_disk(self: "GameWindow") -> Any:
    return _resolve_persistence_service(self).persist_scene_to_disk(self)


def save_scene_as(self: "GameWindow", new_scene_path: str) -> Any:
    return _resolve_persistence_service(self).save_scene_as(self, new_scene_path)


def reload_scene(self: "GameWindow", new_path: str | None = None) -> bool:
    return _resolve_persistence_service(self).reload_scene(self, new_path)


def reload_current_scene(self: "GameWindow") -> None:
    _resolve_persistence_service(self).reload_current_scene(self)


def warp_to_scene(self: "GameWindow", scene_path: str) -> None:
    _resolve_persistence_service(self).warp_to_scene(self, scene_path)


def track_scene_subscription(self: "GameWindow", unsubscribe: Callable[[], None]) -> None:
    self.scene_controller.track_scene_subscription(unsubscribe)


# --- Event bus ---
def emit_event(self: "GameWindow", event: MeshEvent) -> None:
    self._mesh_event_queue.append(event)
    event_bus = getattr(self, "event_bus", None)
    if event_bus is not None:
        try:
            event_bus.emit_event(event)
        except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation - event bus should not break runtime
            _log_swallow("GAME-006", "engine/game.py blanket swallow", once=True)
            logger.error("[Mesh][EventBus] ERROR forwarding event '%s': %s", event.type, exc)


def emit_signal(self: "GameWindow", event_type: str, **payload: Any) -> None:
    emit_event_normalized(self, str(event_type), dict(payload))


def consume_events(self: "GameWindow") -> list[MeshEvent]:
    events = self._mesh_event_queue
    self._mesh_event_queue = []
    return events


def _debug_print_events(self: "GameWindow", events: list[MeshEvent]) -> None:
    if not events or not self.show_debug:
        return
    for event in events:
        payload = event.payload or {}
        payload_preview = (
            payload.get("name")
            or payload.get("collectible")
            or payload.get("collectible_name")
            or payload.get("label")
            or payload
        )
        logger.info("[Mesh][Event] %s %s", event.type, payload_preview)


def _on_entity_died(self: "GameWindow", event: MeshEvent) -> None:
    game_events.on_entity_died(self, event)


def _on_any_event_boss_reward_clarity(self: "GameWindow", event: MeshEvent) -> None:
    game_events.on_any_event_boss_reward_clarity(self, event)


def _on_damage_event(self: "GameWindow", event: MeshEvent) -> None:
    game_events.on_damage_event(self, event)


def _on_collectible_event(self: "GameWindow", event: MeshEvent) -> None:
    game_events.on_collectible_event(self, event)


def _on_level_up(self: "GameWindow", event: MeshEvent) -> None:
    game_events.on_level_up(self, event)


def _on_any_event(self: "GameWindow", event: MeshEvent) -> None:
    game_events.on_any_event(self, event)


# --- Game state (flags, counters, vars, chapter, quest, playtime) ---
def _get_game_state(self: "GameWindow") -> GameState:
    return self.game_state_controller.state


def _set_game_state(self: "GameWindow", value: GameState) -> None:
    self.game_state_controller.state = value


def set_flag(self: "GameWindow", name: str, value: bool = True) -> None:
    key = str(name)
    previous = self.game_state_controller.get_flag(key, False)
    self.game_state_controller.set_flag(key, bool(value))
    if key == "demo.reached_cellar":
        current = self.game_state_controller.get_flag(key, False)
        maybe_trigger_demo_complete_endcap(self, previous=previous, current=current)


def get_flag(self: "GameWindow", name: str, default: bool = False) -> bool:
    return self.game_state_controller.get_flag(name, default)


def toggle_flag(self: "GameWindow", name: str) -> bool:
    return self.game_state_controller.toggle_flag(name)


def inc_counter(self: "GameWindow", name: str, amount: float = 1.0) -> float:
    return self.game_state_controller.inc_counter(name, amount)


def get_counter(self: "GameWindow", name: str, default: float = 0.0) -> float:
    return self.game_state_controller.get_counter(name, default)


def set_counter(self: "GameWindow", name: str, value: float = 0.0) -> float:
    return self.game_state_controller.set_counter(name, value)


def add_counter(self: "GameWindow", name: str, delta: float = 1.0) -> float:
    return self.game_state_controller.add_counter(name, delta)


def set_var(self: "GameWindow", name: str, value: Any) -> None:
    self.game_state_controller.set_var(name, value)


def get_var(self: "GameWindow", name: str, default: Any = None) -> Any:
    return self.game_state_controller.get_var(name, default)


def set_chapter(self: "GameWindow", chapter: int) -> None:
    self.game_state_controller.set_chapter(chapter)


def get_chapter(self: "GameWindow") -> int:
    return self.game_state_controller.get_chapter()


def set_main_quest(self: "GameWindow", quest_id: str | None) -> None:
    self.game_state_controller.set_main_quest(quest_id)


def get_main_quest(self: "GameWindow") -> str | None:
    return self.game_state_controller.get_main_quest()


def get_playtime_seconds(self: "GameWindow") -> float:
    return self.game_state_controller.get_playtime_seconds()


def set_next_spawn_point(self: "GameWindow", spawn_id: str | None) -> None:
    self.game_state_controller.set_next_spawn_point(spawn_id)


def get_next_spawn_point(self: "GameWindow") -> str | None:
    return self.game_state_controller.get_next_spawn_point()


def _consume_next_spawn_point(self: "GameWindow") -> str | None:
    return self.game_state_controller.consume_next_spawn_point()


# --- Camera & scene convenience ---
def _get_all_sprites(self: "GameWindow") -> Iterator[engine.optional_arcade.arcade.Sprite]:
    return self.scene_controller.all_sprites


def find_entity(self: "GameWindow", identifier: str | int) -> engine.optional_arcade.arcade.Sprite | None:
    return self.scene_controller.find_entity(identifier)


def get_all_entities(self: "GameWindow") -> list[engine.optional_arcade.arcade.Sprite]:
    return self.scene_controller.get_all_entities()


def find_sprite_by_name(self: "GameWindow", name: str | None) -> engine.optional_arcade.arcade.Sprite | None:
    return self.scene_controller.find_sprite_by_name(name)


def get_sprites_in_layer(
    self: "GameWindow", layer_name: str
) -> engine.optional_arcade.arcade.SpriteList | None:
    return self.scene_controller.get_sprites_in_layer(layer_name)


def get_camera_center(self: "GameWindow") -> tuple[float, float]:
    return self.camera_controller.get_camera_center()


def build_scene_snapshot(self: "GameWindow", compact: bool = False) -> Dict[str, Any]:
    return _resolve_replay_service(self).build_scene_snapshot(self, compact=compact)


def clamp_camera_to_world(
    self: "GameWindow",
    target_x: float,
    target_y: float,
    *,
    padding: float = 0.0,
) -> tuple[float, float]:
    return self.camera_controller.clamp_camera_to_world(target_x, target_y, padding=padding)


def clamp_camera_to_rect(
    self: "GameWindow",
    target_x: float,
    target_y: float,
    rect: tuple[float, float, float, float],
    *,
    padding: float = 0.0,
) -> tuple[float, float]:
    return self.camera_controller.clamp_camera_to_rect(target_x, target_y, rect, padding=padding)


def screen_to_world(self: "GameWindow", x: float, y: float) -> tuple[float, float]:
    return self.camera_controller.screen_to_world(x, y)


def get_camera_area_for_point(self: "GameWindow", x: float, y: float) -> CameraArea | None:
    return self.camera_controller.get_camera_area_for_point(x, y)


def update_camera_follow(
    self: "GameWindow",
    *,
    target_x: float,
    target_y: float,
    dt: float,
    lerp_factor: float | None = None,
    follow_strength: float | None = None,
    deadzone_px: float | None = None,
    deadzone_w: float | None = None,
    deadzone_h: float | None = None,
    max_speed: float | None = None,
    padding: float = 0.0,
    zoom: float | None = None,
    zoom_speed: float | None = None,
    min_zoom: float | None = None,
    max_zoom: float | None = None,
) -> None:
    self.camera_controller.update_camera_follow(
        target_x=target_x,
        target_y=target_y,
        dt=dt,
        lerp_factor=lerp_factor,
        follow_strength=follow_strength,
        deadzone_px=deadzone_px,
        deadzone_w=deadzone_w,
        deadzone_h=deadzone_h,
        max_speed=max_speed,
        padding=padding,
        zoom=zoom,
        zoom_speed=zoom_speed,
        min_zoom=min_zoom,
        max_zoom=max_zoom,
    )


def set_camera_zoom_target(self: "GameWindow", zoom: float, *, speed: float | None = None) -> None:
    self.camera_controller.set_zoom_target(zoom, speed=speed)


def start_camera_shake(
    self: "GameWindow",
    *,
    duration: float,
    amplitude: float,
    frequency: float = 18.0,
    falloff: float = 1.0,
) -> None:
    self.camera_controller.start_camera_shake(
        duration=duration,
        amplitude=amplitude,
        frequency=frequency,
        falloff=falloff,
    )


def add_camera_trauma(
    self: "GameWindow",
    amount: float,
    *,
    decay: float | None = None,
    max_offset: float | None = None,
    frequency: float | None = None,
    seed: int | None = None,
) -> None:
    self.camera_controller.add_camera_trauma(
        amount,
        decay=decay,
        max_offset=max_offset,
        frequency=frequency,
        seed=seed,
    )


def stop_camera_shake(self: "GameWindow") -> None:
    self.camera_controller.stop_camera_shake()


def on_collectible_picked(
    self: "GameWindow",
    collectible: engine.optional_arcade.arcade.Sprite,
    collector: engine.optional_arcade.arcade.Sprite,
) -> None:
    self.scene_controller.on_collectible_picked(collectible, collector)


def on_damage(
    self: "GameWindow",
    source: engine.optional_arcade.arcade.Sprite,
    target: engine.optional_arcade.arcade.Sprite,
    amount: float,
) -> None:
    self.scene_controller.on_damage(source, target, amount)


def move_entity_with_collision(
    self: "GameWindow",
    sprite: engine.optional_arcade.arcade.Sprite,
    dx: float,
    dy: float,
    friction: float = 1.0,
) -> None:
    self.scene_controller.move_entity_with_collision(sprite, dx, dy, friction)


def _get_camera(self: "GameWindow") -> Any:
    return self.camera_controller.camera


def bind_state_facade_methods(cls: type["GameWindow"]) -> None:
    cls.should_collide = should_collide
    cls.load_scene = load_scene
    cls.request_scene_reload = request_scene_reload
    cls.request_reload_current_scene = request_reload_current_scene
    cls.request_scene_change = request_scene_change
    cls.queue_scene_change = queue_scene_change
    cls.mark_scene_dirty = mark_scene_dirty
    cls.record_recent_scene = record_recent_scene
    cls.get_recent_scenes = get_recent_scenes
    cls.clear_scene_dirty = clear_scene_dirty
    cls.set_hot_reload_error = set_hot_reload_error
    cls.clear_hot_reload_error = clear_hot_reload_error
    cls._undo_enabled = _undo_enabled
    cls._snapshot_current_authored_scene_payload = _snapshot_current_authored_scene_payload
    cls.push_undo_frame = push_undo_frame
    cls.undo = undo
    cls.redo = redo
    cls.reload_scene_from_disk = reload_scene_from_disk
    cls.persist_scene_to_disk = persist_scene_to_disk
    cls.save_scene_as = save_scene_as
    cls.reload_scene = reload_scene
    cls.reload_current_scene = reload_current_scene
    cls.warp_to_scene = warp_to_scene
    cls.track_scene_subscription = track_scene_subscription

    cls.emit_event = emit_event
    cls.emit_signal = emit_signal
    cls.consume_events = consume_events
    cls._debug_print_events = _debug_print_events
    cls._on_entity_died = _on_entity_died
    cls._on_any_event_boss_reward_clarity = _on_any_event_boss_reward_clarity
    cls._on_damage_event = _on_damage_event
    cls._on_collectible_event = _on_collectible_event
    cls._on_level_up = _on_level_up
    cls._on_any_event = _on_any_event

    setattr(cls, "game_state", property(_get_game_state, _set_game_state))
    cls.set_flag = set_flag
    cls.get_flag = get_flag
    cls.toggle_flag = toggle_flag
    cls.inc_counter = inc_counter
    cls.get_counter = get_counter
    cls.set_counter = set_counter
    cls.add_counter = add_counter
    cls.set_var = set_var
    cls.get_var = get_var
    cls.set_chapter = set_chapter
    cls.get_chapter = get_chapter
    cls.set_main_quest = set_main_quest
    cls.get_main_quest = get_main_quest
    cls.get_playtime_seconds = get_playtime_seconds
    cls.set_next_spawn_point = set_next_spawn_point
    cls.get_next_spawn_point = get_next_spawn_point
    cls._consume_next_spawn_point = _consume_next_spawn_point

    setattr(cls, "all_sprites", property(_get_all_sprites))
    cls.find_entity = find_entity
    cls.get_all_entities = get_all_entities
    cls.find_sprite_by_name = find_sprite_by_name
    cls.get_sprites_in_layer = get_sprites_in_layer
    cls.get_camera_center = get_camera_center
    cls.build_scene_snapshot = build_scene_snapshot
    cls.clamp_camera_to_world = clamp_camera_to_world
    cls.clamp_camera_to_rect = clamp_camera_to_rect
    cls.screen_to_world = screen_to_world
    cls.get_camera_area_for_point = get_camera_area_for_point
    cls.update_camera_follow = update_camera_follow
    cls.set_camera_zoom_target = set_camera_zoom_target
    cls.start_camera_shake = start_camera_shake
    cls.add_camera_trauma = add_camera_trauma
    cls.stop_camera_shake = stop_camera_shake
    cls.on_collectible_picked = on_collectible_picked
    cls.on_damage = on_damage
    cls.move_entity_with_collision = move_entity_with_collision
    setattr(cls, "camera", property(_get_camera))
