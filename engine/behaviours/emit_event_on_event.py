from __future__ import annotations

from typing import Any

from ..events import MeshEvent
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "EmitEventOnEvent",
    description="Listens for an event and emits another event.",
    config_fields=[
        {"name": "listen_event", "type": "string", "default": ""},
        {"name": "payload_field", "type": "string", "default": ""},
        {"name": "payload_value", "type": "string", "default": ""},
        {"name": "emit_event", "type": "string", "default": ""},
        {"name": "emit_payload", "type": "object", "default": {}},
    ],
)
class EmitEventOnEvent(Behaviour):
    PARAM_DEFS = {
        "listen_event": ParamDef(str, default=""),
        "payload_field": ParamDef(str, default=""),
        "payload_value": ParamDef(str, default=""),
        "emit_event": ParamDef(str, default=""),
        "emit_payload": ParamDef(dict, default={}),
    }

    def __init__(self, entity, window, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self.listen_event = str(self.config.get("listen_event", "") or "")
        self.payload_field = str(self.config.get("payload_field", "") or "")
        self.payload_value = str(self.config.get("payload_value", "") or "")
        self.emit_event_name = str(self.config.get("emit_event", "") or "")
        self.emit_payload = dict(self.config.get("emit_payload", {}) or {})

    def on_event(self, event: MeshEvent) -> None:
        if not self.listen_event or event.type != self.listen_event:
            return

        if self.payload_field:
            payload = event.payload or {}
            val = payload.get(self.payload_field)
            # Simple string comparison
            if str(val) != self.payload_value:
                return

        if self.emit_event_name:
            self.window.emit_signal(self.emit_event_name, **self.emit_payload)
