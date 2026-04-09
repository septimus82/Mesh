"""Behaviour that increments a game counter when a specific event fires."""

from __future__ import annotations

from typing import Any, Callable

from ..events import MeshEvent
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "IncrementCounterOnEvent",
    description="Listens for a Mesh event and increments a global counter.",
    config_fields=[
        {
            "name": "event_type",
            "description": "Mesh event name to react to (required)",
            "type": "string",
            "default": "",
        },
        {
            "name": "payload_field",
            "description": "Optional payload key to filter by",
            "type": "string",
            "default": "",
        },
        {
            "name": "payload_value",
            "description": "Value that payload_field must match",
            "type": "string",
            "default": "",
        },
        {
            "name": "counter",
            "description": "Name of the counter to increment",
            "type": "string",
            "default": "",
        },
        {
            "name": "amount",
            "description": "Amount to increment by",
            "type": "float",
            "default": 1.0,
        },
        {
            "name": "scope",
            "description": "Scope of the counter ('global' or 'quest')",
            "type": "string",
            "default": "global",
        },
        {
            "name": "quest_id",
            "description": "Quest ID if scope is 'quest'",
            "type": "string",
            "default": "",
        },
    ],
)
class IncrementCounterOnEvent(Behaviour):
    PARAM_DEFS = {
        "event_type": ParamDef(str, default=""),
        "payload_field": ParamDef(str, default=""),
        "payload_value": ParamDef(str, default=""),
        "counter": ParamDef(str, default=""),
        "amount": ParamDef(float, default=1.0),
        "scope": ParamDef(str, default="global"),
        "quest_id": ParamDef(str, default=""),
    }

    def __init__(self, entity, window, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self.event_type = str(self.config.get("event_type", "") or "")
        self.payload_field = str(self.config.get("payload_field", "") or "")
        self.payload_value = str(self.config.get("payload_value", "") or "")
        self.counter = str(self.config.get("counter", "") or "")
        self.amount = float(self.config["amount"])
        self.scope = str(self.config.get("scope", "global") or "global")
        self.quest_id = str(self.config.get("quest_id", "") or "")
        self._unsubscribe: Callable[[], None] | None
        self._unsubscribe = None

        if self.event_type and self.counter:
            self._unsubscribe = self.window.event_bus.subscribe(self.event_type, self._on_event)

    def _on_event(self, event: MeshEvent) -> None:
        if self.payload_field:
            val = event.payload.get(self.payload_field)
            # Simple string comparison for now, could be more robust
            if str(val) != str(self.payload_value):
                return

        if self.scope == "quest" and self.quest_id:
            self.window.game_state_controller.inc_quest_counter(self.quest_id, self.counter, self.amount)
            print(f"[Mesh][IncrementCounterOnEvent] Incremented quest counter '{self.quest_id}:{self.counter}' by {self.amount}")
        else:
            self.window.inc_counter(self.counter, self.amount)
            print(f"[Mesh][IncrementCounterOnEvent] Incremented '{self.counter}' by {self.amount}")

    def destroy(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
