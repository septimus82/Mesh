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
- **place**: "Add a structure" lists the project's .glb models; the chosen one follows the mouse until a click
  places it.

Every change is one ``project_ops`` operation through Mesh Studio's ordinary edit path (``Studio._edit``): one undo
step, saved with the room, the same operations AI tools propose. A 2D room never creates this view's state or
draws through it.
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
from engine.studio_ui import C_MUTED, S_ACTIVE, S_BUTTON, gui

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
        self.snap = True
        self.picker = Picker()
        self.tips: list[tuple[Any, str]] = []  # (button, short tooltip) for the 3D view's buttons
        self._room: str | None = None
        self._buried: set[str] = set()  # objects that can't stand where they are (inside a structure)
        self.newly_buried: list[str] = []  # ... since the last load: what the last change did
        self.timings: dict[str, list[float]] = {"draw_ms": [], "pick_ms": [], "edit_ms": []}

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
            lines = [p for i in range(int(x0), int(x1) + 1) for p in ((float(i), y0, z), (float(i), y1, z))]
            lines += [p for j in range(int(y0), int(y1) + 1) for p in ((x0, float(j), z), (x1, float(j), z))]
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
        start = time.perf_counter()
        origin, direction = self.ray(x, y)
        sprites = [s for s in renderer._sprites() if (getattr(s, "mesh_entity_data", None) or {}).get("id")]
        stretch = 1.0 / max(0.5, math.cos(math.radians(self.camera.pitch)))
        hit = self.picker.pick(origin, direction, self.structures(), renderer.models, sprites, self.camera.right(), stretch)
        self.timings["pick_ms"].append((time.perf_counter() - start) * 1000)
        if hit is None:
            self.select_structure(None)
            self.studio.select(None)
            return True
        if hit.kind == "sprite":  # a character or object: Studio's ordinary object editing
            self.structure = None
            entity_id = hit.target.mesh_entity_data["id"]
            self.studio.select(entity_id)
            entity = self.studio._entity(entity_id) or {}
            z = float((hit.target.mesh_entity_data or {}).get("elevation", 0.0) or 0.0) / PIXELS_PER_METRE
            at = self.ground_px(x, y, z)
            if at is not None:
                self.drag = {"kind": "entity", "id": entity_id, "plane": z, "moved": False,
                             "dx": float(entity.get("x", 0)) - at[0], "dy": float(entity.get("y", 0)) - at[1],
                             "to": (entity.get("x", 0), entity.get("y", 0))}
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

    def drag_to(self, x: float, y: float) -> None:
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
        return self.drag is not None

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
        root = Path(self.studio.project.root)
        found = []
        for path in sorted(root.rglob("*.glb")):
            rel = path.relative_to(root).as_posix()
            if not any(part.startswith(".") or part in ("artifacts", "exports") for part in path.relative_to(root).parts):
                found.append(rel)
        return found

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

    def start_placing(self, model: str) -> None:
        if not self._ensure_model(model):
            return
        self.placing = model
        self.studio.panel = "inspect"
        self.studio._say(f"Placing {Path(model).name}: click the ground to put it there (Esc cancels).")
        self.studio._rebuild()

    def hover(self, x: float, y: float) -> None:
        renderer = self.renderer
        if self.placing is None or renderer is None:
            return
        at = self.ground_px(x, y)
        if at is None:
            renderer.set_preview(None)
            return
        gx = _snap(at[0] / PIXELS_PER_METRE, self.snap) * PIXELS_PER_METRE
        gy = _snap(at[1] / PIXELS_PER_METRE, self.snap) * PIXELS_PER_METRE
        renderer.set_preview(self.placing, gx, gy)

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

        def change(scene: dict[str, Any]) -> dict[str, Any]:
            new_scene, sid = ops.place_structure(scene, model, gx, gy)
            made["id"] = sid
            return new_scene

        self.placing = None
        if self.renderer is not None:
            self.renderer.set_preview(None)
        if self.studio._edit(change, f"Placed {Path(model).name} at {gx / 32:g} m, {gy / 32:g} m."):
            self.select_structure(made.get("id"))

    def cancel(self) -> bool:
        """Esc: stop placing, or let go of the selected structure. True if there was something to cancel."""
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
        box.add(self._button("Add a structure...", self.open_models, "Place a copy of a Blender model (.glb) "
                             "from this project", width=width, style=S_ACTIVE if studio.panel == "structures" else S_BUTTON))

    def open_models(self) -> None:
        studio = self.studio
        studio._flush_fields()
        studio.panel = "inspect" if studio.panel == "structures" else "structures"
        studio._rebuild()

    def models_panel(self, rows: Any, width: int) -> None:
        studio = self.studio
        rows.add(studio._label("Add a structure", bold=True, size=12))
        rows.add(studio._label("Models (.glb) in this project, as exported from Blender. Pick one, then click the "
                               "ground where it goes.", color=C_MUTED, width=width))
        models = self.models_in_project()
        if not models:
            rows.add(studio._label("No .glb files in this project yet: export one from Blender into assets/.",
                                   color=C_MUTED, width=width))
        for model in models:
            rows.add(self._button(Path(model).name, partial(self.start_placing, model), model, width=width))
        rows.add(studio._button("Cancel", self.open_models, width=96))

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
