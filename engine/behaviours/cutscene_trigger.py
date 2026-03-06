"""Behaviour that starts a cutscene when an event is received."""

from __future__ import annotations

from typing import Any

from ..events import MeshEventBus
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "CutsceneTrigger",
    description="Starts a cutscene when the configured event fires.",
    config_fields=[
        {"name": "listen_event", "type": "string", "default": "cutscene", "description": "Event to listen for"},
        {"name": "cutscene_id", "type": "string", "default": "", "description": "Cutscene id to play"},
    ],
)
class CutsceneTrigger(Behaviour):
    PARAM_DEFS = {
        "listen_event": ParamDef(str, default="cutscene", description="Event name to listen for"),
        "cutscene_id": ParamDef(str, default="", description="Cutscene id to play"),
    }

    def __init__(self, entity: Any, window: Any, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self._event_name = str(self.config.get("listen_event", "cutscene") or "cutscene")
        self._cutscene_id = str(self.config.get("cutscene_id", "") or "")
        self._subscription = None
        bus = getattr(window, "event_bus", None)
        if isinstance(bus, MeshEventBus) and self._event_name:
            self._subscription = bus.subscribe(self._event_name, self._on_event)

    def _on_event(self, event: Any) -> None:
        if not self._cutscene_id:
            return
        controller = getattr(self.window, "cutscene_controller", None)
        if controller is not None:
            controller.play_cutscene(self._cutscene_id)

    def on_destroy(self) -> None:
        bus = getattr(self.window, "event_bus", None)
        if bus is not None and self._subscription is not None:
            try:
                bus.unsubscribe(self._subscription)
            except Exception as exc:  # noqa: BLE001
                if not getattr(self, "_mesh_unsubscribe_error_logged", False):
                    print(f"[Mesh][CutsceneTrigger] ERROR unsubscribing: {exc}")
                    setattr(self, "_mesh_unsubscribe_error_logged", True)
        super().on_destroy()
