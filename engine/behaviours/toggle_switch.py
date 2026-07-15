"""Simple interactable toggle switch behaviour."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from arcade import Sprite

from ..events import MeshEvent
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "ToggleSwitch",
    description="Simple interactable switch that flips state and emits an event.",
    config_fields=[
        {
            "name": "allowed_tag",
            "description": "Sprite tag allowed to toggle the switch",
            "type": "string",
            "default": "player",
        },
        {
            "name": "label",
            "description": "Friendly name used in logs",
            "type": "string",
            "default": "",
        },
        {
            "name": "initial_state",
            "description": "Starting ON/OFF state",
            "type": "bool",
            "default": False,
        },
    ],
)
class ToggleSwitch(Behaviour):
    """Toggles an internal state and emits an event when interacted with."""

    PARAM_DEFS = {
        "allowed_tag": ParamDef(str, default="player", description="Sprite tag allowed to toggle the switch"),
        "label": ParamDef(str, default="", description="Friendly name used in logs"),
        "initial_state": ParamDef(bool, default=False, description="Starting ON/OFF state"),
    }

    def __init__(self, entity: Sprite, window, **config) -> None:
        merged: Dict[str, Any] = dict(getattr(entity, "mesh_entity_data", {}) or {})
        if config:
            merged.update(config)
        super().__init__(entity, window, **merged)

        raw_tag = self.config.get("allowed_tag", "player")
        self.allowed_tag = str(raw_tag).strip() if raw_tag not in (None, "") else None
        label_source = self.config.get("label") or getattr(entity, "mesh_name", "Switch")
        self.label = str(label_source)
        self.state = bool(self.config.get("initial_state", False))

    def on_interact(self, window, actor: Sprite) -> None:
        if self.allowed_tag:
            actor_tag = getattr(actor, "mesh_tag", None)
            if actor_tag != self.allowed_tag:
                return

        self.state = not self.state
        payload = {
            "name": getattr(self.entity, "mesh_name", "<unnamed>"),
            "label": self.label,
            "state": self.state,
            "position": (float(self.entity.center_x), float(self.entity.center_y)),
        }
        window.emit_event(MeshEvent(type="switch_toggled", payload=payload))
        window.console_log(f"{self.label} toggled {'ON' if self.state else 'OFF'}")

    def can_interact_with(self, actor: Sprite) -> bool:
        if not self.allowed_tag:
            return True
        return getattr(actor, "mesh_tag", None) == self.allowed_tag

    def get_interact_label(self, _actor: Sprite | None = None) -> str | None:
        return self.label
