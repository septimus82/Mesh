from __future__ import annotations

import math
from typing import Any

from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "AutoAnimationByMovement",
    description="Switches sprite-sheet animations between idle/walk based on movement velocity.",
    config_fields=[
        {
            "name": "idle",
            "description": "Animation state name to use when stationary",
            "type": "string",
            "default": "idle",
        },
        {
            "name": "walk",
            "description": "Animation state name to use when moving",
            "type": "string",
            "default": "walk",
        },
        {
            "name": "speed_threshold",
            "description": "Speed cutoff used to decide between idle and walk",
            "type": "float",
            "default": 0.01,
        },
        {
            "name": "prefer",
            "description": "Fallback animation preference order if idle/walk is missing",
            "type": "array",
            "default": ["walk", "idle"],
        },
    ],
)
class AutoAnimationByMovement(Behaviour):
    PARAM_DEFS = {
        "idle": ParamDef(str, default="idle", description="Animation state for idle"),
        "walk": ParamDef(str, default="walk", description="Animation state for walking"),
        "speed_threshold": ParamDef(float, default=0.01, description="Speed cutoff for walk"),
        "prefer": ParamDef(list, default=["walk", "idle"], description="Fallback preference order"),
    }

    def __init__(self, entity, window, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self._last_pos: tuple[float, float] | None = None

    def late_update(self, dt: float) -> None:
        entity = self.entity
        animator = getattr(entity, "mesh_animator", None)
        if animator is None:
            return

        entity_data = getattr(entity, "mesh_entity_data", None)
        if not isinstance(entity_data, dict):
            return
        animations = entity_data.get("animations")
        if not isinstance(animations, dict) or not animations:
            return

        idle = str(getattr(self, "idle", "idle") or "idle")
        walk = str(getattr(self, "walk", "walk") or "walk")

        explicit_state = entity_data.get("animation_state")
        if (
            isinstance(explicit_state, str)
            and explicit_state.strip()
            and explicit_state.strip() not in {idle, walk}
        ):
            self._remember_position()
            return

        speed = self._compute_speed(dt)
        threshold = max(0.0, float(getattr(self, "speed_threshold", 0.01) or 0.0))
        wants_walk = speed > threshold

        available = self._available_states(animator)
        if not available:
            self._remember_position()
            return

        primary = walk if wants_walk else idle
        secondary = idle if wants_walk else walk
        target = None
        if primary in available:
            target = primary
        elif secondary in available:
            target = secondary
        else:
            prefer = getattr(self, "prefer", None)
            if isinstance(prefer, list):
                for name in prefer:
                    if isinstance(name, str) and name in available:
                        target = name
                        break
            if target is None:
                target = next(iter(sorted(available)))

        current_state = getattr(animator, "current_state", None)
        if current_state != target:
            set_state = getattr(animator, "set_state", None)
            if callable(set_state):
                set_state(target)

        self._remember_position()

    def _available_states(self, animator: Any) -> set[str]:
        getter = getattr(animator, "available_states", None)
        if callable(getter):
            try:
                states = getter()
                if isinstance(states, list):
                    return {str(s) for s in states if isinstance(s, str)}
            except Exception:
                return set()
        clips = getattr(animator, "clips", None)
        if isinstance(clips, dict):
            return {str(k) for k in clips.keys() if isinstance(k, str)}
        return set()

    def _compute_speed(self, dt: float) -> float:
        vx = getattr(self.entity, "change_x", None)
        vy = getattr(self.entity, "change_y", None)
        if isinstance(vx, (int, float)) and isinstance(vy, (int, float)):
            return float(math.hypot(float(vx), float(vy)))

        if dt <= 0:
            return 0.0
        last = self._last_pos
        if last is None:
            return 0.0
        cx = float(getattr(self.entity, "center_x", 0.0))
        cy = float(getattr(self.entity, "center_y", 0.0))
        dx = cx - float(last[0])
        dy = cy - float(last[1])
        return float(math.hypot(dx, dy) / max(float(dt), 0.000001))

    def _remember_position(self) -> None:
        try:
            self._last_pos = (float(getattr(self.entity, "center_x", 0.0)), float(getattr(self.entity, "center_y", 0.0)))
        except Exception:
            self._last_pos = None

