"""Mesh Studio's 3D view of an HD-2D room (Milestone 16 Stage 5A).

When the open room has ``settings.hd2d``, Mesh Studio's canvas shows the room as the game draws it: the game's own
HD-2D renderer (``window.hd2d_renderer``, built when the room loads, as for Play) draws it into the canvas with the
editor's camera, so Edit and Play show the same structures, textures, characters, lighting and shadows. The game's
camera is not touched; this view's camera (``self.camera``) belongs to the editor.

What the creator does here:
- **look around**: middle-drag pans, the wheel zooms, Q / E turn the view, Home resets it, F frames the selection;
  the 3D view section in the left panel has the same as buttons;
- **select**: a click picks what is under the mouse in 3D (``engine.hd2d.picking``: rays against the structures'
  real triangles and the characters' billboards, nearest wins), so overlapping things pick as seen; a structure
  gets a box, a character the ordinary object inspector;
- **move**: drag a structure (or a character) over the ground, snapped to a 0.5 m grid unless snapping is off; the
  inspector raises, lowers and turns it and takes exact values in metres and degrees;
- **place objects**: a person, sign or other object chosen in the Objects list is placed by clicking a floor in 3D
  (the ground, a platform, a bridge deck, a landing): it stands at that floor's height (``elevation``), so the game
  puts it on that floor. A spot nobody could stand on (inside a wall, under a low deck) is refused with the reason;
  while choosing, a green square shows where it would stand;
- **place**: the Models browser ("Models..." in the 3D view section) lists the project's Blender models with their
  pictures; "Place in scene" makes the chosen one follow the mouse until a click places it, turned and scaled as the
  model's defaults say;
- **import and reimport** (Stage 5B): "Import 3D model..." checks a .glb exported from Blender, shows what it holds
  and a picture of it, and copies it into the project's catalogue (``engine.hd2d.catalog``); "Reimport" replaces a
  model's file with a new export after saying what changes (collision, floors, characters left without room to
  stand), and every placed copy keeps its id and place.

Every change to a room is one ``project_ops`` operation through Mesh Studio's ordinary edit path (``Studio._edit``):
one undo step, saved with the room, the same operations AI tools propose. Importing writes model files straight
away, like importing a picture or a tileset (not an undo step); it never overwrites, and a failure writes nothing.
A 2D room never creates this view's state or draws through it.
"""

from __future__ import annotations

import math
import time
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade
from engine import project_ops as ops
from engine.hd2d.picking import Picker, box, box_edges, ground_point
from engine.hd2d.renderer import Camera
from engine.hd2d.settings import PIXELS_PER_METRE
from engine.studio_inspector import LazyRow
from engine.studio_ui import C_ERROR, C_MUTED, C_WARN, S_ACTIVE, S_BUTTON, gui

if TYPE_CHECKING:
    from engine.studio import Studio

GRID_M = 0.5  # metres: where moved structures snap
TURN_DEG = 45.0  # one press of Q / E
STEP_UP_M = 0.5  # one press of Raise / Lower
DEFAULT_PITCH, DEFAULT_YAW = 40.0, 0.0


def _row() -> Any:
    return gui.UIBoxLayout(vertical=False, space_between=4)


def _snap(value_m: float, on: bool) -> float:
    return round(value_m / GRID_M) * GRID_M if on else value_m


class Hd2dView:
    def __init__(self, studio: Studio) -> None:
        self.studio = studio
        self.camera = Camera(DEFAULT_PITCH, 30.0, 22.0, False, DEFAULT_YAW)
        self.structure: str | None = None  # the selected structure's id
        self.drag: dict[str, Any] | None = None
        self.placing: str | None = None  # a model being placed (follows the mouse)
        self.placing_turn, self.placing_scale = 0.0, 1.0  # ... with its catalogue defaults
        self.chosen_model: str | None = None  # the model browser's selection (an asset id)
        self.model_filter = ""
        self.import_form: dict[str, Any] = {"path": "", "name": "", "category": "", "license": "", "sharp": True}
        self.reimport_form: dict[str, Any] = {"id": None, "path": ""}
        self._assets: list[Any] | None = None  # the catalogue as last read (None: read it again)
        self._facts: dict[tuple[str, int, int], tuple[Any | None, str | None]] = {}  # (file, mtime, size) -> (report, problem)
        self.object_marker: tuple[float, float, float] | None = None  # where an object being placed would stand (m)
        self.snap = True
        self.weather = True  # Milestone 18B, "Preview weather": the room's rain, snow or leaves in this view too
        self.picker = Picker()
        self.tips: list[tuple[Any, str]] = []  # (button, short tooltip) for the 3D view's buttons
        self._room: str | None = None
        self._buried: set[str] = set()  # objects that can't stand where they are (inside a structure)
        self.newly_buried: list[str] = []  # ... since the last load: what the last change did
        self.timings: dict[str, list[float]] = {"draw_ms": [], "pick_ms": [], "edit_ms": [], "sculpt_ms": []}
        # Milestone 20A (prototype): sculpting the ground, a click at a time; None: not sculpting
        self.sculpt: dict[str, Any] | None = None  # {"tool", "radius" px, "rate" (a second's worth), "target" px}
        self.stroke: dict[str, Any] | None = None  # a live stroke while the mouse is held (Milestone 20B)
        self._redraw: set[tuple[int, int]] = set()  # chunks a cancelled stroke changed, still to be drawn again
        self.sculpt_at: tuple[float, float, float] | None = None  # the ground under the mouse (m)
        self.unsettled: list[str] = []  # objects the last stroke left off the ground (ids): "Settle on the ground"
        self._grid: tuple[Any, list[tuple[float, float, float]]] = (None, [])  # the 1 m grid over sculpted ground

    # ------------------------------------------------------------------ state
    @property
    def renderer(self) -> Any | None:
        return getattr(self.studio.window, "hd2d_renderer", None)

    @property
    def active(self) -> bool:
        """The open room is HD-2D and Studio is editing (not playing)."""
        return self.studio.mode != "play" and self.renderer is not None

    def structures(self) -> list[Any]:
        renderer = self.renderer
        return list(renderer.settings.structures) if renderer is not None else []

    def find(self, structure_id: str | None) -> Any | None:
        return next((st for st in self.structures() if st.id == structure_id), None)

    def room_loaded(self, recenter: bool) -> None:
        """After every load of the room (opening it, an edit, undo, redo, stopping Play): keep the editor's view,
        drop a selection that no longer exists, and frame the room when it is new to the view."""
        key = self.studio.project.current
        if self.stroke is not None:  # the room was loaded again mid-stroke (undo, a room change, Play): it's gone
            self.stroke = None
            self.studio._say("Stroke cancelled: the room was loaded again.", ok=False)
        if self.renderer is None:  # a 2D room: nothing of the 3D view carries over
            self.structure, self.placing, self.drag = None, None, None
            self._buried, self.newly_buried = set(), []
            self._room = key
            return
        if self.structure is not None and self.find(self.structure) is None:
            self.structure = None
        if recenter or key != self._room:
            self.reset_view()
            self._buried = set()
        buried = self.buried()
        self.newly_buried = sorted(buried - self._buried) if key == self._room else []
        self._buried = buried
        self._room = key
        if self.placing is not None:  # an edit reloaded the room mid-placement: show the preview again
            self._ensure_model(self.placing)

    def buried(self) -> set[str]:
        """Objects (by name) that couldn't stand where they are: inside a structure, or under one with no room."""
        world, renderer = getattr(self.studio.window, "hd2d_world", None), self.renderer
        if world is None or renderer is None:
            return set()
        from engine.physics_runtime import _sprite_to_aabb  # noqa: PLC0415

        out = set()
        for sprite in renderer._sprites():
            data = getattr(sprite, "mesh_entity_data", None) or {}
            if not data.get("id"):
                continue
            box = _sprite_to_aabb(sprite)
            z = float(data.get("elevation", 0.0) or 0.0) / PIXELS_PER_METRE
            if world.stand(box.x / PIXELS_PER_METRE, box.y / PIXELS_PER_METRE, z, box.w / 64, box.h / 64) is None:
                out.add(str(data.get("name") or getattr(sprite, "mesh_name", None) or data["id"]))
        return out

    # ------------------------------------------------------------------ the camera
    def reset_view(self) -> None:
        renderer = self.renderer
        self.camera.yaw, self.camera.pitch = DEFAULT_YAW, DEFAULT_PITCH
        if renderer is None:
            return
        lo, hi = renderer.world_box()
        self.camera.target = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, 0.0)
        span = max(hi[0] - lo[0], hi[1] - lo[1])
        self.camera.distance = max(8.0, min(80.0, span * 1.1))

    def frame_selected(self) -> None:
        st = self.find(self.structure)
        renderer = self.renderer
        if st is None or renderer is None:
            self.studio._say("Select a structure first, then frame it.", ok=False)
            return
        lo, hi = box(st, renderer.models[st.model])
        self.camera.target = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 3)
        self.camera.distance = max(6.0, min(80.0, max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) * 1.6))

    def turn(self, degrees: float) -> None:
        self.camera.yaw = (self.camera.yaw + degrees) % 360.0

    def tilt(self, degrees: float) -> None:
        self.camera.pitch = max(15.0, min(85.0, self.camera.pitch + degrees))

    def zoom(self, steps: float) -> None:
        self.camera.distance = max(4.0, min(120.0, self.camera.distance * (0.9 ** steps)))

    def pan_pixels(self, dx: float, dy: float) -> None:
        """Drag the ground with the mouse: the view moves so the ground follows it."""
        _x0, _x1, _y0, y1 = self._rect()
        height = max(1.0, y1 - _y0)
        metres_per_px = 2 * self.camera.distance * math.tan(math.radians(self.camera.fov) / 2) / height
        self._move_target(-dx * metres_per_px, -dy * metres_per_px / max(0.3, math.sin(math.radians(self.camera.pitch))))

    def pan_keys(self, across: float, ahead: float, delta_time: float) -> None:
        speed = self.camera.distance * 0.8  # metres a second: the further out, the faster
        self._move_target(across * speed * delta_time, ahead * speed * delta_time)

    def _move_target(self, across: float, ahead: float) -> None:
        fx, fy = self.camera.forward()
        rx, ry, _ = self.camera.right()
        t = self.camera.target
        self.camera.target = (t[0] + rx * across + fx * ahead, t[1] + ry * across + fy * ahead, t[2])

    # ------------------------------------------------------------------ the canvas
    def _rect(self) -> tuple[float, float, float, float]:
        return self.studio._map_rect()

    def viewport(self) -> tuple[int, int, int, int]:
        """The canvas in framebuffer pixels (x, y, w, h)."""
        left, right, bottom, top = self._rect()
        window = self.studio.window
        fb_w, _fb_h = window.get_framebuffer_size()
        k = fb_w / max(1, window.width)
        return (int(left * k), int(bottom * k), max(1, int((right - left) * k)), max(1, int((top - bottom) * k)))

    def ray(self, x: float, y: float) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        left, right, bottom, top = self._rect()
        ndc_x = (x - left) / max(1.0, right - left) * 2 - 1
        ndc_y = (y - bottom) / max(1.0, top - bottom) * 2 - 1
        return self.camera.ray(ndc_x, ndc_y, (right - left) / max(1.0, top - bottom))

    def ground_px(self, x: float, y: float, elevation_m: float = 0.0) -> tuple[float, float] | None:
        """Where the mouse meets the ground (or the plane ``elevation_m`` up), in Mesh px."""
        hit = ground_point(*self.ray(x, y), elevation_m)
        return None if hit is None else (hit[0] * PIXELS_PER_METRE, hit[1] * PIXELS_PER_METRE)

    def draw(self) -> None:
        renderer = self.renderer
        if renderer is None:
            return
        start = time.perf_counter()
        renderer.weather_preview = self.weather
        renderer.draw(camera=self.camera, viewport=self.viewport(), overlay=self._overlay)
        self.timings["draw_ms"].append((time.perf_counter() - start) * 1000)
        del self.timings["draw_ms"][:-240]

    def _overlay(self, vp: tuple[float, ...]) -> None:
        renderer = self.renderer
        if renderer is None:
            return
        g = renderer.settings.ground
        if g is not None:  # a 1 m grid on the ground, faint
            x0, y0 = g.lo[0] / PIXELS_PER_METRE, g.lo[1] / PIXELS_PER_METRE
            x1, y1 = g.hi[0] / PIXELS_PER_METRE, g.hi[1] / PIXELS_PER_METRE
            z = g.elevation / PIXELS_PER_METRE + 0.01
            if renderer.terrain is None:
                lines = [p for i in range(int(x0), int(x1) + 1) for p in ((float(i), y0, z), (float(i), y1, z))]
                lines += [p for j in range(int(y0), int(y1) + 1) for p in ((x0, float(j), z), (x1, float(j), z))]
            elif self._grid[0] == (id(renderer.terrain), renderer.terrain_version) or (
                    self.stroke is not None and self._grid[1]):
                lines = self._grid[1]  # (mid-stroke: as it was; worked out again once the stroke ends)
            else:  # over sculpted ground: the grid follows it, in half-metre pieces (worked out once per edit)
                terrain = renderer.terrain

                def on(px: float, py: float) -> tuple[float, float, float]:
                    h = terrain.height(px * PIXELS_PER_METRE, py * PIXELS_PER_METRE)
                    return px, py, (h / PIXELS_PER_METRE if h is not None else z) + 0.02

                lines = []
                for i in range(int(x0), int(x1) + 1):
                    ys = [y0 + k * 0.5 for k in range(int((y1 - y0) / 0.5) + 1)]
                    lines += [p for a, b in zip(ys, ys[1:]) for p in (on(float(i), a), on(float(i), b))]
                for j in range(int(y0), int(y1) + 1):
                    xs = [x0 + k * 0.5 for k in range(int((x1 - x0) / 0.5) + 1)]
                    lines += [p for a, b in zip(xs, xs[1:]) for p in (on(a, float(j)), on(b, float(j)))]
                self._grid = ((id(terrain), renderer.terrain_version), lines)
                self._grid_at = time.perf_counter()
            renderer.draw_lines(vp, lines, (1.0, 1.0, 1.0, 0.16))
        if renderer.preview is not None and self.placing is not None:  # the model about to be placed: a cyan box
            from engine.hd2d.picking import _apply  # noqa: PLC0415

            m = renderer.preview[1]
            mlo, mhi = renderer.models[self.placing].bounds()
            pts = [_apply([[m[c * 4 + r] for c in range(4)] for r in range(4)], x, y, z)
                   for x in (mlo[0], mhi[0]) for y in (mlo[1], mhi[1]) for z in (mlo[2], mhi[2])]
            lo = (min(p[0] for p in pts), min(p[1] for p in pts), min(p[2] for p in pts))
            hi = (max(p[0] for p in pts), max(p[1] for p in pts), max(p[2] for p in pts))
            renderer.draw_lines(vp, box_edges(lo, hi), (0.35, 0.9, 1.0, 1.0), through=True)
        st = self._shown_structure()
        if st is not None:
            lo, hi = box(st, renderer.models[st.model])
            renderer.draw_lines(vp, box_edges(lo, hi), (1.0, 0.82, 0.25, 0.45), through=True)  # where it's hidden
            renderer.draw_lines(vp, box_edges(lo, hi), (1.0, 0.82, 0.25, 1.0))
        if self.sculpt is not None and self.sculpt_at is not None:  # the brush: a ring on the ground, its radius
            cx, cy, _cz = self.sculpt_at
            r = self.sculpt["radius"] / PIXELS_PER_METRE
            ring = []
            for k in range(48):
                pts = []
                for a in (k * math.tau / 48, (k + 1) * math.tau / 48):
                    px, py = cx + r * math.cos(a), cy + r * math.sin(a)
                    h = renderer.terrain.height(px * PIXELS_PER_METRE, py * PIXELS_PER_METRE) if renderer.terrain else None
                    pts.append((px, py, (h / PIXELS_PER_METRE if h is not None else _cz) + 0.04))
                ring += pts
            colour = {"raise": (1.0, 0.85, 0.3, 1.0), "lower": (0.45, 0.75, 1.0, 1.0), "smooth": (0.6, 1.0, 0.6, 1.0),
                      "flatten": (1.0, 0.55, 0.9, 1.0)}.get(self.stroke["tool"] if self.stroke else self.sculpt["tool"],
                                                            (1.0, 0.85, 0.3, 1.0))
            renderer.draw_lines(vp, ring, colour, through=True)
        if self.object_marker is not None and self.studio.place_prefab is not None:  # where it would stand: green
            mx, my, mz = self.object_marker
            renderer.draw_lines(vp, box_edges((mx - 0.3, my - 0.3, mz), (mx + 0.3, my + 0.3, mz + 1.6)),
                                (0.4, 1.0, 0.5, 1.0), through=True)
        entity_sprite = self._selected_sprite()
        if entity_sprite is not None:
            e = (entity_sprite.mesh_entity_data or {}).get("elevation", 0.0) or 0.0
            sx, sy, sz = entity_sprite.center_x / 32, entity_sprite.bottom / 32, float(e) / 32
            half = abs(entity_sprite.width) / 64
            renderer.draw_lines(vp, box_edges((sx - half, sy - half / 2, sz), (sx + half, sy + half / 2, sz + 1.6)),
                                (0.45, 0.8, 1.0, 1.0), through=True)

    def _shown_structure(self) -> Any | None:
        """The selected structure as it is now: where a drag has it, or as placed."""
        st = self.find(self.structure)
        if st is None or self.drag is None or self.drag.get("kind") != "structure":
            return st
        from dataclasses import replace  # noqa: PLC0415

        return replace(st, x=self.drag["x"], y=self.drag["y"])

    def _selected_sprite(self) -> Any | None:
        if not self.studio.selected:
            return None
        return self.studio._sprites_by_id().get(self.studio.selected)

    # ------------------------------------------------------------------ mouse
    def press(self, x: float, y: float) -> bool:
        """A left click on the canvas. Returns True when it was the 3D view's to handle."""
        renderer = self.renderer
        if renderer is None:
            return False
        if self.placing is not None:
            self.place_here(x, y)
            return True
        if self.sculpt is not None:
            self.begin_stroke(x, y)
            return True
        start = time.perf_counter()
        origin, direction = self.ray(x, y)
        sprites = [s for s in renderer._sprites() if (getattr(s, "mesh_entity_data", None) or {}).get("id")]
        stretch = 1.0 / max(0.5, math.cos(math.radians(self.camera.pitch)))
        hit = self.picker.pick(origin, direction, self.structures(), renderer.models, sprites, self.camera.right(), stretch)
        self.timings["pick_ms"].append((time.perf_counter() - start) * 1000)
        water = self._water_at(origin, direction) if hit is None else None
        if water is not None:  # a puddle or pond (no picture to click): the object it is
            self._grab_entity(water[0], water[1], x, y)
            return True
        if hit is None:
            self.select_structure(None)
            self.studio.select(None)
            return True
        if hit.kind == "sprite":  # a character or object: Studio's ordinary object editing
            entity_id = hit.target.mesh_entity_data["id"]
            z = float((hit.target.mesh_entity_data or {}).get("elevation", 0.0) or 0.0) / PIXELS_PER_METRE
            self._grab_entity(entity_id, z, x, y)
            return True
        st = self.find(hit.target)
        self.select_structure(hit.target)
        if st is not None:
            plane = st.elevation / PIXELS_PER_METRE
            at = self.ground_px(x, y, plane)
            if at is not None:
                self.drag = {"kind": "structure", "id": st.id, "plane": plane, "moved": False,
                             "dx": st.x - at[0], "dy": st.y - at[1], "x": st.x, "y": st.y}
        return True

    def _grab_entity(self, entity_id: str, z: float, x: float, y: float) -> None:
        """Select an object and start dragging it on the plane ``z`` m up."""
        self.structure = None
        self.studio.select(entity_id)
        entity = self.studio._entity(entity_id) or {}
        at = self.ground_px(x, y, z)
        if at is not None:
            self.drag = {"kind": "entity", "id": entity_id, "plane": z, "moved": False,
                         "dx": float(entity.get("x", 0)) - at[0], "dy": float(entity.get("y", 0)) - at[1],
                         "to": (entity.get("x", 0), entity.get("y", 0))}

    def _water_at(self, origin: tuple[float, float, float], direction: tuple[float, float, float]) -> tuple[str, float] | None:
        """The nearest water surface the mouse's ray meets (its object's id and level, m), if any (Milestone 19A)."""
        from engine import water as water_mod  # noqa: PLC0415

        best: tuple[float, str, float] | None = None
        for body in water_mod.bodies_of(self.studio.window):
            cx, cy, z = body.place()
            if abs(direction[2]) < 1e-6:
                continue
            t = (z - origin[2]) / direction[2]
            if t <= 0:
                continue
            px = ((origin[0] + direction[0] * t) * PIXELS_PER_METRE, (origin[1] + direction[1] * t) * PIXELS_PER_METRE)
            entity_id = (getattr(body.entity, "mesh_entity_data", None) or {}).get("id")
            on = water_mod.inside(body.water, (cx * PIXELS_PER_METRE, cy * PIXELS_PER_METRE), px)
            if entity_id and on and (best is None or t < best[0]):
                best = (t, str(entity_id), z)
        return None if best is None else (best[1], best[2])

    def drag_to(self, x: float, y: float) -> None:
        if self.stroke is not None:
            self.stroke_to(x, y)
            self.sculpt_at = self.ground_hit(x, y)
            return
        drag, renderer = self.drag, self.renderer
        if drag is None or renderer is None:
            return
        at = self.ground_px(x, y, drag["plane"])
        if at is None:
            return
        nx, ny = at[0] + drag["dx"], at[1] + drag["dy"]
        if drag["kind"] == "entity":
            nx, ny = round(nx / 16) * 16, round(ny / 16) * 16  # Studio's object grid
            if (nx, ny) != drag["to"]:
                drag["to"], drag["moved"] = (nx, ny), True
                sprite = self.studio._sprites_by_id().get(drag["id"])
                if sprite is not None:
                    sprite.center_x, sprite.center_y = nx, ny
            return
        nx = _snap(nx / PIXELS_PER_METRE, self.snap) * PIXELS_PER_METRE
        ny = _snap(ny / PIXELS_PER_METRE, self.snap) * PIXELS_PER_METRE
        if (nx, ny) == (drag["x"], drag["y"]):
            return
        if not drag["moved"]:
            renderer.set_live_ids({drag["id"]})  # out of the static batch: it moves every frame now
        drag.update(x=nx, y=ny, moved=True)
        st = self.find(drag["id"])
        if st is not None:
            renderer.set_live(st.id, nx, ny, st.elevation, st.rotation, st.scale)

    def release(self) -> None:
        if self.stroke is not None:
            self.end_stroke()
            return
        drag, self.drag = self.drag, None
        if drag is None or not drag["moved"]:
            return
        if drag["kind"] == "entity":
            target, (nx, ny) = drag["id"], drag["to"]
            self.studio._edit(lambda s: ops.move_entity(s, target, nx, ny))
            return
        self.set_fields("Moved.", x=drag["x"], y=drag["y"])

    @property
    def dragging(self) -> bool:
        return self.drag is not None or self.stroke is not None

    # ------------------------------------------------------------------ edits (one op each: one undo step)
    def select_structure(self, structure_id: str | None) -> None:
        studio = self.studio
        studio._flush_fields()
        self.structure = structure_id
        if structure_id is not None:
            studio.selected, studio.light = None, None
            studio.panel = "inspect"
        studio._rebuild()

    def set_fields(self, ok: str, **fields: Any) -> bool:
        sid = self.structure
        if sid is None:
            return False
        start = time.perf_counter()
        done = self.studio._edit(lambda s: ops.set_structure(s, sid, **fields), ok)
        self.timings["edit_ms"].append((time.perf_counter() - start) * 1000)
        return done

    def nudge(self, ok: str, *, up_m: float = 0.0, turn_deg: float = 0.0) -> None:
        st = self.find(self.structure)
        if st is None:
            return
        change: dict[str, Any] = {}
        if up_m:
            change["elevation"] = max(0.0, st.elevation + up_m * PIXELS_PER_METRE)
        if turn_deg:
            change["rotation"] = (st.rotation + turn_deg) % 360.0
        self.set_fields(ok, **change)

    def set_metres(self, key: str, text: str) -> None:
        """An inspector field: metres (degrees for rotation, a factor for scale) to the room's px."""
        try:
            value = float(str(text).replace(",", ".").strip())
        except ValueError:
            self.studio._say(f"'{text}' isn't a number.", ok=False)
            return
        if key in ("x", "y", "elevation"):
            value *= PIXELS_PER_METRE
        self.set_fields("Changed.", **{key: value})

    def remove(self) -> None:
        sid = self.structure
        if sid is None:
            return
        if self.studio._edit(lambda s: ops.remove_structure(s, sid), f"Removed structure '{sid}' (Undo brings it back)."):
            self.structure = None
            self.studio._rebuild()

    # ------------------------------------------------------------------ placing a structure
    def models_in_project(self) -> list[str]:
        from engine.hd2d.catalog import glb_files  # noqa: PLC0415

        return glb_files(self.studio.project.root)

    def _ensure_model(self, model: str) -> bool:
        renderer = self.renderer
        if renderer is None:
            return False
        if model not in renderer.models:
            from engine.hd2d.glb import load_glb, model_problem  # noqa: PLC0415

            problem = model_problem(self.studio.project.root, model)
            if problem:
                self.studio._say(problem, ok=False)
                return False
            renderer.models[model] = load_glb(Path(self.studio.project.root) / model)
        return True

    def start_placing(self, model: str, rotation: float = 0.0, scale: float = 1.0) -> None:
        if not self._ensure_model(model):
            return
        self.placing, self.placing_turn, self.placing_scale = model, rotation, scale
        self.studio.panel = "inspect"
        self.studio._say(f"Placing {Path(model).name}: click the ground to put it there (Esc cancels).")
        self.studio._rebuild()

    def hover(self, x: float, y: float) -> None:
        renderer = self.renderer
        if self.sculpt is not None:
            self.sculpt_at = self.ground_hit(x, y)
            if self.sculpt_at is not None and self.stroke is None:  # the ground's height under the brush
                said = f"Ground {self.sculpt_at[2]:+.2f} m here."
                if said != getattr(self, "_height_said", None):
                    self._height_said = said
                    self.studio._say(said)
            return
        if self.studio.place_prefab is not None and renderer is not None:
            spot = self.object_spot(x, y)
            self.object_marker = None if isinstance(spot, str) else spot[1]
            return
        self.object_marker = None
        if self.placing is None or renderer is None:
            return
        at = self.ground_px(x, y)
        if at is None:
            renderer.set_preview(None)
            return
        gx = _snap(at[0] / PIXELS_PER_METRE, self.snap) * PIXELS_PER_METRE
        gy = _snap(at[1] / PIXELS_PER_METRE, self.snap) * PIXELS_PER_METRE
        renderer.set_preview(self.placing, gx, gy, rotation=self.placing_turn, scale=self.placing_scale)

    def _feet_below_centre(self) -> float:
        """How far (px) below its centre the armed object's feet are: what a floor holds up. A character's are the
        bottom of its frame (an "auto" footprint collider, ``engine.physics_runtime.footprint``); other objects
        stand on their centre."""
        from engine.physics_runtime import footprint  # noqa: PLC0415

        raw = (self.studio.place_prefab or {}).get("entity")
        entity: dict[str, Any] = raw if isinstance(raw, dict) else {}
        components = entity.get("components")
        collider = components.get("collider") if isinstance(components, dict) else None
        if not (isinstance(collider, dict) and collider.get("auto")):
            return 0.0
        config = entity.get("behaviour_config")
        animator = config.get("Animator") if isinstance(config, dict) else None
        clips = animator.get("animations") if isinstance(animator, dict) else None
        clips = clips if isinstance(clips, dict) else {}
        height = next((float(c["frame_height"]) for c in clips.values() if isinstance(c, dict) and c.get("frame_height")), 0.0)
        if not height and isinstance(entity.get("sprite"), str):
            image = self.studio._image(str(Path(self.studio.project.root) / entity["sprite"]))
            height = float(image.height) if image is not None else 0.0
        return -float(footprint(32.0, height or 32.0)["offset_y"])

    def object_spot(self, x: float, y: float) -> tuple[tuple[float, float, float], tuple[float, float, float], str] | str:
        """Where the armed object would go if the canvas were clicked at (x, y): ((its x, y, elevation) px, where
        its feet stand (m), the floor's name), or why it can't go there. The feet are on Studio's 16 px object grid
        when that spot is fine, else exactly under the mouse."""
        from engine.hd2d.world import NAV_HALF  # noqa: PLC0415
        from engine.studio import GRID  # noqa: PLC0415

        def snap(v: float) -> float:
            return round(v * PIXELS_PER_METRE / GRID) * GRID / PIXELS_PER_METRE

        lift = self._feet_below_centre()
        world = getattr(self.studio.window, "hd2d_world", None)
        if world is None:  # a room without collision models: everything stands on the ground
            at = self.ground_px(x, y)
            if at is None:
                return "Point at the ground to place it there."
            fx, fy = snap(at[0] / PIXELS_PER_METRE), snap(at[1] / PIXELS_PER_METRE)
            return (fx * PIXELS_PER_METRE, fy * PIXELS_PER_METRE + lift, 0.0), (fx, fy, 0.0), "ground"
        hit = world.walkable_hit(*self.ray(x, y))
        if hit is None:
            return "Point at the ground or a floor (a platform, a bridge, stairs) to place it there."
        (hx, hy, hz), floor = hit
        for fx, fy in ((snap(hx), snap(hy)), (hx, hy)):
            stood = world.stand(fx, fy, hz, *NAV_HALF)
            if stood is not None:
                z = stood[0]
                return ((round(fx * PIXELS_PER_METRE, 2), round(fy * PIXELS_PER_METRE + lift, 2), round(z * PIXELS_PER_METRE, 2)),
                        (fx, fy, z), stood[1])
        where = "the ground" if floor == "ground" else f"'{floor}'"
        return f"Nobody could stand there on {where}: something is in the way, or a floor is too low overhead."

    def place_object(self, x: float, y: float) -> None:
        """A click with an object chosen in the Objects list: put it on the floor under the mouse."""
        spot = self.object_spot(x, y)
        if isinstance(spot, str):
            self.studio._say(spot, ok=False)  # still chosen: click somewhere else
            return
        (px, py, pz), _feet, floor = spot
        self.object_marker = None
        self.studio.place_at(px, py, elevation=pz, where="the ground" if floor == "ground" else f"'{floor}'", snap=False)

    def place_here(self, x: float, y: float) -> None:
        model, at = self.placing, self.ground_px(x, y)
        if model is None or at is None:
            return
        from engine.hd2d.glb import model_problem  # noqa: PLC0415

        problem = model_problem(self.studio.project.root, model)
        if problem:  # the file went away since it was chosen
            self.studio._say(problem, ok=False)
            return
        gx = _snap(at[0] / PIXELS_PER_METRE, self.snap) * PIXELS_PER_METRE
        gy = _snap(at[1] / PIXELS_PER_METRE, self.snap) * PIXELS_PER_METRE
        made: dict[str, str] = {}
        turn, scale = self.placing_turn, self.placing_scale

        def change(scene: dict[str, Any]) -> dict[str, Any]:
            new_scene, sid = ops.place_structure(scene, model, gx, gy, rotation=turn, scale=scale)
            made["id"] = sid
            return new_scene

        self.placing = None
        if self.renderer is not None:
            self.renderer.set_preview(None)
        if self.studio._edit(change, f"Placed {Path(model).name} at {gx / 32:g} m, {gy / 32:g} m."):
            self.select_structure(made.get("id"))

    def cancel(self) -> bool:
        """Esc: cancel a stroke, stop placing, or let go of the selected structure. True if there was something to
        cancel."""
        if self.cancel_stroke():
            return True
        if self.placing is not None:
            self.placing = None
            if self.renderer is not None:
                self.renderer.set_preview(None)
            self.studio._say("Placing cancelled.")
            self.studio._rebuild()
            return True
        if self.structure is not None:
            self.select_structure(None)
            return True
        return False

    # ------------------------------------------------------------------ keys (only while no field is being typed in)
    def key(self, symbol: int) -> bool:
        k = optional_arcade.arcade.key
        if symbol == k.Q:
            self.turn(-TURN_DEG)
        elif symbol == k.E:
            self.turn(TURN_DEG)
        elif symbol == k.HOME:
            self.reset_view()
        elif symbol == k.F:
            self.frame_selected()
        elif symbol == k.DELETE and self.structure is not None:
            self.remove()
        elif symbol in (k.BRACKETLEFT, k.BRACKETRIGHT) and self.sculpt is not None:  # the brush's size
            radius = self.sculpt["radius"] * (1.25 if symbol == k.BRACKETRIGHT else 0.8)
            self.set_sculpt(radius=round(min(1024.0, max(16.0, radius)), 1))
            self.studio._say(f"Brush radius {self.sculpt['radius'] / PIXELS_PER_METRE:.1f} m.")
        elif symbol == k.ESCAPE:
            return self.cancel()
        else:
            return False
        return True

    # ------------------------------------------------------------------ panels
    def _button(self, text: str, action: Any, tip: str, *, width: int, **kw: Any) -> Any:
        button = self.studio._button(text, action, width=width, **kw)
        self.tips.append((button, tip))
        return button

    def view_section(self, box: Any, width: int) -> None:
        """The left panel's "3D view" section: the camera's buttons and how to place a structure."""
        self.tips = []
        studio = self.studio
        box.add(studio._label("3D view", bold=True, size=12))
        half = (width - 4) // 2
        row = _row()
        row.add(self._button("Turn left", lambda: self.turn(-TURN_DEG), "Turn the view 45 degrees (Q)", width=half))
        row.add(self._button("Turn right", lambda: self.turn(TURN_DEG), "Turn the view 45 degrees (E)", width=half))
        box.add(row)
        row = _row()
        row.add(self._button("Tilt up", lambda: self.tilt(-10), "Look across the room, lower", width=half))
        row.add(self._button("Tilt down", lambda: self.tilt(10), "Look down on the room, higher", width=half))
        box.add(row)
        row = _row()
        row.add(self._button("Reset view", self.reset_view, "The whole room, from the front (Home)", width=half))
        row.add(self._button("Frame it", self.frame_selected, "Zoom to the selected structure (F)", width=half))
        box.add(row)
        box.add(studio._label("Middle-drag pans, wheel zooms, WASD moves.", color=C_MUTED, size=10, width=width))
        renderer = self.renderer
        if renderer is not None and renderer.particles is not None:  # the room has weather: show it here, or not
            box.add(self._button(f"Preview weather: {'on' if self.weather else 'off'}", self.toggle_weather,
                                 "Rain, snow and leaves in this view, landing where they would in play",
                                 width=width, style=S_ACTIVE if self.weather else S_BUTTON))
        box.add(self._button("Models...", self.open_models, "Blender models in this project: import, browse, place "
                             "and reimport", width=width, style=S_ACTIVE if studio.panel == "structures" else S_BUTTON))
        if renderer is not None and renderer.settings.ground is not None:
            self._sculpt_section(box, width)

    # ------------------------------------------------------------------ sculpting the ground (Milestone 20A prototype)
    def ground_hit(self, x: float, y: float) -> tuple[float, float, float] | None:
        """Where the mouse meets the ground itself (m): the sculpted ground if any, else its plane."""
        renderer = self.renderer
        if renderer is None or renderer.settings.ground is None:
            return None
        if renderer.terrain is not None:
            hit: tuple[float, float, float] | None = renderer.terrain.ray(*self.ray(x, y))
            return hit
        z = renderer.settings.ground.elevation / PIXELS_PER_METRE
        at = self.ground_px(x, y, z)
        return None if at is None else (at[0] / PIXELS_PER_METRE, at[1] / PIXELS_PER_METRE, z)

    def toggle_sculpt(self) -> None:
        self.cancel_stroke()
        self.sculpt = None if self.sculpt is not None else {"tool": "raise", "radius": 64.0, "rate": 32.0, "target": None}
        self.sculpt_at = None
        self.studio._say("Sculpting: hold the mouse on the ground and drag (each stroke is one undoable change). "
                         "Shift lowers, Ctrl smooths, Alt+click picks a flatten height, [ ] resizes, Esc cancels."
                         if self.sculpt else "Sculpting off.")
        self.studio._rebuild()

    def set_sculpt(self, **change: Any) -> None:
        if self.sculpt is None:
            return
        tool = change.get("tool")
        if tool is not None and (tool in ("smooth", "flatten")) != (self.sculpt["tool"] in ("smooth", "flatten")):
            change.setdefault("rate", 2.0 if tool in ("smooth", "flatten") else 32.0)  # a share a second, or px a second
        self.sculpt.update(change)
        self.studio._rebuild()

    # ------------------------------------------------------------------ a live stroke (Milestone 20B)
    def _brush_now(self) -> tuple[str, float, float | None]:
        """The tool this stroke uses, given the keys held as it starts: Shift lowers (raises, with Lower), Ctrl
        smooths; its rate; the flatten target (px), if one was picked."""
        assert self.sculpt is not None
        k = optional_arcade.arcade.key
        held = self.studio.keys
        tool = self.sculpt["tool"]
        rate = float(self.sculpt["rate"])
        if held & {k.LCTRL, k.RCTRL}:
            tool, rate = "smooth", (rate if self.sculpt["tool"] in ("smooth", "flatten") else 2.0)
        elif held & {k.LSHIFT, k.RSHIFT} and tool in ("raise", "lower"):
            tool = "lower" if tool == "raise" else "raise"
        return tool, rate, self.sculpt.get("target")

    def begin_stroke(self, x: float, y: float) -> None:
        """The mouse went down on the ground with sculpting on: a stroke starts (Alt+click picks a flatten height)."""
        if self.stroke is not None:  # (a press while a stroke is held: that one ends first, as one undo step)
            self.end_stroke()
        renderer = self.renderer
        at = self.ground_hit(x, y)
        if renderer is None or self.sculpt is None or at is None:
            self.studio._say("Point at the ground to sculpt it.", ok=False)
            return
        k = optional_arcade.arcade.key
        if self.sculpt.pop("picking", False) or self.studio.keys & {k.LALT, k.RALT}:  # the eyedropper
            self.sculpt.update(tool="flatten", target=round(at[2] * PIXELS_PER_METRE, 2), rate=2.0)
            self.studio._say(f"Flatten to {at[2]:.2f} m (picked from the ground).")
            self.studio._rebuild()
            return
        was_sculpted = renderer.terrain is not None
        terrain = renderer.ensure_terrain()
        if terrain is None:
            return
        world = getattr(self.studio.window, "hd2d_world", None)
        if world is None:  # a room without floors had no collision world: it gets one now, on the same heights
            from engine.hd2d.world import World  # noqa: PLC0415

            world = self.studio.window.hd2d_world = World(renderer.settings, renderer.models)
        world.update_terrain(terrain)
        tool, rate, target = self._brush_now()
        if tool == "flatten" and target is None:
            here = terrain.height(at[0] * PIXELS_PER_METRE, at[1] * PIXELS_PER_METRE)
            target = here if here is not None else terrain.base
        self.stroke = {"tool": tool, "rate": rate, "radius": float(self.sculpt["radius"]), "target": target,
                       "before": list(terrain.heights), "was_sculpted": was_sculpted, "dabs": [], "touched": set(),
                       "pending": set(), "last": (at[0] * PIXELS_PER_METRE, at[1] * PIXELS_PER_METRE),
                       "t": time.perf_counter(), "moved": False, "started": time.perf_counter()}
        x0, y0 = self.stroke["last"]
        self._dab(x0, y0, 1 / 60)  # (a tap does a little: a 60th of a second's worth)
        self._flush_stroke()

    def _dab(self, x: float, y: float, seconds: float) -> None:
        """One dab of the stroke at (x, y) px worth ``seconds`` of the brush's rate: px for raise and lower, a share
        of the way (1 - e^(-rate t)) for smooth and flatten. Recorded as the saved stroke will replay it."""
        stroke, renderer = self.stroke, self.renderer
        if stroke is None or renderer is None or renderer.terrain is None:
            return
        tool, rate = stroke["tool"], stroke["rate"]
        amount = rate * seconds if tool in ("raise", "lower") else 1.0 - math.exp(-rate * seconds)
        amount = round(min(amount, 512.0 if tool in ("raise", "lower") else 1.0), 6)
        if amount <= 0:
            return
        dirty = renderer.terrain.sculpt(tool, x, y, stroke["radius"], amount, stroke["target"])
        stroke["dabs"].append([round(x, 3), round(y, 3), amount])
        stroke["pending"] |= dirty
        stroke["touched"] |= dirty

    def stroke_to(self, x: float, y: float) -> None:
        """The mouse moved with the button held: dabs along the way, a quarter of the brush's radius apart, sharing
        the time since the last ones (so what is done depends on time, not on how often the mouse reports)."""
        stroke = self.stroke
        at = self.ground_hit(x, y)
        if stroke is None or at is None:
            return
        now = time.perf_counter()
        to = (at[0] * PIXELS_PER_METRE, at[1] * PIXELS_PER_METRE)
        (fx, fy), seconds = stroke["last"], min(0.25, now - stroke["t"])
        n = max(1, math.ceil(math.hypot(to[0] - fx, to[1] - fy) / max(1.0, stroke["radius"] / 4)))
        for i in range(1, n + 1):
            self._dab(fx + (to[0] - fx) * i / n, fy + (to[1] - fy) * i / n, seconds / n)
        stroke.update(last=to, t=now, moved=True)

    def tick(self, delta_time: float) -> None:
        """Each editing frame: a stroke held still keeps working where it is (by the time passed), and what changed
        is drawn and walked on anew (only the changed chunks)."""
        if self._redraw:
            self._redraw_ground()
        stroke = self.stroke
        if stroke is None:
            return
        now = time.perf_counter()
        if not stroke["moved"] and now - stroke["t"] > 0:
            x0, y0 = stroke["last"]
            self._dab(x0, y0, min(0.25, now - stroke["t"]))
            stroke["t"] = now
        stroke["moved"] = False
        self._flush_stroke()

    def _flush_stroke(self) -> None:
        stroke, renderer = self.stroke, self.renderer
        if stroke is None or renderer is None or not stroke["pending"]:
            return
        start = time.perf_counter()
        pending, stroke["pending"] = stroke["pending"], set()
        try:
            renderer.update_terrain(renderer.terrain, pending)
        except Exception as exc:  # noqa: BLE001  # REASON: a refused chunk upload stops the stroke; the ground goes back
            self.cancel_stroke(f"The stroke stopped: the ground couldn't be drawn ({exc}).")
            return
        world = getattr(self.studio.window, "hd2d_world", None)
        if world is not None:
            world.update_terrain(renderer.terrain)
        self.timings["sculpt_ms"].append((time.perf_counter() - start) * 1000)
        del self.timings["sculpt_ms"][:-240]

    def end_stroke(self) -> None:
        """The mouse let go: the stroke becomes one checked edit (``project_ops.sculpt_terrain_stroke``, one undo
        step), without reloading the room (it already shows the result). What was shown is checked against what was
        saved; should they ever differ, the room is reloaded from the saved one."""
        from engine import project_ops as ops  # noqa: PLC0415
        from engine.hd2d.terrain import Terrain  # noqa: PLC0415

        stroke = self.stroke
        if stroke is None:
            return
        self._flush_stroke()
        self.stroke = None
        if not stroke["dabs"]:
            return
        studio = self.studio
        before = studio.project.scene()
        start = time.perf_counter()
        try:
            studio.project.edit_scene(lambda s: ops.sculpt_terrain_stroke(s, stroke["tool"], stroke["dabs"],
                                                                          stroke["radius"], stroke["target"]))
        except ops.OpError as err:
            self.stroke = stroke
            self.cancel_stroke(str(err))
            return
        renderer = self.renderer
        saved = Terrain.from_ground(ops._parsed_ground(studio.project.scene()))
        if renderer is None or renderer.terrain is None or saved.heights != renderer.terrain.heights:
            studio._reload()  # (never expected: the saved stroke is the shown one; the saved one wins)
        self.timings["edit_ms"].append((time.perf_counter() - start) * 1000)
        after = studio.project.scene()
        out_of_place = ops.terrain_anchoring(after, before)
        unsettled = sorted(set(self.unsettled) | set(ops.anchoring_ids(after, before))
                           | {f"structure:{i}" for i in ops.anchoring_structure_ids(after, before)})
        changed_panel, self.unsettled = unsettled != self.unsettled, unsettled
        self._buried = self.buried()
        if changed_panel:  # the Settle button appears or counts more: the panel again
            studio._rebuild()
        else:  # only the top bar (undo, redo, unsaved): a full rebuild costs a quarter of a second
            studio._refresh_top_bar()
        words = {"raise": "Raised", "lower": "Lowered", "smooth": "Smoothed", "flatten": "Flattened"}[stroke["tool"]]
        studio._say(f"{words} the ground ({len(stroke['dabs'])} dabs, one undo step)." + (
            " Out of place now (not moved): " + "; ".join(out_of_place[:3]) + (" ..." if len(out_of_place) > 3 else "")
            if out_of_place else ""), ok=not out_of_place)

    def cancel_stroke(self, why: str = "Stroke cancelled: the ground is as it was.") -> bool:
        """Esc (or a refused upload): the stroke's changes undone on screen and nothing saved. True if there was
        one."""
        stroke, renderer = self.stroke, self.renderer
        self.stroke = None
        if stroke is None:
            return False
        if renderer is not None and renderer.terrain is not None:
            # the heights (what is walked on and saved) go back at once; their drawing as soon as the GPU takes it
            renderer.terrain.heights[:] = stroke["before"]
            world = getattr(self.studio.window, "hd2d_world", None)
            if world is not None:
                world.update_terrain(renderer.terrain)
            self._redraw = set(stroke["touched"])
            self._redraw_ground()
        self.studio._say(why, ok=False)
        return True

    def _redraw_ground(self) -> None:
        """Draw again the chunks a cancelled stroke had changed (tried each frame until the GPU takes them)."""
        renderer = self.renderer
        if not self._redraw or renderer is None or renderer.terrain is None:
            self._redraw = set()
            return
        try:
            renderer.update_terrain(renderer.terrain, self._redraw)
        except Exception as exc:  # noqa: BLE001  # REASON: the GPU refused again; the next frame tries again
            if not getattr(self, "_redraw_said", False):
                self._redraw_said = True
                self.studio._say(f"The ground's drawing will catch up when the GPU allows ({exc}).", ok=False)
            return
        self._redraw, self._redraw_said = set(), False

    def settle(self) -> None:
        """Stand the objects sculpting left off the ground back on it: one undoable edit."""
        from engine import project_ops as ops  # noqa: PLC0415

        scene = self.studio.project.scene()
        ids = [i for i in self.unsettled if ops.find_entity_or_none(scene, i) is not None]
        sids = [i.split(":", 1)[1] for i in self.unsettled if i.startswith("structure:")
                and ops.find_structure(scene, i.split(":", 1)[1]) is not None]
        self.unsettled = []
        if (ids or sids) and self.studio._edit(lambda s: ops.settle_on_ground(s, ids, sids),
                                               f"Stood {len(ids) + len(sids)} back on the ground."):
            return
        self.studio._rebuild()

    def _sculpt_section(self, box: Any, width: int) -> None:
        studio, brush = self.studio, self.sculpt
        box.add(self._button(f"Sculpt ground: {'on' if brush else 'off'}", self.toggle_sculpt,
                             "Hold the mouse on the ground and drag to raise, lower, smooth or flatten it", width=width,
                             style=S_ACTIVE if brush else S_BUTTON))
        if brush is None:
            return
        quarter = (width - 12) // 4
        row = _row()
        tips = {"raise": "Raise the ground (Shift: lower)", "lower": "Lower the ground (Shift: raise)",
                "smooth": "Smooth bumps away (or hold Ctrl with any tool)",
                "flatten": "Flatten to one height: the one under the stroke's start, or Alt+click to pick it"}
        for tool in ("raise", "lower", "smooth", "flatten"):
            row.add(self._button(tool.capitalize(), lambda tool=tool: self.set_sculpt(tool=tool), tips[tool],
                                 width=quarter, style=S_ACTIVE if brush["tool"] == tool else S_BUTTON))
        box.add(row)
        gentle = brush["tool"] in ("smooth", "flatten")

        def number(key: str, lo: float, hi: float, scale: float) -> Any:
            def commit(text: str) -> None:
                try:
                    value = float(text)
                except ValueError:
                    studio._say("Type a number.", ok=False)
                    return
                self.set_sculpt(**{key: min(hi, max(lo, value)) * scale})
            return commit

        half = (width - 4) // 2
        row = _row()
        row.add(studio._label("Radius (m)", color=C_MUTED, size=10, width=half // 2))
        row.add(studio._field(f"{brush['radius'] / PIXELS_PER_METRE:.2g}", number("radius", 0.5, 32.0, PIXELS_PER_METRE),
                              width=half - half // 2, key="sculpt_radius"))
        row.add(studio._label("Strength" if gentle else "m a second", color=C_MUTED, size=10, width=half // 2))
        row.add(studio._field(f"{brush['rate']:.2g}" if gentle else f"{brush['rate'] / PIXELS_PER_METRE:.2g}",
                              number("rate", 0.05, 20.0, 1.0) if gentle else number("rate", 0.05, 8.0, PIXELS_PER_METRE),
                              width=half - half // 2, key="sculpt_rate"))
        box.add(row)
        if brush["tool"] == "flatten":
            target = brush.get("target")
            row = _row()
            row.add(studio._label(f"To {target / PIXELS_PER_METRE:+.2f} m (picked)" if target is not None
                                  else "To the height where a stroke starts", color=C_MUTED, size=10, width=width - quarter - 4))
            row.add(self._button("Pick", lambda: self.set_sculpt(picking=True), "The next click picks the height to "
                                 "flatten to (as Alt+click)", width=(quarter - 2) // 2,
                                 style=S_ACTIVE if brush.get("picking") else S_BUTTON))
            row.add(self._button("Clear", lambda: self.set_sculpt(target=None), "Flatten to where each stroke starts",
                                 width=(quarter - 2) // 2))
            box.add(row)
        if self.unsettled:
            box.add(self._button(f"Settle on the ground ({len(self.unsettled)})", self.settle,
                                 "Stand the objects sculpting left floating or buried back on the ground", width=width))
        box.add(studio._label("Drag to sculpt (one undo step a stroke). Shift lowers, Ctrl smooths, Alt+click picks a "
                              "flatten height, [ ] resize, Esc cancels a stroke.", color=C_MUTED, size=10, width=width))

    def toggle_weather(self) -> None:
        self.weather = not self.weather
        self.studio._say(f"Weather preview {'on' if self.weather else 'off'}.")
        self.studio._rebuild()

    def advance_weather(self, delta_time: float) -> None:
        """The previewed weather moves while editing (nothing else of the game runs)."""
        renderer = self.renderer
        if self.weather and renderer is not None and renderer.particles is not None:
            renderer.particles.update(delta_time)

    # ------------------------------------------------------------------ the model browser (Stage 5B)
    def open_models(self) -> None:
        studio = self.studio
        studio._flush_fields()
        self._assets = None
        studio.panel = "inspect" if studio.panel == "structures" else "structures"
        studio.panel_scroll = 0
        studio._rebuild()

    def models(self) -> list[Any]:
        """The project's models (``engine.hd2d.catalog.ModelAsset``), read once per visit to the browser."""
        if self._assets is None:
            try:
                self._assets = self.studio.project.model_assets()
            except ops.OpError as err:
                self.studio._say(str(err), ok=False)
                self._assets = []
        return self._assets

    def _asset(self, asset_id: str | None) -> Any | None:
        return next((a for a in self.models() if a.id == asset_id), None)

    def facts(self, asset: Any) -> tuple[Any | None, str | None]:
        """``(report, problem)`` for a model's file, read once per version of the file."""
        from engine.hd2d.glb import GlbError, inspect_glb, model_problem  # noqa: PLC0415

        path = Path(self.studio.project.root) / asset.model
        try:
            stat = path.stat()
        except OSError:
            return None, f"The file {asset.model} is missing: reimport it, or put it back."
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        if key not in self._facts:
            problem = model_problem(self.studio.project.root, asset.model)
            try:
                self._facts[key] = (None, problem) if problem else (inspect_glb(path)[1], None)
            except GlbError as err:
                self._facts[key] = (None, str(err))
        return self._facts[key]

    def _thumbnail(self, rows: Any, asset: Any, width: int, height: int) -> None:
        """A model's picture: its saved preview, or (for a model imported before Stage 5B) one drawn now."""
        studio = self.studio
        space = gui.UISpace(width=width, height=height)
        key = str(Path(studio.project.root) / asset.preview) if asset.preview else ""
        if not key or not Path(key).is_file():
            key = f"model-preview:{asset.model}"
            if key not in studio._images:
                from engine.hd2d.glb import GlbError, load_glb  # noqa: PLC0415
                from engine.hd2d.thumbnail import render  # noqa: PLC0415

                try:
                    studio._images[key] = render(load_glb(Path(studio.project.root) / asset.model))
                except (GlbError, OSError):
                    studio._images[key] = None
        studio._thumbs.append((space, key))
        rows.add(space)

    def _forget_pictures(self, asset_id: str) -> None:
        """After an import or reimport: the browser reads the new preview and facts."""
        studio = self.studio
        for key in [k for k in studio._images if asset_id in k or k.startswith("model-preview:")]:
            studio._images.pop(key, None)
            studio._textures.pop(("thumb", key), None)
        self._assets = None

    def choose_model(self, asset_id: str | None) -> None:
        """Show a model's page (None: back to the list)."""
        self.chosen_model = asset_id
        self.studio.panel_scroll = 0
        self.studio._rebuild()

    def set_model_filter(self, text: str) -> None:
        self.model_filter = text.strip()
        self.studio.panel_scroll = 0
        self.studio._rebuild()

    def models_panel(self, rows: Any, width: int) -> None:
        """The list of models, or the chosen model's page."""
        studio = self.studio
        here: dict[str, int] = {}
        for st in self.structures():
            here[st.model] = here.get(st.model, 0) + 1
        chosen = self._asset(self.chosen_model)
        if chosen is not None:
            row = _row()
            row.add(studio._button("< All models", partial(self.choose_model, None), width=width - 86))
            row.add(studio._button("Close", self.open_models, width=80))
            rows.add(row)
            rows.add(studio._label(chosen.name, bold=True, size=12))
            rows.add(studio._label(f"{chosen.category or 'Uncatalogued'}  -  3D model (.glb)", color=C_MUTED, size=10))
            self._model_details(rows, chosen, width, here.get(chosen.model, 0))
            return
        rows.add(studio._label("Models", bold=True, size=12))
        rows.add(studio._label("3D structures made in Blender (.glb). Pictures and sprites are under each object's "
                               "Picture.", color=C_MUTED, size=10, width=width))
        row = _row()
        row.add(self._button("Import 3D model...", self.open_import, "Bring a .glb exported from Blender into the "
                             "project", width=width - 86, style=S_ACTIVE))
        row.add(studio._button("Close", self.open_models, width=80))
        rows.add(row)
        rows.add(self._search_row(width))
        words = self.model_filter.lower().split()
        everything = self.models()
        shown = [a for a in everything if all(w in f"{a.name} {a.category} {a.id} {a.notes}".lower() for w in words)]
        if not everything:
            rows.add(studio._label("No models yet. Export one from Blender (File > Export > glTF 2.0, glTF Binary), "
                                   "then Import 3D model.", color=C_MUTED, width=width))
        elif not shown:
            rows.add(studio._label(f"No model matches '{self.model_filter}'.", color=C_MUTED, width=width))
        category = None
        for asset in shown:
            if asset.category != category and asset.category:
                category = asset.category
                rows.add(studio._label(category, color=C_MUTED, size=10))
            count = here.get(asset.model, 0)
            label = asset.name + (" (missing file)" if asset.missing else f"  x{count}" if count else "")
            rows.add(LazyRow(36, partial(self._model_row, asset, label, width)))

    def _model_row(self, asset: Any, label: str, width: int) -> Any:
        row = _row()
        self._thumbnail(row, asset, 48, 36)
        row.add(self._button(label, partial(self.choose_model, asset.id), f"{asset.model}", width=width - 54))
        return row

    def _search_row(self, width: int) -> Any:
        row = _row()
        row.add(self.studio._label("Search", color=C_MUTED, size=10, width=56))
        row.add(self.studio._field(self.model_filter, self.set_model_filter, width=width - 62, key="model_search"))
        return row

    def _model_details(self, rows: Any, asset: Any, width: int, count: int) -> None:
        studio = self.studio
        self._thumbnail(rows, asset, width, int(width * 0.55))
        report, problem = self.facts(asset)
        if problem:
            rows.add(studio._label(problem, color=C_ERROR, size=10, width=width))
        elif report is not None:
            for line in report.lines():
                rows.add(studio._label(line, color=C_MUTED, size=10, width=width))
            if report.floors:
                rows.add(studio._label("Floors: " + ", ".join(report.floors), color=C_MUTED, size=10, width=width))
        rows.add(studio._label(f"{count} cop{'y' if count == 1 else 'ies'} in this room. File: {asset.model}",
                               color=C_MUTED, size=10, width=width))
        source = asset.source or {}
        if source:
            rows.add(studio._label(f"Imported {str(source.get('imported', '?'))[:10]} from {source.get('file', '?')}",
                                   color=C_MUTED, size=10, width=width))
        elif not asset.catalogued:
            rows.add(studio._label("Not in the catalogue yet (from before model import); fill in its details below.",
                                   color=C_MUTED, size=10, width=width))
        half = (width - 6) // 2
        row = _row()
        row.add(self._button("Place in scene", partial(self.place_chosen, asset.id), "Then click the ground where it "
                             "goes (Esc cancels)", width=half, style=S_ACTIVE, disabled=bool(problem)))
        row.add(self._button("Reimport...", partial(self.open_reimport, asset.id), "Update it from a new Blender "
                             "export; placed copies keep their places", width=half))
        rows.add(row)
        rows.add(studio._label("Details", bold=True, size=11))
        for label, key, value in (("Name", "name", asset.name), ("Category", "category", asset.category),
                                  ("Default turn", "rotation", f"{asset.rotation:g}"),
                                  ("Default scale", "scale", f"{asset.scale:g}"),
                                  ("Licence", "license", asset.license), ("Notes", "notes", asset.notes)):
            studio._labeled(rows, label, studio._field(value, partial(self.set_model_property, asset.id, key),
                                                       width=width - 122, key=f"model_{key}"), width)

    def set_model_property(self, asset_id: str, key: str, value: str) -> None:
        try:
            asset = self.studio.project.set_model_properties(asset_id, **{key: value})
        except ops.OpError as err:
            self.studio._say(str(err), ok=False)
            return
        self._assets = None
        self.chosen_model = asset.id
        self.studio._say(f"{asset.name}: {key} saved.")
        self.studio._rebuild()

    def place_chosen(self, asset_id: str) -> None:
        asset = self._asset(asset_id)
        if asset is not None:
            self.start_placing(asset.model, asset.rotation, asset.scale)

    # ------------------------------------------------------------------ import
    def open_import(self) -> None:
        self.studio._flush_fields()
        self.studio.panel, self.studio.panel_scroll = "import_model", 0
        self.studio._rebuild()

    def browse_import(self, form_key: str = "import") -> None:
        from engine.studio_ui import ask_path  # noqa: PLC0415  # a native file dialog: people only, never tests

        path = ask_path(folder=False, title="A model exported from Blender (glTF Binary)",
                        filetypes=[("glTF Binary", "*.glb"), ("All files", "*.*")])
        if path:
            (self.set_import_path if form_key == "import" else self.set_reimport_path)(path)

    def set_import_path(self, path: str) -> None:
        form = self.import_form
        form["path"] = path.strip().strip('"')
        if form["path"] and not form["name"]:
            form["name"] = Path(form["path"]).stem.replace("_", " ").replace("-", " ").strip().title()
        self.studio._rebuild()

    def _set_import(self, key: str, value: Any) -> None:
        self.import_form[key] = value.strip() if isinstance(value, str) else value
        self.studio._rebuild()

    def _inspection_picture(self, rows: Any, found: Any, width: int) -> None:
        if found.model is None:
            return
        studio = self.studio
        try:
            stat = found.source.stat()
            key = f"model-import:{found.source}:{stat.st_mtime_ns}:{stat.st_size}"
        except OSError:
            return
        if key not in studio._images:
            from engine.hd2d.thumbnail import render  # noqa: PLC0415

            studio._images[key] = render(found.model)
        space = gui.UISpace(width=width, height=int(width * 0.5))
        studio._thumbs.append((space, key))
        rows.add(space)

    def import_panel(self, rows: Any, width: int) -> None:
        from engine.hd2d.catalog import inspect_source  # noqa: PLC0415

        studio, form = self.studio, self.import_form
        rows.add(studio._label("Import a 3D model", bold=True, size=12))
        rows.add(studio._label("A .glb from Blender: File > Export > glTF 2.0, Format glTF Binary, with "
                               "Include > Custom Properties on (for collision).", color=C_MUTED, size=10, width=width))
        rows.add(studio._label("File (Enter to check)", color=C_MUTED))
        row = _row()
        row.add(studio._field(form["path"], self.set_import_path, width=width - 92, key="model_path"))
        row.add(studio._button("Browse...", self.browse_import, width=86))
        rows.add(row)
        for label, key in (("Name", "name"), ("Category", "category"), ("Licence / source", "license")):
            studio._labeled(rows, label, studio._field(form[key], partial(self._set_import, key), width=width - 122,
                                                       key=f"model_import_{key}"), width)
        rows.add(self._button(f"Keep pixels sharp: {'On' if form['sharp'] else 'Off'}",
                              lambda: self._set_import("sharp", not form["sharp"]),
                              "Pixel-art textures stay crisp even if Blender exported them smooth (Linear)",
                              width=width, style=S_ACTIVE if form["sharp"] else S_BUTTON))
        found = inspect_source(studio.project.root, form["path"], name=form["name"],
                               pixels="sharp" if form["sharp"] else "as exported") if form["path"] else None
        ok = found is not None and found.ok and not found.duplicate_of
        row = _row()
        row.add(studio._button("Import", self.import_now, width=96, style=S_ACTIVE, disabled=not ok))
        row.add(studio._button("Cancel", self.open_models_again, width=80))
        rows.add(row)
        if found is None:
            rows.add(studio._label("Choose a file to see what it holds.", color=C_MUTED, size=10, width=width))
        elif not found.ok:
            rows.add(studio._label(found.problem or "", color=C_ERROR, size=10, width=width))
        else:  # what happens and what to watch first, then the picture, then the facts
            if found.duplicate_of:
                rows.add(studio._label(f"Already imported as '{found.duplicate_of}'.", color=C_ERROR, size=10, width=width))
            else:
                rows.add(studio._label(f"It becomes assets/models/{found.asset_id}.glb.", color=C_MUTED, size=10, width=width))
            if found.sharpened:
                rows.add(studio._label(f"Made sharp: {', '.join(found.sharpened)}.", color=C_WARN, size=10, width=width))
            report = found.report
            for line in report.warnings if report else []:
                if not (found.sharpened and line.startswith("Smooth")):
                    rows.add(studio._label(line, color=C_WARN, size=10, width=width))
            self._inspection_picture(rows, found, width)
            for line in report.lines()[:len(report.lines()) - len(report.warnings)] if report else []:
                rows.add(studio._label(line, color=C_MUTED, size=10, width=width))

    def open_models_again(self) -> None:
        self.studio.panel, self.studio.panel_scroll = "structures", 0
        self.studio._rebuild()

    def import_now(self) -> None:
        studio, form = self.studio, self.import_form
        studio._flush_fields()
        try:
            asset = studio.project.import_model(form["path"], name=form["name"], category=form["category"],
                                                license=form["license"],
                                                pixels="sharp" if form["sharp"] else "as exported")
        except ops.OpError as err:
            studio._say(str(err), ok=False)
            return
        self._forget_pictures(asset.id)
        self.import_form = {"path": "", "name": "", "category": "", "license": "", "sharp": True}
        self.chosen_model = asset.id
        self.open_models_again()
        studio._say(f"Imported {asset.name} as {asset.model}. Place in scene puts a copy in the room.")

    # ------------------------------------------------------------------ reimport
    def open_reimport(self, asset_id: str) -> None:
        asset = self._asset(asset_id)
        if asset is None:
            return
        self.studio._flush_fields()
        self.reimport_form = {"id": asset.id, "path": str((asset.source or {}).get("file", ""))}
        self.studio.panel, self.studio.panel_scroll = "reimport_model", 0
        self.studio._rebuild()

    def set_reimport_path(self, path: str) -> None:
        self.reimport_form["path"] = path.strip().strip('"')
        self.studio._rebuild()

    def reimport_panel(self, rows: Any, width: int) -> None:
        studio, form = self.studio, self.reimport_form
        asset = self._asset(form["id"])
        if asset is None:
            self.open_models_again()
            return
        rows.add(studio._label(f"Reimport {asset.name}", bold=True, size=12))
        rows.add(studio._label("Replace this model with a new export from Blender. Every copy in every room keeps "
                               "its name, place and turn.", color=C_MUTED, size=10, width=width))
        rows.add(studio._label("From file (Enter to check)", color=C_MUTED))
        row = _row()
        row.add(studio._field(form["path"], self.set_reimport_path, width=width - 92, key="reimport_path"))
        row.add(studio._button("Browse...", partial(self.browse_import, "reimport"), width=86))
        rows.add(row)
        try:
            plan = studio.project.plan_reimport(asset.id, form["path"] or None)
        except ops.OpError as err:
            plan, problem = None, str(err)
        else:
            problem = plan.inspection.problem
        row = _row()
        row.add(studio._button("Reimport", self.reimport_now, width=96, style=S_ACTIVE, disabled=bool(problem)))
        row.add(studio._button("Cancel", self.open_models_again, width=80))
        rows.add(row)
        if problem or plan is None:
            rows.add(studio._label(problem or "", color=C_ERROR, size=10, width=width))
        else:
            rows.add(studio._label("What changes", bold=True, size=11))
            for line in plan.warnings:
                rows.add(studio._label(line, color=C_WARN, size=10, width=width))
            for line in plan.changes:
                rows.add(studio._label(line, color=C_MUTED, size=10, width=width))
            self._inspection_picture(rows, plan.inspection, width)

    def reimport_now(self) -> None:
        studio, form = self.studio, self.reimport_form
        studio._flush_fields()
        root = Path(studio.project.root)
        asset = self._asset(form["id"])
        if asset is None:
            return
        keep = {rel: (root / rel).read_bytes() if (root / rel).is_file() else None
                for rel in (asset.model, asset.preview or "", "assets/models/catalog.json") if rel}
        try:
            plan = studio.project.reimport_model(asset.id, form["path"] or None)
        except ops.OpError as err:
            studio._say(str(err), ok=False)
            return
        self._forget_pictures(asset.id)
        studio._reload()  # the room's renderer and world are rebuilt from the new file (the old GPU objects freed)
        error = getattr(studio.window, "hd2d_error", None)
        if error:  # it read fine but the room won't build with it: put the previous files back
            for rel, data in keep.items():
                if data is None:
                    (root / rel).unlink(missing_ok=True)
                else:
                    (root / rel).write_bytes(data)
            self._forget_pictures(asset.id)
            studio._reload()
            studio._say(f"The room couldn't use the new {asset.name} ({error}); the previous version is back.", ok=False)
            return
        self.open_models_again()
        changed = "; ".join(line.rstrip(".") for line in plan.changes[:2])
        warned = f" Check: {plan.warnings[0]}" if plan.warnings else ""
        studio._say(f"Reimported {asset.name}: {changed}.{warned}", ok=not plan.warnings)

    def inspector(self, rows: Any, width: int) -> None:
        """The selected structure: what it is, where it is (metres, degrees), and buttons to move it."""
        studio = self.studio
        st = self.find(self.structure)
        if st is None:
            return
        rows.add(studio._label(f"Structure '{st.id}'", bold=True, size=12))
        rows.add(studio._label(f"Model: {st.model}", color=C_MUTED, size=10, width=width))
        rows.add(studio._label("Blender made its shape and collision; here you place it.", color=C_MUTED,
                               size=10, width=width))
        field_w = width - 122
        for label, key, value in (("X (m)", "x", st.x / 32), ("Y (m)", "y", st.y / 32),
                                  ("Height (m)", "elevation", st.elevation / 32), ("Turn (degrees)", "rotation", st.rotation),
                                  ("Scale", "scale", st.scale)):
            studio._labeled(rows, label, studio._field(f"{value:g}", partial(self.set_metres, key),
                                                       width=field_w, key=f"structure_{key}"), width)
        third = (width - 8) // 3
        row = _row()
        row.add(self._button("Turn -90", lambda: self.nudge("Turned.", turn_deg=-90), "Turn it a quarter left", width=third))
        row.add(self._button("Turn +90", lambda: self.nudge("Turned.", turn_deg=90), "Turn it a quarter right", width=third))
        row.add(self._button("Turn +15", lambda: self.nudge("Turned.", turn_deg=15), "Turn it a little", width=third))
        rows.add(row)
        half = (width - 6) // 2
        row = _row()
        row.add(self._button("Raise 0.5 m", lambda: self.nudge("Raised.", up_m=STEP_UP_M), "Lift it off the ground", width=half))
        row.add(self._button("Lower 0.5 m", lambda: self.nudge("Lowered.", up_m=-STEP_UP_M), "Lower it (not below 0)", width=half))
        rows.add(row)
        row = _row()
        row.add(self._button(f"Snap 0.5 m: {'On' if self.snap else 'Off'}", self.toggle_snap,
                             "Dragging moves it in 0.5 m steps", width=half, style=S_ACTIVE if self.snap else S_BUTTON))
        row.add(self._button("Delete", self.remove, "Take it out of the room (Delete)", width=half))
        rows.add(row)
        rows.add(self._button(f"See-through in play: {'On' if st.cutaway else 'Off'}",
                              lambda: self.set_fields("See-through changed.", cutaway=not st.cutaway),
                              "In play, open a window in it where it would hide the player (a house, not a bridge)",
                              width=width, style=S_ACTIVE if st.cutaway else S_BUTTON))
        rows.add(studio._label("Drag it on the map to move it.", color=C_MUTED, size=10, width=width))

    def toggle_snap(self) -> None:
        self.snap = not self.snap
        self.studio._rebuild()

    def tooltip(self, x: float, y: float) -> str | None:
        for widget, tip in self.tips:
            rect = getattr(widget, "rect", None)
            if rect is not None and rect.left <= x <= rect.right and rect.bottom <= y <= rect.top:
                return tip
        return None
