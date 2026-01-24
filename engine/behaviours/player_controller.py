"""Player controller behaviour that responds to WASD input."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ..animation_state import request_animation_state
from .base import Behaviour, ParamDef
from .registry import register_behaviour
import engine.optional_arcade as optional_arcade

if TYPE_CHECKING:  # pragma: no cover - typing only
    import optional_arcade.arcade


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

    def __init__(self, entity: "optional_arcade.arcade.Sprite", window, **config):  # type: ignore[override]
        super().__init__(entity, window, **config)
        self.speed = float(self.config.get("speed", 150.0))
        self._interact_was_down = False
        self._facing = "down"

    def update(self, dt: float) -> None:
        speed = self.speed
        input_manager = getattr(self.window, "input", None)

        if self._player_input_disabled():
            if input_manager is not None:
                self._interact_was_down = input_manager.is_action_down("interact")
            self._sync_animation_state(0.0, 0.0)
            return

        if input_manager is not None:
            vx = input_manager.get_axis("move_left", "move_right")
            vy = input_manager.get_axis("move_down", "move_up")
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
        # move_entity_with_collision expects absolute deltas; scale velocity by dt
        self.window.move_entity_with_collision(self.entity, vx * dt, vy * dt)
        self._handle_interact(input_manager)
        self._handle_attack(input_manager)

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
                except Exception as exc:  # noqa: BLE001
                    if not getattr(self, "_mesh_set_facing_error_logged", False):
                        print(f"[Mesh][PlayerController] ERROR forwarding facing to animator: {exc}")
                        setattr(self, "_mesh_set_facing_error_logged", True)
                break

    def _handle_interact(self, input_manager) -> None:
        if input_manager is None:
            return

        interact_down = input_manager.is_action_down("interact")
        if interact_down and not self._interact_was_down:
            if getattr(self.window, "_mesh_interact_consumed", False):
                setattr(self.window, "_mesh_interact_consumed", False)
            else:
                self._perform_interaction()
            request_animation_state(self.entity, "interact", priority=25.0, ttl=0.35)
        self._interact_was_down = interact_down

    def _handle_attack(self, input_manager) -> None:
        if input_manager is None:
            return

        if input_manager.is_action_down("attack"):
            behaviours = getattr(self.entity, "mesh_behaviours_runtime", [])
            for behaviour in behaviours:
                if hasattr(behaviour, "attack"):
                    behaviour.attack()
                    break

    def _perform_interaction(self) -> None:
        window = getattr(self, "window", None)
        if window is None:
            return
        from ..interaction import perform_interaction  # noqa: PLC0415

        try:
            perform_interaction(window, max_dist=float(self.INTERACT_RADIUS))
        except Exception as exc:  # noqa: BLE001
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
                pass
        locker = getattr(window, "is_input_locked", None)
        if callable(locker):
            try:
                if bool(locker()):
                    return True
            except Exception:  # pragma: no cover - defensive
                pass
        return self._dialogue_blocks_input()
