"""Awards XP to the player when this entity dies."""

from __future__ import annotations

from typing import Any

from ..events import MeshEventBus
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "GrantExperience",
    description="Grants experience to the player when this entity dies.",
    config_fields=[
        {"name": "xp", "type": "int", "default": 10, "description": "XP awarded on death"},
        {"name": "event", "type": "string", "default": "died", "description": "Event name to listen for"},
        {"name": "target_tag", "type": "string", "default": "player", "description": "Tag of player to reward"},
    ],
)
class GrantExperience(Behaviour):
    PARAM_DEFS = {
        "xp": ParamDef(int, default=10, description="XP awarded on death"),
        "event": ParamDef(str, default="died", description="Event name to listen for"),
        "target_tag": ParamDef(str, default="player", description="Player tag to reward"),
    }

    def __init__(self, entity: Any, window: Any, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self.xp_amount = int(self.config.get("xp", 10))
        self.event_name = str(self.config.get("event", "died") or "died")
        self.target_tag = str(self.config.get("target_tag", "player") or "player")
        self._subscription = None
        bus = getattr(window, "event_bus", None)
        if isinstance(bus, MeshEventBus) and self.event_name:
            self._subscription = bus.subscribe(self.event_name, self._on_event)

    def _on_event(self, event) -> None:
        payload = getattr(event, "payload", {}) or {}
        actor = payload.get("actor")
        if actor is None or actor is not self.entity:
            return
        gs = getattr(self.window, "game_state_controller", None)
        if gs is None:
            return
        gs.add_xp(self.xp_amount)

    def on_destroy(self) -> None:
        bus = getattr(self.window, "event_bus", None)
        if bus is not None and self._subscription is not None:
            try:
                bus.unsubscribe(self._subscription)
            except Exception as exc:  # noqa: BLE001
                if not getattr(self, "_mesh_unsubscribe_error_logged", False):
                    print(f"[Mesh][GrantExperience] ERROR unsubscribing: {exc}")
                    setattr(self, "_mesh_unsubscribe_error_logged", True)
        super().on_destroy()
