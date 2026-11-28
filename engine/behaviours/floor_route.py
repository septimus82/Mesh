"""FloorRoute: an HD-2D character walks a route of points on different floors, finding its way over stairs and
bridges (Milestone 16 Stage 3).

The walk itself (route legs, waits, walking out of water it can't stand in, being stranded, backing off a point it
can't get through to) is ``engine.hd2d.route.FloorRoute``, one graphics-free model the net authority runs for its
enemies too (M4-4, owner decision OD7). This behaviour is its adapter: it hands the model the window's HD-2D World and
solid sprites each frame, and says what the model reports in the log, and as a ``stranded`` gameplay event
(``mesh_hd2d_stranded`` on the character). In a 2D scene (no HD-2D floors) it does nothing.
"""

from __future__ import annotations

from typing import Any

from engine.hd2d.route import SPEED, WAIT, FloorRoute
from engine.log_utils import get_logger

from .base import Behaviour, ParamDef
from .registry import register_behaviour

logger = get_logger(__name__)


@register_behaviour(
    "FloorRoute",
    description="HD-2D: walks between points on different floors, using stairs and bridges.",
    config_fields=[
        {"name": "route", "description": "Points to visit in turn: [x, y, elevation] in px", "type": "array",
         "default": []},
        {"name": "speed", "description": "Walking speed (px per second)", "type": "float", "default": SPEED},
        {"name": "wait", "description": "Seconds to stand at each point", "type": "float", "default": WAIT},
    ],
)
class FloorRouteBehaviour(Behaviour):
    PARAM_DEFS = {
        "route": ParamDef(list, default=[], description="Points to visit in turn: [x, y, elevation] in px"),
        "speed": ParamDef(float, default=SPEED, description="Walking speed (px per second)"),
        "wait": ParamDef(float, default=WAIT, description="Seconds to stand at each point"),
    }

    def __init__(self, entity: Any, window: Any, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self.model = FloorRoute.from_config(self.config, on_stuck=self._said_stuck, on_strand=self._stranded)

    def update(self, dt: float) -> None:
        solids = getattr(getattr(self.window, "scene_controller", None), "solid_sprites", None)
        self.model.update(getattr(self.window, "hd2d_world", None), self.entity, dt, solids)  # (a 2D scene: None)

    def _said_stuck(self, sprite: Any, point: tuple[float, float]) -> None:
        logger.warning("[Mesh][HD-2D] %s can't get through to its next point at %s: trying later",
                       getattr(sprite, "mesh_name", "") or "a character", point)

    def _stranded(self, sprite: Any, where: str, fx: float, fy: float) -> None:
        logger.warning("[Mesh][HD-2D] %s is stranded: it can't walk out of the water at %s",
                       getattr(sprite, "mesh_name", "") or "a character", where)
        from engine.event_emit import emit_gameplay_event  # noqa: PLC0415

        emit_gameplay_event(self.window, "stranded", {"who": str(getattr(sprite, "mesh_name", "") or ""),
                                                      "x": round(fx, 1), "y": round(fy, 1)},
                            source_entity_id=None, source_behaviour="FloorRoute")
