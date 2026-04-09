from __future__ import annotations

from typing import Any

from ..events import MeshEventBus
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "QuestGiver",
    description="Starts a quest when an event occurs (e.g. after talking to an NPC).",
    config_fields=[
        {
            "name": "quest_id",
            "type": "string",
            "default": "",
            "description": "Quest id to start.",
        },
        {
            "name": "listen_event",
            "type": "string",
            "default": "quest_start",
            "description": "Event name to listen for.",
        },
        {
            "name": "auto_activate",
            "type": "bool",
            "default": True,
            "description": "Immediately start the quest when event fires.",
        },
    ],
)
class QuestGiver(Behaviour):
    PARAM_DEFS = {
        "quest_id": ParamDef(str, default="", description="Quest id to start."),
        "listen_event": ParamDef(str, default="quest_start", description="Event to listen for."),
        "auto_activate": ParamDef(bool, default=True, description="If true, start quest on event."),
    }

    def __init__(self, entity, window, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self._quest_id: str = self.config.get("quest_id", "") or ""
        self._listen_event: str = self.config.get("listen_event", "quest_start") or "quest_start"
        self._subscription = None
        bus = getattr(window, "event_bus", None)
        if bus is not None and isinstance(bus, MeshEventBus) and self._listen_event:
            self._subscription = bus.subscribe(self._listen_event, self._on_event)

    def _on_event(self, event: Any) -> None:
        if not self._quest_id:
            return
        gs = getattr(self.window, "game_state_controller", None)
        if gs is None or getattr(gs, "quests", None) is None:
            return
        gs.quests.start_quest(self._quest_id)

    def on_destroy(self) -> None:
        bus = getattr(self.window, "event_bus", None)
        if bus is not None and self._subscription is not None:
            try:
                bus.unsubscribe(self._subscription)
            except Exception as exc:  # noqa: BLE001  # REASON: teardown unsubscribe failures should not block entity cleanup
                if not getattr(self, "_mesh_unsubscribe_error_logged", False):
                    print(f"[Mesh][QuestGiver] ERROR unsubscribing: {exc}")
                    setattr(self, "_mesh_unsubscribe_error_logged", True)
        on_destroy = getattr(super(), "on_destroy", None)
        if callable(on_destroy):
            on_destroy()
