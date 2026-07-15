"""Player controller behaviour that responds to WASD input."""

from __future__ import annotations

import math
from typing import Any

import engine.optional_arcade as optional_arcade
from engine.swallowed_exceptions import _log_swallow

from ..animation_state import request_animation_state
from ..player_actions import (
    PlayerActionState,
    build_player_input_snapshot,
    dispatch_attack_action,
    map_input_to_actions,
)
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "PlayerController",
    description="Handles WASD movement and interaction for the player sprite.",
    config_fields=[
        {
            "name": "speed",
            "description": "Movement speed in units per second (fixed at 150)",
            "type": "float",
            "default": 150.0,
        },
    ],
)
class PlayerController(Behaviour):
    """Moves the attached sprite based on InputManager actions."""

    INTERACT_RADIUS = 72.0

    PARAM_DEFS = {
        "speed": ParamDef(float, default=150.0, description="Movement speed in units per second"),
    }

    def __init__(self, entity: Any, window: Any, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self.speed = float(self.config.get("speed", 150.0))
        self._action_state = PlayerActionState()
        self._facing = "down"

    def update(self, dt: float) -> None:
        speed = self.speed
        input_manager = getattr(self.window, "input", None)

        if self._player_input_disabled():
            if input_manager is not None:
                _, self._action_state = map_input_to_actions(
                    build_player_input_snapshot(
                        input_manager,
                        move_x=0.0,
                        move_y=0.0,
                    ),
                    self._action_state,
                )
            self._sync_animation_state(0.0, 0.0)
            return

        decision = None
        if input_manager is not None:
            vx = input_manager.get_axis("move_left", "move_right")
            vy = input_manager.get_axis("move_down", "move_up")
            decision, self._action_state = map_input_to_actions(
                build_player_input_snapshot(
                    input_manager,
                    move_x=vx,
                    move_y=vy,
                ),
                self._action_state,
            )
            vx = decision.move_x
            vy = decision.move_y
        else:  # Fallback for legacy windows without an InputManager.
            keys = self.window.get_pressed_keys()
            vx = 0.0
            vy = 0.0

            if optional_arcade.arcade.key.W in keys:
                vy += 1.0
            if optional_arcade.arcade.key.S in keys:
                vy -= 1.0
            if optional_arcade.arcade.key.A in keys:
                vx -= 1.0
            if optional_arcade.arcade.key.D in keys:
                vx += 1.0

        if vx != 0.0 or vy != 0.0:
            length = (vx**2 + vy**2) ** 0.5
            vx = (vx / length) * speed
            vy = (vy / length) * speed
            self._update_facing_from_velocity(vx, vy)
        self._sync_animation_state(vx, vy)
        self.entity.mesh_velocity_x = vx
        self.entity.mesh_velocity_y = vy

        before_x = float(getattr(self.entity, "center_x", 0.0))
        before_y = float(getattr(self.entity, "center_y", 0.0))

        # Physics Facade V1: Use pure physics model if possible
        scene_controller = getattr(self.window, "scene_controller", None)
        solid_sprites = getattr(scene_controller, "solid_sprites", None)

        if solid_sprites is not None:
            from engine.physics_runtime import move_entity_with_physics
            move_entity_with_physics(self.entity, (vx * dt, vy * dt), solid_sprites)
        else:
            # Fallback for legacy / headless without scene
            self.window.move_entity_with_collision(self.entity, vx * dt, vy * dt)

        after_x = float(getattr(self.entity, "center_x", 0.0))
        after_y = float(getattr(self.entity, "center_y", 0.0))
        walked = math.hypot(after_x - before_x, after_y - before_y)
        if walked > 0.0:
            controller = getattr(self.window, "game_state_controller", None)
            recorder = getattr(controller, "record_overworld_walk_distance", None)
            if callable(recorder):
                recorder(walked)

        # Sensors V1
        if scene_controller and hasattr(scene_controller, "sensors_runtime"):
            from engine.physics_model import Aabb
            entity_data = getattr(self.entity, "mesh_entity_data", {})
            # Use instance ID as fallback if no data ID
            eid = str(entity_data.get("id", f"id_{id(self.entity)}"))

            aabb = Aabb(
                self.entity.center_x,
                self.entity.center_y,
                self.entity.width,
                self.entity.height
            )

            events = scene_controller.sensors_runtime.update_entity_sensors(
                scene_controller._loaded_scene_data,
                eid,
                aabb
            )

            if events:
                from engine.behaviour_event_router import dispatch_events
                from engine.behaviour_event_router_model import build_sensor_behaviour_events

                sensors = scene_controller.sensors_runtime.get_sensors(scene_controller._loaded_scene_data)
                b_events = build_sensor_behaviour_events(
                    events,
                    sensors,
                    getattr(scene_controller, "current_scene_path", None),
                    origin="player",
                )
                dispatch_events(scene_controller, b_events)

        self._handle_interact(decision.interact_triggered if decision is not None else False)
        self._handle_attack(decision.attack_triggered if decision is not None else False)

    def on_sensor_enter(self, sensor_id: str) -> None:
        """Hook for sensor entry."""
        pass  # Override in subclasses or dynamically attached methods

    def on_sensor_exit(self, sensor_id: str) -> None:
        """Hook for sensor exit."""
        pass

    def _sync_animation_state(self, vx: float, vy: float) -> None:
        entity_data = getattr(self.entity, "mesh_entity_data", None)
        if not isinstance(entity_data, dict):
            return
        speed_mag = math.hypot(vx, vy)
        state = "walk" if speed_mag > 1e-3 else "idle"
        entity_data["movement_state"] = state
        request_animation_state(self.entity, state, priority=-100.0)
        entity_data["facing"] = self._facing
        self._notify_animator_facing(self._facing)

    def _update_facing_from_velocity(self, vx: float, vy: float) -> None:
        if abs(vx) >= abs(vy):
            if vx > 0:
                self._facing = "right"
            elif vx < 0:
                self._facing = "left"
        else:
            if vy > 0:
                self._facing = "up"
            elif vy < 0:
                self._facing = "down"

    def _notify_animator_facing(self, facing: str) -> None:
        behaviours = getattr(self.entity, "mesh_behaviours_runtime", [])
        for behaviour in behaviours:
            setter = getattr(behaviour, "set_facing", None)
            if callable(setter):
                try:
                    setter(facing)
                except Exception as exc:  # noqa: BLE001  # REASON: optional animator hooks can fail without blocking core player movement
                    if not getattr(self, "_mesh_set_facing_error_logged", False):
                        print(f"[Mesh][PlayerController] ERROR forwarding facing to animator: {exc}")
                        setattr(self, "_mesh_set_facing_error_logged", True)
                break

    def _handle_interact(self, interact_triggered: bool) -> None:
        if interact_triggered:
            self._perform_interaction()
            request_animation_state(self.entity, "interact", priority=25.0, ttl=0.35)

    def _handle_attack(self, attack_triggered: bool) -> None:
        if not attack_triggered:
            return

        dispatch_attack_action(self.entity, self.window)

    def _perform_interaction(self) -> None:
        window = getattr(self, "window", None)
        if window is None:
            return
        from ..interaction import perform_interaction  # noqa: PLC0415

        try:
            perform_interaction(window, actor=self.entity, max_dist=float(self.INTERACT_RADIUS))
        except Exception as exc:  # noqa: BLE001  # REASON: interaction failures should be reported to the console without breaking input handling
            logger = getattr(window, "console_log", None)
            if callable(logger):
                logger(f"Interaction failed: {exc}")

    def _dialogue_blocks_input(self) -> bool:
        window = getattr(self, "window", None)
        if window is None:
            return False
        checker = getattr(window, "dialogue_blocks_input", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:  # pragma: no cover - defensive
                return False
        box = getattr(window, "dialogue_box", None)
        if box is None and hasattr(window, "ui_controller"):
            box = getattr(window.ui_controller, "dialogue_box", None)
        return bool(box and box.is_active())

    def _player_input_disabled(self) -> bool:
        window = getattr(self, "window", None)
        if window is None:
            return False
        checker = getattr(window, "player_input_blocked", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:  # pragma: no cover - defensive
                _log_swallow("PLAY-001", "engine/behaviours/player_controller.py pass-only blanket swallow")
                pass
        locker = getattr(window, "is_input_locked", None)
        if callable(locker):
            try:
                if bool(locker()):
                    return True
            except Exception:  # pragma: no cover - defensive
                _log_swallow("PLAY-002", "engine/behaviours/player_controller.py pass-only blanket swallow")
                pass
        return self._dialogue_blocks_input()
