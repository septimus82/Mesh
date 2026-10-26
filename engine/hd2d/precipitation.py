"""Precipitation maps (Milestone 18B): where falling rain and snow meet the world, independent of the camera.

A precipitation map is an orthographic depth map looking along a fall direction (down, tilted by the wind), drawn
from the room's real geometry: its ground and every structure (roofs, decks, stairs, terraces, walls), structures
being dragged in Mesh Studio included. Its depth at a column is the first surface a drop falling along that direction
meets, so the particle shader can tell a drop still falling (above it) from one that has landed or is under shelter
(past it), and where it landed. That is shelter, not the camera's depth test: a drop under the bridge's deck is past
the deck whatever the camera sees.

- Its own matrix, resolution, program and lifecycle: the sun's direction, intensity, shadow softness or shadows
  switched off never change it (it borrows only ``sun_matrix``'s fitting and the casters' shaders).
- Every structure is drawn whole: a cutaway (the camera pass's see-through roof) opens no hole in the shelter.
- Billboards (characters, doors, lamps) are not in it: people don't shelter rain.
- A cache: one map per fall direction in use (at most one per falling effect), keyed by the direction quantised to
  ``STEP_DEG``, built the first time it's needed, dropped by ``invalidate`` (structures changed) and ``retain``
  (directions no longer used), freed by ``release``. A build that fails frees what it made, keeps the reason
  (``error``) and isn't retried while this renderer lasts (the room's next load tries again): the effect falls as
  in Stage 18A, without shelter.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable

from engine.hd2d.lighting import CASTER_FS, CASTER_VS, _column_major, sun_matrix

RESOLUTION = 1024  # texels a side: about 6 cm a texel over the starter village
STEP_DEG = 0.5  # fall directions this close share a map (an error of at most 12 m x tan(0.25 deg) = 5 cm)

Key = tuple[float, float]


@dataclass
class PrecipitationMap:
    direction: tuple[float, float, float]  # the fall (unit, pointing down) the map was drawn along: its key's
    vp: tuple[float, ...]  # world -> the map's clip space (column-major)
    depth_m: float  # metres along the fall per unit of the map's depth (0..1)
    depth: Any
    colour: Any
    fbo: Any

    def objects(self) -> list[Any]:
        return [self.fbo, self.depth, self.colour]


def key_for(fall: tuple[float, float, float]) -> Key:
    """The fall direction quantised: (tilt from straight down, heading of the tilt), degrees in STEP_DEG steps."""
    n = math.sqrt(sum(c * c for c in fall)) or 1.0
    x, y, z = (c / n for c in fall)
    tilt = round(math.degrees(math.acos(max(-1.0, min(1.0, -z)))) / STEP_DEG) * STEP_DEG
    heading = round(math.degrees(math.atan2(y, x)) / STEP_DEG) * STEP_DEG % 360.0 if tilt else 0.0
    return (tilt, heading)


def direction_of(key: Key) -> tuple[float, float, float]:
    tilt, heading = (math.radians(a) for a in key)
    return (math.sin(tilt) * math.cos(heading), math.sin(tilt) * math.sin(heading), -math.cos(tilt))


class PrecipitationMaps:
    """A renderer's precipitation maps (see the module's notes)."""

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.maps: dict[Key, PrecipitationMap] = {}
        self.failed: dict[Key, str] = {}
        self.program: Any = None
        self.builds = 0  # maps drawn since made (to see invalidations at work)
        self.build_ms: list[float] = []  # how long each took (CPU wall, until its draws were issued; no GPU wait)
        self.error: str | None = None  # the last build's failure, if any

    def get(self, fall: tuple[float, float, float], draws: Callable[[], list[tuple[Any, Any, tuple[float, ...]]]],
            lo: tuple[float, float, float], hi: tuple[float, float, float]) -> PrecipitationMap | None:
        """The map for this fall direction over the box (lo, hi), drawn from ``draws()`` (geometry, texture, model
        matrix; asked for only when a map is made) if it isn't cached; None if it can't be made."""
        key = key_for(fall)
        found = self.maps.get(key)
        if found is not None or key in self.failed:
            return found
        try:
            built = self._build(key, draws(), lo, hi)
        except Exception as exc:  # a driver that can't: shelter off for this direction, the room carries on
            self.failed[key] = self.error = f"precipitation map: {exc}"
            from engine.logging_tools import get_logger  # noqa: PLC0415

            get_logger(__name__).error("[Mesh][Particles] %s (rain and snow fall without shelter)", self.error)
            return None
        self.maps[key] = built
        return built

    def _build(self, key: Key, draws: list[tuple[Any, Any, tuple[float, ...]]], lo: tuple[float, float, float],
               hi: tuple[float, float, float]) -> PrecipitationMap:
        ctx = self.ctx
        start = time.perf_counter()
        if self.program is None:
            self.program = ctx.program(vertex_shader=CASTER_VS, fragment_shader=CASTER_FS)
        fall = direction_of(key)
        m = sun_matrix((-fall[0], -fall[1], -fall[2]), lo, hi)  # looking along the fall, from the sky
        depth_m = 2.0 / math.sqrt(m[2][0] ** 2 + m[2][1] ** 2 + m[2][2] ** 2)  # the ortho's far - near
        made: list[Any] = []
        try:
            depth = ctx.depth_texture((RESOLUTION, RESOLUTION))
            made.append(depth)
            depth.compare_func = None  # read as depth, compared in the particle shader
            depth.filter = (ctx.NEAREST, ctx.NEAREST)
            colour = ctx.texture((RESOLUTION, RESOLUTION), components=1, dtype="u1")  # arcade's fbos need one
            made.append(colour)
            fbo = ctx.framebuffer(color_attachments=[colour], depth_attachment=depth)
            made.append(fbo)
            previous = ctx.active_framebuffer
            try:
                fbo.use()
                fbo.clear(depth=1.0)
                ctx.enable(ctx.DEPTH_TEST)
                ctx.disable(ctx.CULL_FACE)
                vp = _column_major(m)
                self.program["u_vp"] = vp
                for geometry, _texture, matrix in draws:
                    self.program["u_model"] = matrix
                    geometry.render(self.program)
            finally:
                previous.use()
        except BaseException:
            for obj in reversed(made):
                obj.delete()
            raise
        self.builds += 1
        self.build_ms.append((time.perf_counter() - start) * 1000)
        del self.build_ms[:-64]
        return PrecipitationMap(fall, vp, depth_m, depth, colour, fbo)

    def retain(self, keys: set[Key]) -> None:
        """Free the maps for directions no effect uses now."""
        for key in [k for k in self.maps if k not in keys]:
            self._free(key)

    def invalidate(self) -> None:
        """The structures changed (moved, edited, reimported): every map is drawn again when next needed. A
        direction whose map couldn't be made stays failed (no retrying every frame of a Studio drag): the room's
        next load (a new renderer) tries again."""
        for key in list(self.maps):
            self._free(key)

    def _free(self, key: Key) -> None:
        for obj in self.maps.pop(key).objects():
            obj.delete()

    def release(self) -> None:
        self.invalidate()
        self.failed.clear()
        self.error = None
        if self.program is not None:
            self.program.delete()
            self.program = None

    def gl_objects(self) -> list[Any]:
        return [o for m in self.maps.values() for o in m.objects()] + ([self.program] if self.program else [])

    def memory_bytes(self) -> int:
        return len(self.maps) * RESOLUTION * RESOLUTION * (4 + 1)  # 32-bit depth, the 1-byte colour arcade wants
