"""Trigger zone behaviour for proximity detection."""

from __future__ import annotations

import math
from typing import Any

from engine.log_utils import get_logger

from ..constants import EVENT_ENTERED_ZONE
from ..event_emit import emit_gameplay_event
from .base import Behaviour, ParamDef
from .registry import register_behaviour

logger = get_logger(__name__)

PLAY_ONCE_NOTE = ("On: it fires once per playthrough, never again after leaving the room or loading a save (a cutscene "
                  "it starts that is interrupted is not replayed). Off: once each time the room loads.")


@register_behaviour(
    "TriggerZone",
    description="Sends entered_zone, and the event it sends (on_trigger) if set, once when a target sprite enters a "
    "radius: once each time the room loads, or with Play once (play_once) once per playthrough, kept in room memory "
    "and saves. Play once counts as used when the events are sent, so a cutscene they start that is interrupted is "
    "not replayed.",
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
            "description": "Event it sends when the target comes within reach (entered_zone is always sent too)",
            "type": "string",
            "default": "",
        },
        {
            "name": "play_once",
            "description": PLAY_ONCE_NOTE,
            "type": "bool",
            "default": False,
        },
    ],
)
class TriggerZoneBehaviour(Behaviour):
    """Detects when a target sprite enters a radius, once.

    It then sends ``entered_zone`` (payload ``zone``: its name, ``actor``: the target's name, ``position``) and, when
    ``on_trigger`` is set, that event ("Event it sends" in Studio) with the same payload. Each is sent once.

    Once per room load by default: the room is rebuilt on entry, so re-entering it arms the zone again. With
    ``play_once`` ("Play once") the zone records the room-memory fact ``fired`` (``engine.scene_runtime.room_memory``,
    keyed by the room and the object's authored id) as soon as its events are sent, and from then on stays silent in
    this playthrough: after re-entry, a save and load, and in exported games. A save without the fact: not fired yet.
    The fact is written when the events are sent, not when what they start ends: a cutscene they start that is
    interrupted (the game quit mid-way, a save loaded) is not replayed. An object without its own authored id in the
    room (spawned, or sharing an id) has no facts: it fires once per room load, with a warning.
    """

    FACT_FIELDS = ("fired",)

    PARAM_DEFS = {
        "trigger_radius": ParamDef(float, default=0.0, description="Distance threshold for triggering"),
        "trigger_target": ParamDef(str, default="", description="Name of the sprite to watch"),
        "on_trigger": ParamDef(str, default="", description="Event it sends when the target comes within reach"),
        "play_once": ParamDef(bool, default=False, description=PLAY_ONCE_NOTE),
    }

    def __init__(self, entity, window, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self.radius: float | None = None
        raw_radius = self.config.get("trigger_radius")
        self.target_name = str(self.config.get("trigger_target", "")).strip()
        self.event_name = str(self.config.get("on_trigger", "")).strip()
        self.play_once = bool(self.config.get("play_once", False))
        self._triggered = False
        self.fired = False  # (play once: recorded in room memory, applied by the factory before the first update)

        if not raw_radius or not self.target_name:
            print("[Mesh][Behaviour:Trigger] WARNING: trigger_radius and trigger_target required")
            self._disabled = True
        else:
            self.radius = float(raw_radius)
            self._disabled = False

    def update(self, dt: float) -> None:  # noqa: ARG002
        if getattr(self, "_disabled", False) or self._triggered or (self.play_once and self.fired):
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

            payload = {
                "zone": entity_name,
                "actor": actor_name,
                "position": (float(self.entity.center_x), float(self.entity.center_y)),
            }
            # entered_zone (what shipped content keys on, with the zone's name), then the creator's own event; each
            # once, through the one emit path (#640: a second window.emit_signal put every entered_zone on the bus
            # twice). A chosen event named entered_zone is not sent a second time.
            for name in dict.fromkeys((EVENT_ENTERED_ZONE, self.event_name)):
                if name:
                    emit_gameplay_event(
                        self.window,
                        name,
                        payload,
                        source_entity_id=str(getattr(self.entity, "mesh_id", "") or ""),
                        source_behaviour="TriggerZone",
                    )
            if self.play_once:
                if self._mesh_fact_key is None:
                    logger.warning("TriggerZone %r: Play once needs the object's own id in the room; it fires once per "
                                   "room load instead", entity_name)
                self.record_fact("fired", True)
