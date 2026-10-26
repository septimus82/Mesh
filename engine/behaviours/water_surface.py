"""A puddle or a pond (Milestone 19A): the object is a water surface (``engine.water``).

It registers its water with the room (drawn by the HD-2D renderer, or in a 2D room by ``engine.water.draw_2d``) and
watches the characters it names (``target_tags``, the player by default): each step one takes through the water
starts a ripple and a few splash pixels where it lands, plays the water's ``step_sound`` if it has one, and announces
a ``water_step`` event (who, which water, where). Blocking ponds don't need it: ``project_ops.set_water`` makes a
pond that can't be walked through a solid object with a box the water's size, so the movement code stops characters.
"""

from __future__ import annotations

from typing import Any

from engine import water as water_mod
from engine.event_emit import emit_gameplay_event

from .base import Behaviour, ParamDef
from .registry import register_behaviour

STEP_PX = 14.0  # a footstep every this many px walked through water


@register_behaviour(
    "WaterSurface",
    description="A puddle or pond: drawn as water, rippled by rain and footsteps (Studio: the Water object).",
    config_fields=[
        {"name": "preset", "description": "muddy_puddle, natural_pond, stone_pool, or the simple puddle or pond",
         "type": "string", "default": "puddle"},
        {"name": "width", "description": "Width (px)", "type": "float", "default": 64.0},
        {"name": "height", "description": "Height (px)", "type": "float", "default": 40.0},
    ],
)
class WaterSurface(Behaviour):
    PARAM_DEFS = {  # what engine.water.parse_water reads (checked there; Studio and AI: project_ops.set_water)
        "preset": ParamDef(str, default="puddle",
                           description="muddy_puddle, natural_pond, stone_pool, or Stage 19A's simple puddle or pond"),
        "width": ParamDef(float, default=0.0, description="Width (px; 0: the preset's)"),
        "height": ParamDef(float, default=0.0, description="Height (px; 0: the preset's)"),
        "colour": ParamDef(str, default="", description="Colour (#rrggbb; empty: the preset's)"),
        "opacity": ParamDef(float, default=0.0, description="Opacity (0.05-1; 0: the preset's)"),
        "shape": ParamDef(str, default="", description="ellipse, rect or natural (empty: the preset's)"),
        "rotation": ParamDef(float, default=0.0, description="Turned by this many degrees, anticlockwise"),
        "seed": ParamDef(int, default=0, description="Which natural outline (1-9999; 0: the preset's)"),
        "shore": ParamDef(str, default="", description="The bank: none, mud, grass, stone, or terrain (the sculpted ground; empty: the preset's)"),
        "shore_width": ParamDef(float, default=-1.0, description="The bank's width (px, 0-64; -1: the preset's)"),
        "deep_colour": ParamDef(str, default="", description="Colour where deep (#rrggbb; empty: the preset's)"),
        "depth": ParamDef(float, default=-1.0, description="How soon it gets deep, 0-1 (-1: the preset's)"),
        "ripples": ParamDef(float, default=-1.0, description="Rain and footstep ripple strength, 0-1 (-1: the preset's)"),
        "waves": ParamDef(float, default=-1.0, description="How much it moves (0-1; -1: the preset's)"),
        "reflection": ParamDef(float, default=-1.0, description="How much it mirrors (0-1; -1: the preset's)"),
        "rain_ripples": ParamDef(bool, default=True, description="The room's rain rings it"),
        "walkable": ParamDef(bool, default=True, description="Characters walk through it (false: it blocks)"),
        "step_sound": ParamDef(str, default="", description="A sound played on each step through it"),
        "target_tags": ParamDef(list, default=[], description="Tags of the characters whose steps splash (player)"),
    }

    def __init__(self, entity: Any, window: Any, **config: Any) -> None:
        settings = {k: v for k, v in config.items() if k in water_mod._KEYS}  # UNSET values: parse_water's
        super().__init__(entity, window, **{k: v for k, v in config.items() if k in self.PARAM_DEFS})
        self.entity_name = str(getattr(entity, "mesh_name", "") or "Water")
        try:
            self.water: water_mod.Water | None = water_mod.parse_water(settings)
        except water_mod.WaterError as exc:
            self.water = None
            self._log(f"water off: {exc}")
            return
        tags = config.get("target_tags")
        self.tags = {str(t) for t in tags} if isinstance(tags, list) and tags else {"player"}
        self._last: dict[int, tuple[float, float]] = {}  # character -> where its last splash was (px)
        self.steps = 0
        self.sound = self.water.step_sound
        if self.sound:
            from engine.paths import resolve_path  # noqa: PLC0415

            if not resolve_path(self.sound).is_file():  # said once, not on every step
                self._log(f"step sound {self.sound!r} not found: steps are silent")
                self.sound = ""
        if not getattr(entity, "mesh_entity_data", {}).get("sprite"):
            entity.mesh_drawn = False  # the water is its picture
        bodies = getattr(window, "water_bodies", None)
        if bodies is None:
            bodies = window.water_bodies = []
        bodies.append(water_mod.Body(entity, self.water))

    def update(self, dt: float) -> None:
        water = self.water
        scene = getattr(self.window, "scene_controller", None)
        if water is None or scene is None or not water_mod.active(self.window, self.entity):
            return  # (not there now: its "Show when" flags hide it)
        centre = (float(self.entity.center_x), float(self.entity.center_y))
        for sprite in list(getattr(scene, "all_sprites", None) or []):
            if getattr(sprite, "mesh_tag", None) not in self.tags:
                continue
            feet = (float(sprite.center_x), float(sprite.bottom))
            key = id(sprite)
            if not water_mod.inside(water, centre, feet):
                self._last.pop(key, None)
                continue
            last = self._last.get(key)
            if last is not None and (feet[0] - last[0]) ** 2 + (feet[1] - last[1]) ** 2 < STEP_PX ** 2:
                continue
            self._last[key] = feet
            self._step(sprite, feet)

    def _step(self, sprite: Any, feet: tuple[float, float]) -> None:
        self.steps += 1
        water_mod.add_step(self.window, feet[0] / water_mod.PX_PER_M, feet[1] / water_mod.PX_PER_M)
        if self.sound:
            audio = getattr(self.window, "audio", None)
            if audio is not None and hasattr(audio, "play_world_sfx"):
                audio.play_world_sfx(self.sound, feet, window=self.window, base_volume=0.6)
        emit_gameplay_event(self.window, "water_step",
                            {"who": str(getattr(sprite, "mesh_name", "") or ""), "water": self.entity_name,
                             "x": round(feet[0], 1), "y": round(feet[1], 1)},
                            source_entity_id=str(getattr(self.entity, "mesh_id", "") or ""),
                            source_behaviour="WaterSurface")

    def _log(self, message: str) -> None:
        from engine.logging_tools import get_logger  # noqa: PLC0415

        get_logger(__name__).error("[Mesh][Water] %s: %s", self.entity_name, message)
