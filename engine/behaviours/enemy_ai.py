"""Enemy AI behaviour for Mesh Engine."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from ..events import MeshEvent
from .base import Behaviour, ParamDef
from .registry import register_behaviour
from engine.logging_tools import get_logger

_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)


if TYPE_CHECKING:
    from arcade import Sprite

    from engine.game import GameWindow


@register_behaviour(
    "EnemyAI",
    description="Simple AI that chases and attacks a target.",
    config_fields=[
        {
            "name": "target_tag",
            "description": "Tag of the entity to chase",
            "type": "string",
            "default": "player",
        },
        {
            "name": "detect_radius",
            "description": "Distance to start chasing",
            "type": "float",
            "default": 300.0,
        },
        {
            "name": "lose_radius",
            "description": "Distance to stop chasing",
            "type": "float",
            "default": 360.0,
        },
        {
            "name": "attack_radius",
            "description": "Distance to start attacking",
            "type": "float",
            "default": 40.0,
        },
        {
            "name": "speed",
            "description": "Movement speed",
            "type": "float",
            "default": 100.0,
        },
        {
            "name": "attack_cooldown",
            "description": "Seconds between attacks",
            "type": "float",
            "default": 1.0,
        },
        {
            "name": "attack_anim_duration",
            "description": "Seconds to play attack animation (if Animator attached)",
            "type": "float",
            "default": 0.25,
        },
        {
            "name": "repath_interval",
            "description": "Seconds between chase direction updates",
            "type": "float",
            "default": 0.2,
        },
        {
            "name": "use_patrol",
            "description": "If true, idle/patrol when not chasing",
            "type": "bool",
            "default": True,
        },
        {
            "name": "flee_below_health",
            "description": "Fraction of max health below which enemy flees (0 disables)",
            "type": "float",
            "default": 0.0,
        },
        {
            "name": "attack_event",
            "description": "Event emitted on attack",
            "type": "string",
            "default": "enemy_attack",
        },
    ],
)
class EnemyAI(Behaviour):
    """Chases a target and triggers Combat behaviour."""

    PARAM_DEFS = {
        "target_tag": ParamDef(str, default="player", description="Tag of the entity to chase"),
        "detect_radius": ParamDef(float, default=300.0, description="Distance to start chasing"),
        "lose_radius": ParamDef(float, default=360.0, description="Distance to stop chasing"),
        "attack_radius": ParamDef(float, default=40.0, description="Distance to start attacking"),
        "speed": ParamDef(float, default=100.0, description="Movement speed"),
        "attack_cooldown": ParamDef(float, default=1.0, description="Seconds between attacks"),
        "attack_anim_duration": ParamDef(float, default=0.25, description="Seconds to play attack animation"),
        "repath_interval": ParamDef(float, default=0.2, description="Seconds between chase direction updates"),
        "use_patrol": ParamDef(bool, default=True, description="If true, idle/patrol when not chasing"),
        "flee_below_health": ParamDef(float, default=0.0, description="Fraction of max health to flee"),
        "attack_event": ParamDef(str, default="enemy_attack", description="Event emitted on attack"),
    }

    def __init__(self, entity: "Sprite", window: "GameWindow", **config) -> None:
        super().__init__(entity, window, **config)
        self.target_tag = str(self.config.get("target_tag", "player"))
        self.detect_radius = float(self.config.get("detect_radius", 300.0))
        self.lose_radius = float(self.config.get("lose_radius", 360.0))
        self.attack_radius = float(self.config.get("attack_radius", 40.0))
        self.speed = float(self.config.get("speed", 100.0))
        self.attack_cooldown = float(self.config.get("attack_cooldown", 1.0))
        self.attack_anim_duration = float(self.config.get("attack_anim_duration", 0.25))
        self.repath_interval = float(self.config.get("repath_interval", 0.2))
        self.use_patrol = bool(self.config.get("use_patrol", True))
        self.flee_below_health = max(0.0, float(self.config.get("flee_below_health", 0.0)))
        self.attack_event = str(self.config.get("attack_event", "enemy_attack"))

        self._target: Sprite | None = None
        self._attack_cooldown_timer: float = 0.0
        self._repath_timer: float = 0.0
        self._facing: str = "down"

        self.IDLE = "idle"
        self.PATROL = "patrol"
        self.CHASE = "chase"
        self.ATTACK = "attack"
        self.FLEE = "flee"
        self.DEAD = "dead"

        self._state = self.PATROL if self.use_patrol else self.IDLE

    def _log_exception_once(self, key: str, exc: Exception) -> None:
        logged = getattr(self, "_mesh_logged_exceptions", None)
        if not isinstance(logged, set):
            logged = set()
            setattr(self, "_mesh_logged_exceptions", logged)
        if key in logged:
            return
        logged.add(key)
        print(f"[Mesh][EnemyAI] ERROR {key}: {exc}")
        self._state: str = self.IDLE

    def update(self, dt: float) -> None:
        if self._attack_cooldown_timer > 0:
            self._attack_cooldown_timer -= dt
        if self._repath_timer > 0:
            self._repath_timer -= dt

        if self._is_dead():
            self._state = self.DEAD
            self._update_dead(dt)
            return

        # Find target if needed
        if not self._target:
            self._find_target()

        if not self._target:
            if self.use_patrol:
                self._state = self.PATROL
            else:
                self._state = self.IDLE
            self._update_idle(dt)
            return

        # Calculate distance
        dx = self._target.center_x - self.entity.center_x
        dy = self._target.center_y - self.entity.center_y
        dist_sq = dx*dx + dy*dy
        dist = math.sqrt(dist_sq)

        if self.flee_below_health > 0 and self._should_flee():
            self._state = self.FLEE
            self._update_flee(dt, dx, dy, dist)
            return

        # State transitions
        if self._state in {self.IDLE, self.PATROL} and dist <= self.detect_radius:
            self._state = self.CHASE
        elif self._state == self.CHASE and dist <= self.attack_radius:
            self._state = self.ATTACK
        elif self._state == self.ATTACK and dist > self.attack_radius:
            self._state = self.CHASE
        elif self._state == self.CHASE and dist > self.lose_radius:
            self._state = self.PATROL if self.use_patrol else self.IDLE
        elif self._state == self.FLEE and dist > self.lose_radius * 1.5:
            self._state = self.PATROL if self.use_patrol else self.IDLE

        # State handling
        if self._state == self.IDLE:
            self._update_idle(dt)
        elif self._state == self.PATROL:
            self._update_patrol(dt)
        elif self._state == self.CHASE:
            self._update_chase(dt, dx, dy, dist)
        elif self._state == self.ATTACK:
            self._update_attack(dt, dx, dy, dist)
        elif self._state == self.FLEE:
            self._update_flee(dt, dx, dy, dist)
        elif self._state == self.DEAD:
            self._update_dead(dt)

    def _find_target(self) -> None:
        scene_controller = getattr(self.window, "scene_controller", None)
        if not scene_controller:
            return

        for sprite in scene_controller.all_sprites:
            if getattr(sprite, "mesh_tag", "") == self.target_tag:
                self._target = sprite
                break
    def _update_idle(self, dt: float) -> None:  # noqa: ARG002
        self.entity.change_x = 0
        self.entity.change_y = 0

    def _update_patrol(self, dt: float) -> None:  # noqa: ARG002
        # Patrol behaviour runs independently if attached; do not override velocity here.
        return

    def _update_chase(self, dt: float, dx: float, dy: float, dist: float) -> None:
        if dist == 0:
            return
        if self._repath_timer > 0:
            return
        self._repath_timer = self.repath_interval
        nx = dx / dist
        ny = dy / dist
        move_x = nx * self.speed * dt
        move_y = ny * self.speed * dt
        scene_controller = getattr(self.window, "scene_controller", None)
        if scene_controller:
            scene_controller.move_entity_with_collision(self.entity, move_x, move_y)
        self._update_facing_from_vector(nx, ny)
        if dx != 0 or dy != 0:
            angle = math.degrees(math.atan2(dy, dx))
            self.entity.angle = angle

    def _update_attack(self, dt: float, dx: float, dy: float, dist: float) -> None:  # noqa: ARG002
        self.entity.change_x = 0
        self.entity.change_y = 0
        if self._attack_cooldown_timer <= 0:
            self._perform_attack()
            self._attack_cooldown_timer = self.attack_cooldown

    def _update_flee(self, dt: float, dx: float, dy: float, dist: float) -> None:
        if dist == 0:
            return
        nx = dx / dist
        ny = dy / dist
        move_x = -nx * self.speed * dt
        move_y = -ny * self.speed * dt
        scene_controller = getattr(self.window, "scene_controller", None)
        if scene_controller:
            scene_controller.move_entity_with_collision(self.entity, move_x, move_y)
        self._update_facing_from_vector(-nx, -ny)

    def _update_dead(self, dt: float) -> None:  # noqa: ARG002
        self.entity.change_x = 0
        self.entity.change_y = 0

    def _perform_attack(self) -> None:
        bus = getattr(self.window, "event_bus", None)
        if bus is not None:
            try:
                bus.emit_event(MeshEvent(type=self.attack_event, payload={"attacker": self.entity, "target": self._target}))
            except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
                _log_swallow("ENAI-001", "engine/behaviours/enemy_ai.py blanket swallow", once=True)
                self._log_exception_once("emit_attack_event", exc)
        animator = self._get_animator_behaviour()
        if animator is not None and hasattr(animator, "request_state_override"):
            try:
                animator.request_state_override("attack", "attack", self.attack_anim_duration)
            except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
                _log_swallow("ENAI-002", "engine/behaviours/enemy_ai.py blanket swallow", once=True)
                self._log_exception_once("request_state_override", exc)
        behaviours = getattr(self.entity, "mesh_behaviours_runtime", [])
        for behaviour in behaviours:
            if hasattr(behaviour, "attack"):
                try:
                    behaviour.attack()
                except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
                    _log_swallow("ENAI-003", "engine/behaviours/enemy_ai.py blanket swallow", once=True)
                    self._log_exception_once("combat_attack", exc)
                break

    def _should_flee(self) -> bool:
        if self.flee_below_health <= 0:
            return False
        health = self._get_health_behaviour()
        if health is None:
            return False
        max_hp = getattr(health, "max_health", None) or getattr(health, "max_hp", None)
        current = getattr(health, "health", None) or getattr(health, "current_health", None)
        try:
            ratio = float(current) / float(max_hp)
        except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
            _log_swallow("ENAI-004", "engine/behaviours/enemy_ai.py blanket swallow", once=True)
            self._log_exception_once("health_ratio", exc)
            return False
        return ratio <= self.flee_below_health

    def _is_dead(self) -> bool:
        health = self._get_health_behaviour()
        if health is None:
            return False
        return bool(getattr(health, "is_dead", False))

    def _get_health_behaviour(self):
        behaviours = getattr(self.entity, "mesh_behaviours_runtime", [])
        for b in behaviours:
            if hasattr(b, "max_health") or hasattr(b, "max_hp") or b.__class__.__name__ == "Health":
                return b
        return None

    def _update_facing_from_vector(self, nx: float, ny: float) -> None:
        if abs(nx) >= abs(ny):
            if nx > 0:
                self._facing = "right"
            elif nx < 0:
                self._facing = "left"
        else:
            if ny > 0:
                self._facing = "up"
            elif ny < 0:
                self._facing = "down"
        animator = self._get_animator_behaviour()
        if animator is not None and hasattr(animator, "set_facing"):
            try:
                animator.set_facing(self._facing)
            except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
                _log_swallow("ENAI-005", "engine/behaviours/enemy_ai.py blanket swallow", once=True)
                self._log_exception_once("set_facing", exc)

    def _get_animator_behaviour(self):
        behaviours = getattr(self.entity, "mesh_behaviours_runtime", [])
        for b in behaviours:
            if b.__class__.__name__ == "SpriteAnimatorBehaviour":
                return b
            if hasattr(b, "request_state_override") or hasattr(b, "set_facing"):
                return b
        return None
