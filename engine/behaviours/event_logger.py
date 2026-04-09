"""Event Logger behaviour for debugging."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from .base import Behaviour, ParamDef
from .registry import register_behaviour

if TYPE_CHECKING:
    from arcade import Sprite

    from engine.events import MeshEvent
    from engine.game import GameWindow


@register_behaviour(
    "EventLogger",
    description="Logs specific events to the console.",
    config_fields=[
        {
            "name": "events",
            "description": "Comma-separated list of events to log (or '*' for all)",
            "type": "string",
            "default": "*",
        },
    ],
)
class EventLogger(Behaviour):
    """Subscribes to the event bus and logs events."""

    PARAM_DEFS = {
        "events": ParamDef(str, default="*", description="Comma-separated list of events to log (or '*')"),
    }

    def __init__(self, entity: "Sprite", window: "GameWindow", **config: Any) -> None:
        super().__init__(entity, window, **config)
        raw_events = str(self.config.get("events", "*"))
        self.events_to_log = raw_events.split(",")
        self.events_to_log = [e.strip() for e in self.events_to_log if e.strip()]
        self._unsubscribers: list[Callable[[], None]]
        self._unsubscribers = []

    def on_added(self) -> None:
        """Subscribe when added to the scene."""
        if "*" in self.events_to_log:
            unsub = self.window.event_bus.subscribe_all(self._on_any_event)
            self._unsubscribers.append(unsub)
        else:
            for event_type in self.events_to_log:
                unsub = self.window.event_bus.subscribe(event_type, self._make_handler(event_type))
                self._unsubscribers.append(unsub)

    def on_removed(self) -> None:
        """Unsubscribe when removed."""
        for unsub in self._unsubscribers:
            unsub()
        self._unsubscribers.clear()

    def _make_handler(self, event_type: str):
        def handler(event: "MeshEvent"):
            print(f"[Mesh][EventLogger] Received '{event_type}': {event.payload}")
        return handler

    def _on_any_event(self, event: "MeshEvent"):
        print(f"[Mesh][EventLogger] Received '{event.type}': {event.payload}")
