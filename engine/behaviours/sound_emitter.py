"""A sound in the world (Milestone 21B): the object is a sound emitter (``engine.sound_emitters``).

It registers with the room's soundscape as it is made; the soundscape plays it louder as the listener comes near and
quieter as they go (its ``radius`` and ``distance``), from their side if ``stereo``. It has no picture in the game:
Mesh Studio shows where it is and how far it reaches while editing, never in play."""

from __future__ import annotations

from typing import Any

from engine import sound_emitters

from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "SoundEmitter",
    description="A sound in the world, louder near it: water, birds, a humming machine (Studio: the Sound object).",
    config_fields=[
        {"name": "sound", "description": "The sound file (.wav plays everywhere; .ogg, .mp3)", "type": "string",
         "default": ""},
        {"name": "volume", "description": "Volume at full strength (0-1)", "type": "float", "default": 0.8},
        {"name": "radius", "description": "Full strength within this distance (px)", "type": "float", "default": 64.0},
        {"name": "distance", "description": "Heard up to this distance (px)", "type": "float", "default": 320.0},
    ],
)
class SoundEmitter(Behaviour):
    PARAM_DEFS = {  # what engine.sound_emitters.parse_emitter reads (checked there; Studio and AI: project_ops)
        "sound": ParamDef(str, default="", description="The sound file"),
        "volume": ParamDef(float, default=0.8, description="Volume at full strength (0-1)"),
        "radius": ParamDef(float, default=64.0, description="Full strength within this distance (px)"),
        "distance": ParamDef(float, default=320.0, description="Heard up to this distance (px)"),
        "stereo": ParamDef(bool, default=True, description="Heard from its side"),
        "loop": ParamDef(bool, default=True, description="Plays round (off: once each time the listener comes near)"),
        "enabled": ParamDef(bool, default=True, description="On"),
        "fade_in": ParamDef(float, default=1.0, description="Fade in (s)"),
        "fade_out": ParamDef(float, default=1.0, description="Fade out (s)"),
    }

    def __init__(self, entity: Any, window: Any, **config: Any) -> None:
        super().__init__(entity, window, **{k: v for k, v in config.items() if k in self.PARAM_DEFS})
        if not getattr(entity, "mesh_entity_data", {}).get("sprite"):
            entity.mesh_drawn = False  # a sound: nothing to see in the game
        try:
            emitter = sound_emitters.parse_emitter({k: v for k, v in config.items() if k in self.PARAM_DEFS})
        except sound_emitters.EmitterError as exc:
            self._log(f"sound off: {exc}")
            return
        if emitter.sound:
            from engine.paths import resolve_path  # noqa: PLC0415

            if not resolve_path(emitter.sound).is_file():  # said once, here, not every frame
                self._log(f"sound {emitter.sound!r} not found: this emitter is silent")
                return
        self.emitter = emitter
        sound_emitters.soundscape_of(window).register(entity, emitter)

    def _log(self, message: str) -> None:
        from engine.logging_tools import get_logger  # noqa: PLC0415

        name = str(getattr(self.entity, "mesh_name", "") or "Sound")
        get_logger(__name__).error("[Mesh][Audio] %s: %s", name, message)
