"""Behaviour that reacts to Mesh events emitted during the frame."""

from __future__ import annotations

from typing import Any, Dict

from ..events import MeshEvent
from .base import Behaviour, ParamDef
from .registry import register_behaviour


class _SafePayload(dict):
    def __missing__(self, key: str) -> str:  # pragma: no cover - best-effort formatting only
        return "{" + key + "}"


@register_behaviour(
    "ListenForEvent",
    description="Invokes reactions when a Mesh event with the desired payload arrives.",
    config_fields=[
        {
            "name": "event_type",
            "description": "Mesh event name to react to",
            "type": "string",
            "default": "",
        },
        {
            "name": "payload_field",
            "description": "Optional payload field that must be present",
            "type": "string",
            "default": "",
        },
        {
            "name": "payload_value",
            "description": "Optional value to match on the payload field",
            "type": "string",
            "default": "",
        },
        {
            "name": "forward_as",
            "description": "Re-emit the payload under this event name when matched",
            "type": "string",
            "default": "",
        },
        {
            "name": "message",
            "description": "Console message template when triggered (format with payload)",
            "type": "string",
            "default": "",
        },
        {
            "name": "once",
            "description": "Stop listening after the first match",
            "type": "bool",
            "default": False,
        },
    ],
)
class ListenForEvent(Behaviour):
    """Subscribes to Mesh events routed through GameWindow."""

    PARAM_DEFS = {
        "event_type": ParamDef(str, default="", description="Mesh event name to react to"),
        "payload_field": ParamDef(str, default="", description="Optional payload field that must be present"),
        "payload_value": ParamDef(str, default="", description="Optional value to match on the payload field"),
        "forward_as": ParamDef(str, default="", description="Re-emit the payload under this event name when matched"),
        "message": ParamDef(str, default="", description="Console message template when triggered"),
        "once": ParamDef(bool, default=False, description="Stop listening after the first match"),
    }

    def __init__(self, entity, window, **config) -> None:  # noqa: ANN001 - arcade sprite
        merged = self._merge_entity_data(entity, config)
        super().__init__(entity, window, **merged)
        self.event_type = str(merged.get("event_type", "")).strip()
        self.payload_field = str(merged.get("payload_field", "")).strip()
        raw_value = merged.get("payload_value", "")
        self.payload_value = str(raw_value).strip() if raw_value not in (None, "") else None
        self.forward_as = str(merged.get("forward_as", "")).strip()
        self.message_template = str(merged.get("message", ""))
        self.once = bool(merged.get("once", False))
        self.config.update(
            {
                "event_type": self.event_type,
                "payload_field": self.payload_field,
                "payload_value": self.payload_value,
                "forward_as": self.forward_as,
                "message": self.message_template,
                "once": self.once,
            },
        )
        self._consumed = False
        if not self.event_type:
            print("[Mesh][ListenForEvent] WARNING: event_type is required")

    @staticmethod
    def _merge_entity_data(entity, config: Dict[str, Any] | None) -> Dict[str, Any]:  # noqa: ANN001 - sprite
        data = dict(getattr(entity, "mesh_entity_data", {}) or {})
        if config:
            data.update(config)
        return data

    def subscribed_event_types(self) -> frozenset[str] | None:
        return frozenset({self.event_type}) if self.event_type else frozenset()

    def on_event(self, event: MeshEvent) -> None:  # noqa: D401
        if self._consumed:
            return
        if not self.event_type or event.type != self.event_type:
            return

        payload = dict(event.payload or {})
        if self.payload_field:
            candidate = payload.get(self.payload_field)
            if self.payload_value is not None:
                if str(candidate) != self.payload_value:
                    return
            elif candidate is None:
                return

        self._emit_message(payload)
        if self.forward_as:
            self._forward_event(payload)
        if self.once:
            self._consumed = True

    def _emit_message(self, payload: Dict[str, Any]) -> None:
        if not self.message_template:
            return
        safe_payload: Dict[str, Any] = _SafePayload(payload)
        safe_payload.setdefault("entity", getattr(self.entity, "mesh_name", "<unnamed>"))
        try:
            message = self.message_template.format_map(safe_payload)
        except Exception:
            message = self.message_template
        logger = getattr(self.window, "console_log", None)
        if callable(logger):
            logger(message)
        else:
            print(f"[Mesh][ListenForEvent] {message}")

    def _forward_event(self, payload: Dict[str, Any]) -> None:
        window_emit = getattr(self.window, "emit_signal", None)
        if not callable(window_emit):
            return
        try:
            window_emit(self.forward_as, **payload)
        except Exception as exc:  # noqa: BLE001  # REASON: event forwarding failures should be reported without breaking the source event reaction
            print(f"[Mesh][ListenForEvent] ERROR forwarding '{self.forward_as}': {exc}")
