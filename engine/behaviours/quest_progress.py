"""Behaviour that advances quests when specific events fire."""

from __future__ import annotations

from typing import Any, Dict

from ..events import MeshEvent
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "QuestProgressOnEvent",
    description=(
        "Listens for a Mesh event and forwards it to the QuestManager to start,"
        " advance, or complete a quest stage."
    ),
    config_fields=[
        {
            "name": "quest_id",
            "description": "Quest identifier that should be updated",
            "type": "string",
            "default": "",
        },
        {
            "name": "action",
            "description": "Action to perform (start, set_stage, complete_stage, complete_quest)",
            "type": "string",
            "default": "complete_stage",
        },
        {
            "name": "stage_id",
            "description": "Optional stage to target (falls back to current stage)",
            "type": "string",
            "default": "",
        },
        {
            "name": "event_type",
            "description": "Mesh event that should trigger the quest update",
            "type": "string",
            "default": "",
        },
        {
            "name": "payload_field",
            "description": "Payload key that must be present on the event",
            "type": "string",
            "default": "",
        },
        {
            "name": "payload_value",
            "description": "Optional value that payload_field must equal",
            "type": "string",
            "default": "",
        },
        {
            "name": "payload_equals",
            "description": "Object of payload key/value pairs that must match",
            "type": "object",
            "default": {},
        },
        {
            "name": "once",
            "description": "If true the behaviour only fires the first time",
            "type": "bool",
            "default": False,
        },
    ],
)
class QuestProgressOnEvent(Behaviour):
    """Bridges arbitrary events into the quest runtime."""

    PARAM_DEFS = {
        "quest_id": ParamDef(str, default="", description="Quest identifier that should be updated"),
        "action": ParamDef(str, default="complete_stage", description="Action to perform"),
        "stage_id": ParamDef(str, default="", description="Optional stage to target"),
        "event_type": ParamDef(str, default="", description="Mesh event that should trigger the quest update"),
        "payload_field": ParamDef(str, default="", description="Payload key that must be present"),
        "payload_value": ParamDef(str, default="", description="Optional value that payload_field must equal"),
        "payload_equals": ParamDef(dict, default={}, description="Object of payload key/value pairs that must match"),
        "once": ParamDef(bool, default=False, description="If true the behaviour only fires the first time"),
    }

    def __init__(self, entity: Any, window: Any, **config: Any) -> None:
        merged: Dict[str, Any] = dict(getattr(entity, "mesh_entity_data", {}) or {})
        if config:
            merged.update(config)
        super().__init__(entity, window, **merged)

        self.quest_id = str(merged.get("quest_id", "")).strip()
        self.action = str(merged.get("action", "complete_stage"))
        self.stage_id = str(merged.get("stage_id", "")).strip() or None
        self.event_type = str(merged.get("event_type", "")).strip()
        self.payload_field = str(merged.get("payload_field", "")).strip()
        payload_value = merged.get("payload_value", "")
        self.payload_value = str(payload_value).strip() if payload_value not in (None, "") else None
        payload_equals = merged.get("payload_equals")
        if not isinstance(payload_equals, dict):
            payload_equals = {}
        self.payload_equals = {str(key): value for key, value in payload_equals.items() if str(key)}
        self.once = bool(merged.get("once", False))
        self._fired = False

    def subscribed_event_types(self) -> frozenset[str] | None:
        return frozenset({self.event_type}) if self.event_type else frozenset()

    def on_event(self, event: MeshEvent) -> None:  # noqa: D401
        if self.once and self._fired:
            return
        if not self.quest_id or not self.event_type:
            return
        if event.type != self.event_type:
            return
        payload = event.payload or {}
        if self.payload_field:
            if self.payload_field not in payload:
                return
            if self.payload_value is not None and payload.get(self.payload_field) != self.payload_value:
                return
        for key, value in self.payload_equals.items():
            if payload.get(key) != value:
                return
        manager = getattr(self.window, "quest_manager", None)
        if manager is None:
            return
        success = manager.request_progress(self.quest_id, self.action, self.stage_id)
        if success and self.once:
            self._fired = True
