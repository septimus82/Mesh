"""Mesh Studio's River tool (#461, R2): draw and edit a room's rivers in the HD-2D view, through R1's data and checks.

A river is ``settings.hd2d.rivers`` (engine.hd2d.river); every change the tool saves is one of R1's checked edits
(``project_ops.add_river``, ``set_river``, ``remove_river``): one undo step each, refused with R1's reasons. What the
tool shows before a change is saved (a river being drawn, a point being dragged) lives only in the renderer's
settings, never in the scene, and goes when the gesture is cancelled (Esc, undo, another room, Play) or refused.

- **Draw:** with nothing selected, a click on the ground starts a river there (its first point is upstream); each
  click adds a point downstream, at the ground under the mouse (the real terrain hit). Its water stands
  ``ABOVE_PX`` (0.25 m) over the ground clicked, never higher than the point before: a river only falls. Enter (or
  Finish) saves it once it has two points; Esc drops it.
- **Edit:** click a river to select it, a control point (its post) to select that; drag a point to move it (one
  undo step when let go, its width and water level kept); Insert puts a point after the selected one (on the
  course, halfway), Delete removes the selected point (a river keeps at least two) or, with no point selected, the
  river. The panel sets the point's width and water level, the river's flow and look, and turns it round: Reverse
  flow puts the points in the opposite order and gives them the levels in their old order (the highest first), so
  it relevels the water where it stands: a sloping river's surface rises at its old mouth and falls at its old
  source, and may need its bed sculpted again.
- **Refused edits:** a point, drag or field the checks refuse (a bank folding, banks touching, uphill, off the
  ground, too long) changes nothing: the last valid river stays drawn and saved, and the reason is said. While a
  drag goes somewhere refused the river stays as it last was valid and a red post marks the mouse.

Checking a candidate costs about 0.1 ms a metre of river (R1's measure); a drag checks at most once a frame (the
mouse's latest position: ``tick``), and the drawn ribbon is rebuilt only when what is shown changes, written into the
water layer's buffers while it fits their reserve (half as much again as when they were made); a river that grows
past it gets bigger buffers (engine.water.WaterLayer.set_rivers).
"""

from __future__ import annotations

import dataclasses
import math
import time
from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade
from engine import project_ops as ops
from engine.hd2d.settings import PIXELS_PER_METRE as PX

if TYPE_CHECKING:
    from engine.studio_hd2d import Hd2dView

PICK_PX = 12.0  # a control point's post is picked within this many screen pixels
NEW_WIDTH_PX = 64.0  # a new river's width: 2 m
ABOVE_PX = 8.0  # a new point's water stands this far above the ground clicked: 0.25 m
NEW_FLOW = 1.0  # m/s
POST_M = 0.6  # a control point's post: this tall over the water
IN_FRONT_M = 0.05  # something drawn this much nearer than the water, along the view, stands in front of it (the
# rivers' own centre lines, drawn 2 cm over the water, don't)


class RiverTool:
    def __init__(self, view: Hd2dView) -> None:
        self.view = view
        self.on = False
        self.selected: str | None = None  # the selected river's id
        self.point: int | None = None  # ... and its selected control point
        self.draft: list[list[float]] | None = None  # a river being drawn: its points so far (px), not saved
        self.draft_id: str | None = None
        self.gesture: dict[str, Any] | None = None  # a control point being dragged
        self.error: str | None = None  # why the last thing tried was refused (shown in the panel)
        self.width_px, self.above_px = NEW_WIDTH_PX, ABOVE_PX
        self.bed_depth: float | None = None  # Carve the bed: one depth (m) for every point, or None: by its width
        self._centres: dict[Any, list[tuple[float, float, float]]] = {}  # shown river -> its course (m), for drawing
        self.timings: dict[str, list[float]] = {"check_ms": [], "commit_ms": []}

    @property
    def studio(self) -> Any:
        return self.view.studio

    @property
    def renderer(self) -> Any | None:
        return self.view.renderer

    # ------------------------------------------------------------------ what is saved, what is shown
    def saved(self) -> list[dict[str, Any]]:
        return ops.rivers(self.studio.project.scene())

    def find(self, river_id: str | None) -> dict[str, Any] | None:
        return next((r for r in self.saved() if r.get("id") == river_id), None)

    def _check(self, raw: list[dict[str, Any]]) -> tuple[Any, ...] | str:
        """R1's checks on what would be saved (against the room's ground): the rivers, or why they can't be."""
        from engine.hd2d.river import RiverError, parse_rivers  # noqa: PLC0415

        renderer = self.renderer
        g = None if renderer is None else renderer.settings.ground
        bounds = None if g is None else (g.lo[0], g.lo[1], g.hi[0], g.hi[1])
        start = time.perf_counter()
        try:
            return parse_rivers(raw, bounds)
        except RiverError as err:
            return str(err)
        finally:
            self.timings["check_ms"].append((time.perf_counter() - start) * 1000)
            del self.timings["check_ms"][:-240]

    def _show(self, rivers: tuple[Any, ...]) -> None:
        """Draw these rivers (the renderer's settings only: nothing saved)."""
        renderer = self.renderer
        if renderer is not None and renderer.settings.rivers != rivers:
            renderer.settings = dataclasses.replace(renderer.settings, rivers=rivers)

    def show_saved(self) -> None:
        shown = self._check(self.saved())
        self._show(shown if isinstance(shown, tuple) else ())  # (broken rivers: set aside, as a load does)

    def _with(self, river_id: str, points: list[list[float]]) -> list[dict[str, Any]]:
        """The saved rivers with one river's points replaced (or a new river with them)."""
        rivers = [dict(r, points=points) if r.get("id") == river_id else r for r in self.saved()]
        if not any(r.get("id") == river_id for r in rivers):
            rivers.append({"id": river_id, "points": points})
        return rivers

    def _points(self, river_id: str | None) -> list[list[float]]:
        found = self.find(river_id)
        return [list(p) for p in found["points"]] if found else []

    # ------------------------------------------------------------------ the mode
    def toggle(self) -> None:
        if self.on:
            self.leave()
            self.studio._say("River tool off.")
        else:
            view = self.view
            view.cancel_stroke()
            view.sculpt, view.sculpt_at = None, None
            self.on = True
            self.studio._say("River: click the ground to start a river, upstream first; each click adds a point "
                             "downstream; Enter finishes. Click a river to select it, drag its posts to move points. "
                             "Insert adds a point, Delete removes one, Esc cancels.")
        self.studio._rebuild()

    def leave(self) -> None:
        self.cancel_edit()
        self.on, self.selected, self.point, self.error = False, None, None, None

    def cancel_edit(self, why: str | None = None) -> bool:
        """Drop an unfinished drag or a river being drawn (nothing saved). True if there was one."""
        had = self.gesture is not None or self.draft is not None
        self.gesture, self.draft, self.draft_id = None, None, None
        if had:
            self.show_saved()
            if why:
                self.studio._say(why, ok=False)
        return had

    def room_loaded(self) -> None:
        """The room was loaded again (an edit elsewhere, undo, redo, another room, Play stopped): an unfinished
        gesture is gone with it; the selection stays if its river is still there."""
        if self.gesture is not None or self.draft is not None:
            self.gesture, self.draft, self.draft_id = None, None, None
            self.studio._say("River edit cancelled: the room was loaded again.", ok=False)
        found = self.find(self.selected)
        if found is None:
            self.selected, self.point = None, None
        elif self.point is not None and self.point >= len(found.get("points") or []):
            self.point = None
        self._centres.clear()

    # ------------------------------------------------------------------ the mouse
    def _to_screen(self, p: tuple[float, float, float]) -> tuple[float, float] | None:
        left, right, bottom, top = self.view._rect()
        vp = self.view.camera.view_projection((right - left) / max(1.0, top - bottom))
        c = [sum(vp[r][k] * v for k, v in enumerate((*p, 1.0))) for r in range(4)]
        if c[3] <= 1e-6:
            return None
        return (left + (c[0] / c[3] * 0.5 + 0.5) * (right - left), bottom + (c[1] / c[3] * 0.5 + 0.5) * (top - bottom))

    def _point_under(self, x: float, y: float) -> tuple[str, int] | None:
        """The control point whose post is nearest the mouse (within PICK_PX): the selected river's first."""
        best: tuple[float, str, int] | None = None
        rivers = sorted(self.saved(), key=lambda r: r.get("id") != self.selected)
        for r in rivers:
            for i, p in enumerate(r.get("points") or []):
                for z in (p[3] / PX, p[3] / PX + POST_M):  # its foot or its top
                    at = self._to_screen((p[0] / PX, p[1] / PX, z))
                    if at is None:
                        continue
                    d = math.hypot(at[0] - x, at[1] - y)
                    if d <= PICK_PX and (best is None or d < best[0] - 1e-6):
                        best = (d, str(r.get("id")), i)
            if best is not None and r.get("id") == self.selected:
                break  # (the selected river's own points win)
        return None if best is None else (best[1], best[2])

    def _river_under(self, x: float, y: float) -> str | None:
        """The river whose water is drawn under the mouse: where the view's ray meets each river's surface (each quad
        of its ribbon at its height, as drawn: its level and the lift), the nearest such place, unless the ground
        rises over the water there (none is drawn) or something drawn solid stands in front of it along the ray (a
        bank, a bridge's deck: the last frame's depth at that pixel). Not the ground under the mouse: the water
        stands above it, so with the view at an angle the ground hit lies beyond the water, outside a narrow river."""
        from engine.hd2d.river import ribbon  # noqa: PLC0415
        from engine.water import LIFT_M  # noqa: PLC0415

        renderer, view = self.renderer, self.view
        if renderer is None:
            return None
        origin, direction = view.ray(x, y)
        if abs(direction[2]) < 1e-9:
            return None
        terrain = renderer.terrain
        best: tuple[float, str] | None = None
        for river in renderer.settings.rivers:
            rib = ribbon(river)
            for k in range(len(rib.centre) - 1):
                z = (rib.level[k] + rib.level[k + 1]) / 2 + LIFT_M
                t = (z - origin[2]) / direction[2]
                if t <= 0 or (best is not None and t >= best[0]):
                    continue
                p = (origin[0] + direction[0] * t, origin[1] + direction[1] * t)
                if not _in_quad((rib.left[k], rib.left[k + 1], rib.right[k + 1], rib.right[k]), p):
                    continue
                ground = None if terrain is None else terrain.height(p[0] * PX, p[1] * PX)
                if ground is not None and ground / PX >= z - LIFT_M:
                    continue  # (the ground rises over the water here: none is drawn)
                best = (t, river.id)
        if best is None:
            return None
        solid = self._solid_along(x, y, origin, direction)
        if solid is not None and solid < best[0] - IN_FRONT_M / math.sqrt(sum(c * c for c in direction)):
            return None
        return best[1]

    def _solid_along(self, x: float, y: float, origin: tuple[float, float, float],
                     direction: tuple[float, float, float]) -> float | None:
        """How far along the view's ray (in its own steps) the nearest thing drawn solid is at the mouse, from the
        last frame's depth there; None if nothing is (or there's no frame)."""
        renderer, view = self.renderer, self.view
        if renderer is None:
            return None
        vx, vy, _vw, _vh = view.viewport()
        window = self.studio.window
        k = window.get_framebuffer_size()[0] / max(1, window.width)
        depth = renderer.depth_at(int(x * k) - vx, int(y * k) - vy)
        vp = renderer.last_vp
        if depth is None or vp is None or depth >= 1.0:
            return None
        # where along the ray the projected depth is the depth drawn: ndc z = (a + b s) / (c + d s)
        a = sum(vp[2][i] * v for i, v in enumerate((*origin, 1.0)))
        b = sum(vp[2][i] * v for i, v in enumerate(direction))
        c = sum(vp[3][i] * v for i, v in enumerate((*origin, 1.0)))
        d = sum(vp[3][i] * v for i, v in enumerate(direction))
        ndc = depth * 2.0 - 1.0
        under = ndc * d - b
        return None if abs(under) < 1e-12 else (a - ndc * c) / under

    def press(self, x: float, y: float) -> None:
        studio, view = self.studio, self.view
        self.error = None
        at = view.ground_hit(x, y)
        if self.draft is not None:
            if at is None:
                studio._say("Point at the ground to add a point there.", ok=False)
                return
            self._add_draft_point(at)
            return
        hit = self._point_under(x, y)
        if hit is not None:
            same = hit == (self.selected, self.point)
            self.selected, self.point = hit
            points = self._points(self.selected)
            self.gesture = {"id": self.selected, "index": self.point, "before": points, "points": points,
                            "pending": None, "moved": False, "bad": None, "at": None, "started": time.perf_counter()}
            studio._say(f"River '{self.selected}', point {self.point + 1} of {len(points)}: drag to move it.")
            if not same:  # (the panel shows the selected point's fields: again only when it's another one)
                studio._rebuild()
            return
        rid = self._river_under(x, y)
        if rid is not None:
            self.selected, self.point = rid, None
            studio._say(f"River '{rid}' selected: drag its posts to move points; Delete removes it.")
            studio._rebuild()
            return
        if self.selected is not None:  # a click away from it: let go of it
            self.selected, self.point = None, None
            studio._say("Click the ground to start a river, or a river to select it.")
            studio._rebuild()
            return
        if at is None:
            studio._say("Point at the ground to start a river there.", ok=False)
            return
        self.draft, self.draft_id = [], self._new_id()
        self._add_draft_point(at)

    def _new_id(self) -> str:
        taken = {r.get("id") for r in self.saved()}
        return next(rid for rid in ("river", *(f"river-{n}" for n in range(2, 1000))) if rid not in taken)

    def _add_draft_point(self, at: tuple[float, float, float]) -> None:
        studio = self.studio
        assert self.draft is not None and self.draft_id is not None
        level = at[2] * PX + self.above_px
        width = self.width_px
        if self.draft:  # never above the point before: a river only falls
            level, width = min(level, self.draft[-1][3]), self.draft[-1][2]
        points = [*self.draft, [round(at[0] * PX, 2), round(at[1] * PX, 2), width, round(level, 2)]]
        if len(points) >= 2:
            shown = self._check(self._with(self.draft_id, points))
            if isinstance(shown, str):
                self.error = shown
                studio._say(f"That point is refused: {shown}. The river is as it was.", ok=False)
                studio._rebuild()
                return
            self._show(shown)
        self.draft = points
        studio._say(f"New river: {len(points)} point{'s' if len(points) > 1 else ''}. Click to add the next one "
                    "downstream; " + ("Enter finishes it, " if len(points) >= 2 else "") + "Esc drops it.")
        studio._rebuild()

    def finish(self) -> None:
        """Save the river being drawn (one undo step)."""
        draft, rid = self.draft, self.draft_id
        if draft is None or rid is None:
            return
        if len(draft) < 2:
            self.studio._say("A river needs at least two points: click the ground downstream of the first.", ok=False)
            return
        self.draft, self.draft_id = None, None
        if self._commit(lambda s: ops.add_river(s, rid, draft, flow=NEW_FLOW),
                        f"River '{rid}' added ({len(draft)} points). Drag its posts to shape it."):
            self.selected, self.point = rid, None
        self.studio._rebuild()

    def drag_to(self, x: float, y: float) -> None:
        if self.gesture is not None:
            self.gesture["pending"] = (x, y)  # (checked once a frame: tick)

    def tick(self) -> None:
        g = self.gesture
        if g is None or g["pending"] is None:
            return
        x, y = g["pending"]
        g["pending"] = None
        at = self.view.ground_hit(x, y)
        if at is None:
            g["bad"], g["at"] = "the mouse is off the ground", None
            return
        points = [list(p) for p in g["points"]]
        p = points[g["index"]]
        moved = [round(at[0] * PX, 2), round(at[1] * PX, 2), p[2], p[3]]  # (its width and water level kept)
        if moved[:2] == g["points"][g["index"]][:2] and g["bad"] is None:
            return
        g["moved"] = True
        points[g["index"]] = moved
        shown = self._check(self._with(g["id"], points))
        if isinstance(shown, str):  # the last valid shape stays drawn; a red post marks the mouse
            g["bad"], g["at"] = shown, at
            return
        g["points"], g["bad"], g["at"] = points, None, None
        self._show(shown)

    def release(self) -> None:
        g = self.gesture
        if g is None:
            return
        self.tick()
        self.gesture = None
        if not g["moved"]:
            return
        if g["bad"] is not None:
            self.show_saved()
            self.error = g["bad"]
            self.studio._say(f"Refused: {g['bad']}. The river is as it was.", ok=False)
            self.studio._rebuild()
            return
        if g["points"] == g["before"]:
            return
        rid, points, index = g["id"], g["points"], g["index"]
        self._commit(lambda s: ops.set_river(s, rid, points=points), f"Moved point {index + 1} of river '{rid}'.",
                     panel=False)  # (a move changes nothing the panel shows: only the top bar's Undo and unsaved mark)

    # ------------------------------------------------------------------ edits (one checked op each: one undo step)
    def _commit(self, change: Any, ok: str, *, panel: bool = True) -> bool:
        studio = self.studio
        start = time.perf_counter()
        try:
            studio.project.edit_scene(change)
        except ops.OpError as err:
            self.error = str(err)
            self.show_saved()
            studio._say(f"Refused: {err}. The river is as it was.", ok=False)
            studio._rebuild()
            return False
        self.error = None
        self.show_saved()  # (no reload: the room's rivers are drawn from what was saved)
        self.timings["commit_ms"].append((time.perf_counter() - start) * 1000)
        del self.timings["commit_ms"][:-240]
        if panel:
            studio._rebuild()
        else:
            studio._refresh_top_bar()
        studio._say(ok)
        return True

    def set_points(self, points: list[list[float]], ok: str) -> bool:
        rid = self.selected
        if rid is None:
            return False
        return self._commit(lambda s: ops.set_river(s, rid, points=points), ok)

    def insert_point(self) -> None:
        """A point after the selected one (before it, if it is the last), halfway along the course between them."""
        from engine.hd2d.river import halfway  # noqa: PLC0415

        points = self._points(self.selected)
        if self.point is None or len(points) < 2:
            self.studio._say("Select a river's point first (click its post).", ok=False)
            return
        i = min(self.point, len(points) - 2)
        x, y = halfway(points, i)
        a, b = points[i], points[i + 1]
        new = [round(x, 2), round(y, 2), round((a[2] + b[2]) / 2, 2), round((a[3] + b[3]) / 2, 2)]
        if self.set_points([*points[:i + 1], new, *points[i + 1:]], f"Point added between points {i + 1} and {i + 2}."):
            self.point = i + 1

    def remove_point(self) -> None:
        points = self._points(self.selected)
        if self.point is None:
            return
        if len(points) <= 2:
            self.studio._say("A river keeps at least two points: Remove river removes it all.", ok=False)
            return
        index = self.point
        if self.set_points([p for i, p in enumerate(points) if i != index], f"Point {index + 1} removed."):
            self.point = min(index, len(points) - 2)

    def set_point(self, *, width_m: float | None = None, level_m: float | None = None) -> None:
        points = self._points(self.selected)
        if self.point is None or self.point >= len(points):
            return
        p = points[self.point]
        if width_m is not None:
            p[2] = round(width_m * PX, 2)
        if level_m is not None:
            p[3] = round(level_m * PX, 2)
        self.set_points(points, f"Point {self.point + 1}: width {p[2] / PX:.2f} m, water at {p[3] / PX:+.2f} m.")

    def set_look(self, **change: Any) -> None:
        rid = self.selected
        if rid is None:
            return
        words = ", ".join(f"{k.replace('_', ' ')} {v:g}" if isinstance(v, float) else f"{k} {v}"
                          for k, v in change.items())
        self._commit(lambda s: ops.set_river(s, rid, **change), f"River '{rid}': {words}.")

    def reverse(self) -> None:
        """Flow the other way: the points in the opposite order, given the levels in their old order (the highest
        first, as a river must fall). This relevels the water where it stands: a sloping river's surface rises at
        its old mouth and falls at its old source (its bed may need sculpting again)."""
        points = self._points(self.selected)
        if len(points) < 2:
            return
        turned = [[x, y, w, level] for (x, y, w, _l), level in zip(reversed(points), [p[3] for p in points])]
        sloped = points[0][3] != points[-1][3]
        if self.set_points(turned, "The river flows the other way now." + (
                f" Its water was relevelled: {turned[0][3] / PX:+.2f} m at its new source, {turned[-1][3] / PX:+.2f} m "
                "at its new mouth (check it against the bed)." if sloped else "")):
            self.point = None

    def remove_river(self) -> None:
        rid = self.selected
        if rid is None:
            return
        if self._commit(lambda s: ops.remove_river(s, rid), f"River '{rid}' removed."):
            self.selected, self.point = None, None

    def key(self, symbol: int) -> bool:
        k = optional_arcade.arcade.key
        if symbol in (k.ENTER, k.NUM_ENTER) and self.draft is not None:
            self.finish()
        elif symbol == k.INSERT and self.selected is not None and self.gesture is None:
            self.insert_point()
        elif symbol == k.DELETE and self.gesture is None and self.draft is None and self.selected is not None:
            self.remove_point() if self.point is not None else self.remove_river()
        else:
            return False
        return True

    def cancel(self) -> bool:
        """Esc: drop a drag or a river being drawn, else let go of the selected point, else of the river."""
        if self.cancel_edit("Cancelled: the river is as it was." if self.gesture is not None
                            else "The new river is dropped."):
            self.studio._rebuild()
            return True
        if self.point is not None:
            self.point = None
        elif self.selected is not None:
            self.selected = None
        else:
            return False
        self.studio._rebuild()
        return True

    # ------------------------------------------------------------------ drawing (Studio's overlay, through the world)
    def _course(self, river: Any) -> list[tuple[float, float, float]]:
        found = self._centres.get(river)
        if found is None:
            from engine.hd2d.river import ribbon  # noqa: PLC0415

            rib = ribbon(river)
            found = [(c[0], c[1], z + 0.02) for c, z in zip(rib.centre, rib.level)]
            if len(self._centres) > 32:
                self._centres.clear()
            self._centres[river] = found
        return found

    def overlay(self, vp: tuple[float, ...]) -> None:
        renderer = self.renderer
        if renderer is None or not self.on:
            return
        shown = {r.id: r for r in renderer.settings.rivers}
        for rid, river in shown.items():
            mine = rid in (self.selected, self.draft_id)
            course = self._course(river)
            renderer.draw_lines(vp, [p for a, b in zip(course, course[1:]) for p in (a, b)],
                                (0.45, 0.85, 1.0, 0.9 if mine else 0.35), through=mine)
        points: list[tuple[str | None, list[float]]] = []
        for r in self.saved():
            if r.get("id") == self.selected and self.gesture is not None:
                points += [(r.get("id"), p) for p in self.gesture["points"]]
            elif r.get("id") in shown:
                points += [(r.get("id"), list(p)) for p in r.get("points") or []]
        if self.draft is not None:
            points += [(self.draft_id, p) for p in self.draft]
        index: dict[str | None, int] = {}
        for rid, p in points:
            i = index[rid] = index.get(rid, -1) + 1
            x, y, z = p[0] / PX, p[1] / PX, p[3] / PX
            colour = ((0.5, 1.0, 0.5, 1.0) if rid == self.draft_id else
                      (1.0, 0.85, 0.3, 1.0) if rid == self.selected and i == self.point else
                      (0.45, 0.85, 1.0, 1.0) if rid == self.selected else (0.85, 0.9, 1.0, 0.55))
            s = 0.12 if rid in (self.selected, self.draft_id) else 0.08
            renderer.draw_lines(vp, [(x, y, z), (x, y, z + POST_M)], colour, through=True)
            renderer.draw_lines(vp, _box((x - s, y - s, z + POST_M - 2 * s), (x + s, y + s, z + POST_M)), colour,
                                through=True)
        g = self.gesture
        if g is not None and g["bad"] is not None and g["at"] is not None:  # where the mouse is, refused: red
            x, y, z = g["at"]
            renderer.draw_lines(vp, [(x, y, z), (x, y, z + POST_M)], (1.0, 0.35, 0.3, 1.0), through=True)
            renderer.draw_lines(vp, _box((x - 0.14, y - 0.14, z + POST_M - 0.28), (x + 0.14, y + 0.14, z + POST_M)),
                                (1.0, 0.35, 0.3, 1.0), through=True)

    # ------------------------------------------------------------------ the panel
    def section(self, box: Any, width: int) -> None:
        from engine.studio_ui import C_ERROR, C_MUTED, S_ACTIVE, S_BUTTON  # noqa: PLC0415  # (the panel only: GUI)

        studio, view = self.studio, self.view
        half = (width - 4) // 2

        def metres(apply: Any, lo: float, hi: float) -> Any:
            def commit(text: str) -> None:
                try:
                    value = float(text)
                except ValueError:
                    value = math.nan
                if not math.isfinite(value) or not lo <= value <= hi:
                    studio._say(f"Type a number from {lo:g} to {hi:g}.", ok=False)
                    studio._rebuild()
                    return
                apply(value)
            return commit

        def field_row(label: str, text: str, commit: Any, key: str) -> None:
            row = _row()
            row.add(studio._label(label, color=C_MUTED, size=10, width=half))
            row.add(studio._field(text, commit, width=width - half - 4, key=key))
            box.add(row)

        if self.draft is not None:
            box.add(studio._label(f"Drawing a new river: {len(self.draft)} point(s). Click the ground downstream to "
                                  "add points; Enter finishes (two at least); Esc drops it.", size=10, width=width))
            row = _row()
            row.add(view._button("Finish", self.finish, "Save the new river (Enter): one undo step", width=half,
                                 style=S_ACTIVE if len(self.draft) >= 2 else S_BUTTON))
            row.add(view._button("Drop", self.cancel, "Drop the new river (Esc)", width=half))
            box.add(row)
        found = self.find(self.selected)
        if found is not None and self.draft is None:
            pts = found.get("points") or []
            box.add(studio._label(f"River '{self.selected}': {len(pts)} points, flowing "
                                  f"{float(found.get('flow', NEW_FLOW)):g} m/s from point 1.", bold=True, size=10,
                                  width=width))
            field_row("Flow (m/s)", f"{float(found.get('flow', NEW_FLOW)):g}",
                      metres(lambda v: self.set_look(flow=v), 0.0, 8.0), "river_flow")
            field_row("Waves (0-1)", f"{float(found.get('waves', 0.5)):g}",
                      metres(lambda v: self.set_look(waves=v), 0.0, 1.0), "river_waves")
            field_row("Reflection (0-1)", f"{float(found.get('reflection', 0.35)):g}",
                      metres(lambda v: self.set_look(reflection=v), 0.0, 1.0), "river_reflection")
            if self.point is not None and self.point < len(pts):
                p = pts[self.point]
                box.add(studio._label(f"Point {self.point + 1} of {len(pts)} (drag its post to move it)", size=10,
                                      width=width))
                field_row("Width (m)", f"{p[2] / PX:.2f}", metres(lambda v: self.set_point(width_m=v), 0.5, 16.0),
                          "river_width")
                field_row("Water level (m)", f"{p[3] / PX:+.2f}",
                          metres(lambda v: self.set_point(level_m=v), -2048.0, 2048.0), "river_level")
                row = _row()
                row.add(view._button("Insert point", self.insert_point, "A point after this one, halfway along the "
                                     "course (Insert)", width=half))
                row.add(view._button("Remove point", self.remove_point, "Remove this point (Delete); a river keeps "
                                     "two at least", width=half))
                box.add(row)
            else:
                box.add(studio._label("Click a post to select its point.", color=C_MUTED, size=10, width=width))
            row = _row()
            row.add(view._button("Reverse flow", self.reverse, "Turn the river round: its points in the opposite "
                                 "order, its water levels moved so they still fall downstream. This relevels the "
                                 "water: where it ran low it now stands high (sculpt the bed to match)", width=half))
            row.add(view._button("Remove river", self.remove_river, "Remove the whole river (Delete with no point "
                                 "selected)", width=half))
            box.add(row)
            box.add(studio._label("Its bed: carving lowers the ground under the water into a channel with "
                                  "walkable banks. Water deeper than 0.5 m can't be waded.", color=C_MUTED, size=10,
                                  width=width))
            field_row("Bed depth (m)", "by width" if self.bed_depth is None else f"{self.bed_depth:.2f}",
                      self._set_bed_depth, "river_bed_depth")
            row = _row()
            row.add(view._button("Carve the bed", self.carve_bed, "Lower the ground under the river into its bed and "
                                 "banks (one undo step; ground already lower is kept)", width=half))
            row.add(view._button("Clear plants", self.clear_scatter, "Take away the scattered grass, flowers, bushes "
                                 "and rocks standing in its water (reeds may stay in the shallows; nothing else is "
                                 "touched)", width=half))
            box.add(row)
        elif self.draft is None:
            box.add(studio._label("Click the ground to start a river (its first point is upstream), or click a river "
                                  "to select it.", size=10, width=width))
            for r in self.saved():
                rid = str(r.get("id"))
                box.add(view._button(f"Select '{rid}'", lambda rid=rid: self._select(rid),
                                     f"Select river '{rid}'", width=width))
        if found is None or self.draft is not None:
            field_row("New width (m)", f"{self.width_px / PX:.2f}",
                      metres(lambda v: self._set_new(width_px=v * PX), 0.5, 16.0), "river_new_width")
            field_row("Water above ground (m)", f"{self.above_px / PX:.2f}",
                      metres(lambda v: self._set_new(above_px=v * PX), -4.0, 4.0), "river_new_above")
        box.add(studio._label("Its water shows where it stands above the ground: carve its bed (select it, then Carve "
                              "the bed) or sculpt one. A point's water is never above the one before.", color=C_MUTED,
                              size=10, width=width))
        if self.error:
            box.add(studio._label(f"Last refused: {self.error}", color=C_ERROR, size=10, width=width))

    def _set_bed_depth(self, text: str) -> None:
        """The Bed depth box: a depth in metres (0 to 8), or empty / "by width" for a quarter of the river's width."""
        text = text.strip().lower()
        if text in ("", "by width", "auto"):
            self.bed_depth = None
        else:
            try:
                value = float(text)
            except ValueError:
                value = math.nan
            if not math.isfinite(value) or not 0.0 <= value <= 8.0:
                self.studio._say("Type a depth from 0 to 8 m, or leave it empty: a quarter of the river's width.",
                                 ok=False)
                self.studio._rebuild()
                return
            self.bed_depth = value
        self.studio._rebuild()

    def carve_bed(self) -> None:
        """Carve the selected river's bed into the ground (project_ops.carve_river_bed, one undo step; the room is
        loaded again: its ground and what is walked on change)."""
        rid = self.selected
        if rid is None or self.gesture is not None or self.draft is not None:
            return
        n = len(self._points(rid))
        depths = None if self.bed_depth is None else [self.bed_depth] * n
        how = "a quarter of its width deep" if depths is None else f"{self.bed_depth:.2f} m deep"
        self.studio._edit(lambda s: ops.carve_river_bed(s, rid, depths),
                          f"River '{rid}': its bed carved, {how} in the middle. Undo puts the ground back.")

    def clear_scatter(self) -> None:
        """Take away the scattered decoration standing in the selected river's water (one undo step)."""
        rid = self.selected
        if rid is None or self.gesture is not None or self.draft is not None:
            return
        self.studio._edit(lambda s: ops.clear_scatter_in_rivers(s, rid),
                          f"River '{rid}': the scattered plants and rocks in its water taken away.")

    def _select(self, river_id: str) -> None:
        self.selected, self.point = river_id, None
        self.studio._rebuild()

    def _set_new(self, **change: float) -> None:
        for key, value in change.items():
            setattr(self, key, value)
        self.studio._rebuild()


def _row() -> Any:
    from engine.studio_ui import gui  # noqa: PLC0415

    return gui.UIBoxLayout(vertical=False, space_between=4)


def _in_quad(quad: tuple[tuple[float, float], ...], p: tuple[float, float]) -> bool:
    """Whether ``p`` lies in the convex quad (its corners in order, either way round)."""
    signs = set()
    for i in range(4):
        (ax, ay), (bx, by) = quad[i], quad[(i + 1) % 4]
        c = (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)
        if c != 0.0:
            signs.add(c > 0)
    return len(signs) < 2


def _box(lo: tuple[float, float, float], hi: tuple[float, float, float]) -> list[tuple[float, float, float]]:
    from engine.hd2d.picking import box_edges  # noqa: PLC0415

    return list(box_edges(lo, hi))
