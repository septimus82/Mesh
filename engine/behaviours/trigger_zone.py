"""Trigger zone behaviour for proximity detection."""

from __future__ import annotations

import math
from typing import Any

from ..constants import EVENT_ENTERED_ZONE
from ..event_emit import emit_gameplay_event
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "TriggerZone",
    description="Fires once when a target sprite enters a radius.",
    config_fields=[
        {
            "name": "trigger_radius",
            "description": "Distance threshold for triggering",
            "type": "float",
            "default": 0.0,
        },
        {
            "name": "trigger_target",
            "description": "Name of the sprite to watch",
            "type": "string",
            "default": "",
        },
        {
            "name": "on_trigger",
            "description": "Label describing the triggered event",
            "type": "string",
            "default": "",
        },
    ],
)
class TriggerZoneBehaviour(Behaviour):
    """Detects when a target sprite enters a radius."""

    PARAM_DEFS = {
        "trigger_radius": ParamDef(float, default=0.0, description="Distance threshold for triggering"),
        "trigger_target": ParamDef(str, default="", description="Name of the sprite to watch"),
        "on_trigger": ParamDef(str, default="", description="Label describing the triggered event"),
    }

    def __init__(self, entity, window, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self.radius: float | None = None
        raw_radius = self.config.get("trigger_radius")
        self.target_name = str(self.config.get("trigger_target", "")).strip()
        self.event_name = str(self.config.get("on_trigger", "")).strip()
        self._triggered = False

        if not raw_radius or not self.target_name:
            print("[Mesh][Behaviour:Trigger] WARNING: trigger_radius and trigger_target required")
            self._disabled = True
        else:
            self.radius = float(raw_radius)
            self._disabled = False

    def update(self, dt: float) -> None:  # noqa: ARG002
        if getattr(self, "_disabled", False) or self._triggered:
            return

        target = self.window.find_sprite_by_name(self.target_name)
        if target is None:
            return

        radius = self.radius
        if radius is None:
            return

        dx = target.center_x - self.entity.center_x
        dy = target.center_y - self.entity.center_y
        dist = math.hypot(dx, dy)
        if dist <= radius:
            self._triggered = True
            entity_name = getattr(self.entity, "mesh_name", "<unnamed>")
            event = self.event_name or "event"
            print(f"[Mesh][Trigger] {entity_name} triggered {event}")
            actor_name = getattr(target, "mesh_name", "<unnamed>")

            # Emit explicit event via gameplay bus adapter.
            emit_gameplay_event(
                self.window,
                EVENT_ENTERED_ZONE,
                {
                    "zone": entity_name,
                    "actor": actor_name,
                    "position": (float(self.entity.center_x), float(self.entity.center_y)),
                },
                source_entity_id=str(getattr(self.entity, "mesh_id", "") or ""),
                source_behaviour="TriggerZone",
            )

            # Legacy signal support (optional, but good for compatibility)
            if hasattr(self.window, "emit_signal"):
                position = (float(self.entity.center_x), float(self.entity.center_y))
                self.window.emit_signal(
                    EVENT_ENTERED_ZONE,
                    zone=entity_name,
                    actor=actor_name,
                    position=position,
                )
