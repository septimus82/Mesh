"""Behaviour that prints a console message when a zone is entered."""

from __future__ import annotations

from typing import Callable, Optional

from ..events import MeshEvent
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "MessageOnZoneEnter",
    description="Logs a console message whenever a configured zone is entered.",
    config_fields=[
        {
            "name": "zone_name",
            "description": "Name of the TriggerZone entity to watch",
            "type": "string",
            "default": "",
        },
        {
            "name": "message",
            "description": "Optional message template (supports {actor} and {zone})",
            "type": "string",
            "default": "",
        },
    ],
)
class MessageOnZoneEnter(Behaviour):
    """Subscribes to the event bus and logs when a zone is entered."""

    PARAM_DEFS = {
        "zone_name": ParamDef(str, default="", description="Name of the TriggerZone entity to watch"),
        "message": ParamDef(str, default="", description="Optional message template"),
    }

    def __init__(self, entity, window, **config) -> None:  # noqa: ANN001 - arcade entity
        super().__init__(entity, window, **config)
        self.zone_name = str(self.config.get("zone_name", "")).strip()
        self.message_template = str(self.config.get("message", ""))
        self._unsubscribe: Optional[Callable[[], None]] = None

        bus = getattr(window, "event_bus", None)
        if self.zone_name and bus is not None:
            self._unsubscribe = bus.subscribe("entered_zone", self._on_entered_zone)
        else:
            print("[Mesh][MessageOnZoneEnter] WARNING: Missing zone_name or event bus")

    def _on_entered_zone(self, event: MeshEvent) -> None:
        payload = event.payload or {}
        zone = str(payload.get("zone", "")).strip()
        if not zone or (self.zone_name and zone != self.zone_name):
            return
        actor = payload.get("actor", "<unknown>")
        message = self.message_template or "{actor} entered zone {zone}"
        formatted = message.format(actor=actor, zone=zone)
        if hasattr(self.window, "console_log"):
            self.window.console_log(formatted)
        else:
            print(f"[Mesh][ZoneMessage] {formatted}")

    def dispose(self) -> None:
        if self._unsubscribe is not None:
            try:
                self._unsubscribe()
            finally:
                self._unsubscribe = None
