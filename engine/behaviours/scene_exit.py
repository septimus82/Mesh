from __future__ import annotations

from typing import Any

from ..events import MeshEventBus
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "SceneExit",
    description="Triggers a scene change to a target scene/spawn when an event fires.",
    config_fields=[
        {
            "name": "listen_event",
            "type": "string",
            "default": "use_exit",
            "description": "Event name to listen for (e.g. from TriggerZone or Interact).",
        },
        {
            "name": "target_scene",
            "type": "string",
            "default": "",
            "description": "Path to the target scene JSON.",
        },
        {
            "name": "target_spawn",
            "type": "string",
            "default": "",
            "description": "Spawn id in the target scene.",
        },
    ],
)
class SceneExit(Behaviour):
    PARAM_DEFS = {
        "listen_event": ParamDef(str, default="use_exit", description="Event name to listen for."),
        "target_scene": ParamDef(str, default="", description="Target scene path."),
        "target_spawn": ParamDef(str, default="", description="Target spawn id."),
    }

    def __init__(self, entity, window, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self._listen_event: str = self.config.get("listen_event", "use_exit") or "use_exit"
        self._target_scene: str = self.config.get("target_scene", "") or ""
        self._target_spawn: str | None = self.config.get("target_spawn", "") or None

        self._subscription = None
        bus = getattr(window, "event_bus", None)
        if bus is not None and isinstance(bus, MeshEventBus) and self._listen_event:
            self._subscription = bus.subscribe(self._listen_event, self._on_event)

    def _on_event(self, event: Any) -> None:
        if not self._target_scene:
            return
        scene_controller = getattr(self.window, "scene_controller", None)
        if scene_controller is None:
            return
        scene_controller.queue_scene_change(self._target_scene, self._target_spawn)

    def on_destroy(self) -> None:
        bus = getattr(self.window, "event_bus", None)
        if bus is not None and self._subscription is not None:
            try:
                bus.unsubscribe(self._subscription)
            except Exception as exc:  # noqa: BLE001
                if not getattr(self, "_mesh_unsubscribe_error_logged", False):
                    print(f"[Mesh][SceneExit] ERROR unsubscribing: {exc}")
                    setattr(self, "_mesh_unsubscribe_error_logged", True)
        on_destroy = getattr(super(), "on_destroy", None)
        if callable(on_destroy):
            on_destroy()
