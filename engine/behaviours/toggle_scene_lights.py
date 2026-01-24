"""Behaviour that toggles scene lights by group or indices when an event fires."""

from __future__ import annotations

from typing import Any, List

from ..events import MeshEventBus
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "ToggleSceneLights",
    description="Toggle or force on/off one or more scene lights in response to an event.",
    config_fields=[
        {
            "name": "listen_event",
            "type": "string",
            "default": "",
            "description": "Name of the event to listen for.",
        },
        {
            "name": "group",
            "type": "string",
            "default": "",
            "description": "Optional group name to match lights by their 'group' field.",
        },
        {
            "name": "indices",
            "type": "list[int]",
            "default": [],
            "description": "Optional list of indices into scene['lights'].",
        },
        {
            "name": "mode",
            "type": "string",
            "default": "toggle",
            "description": "One of 'toggle', 'on', 'off'.",
        },
    ],
)
class ToggleSceneLights(Behaviour):
    """Toggle scene lights when an event is emitted."""

    PARAM_DEFS = {
        "listen_event": ParamDef(str, default="", description="Event name to listen for."),
        "group": ParamDef(str, default="", description="Lights group name."),
        "indices": ParamDef(list, default=[], description="Indices into scene['lights']."),
        "mode": ParamDef(str, default="toggle", description="'toggle', 'on', or 'off'."),
    }

    def __init__(self, entity, window, **config: Any) -> None:  # noqa: ANN001
        super().__init__(entity, window, **config)
        self._listen_event: str = self.config.get("listen_event", "") or ""
        self._group: str = self.config.get("group", "") or ""
        indices = self.config.get("indices", []) or []
        self._indices = [int(i) for i in indices if isinstance(i, (int, float, str))]
        self._mode: str = (self.config.get("mode", "toggle") or "toggle").lower()

        self._subscription = None
        if self._listen_event:
            bus = getattr(self.window, "event_bus", None)
            if isinstance(bus, MeshEventBus):
                self._subscription = bus.subscribe(self._listen_event, self._on_event)

    def _on_event(self, event: Any) -> None:
        scene_controller = getattr(self.window, "scene_controller", None)
        if scene_controller is None or not hasattr(scene_controller, "_loaded_scene_data"):
            return
        scene = scene_controller._loaded_scene_data or {}
        lights = scene.setdefault("lights", [])
        if not isinstance(lights, list) or not lights:
            return

        target_indices: List[int] = []
        if self._indices:
            for i in self._indices:
                if 0 <= i < len(lights):
                    target_indices.append(i)
        if self._group:
            for idx, light in enumerate(lights):
                if str(light.get("group", "")) == self._group:
                    target_indices.append(idx)

        if not target_indices:
            return

        changed = False
        for idx in target_indices:
            light = lights[idx]
            current = bool(light.get("enabled", True))
            if self._mode == "on":
                new_state = True
            elif self._mode == "off":
                new_state = False
            else:
                new_state = not current
            if new_state != current:
                light["enabled"] = new_state
                changed = True

        if not changed:
            return

        lighting = getattr(self.window, "lighting", None)
        if lighting is not None:
            try:
                lighting.configure_scene_lights(lights)
            except Exception as exc:  # noqa: BLE001
                if not getattr(self, "_mesh_configure_scene_lights_error_logged", False):
                    print(f"[Mesh][ToggleSceneLights] ERROR configuring scene lights: {exc}")
                    setattr(self, "_mesh_configure_scene_lights_error_logged", True)

    def on_destroy(self) -> None:
        bus = getattr(self.window, "event_bus", None)
        if self._subscription is not None and isinstance(bus, MeshEventBus):
            try:
                bus.unsubscribe(self._subscription)
            except Exception as exc:  # noqa: BLE001
                if not getattr(self, "_mesh_unsubscribe_error_logged", False):
                    print(f"[Mesh][ToggleSceneLights] ERROR unsubscribing: {exc}")
                    setattr(self, "_mesh_unsubscribe_error_logged", True)
        super().on_destroy()
