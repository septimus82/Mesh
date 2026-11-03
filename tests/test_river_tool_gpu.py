"""#461 R2: Mesh Studio's River tool, in a hidden Studio window driven by its own input events (GL-gated:
MESH_GL_SMOKE=1).

The starter village with a stream bed already sculpted under its bridge (tooling/r1_river_study.py, beds only):
River beside Sculpt, Paint and Scatter; a river drawn by clicking the ground from upstream to downstream and
finished with Enter; a point dragged; a drag the checks refuse (the river as it was); insert and remove a point;
width, water level and flow typed in (an uphill level refused); undo and redo; Esc mid-drag and a room change
mid-draw cancel without saving; save and reopen; Play shows the saved river flowing. Each saved change is one undo
step; a drag allocates no new GPU buffers and builds no new shader while it moves."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
    pytest.mark.filterwarnings("ignore:.*style dict.*:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


def _rivers(d: Any) -> list[dict[str, Any]]:
    from engine import project_ops as ops

    return ops.rivers(d.studio.project.scene())


def test_a_creator_draws_edits_and_plays_a_river_in_studio(tmp_path: Path, record_testsuite_property: Any) -> None:
    import r1_river_study as r1
    from hd2d_studio_demo import StudioDriver

    from engine.studio_project import Project

    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    project = r1.make_project(tmp_path, "tool", rivers=False)  # the beds, sculpted; no river yet
    d = StudioDriver(project)
    measures: dict[str, Any] = {}
    try:
        k, studio, view = d.arcade.key, d.studio, d.studio.hd2d
        tool = view.river
        terrain = d.renderer.terrain

        def ground(px: float, py: float) -> tuple[float, float, float]:
            return (px / 32, py / 32, terrain.surface_at(px, py)[0] / 32)

        def post(index: int) -> tuple[float, float]:
            x, y, _w, level = _rivers(d)[0]["points"][index]
            return d.screen((x / 32, y / 32, level / 32))

        def steps() -> int:
            return len(studio.project._undo)

        d.button("Terrain")
        assert d.has_button("Sculpt") and d.has_button("Paint") and d.has_button("Scatter") and d.has_button("River")
        d.button("River")
        assert tool.on and view.sculpt is None
        view.camera.target = (20.0, 24.0, 0.0)
        d.advance(2)

        # draw: a click a point, upstream to downstream, on the bed's ground (the real terrain hit); Enter finishes
        undo0 = steps()
        for x, y, _w, _l in r1.NORTH:
            d.click(*d.screen(ground(x, y)))
        assert tool.draft is not None and len(tool.draft) == 5 and _rivers(d) == [], "drawn, not saved yet"
        assert steps() == undo0, "drawing saves nothing until it's finished"
        d.key(k.ENTER)
        (river,) = _rivers(d)
        assert steps() == undo0 + 1, "the new river: one undo step"
        pts = river["points"]
        assert len(pts) == 5 and all(b[3] <= a[3] for a, b in zip(pts, pts[1:])), "falling downstream"
        for (x, y, _w, level), (cx, cy, _cw, _cl) in zip(pts, r1.NORTH):
            assert abs(x - cx) < 2 and abs(y - cy) < 2, (x, y, cx, cy)  # where it was clicked
            assert level > terrain.surface_at(x, y)[0], "its water stands over the bed it was drawn on"
        assert [r.id for r in d.renderer.settings.rivers] == ["river"]
        d.frame()
        assert d.renderer.water is not None and d.renderer.water.rivers, "drawn"

        # drag a point: one undo step when let go; it moves, the others stay, its width and water level kept
        before = [list(p) for p in pts]
        water = d.renderer.water
        allocations, programs = water.river_allocations, d.gl_counts()["program"]
        target = ground(before[2][0] + 24, before[2][1])
        start = time.perf_counter()
        d.drag(post(2), d.screen(target), steps=12)
        measures["drag_12_moves_ms"] = round((time.perf_counter() - start) * 1000, 1)
        after = _rivers(d)[0]["points"]
        assert steps() == undo0 + 2 and abs(after[2][0] - (before[2][0] + 24)) < 2, (after[2], before[2])
        assert after[2][2:] == before[2][2:] and [p for i, p in enumerate(after) if i != 2] == \
            [p for i, p in enumerate(before) if i != 2]
        assert water.river_allocations - allocations <= 1, "a drag writes into the buffers it has"
        assert d.gl_counts()["program"] == programs, "no shader built for a drag"

        # a drag the checks refuse: dragged back past the first point (the course would fold); nothing changes
        good = [list(p) for p in after]
        d.window.dispatch_event("on_mouse_motion", *post(1), 0, 0)
        d.window.dispatch_event("on_mouse_press", *post(1), d.arcade.MOUSE_BUTTON_LEFT, 0)
        bad = d.screen(ground(good[0][0] + 40, good[0][1] - 140))
        d.window.dispatch_event("on_mouse_drag", *bad, 0, 0, d.arcade.MOUSE_BUTTON_LEFT, 0)
        d.advance()
        assert tool.gesture is not None and tool.gesture["bad"], "refused while it's dragged there"
        assert [list(p) for p in d.renderer.settings.rivers[0].points] == good, "the last valid river stays drawn"
        d.window.dispatch_event("on_mouse_release", *bad, d.arcade.MOUSE_BUTTON_LEFT, 0)
        d.advance()
        assert _rivers(d)[0]["points"] == good and steps() == undo0 + 2, "refused: nothing saved"
        assert "Refused" in studio.message and tool.error, studio.message
        d.picture(tmp_path / "refused.png")

        # Esc mid-drag: cancelled, nothing saved, the saved river drawn
        d.window.dispatch_event("on_mouse_press", *post(3), d.arcade.MOUSE_BUTTON_LEFT, 0)
        moved = d.screen(ground(good[3][0] + 20, good[3][1]))
        d.window.dispatch_event("on_mouse_drag", *moved, 0, 0, d.arcade.MOUSE_BUTTON_LEFT, 0)
        d.advance()
        d.key(k.ESCAPE)
        d.window.dispatch_event("on_mouse_release", *moved, d.arcade.MOUSE_BUTTON_LEFT, 0)
        d.advance()
        assert tool.gesture is None and _rivers(d)[0]["points"] == good and steps() == undo0 + 2
        assert [list(p) for p in d.renderer.settings.rivers[0].points] == good

        # insert after point 1, then remove it again: one undo step each
        d.click(*post(0))
        assert tool.point == 0
        d.key(k.INSERT)
        assert len(_rivers(d)[0]["points"]) == 6 and tool.point == 1 and steps() == undo0 + 3
        d.key(k.DELETE)
        assert _rivers(d)[0]["points"] == good and steps() == undo0 + 4

        # width and water level typed in; a level above the point upstream is refused (the river as it was)
        d.click(*post(2))
        d.type_into("river_width", "2.5")
        assert _rivers(d)[0]["points"][2][2] == 80.0 and steps() == undo0 + 5
        uphill = good[1][3] / 32 + 0.5
        d.type_into("river_level", f"{uphill:.2f}")
        assert _rivers(d)[0]["points"][2][3] == good[2][3] and steps() == undo0 + 5, "uphill: refused"
        assert "uphill" in studio.message, studio.message
        assert "river_level" in studio._held, "Studio holds the refused value in its box, as for any field"
        box = studio._focusable["river_level"].rect
        d.click(box.left + box.width / 2, box.bottom + box.height / 2)
        d.key(k.ESCAPE)  # (in the box: put back as it was)
        assert "river_level" not in studio._held
        d.type_into("river_flow", "0.5")
        assert _rivers(d)[0]["flow"] == 0.5 and steps() == undo0 + 6

        # undo, redo: a step at a time, drawn as saved (Esc first: out of the box typed in, as a person would)
        d.key(k.ESCAPE)
        d.key(k.Z, k.MOD_CTRL)
        assert "flow" not in _rivers(d)[0] and steps() == undo0 + 5
        d.key(k.Y, k.MOD_CTRL)
        assert _rivers(d)[0]["flow"] == 0.5
        assert [list(p) for p in d.renderer.settings.rivers[0].points] == _rivers(d)[0]["points"]

        # a room change mid-draw: the unfinished river is dropped, nothing saved
        d.key(k.ESCAPE)  # (let go of the point)
        d.key(k.ESCAPE)  # (... and of the river)
        d.click(*d.screen(ground(800, 520)))
        d.click(*d.screen(ground(900, 520)))
        assert tool.draft is not None and len(tool.draft) == 2
        d.button("Rooms")
        d.button("Cottage", prefix=True)
        d.button("Village", prefix=True)
        assert tool.draft is None and len(_rivers(d)) == 1

        # save, reopen: the same river
        saved = _rivers(d)
        d.key(k.S, k.MOD_CTRL)
        world = json.loads((project / "config.json").read_text(encoding="utf-8"))["world_file"]
        reopened = Project(project, world)
        from engine import project_ops as ops

        assert ops.rivers(reopened.scene(studio.project.current)) == saved

        # Play: the saved river, flowing on the game's own clock; Stop: back to editing it
        d.key(k.F4)
        assert studio.mode == "play"
        game_renderer = d.window.hd2d_renderer
        d.advance(30)
        assert [r.id for r in game_renderer.settings.rivers] == ["river"]
        assert [list(p) for p in game_renderer.settings.rivers[0].points] == saved[0]["points"]
        assert d.window.water_time > 0.4 and game_renderer.water is not None and game_renderer.water.rivers
        d.key(k.F4)
        assert studio.mode == "edit" and _rivers(d) == saved

        measures.update({k2: {"median": round(sorted(v)[len(v) // 2], 2), "max": round(max(v), 2), "n": len(v)}
                         for k2, v in tool.timings.items() if v})
    finally:
        record_testsuite_property("measure.river_tool", json.dumps(measures))  # reporting only
        d.close()


def test_losing_focus_drops_a_river_being_drawn_or_a_point_being_dragged(tmp_path: Path) -> None:
    """The window loses the keyboard (Alt+Tab) mid-gesture: a river still being drawn and a point being dragged are
    both dropped. Nothing is saved, the undo history and unsaved state are as they were, the saved rivers are
    drawn again, and nothing of the gesture resumes when the person comes back."""
    import r1_river_study as r1
    from hd2d_studio_demo import StudioDriver

    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    project = r1.make_project(tmp_path, "focus", rivers=False)
    d = StudioDriver(project)
    try:
        k, left, studio = d.arcade.key, d.arcade.MOUSE_BUTTON_LEFT, d.studio
        tool, terrain = studio.hd2d.river, d.renderer.terrain

        def ground(px: float, py: float) -> tuple[float, float, float]:
            return (px / 32, py / 32, terrain.surface_at(px, py)[0] / 32)

        def state() -> tuple[Any, ...]:
            p = studio.project
            return (json.dumps(_rivers(d)), len(p._undo), len(p._redo), p.revision, sorted(p.dirty))

        def shown() -> list[list[list[float]]]:
            return [[list(p) for p in r.points] for r in d.renderer.settings.rivers]

        d.button("Terrain")
        d.button("River")
        studio.hd2d.camera.target = (20.0, 24.0, 0.0)
        d.advance(2)

        # (a) a river being drawn: two points, not saved
        before = state()
        for x, y, _w, _l in r1.NORTH[:2]:
            d.click(*d.screen(ground(x, y)))
        assert tool.draft is not None and len(tool.draft) == 2 and len(shown()) == 1, "drawn, shown, not saved"
        d.window.dispatch_event("on_deactivate")
        d.advance()
        assert tool.draft is None and tool.gesture is None and state() == before and shown() == []
        assert "lost focus" in studio.message, studio.message
        d.click(*d.screen(ground(*r1.NORTH[2][:2])))  # back: a click starts afresh, nothing resumed
        assert tool.draft is not None and len(tool.draft) == 1
        d.key(k.ESCAPE)
        assert tool.draft is None and state() == before

        # (b) a point being dragged: the river saved first, then a drag that loses focus before it's let go
        for x, y, _w, _l in r1.NORTH:
            d.click(*d.screen(ground(x, y)))
        d.key(k.ENTER)
        saved, saved_shown = state(), shown()
        x, y, _w, level = _rivers(d)[0]["points"][2]
        start, to = d.screen((x / 32, y / 32, level / 32)), d.screen(ground(x + 24, y))
        d.window.dispatch_event("on_mouse_press", *start, left, 0)
        d.window.dispatch_event("on_mouse_drag", *to, to[0] - start[0], to[1] - start[1], left, 0)
        d.advance()
        assert tool.gesture is not None and shown() != saved_shown, "dragged, shown where it is dragged"
        d.window.dispatch_event("on_deactivate")
        d.advance()
        assert tool.gesture is None and state() == saved and shown() == saved_shown, "dropped: as saved"
        # the release that comes when the person is back (or a stray drag) does nothing
        d.window.dispatch_event("on_mouse_drag", *start, 0, 0, left, 0)
        d.window.dispatch_event("on_mouse_release", *start, left, 0)
        d.advance()
        assert tool.gesture is None and state() == saved and shown() == saved_shown
    finally:
        d.close()


def test_a_narrow_raised_river_is_selected_by_its_water_not_the_ground_behind_it(tmp_path: Path) -> None:
    """Studio's ordinary angled camera, 0.5 m rivers standing 0.31 m over their beds: a click on a visible water pixel
    (away from every post) of one running across the view selects it, though the ground under that pixel lies
    beyond the river; a click on dry ground beside it doesn't; a click where the bridge's deck hides the other one
    doesn't either. Which pixels show a river is measured: the frame with the rivers against the frame without."""
    import dataclasses
    import math

    import r1_river_study as r1
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops
    from engine.hd2d.river import ribbon
    from engine.studio_river import PICK_PX
    from engine.water import LIFT_M

    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    project = r1.make_project(tmp_path, "narrow", rivers=False)  # the beds: floors 17-22 px below the ground
    path = project / "packs" / "core_regions" / "scenes" / "start.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    # 0.5 m wide, 10 px (0.31 m) over the floor
    narrow = {rid: [[x, y, 16.0, level - 2.0] for x, y, _w, level in course]
              for rid, course in (("across", r1.EAST), ("under", r1.NORTH))}
    for rid, points in narrow.items():
        scene = ops.add_river(scene, rid, points)
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    d = StudioDriver(project)
    try:
        k, studio = d.arcade.key, d.studio
        view, tool = studio.hd2d, studio.hd2d.river
        d.button("Terrain")
        d.button("River")
        renderer = d.renderer
        shown = renderer.settings.rivers

        def look_at(target: tuple[float, float, float]) -> None:  # (Studio's own pitch and lens: its angled view)
            view.camera.target = target
            d.advance(2)

        def pixel(at: tuple[float, float], rivers: tuple[Any, ...]) -> Any:
            renderer.settings = dataclasses.replace(renderer.settings, rivers=rivers)
            try:
                return d.frame().convert("RGB").getpixel((int(at[0]), d.window.height - 1 - int(at[1])))
            finally:  # (the rivers drawn again, as saved: what the clicks below pick from)
                renderer.settings = dataclasses.replace(renderer.settings, rivers=shown)

        def surface(rid: str, near_px: tuple[float, float]) -> tuple[float, float, float]:
            rib = ribbon(next(r for r in shown if r.id == rid))
            i = min(range(len(rib.centre)), key=lambda j: math.dist(rib.centre[j], (near_px[0] / 32, near_px[1] / 32)))
            return (rib.centre[i][0], rib.centre[i][1], rib.level[i] + LIFT_M)

        # across the view: a water pixel halfway between two posts, and dry floor 1 m nearer the camera
        look_at((11.0, 1.0, 0.0))
        water = surface("across", (365.0, 95.0))
        floor = renderer.terrain.surface_at(water[0] * 32, water[1] * 32)[0] / 32
        assert water[2] - floor >= 0.25, (water, floor)
        water_at = d.screen(water)
        posts = [d.screen((p[0] / 32, p[1] / 32, p[3] / 32 + z)) for p in narrow["across"] for z in (0.0, 0.6)]
        assert min(math.dist(water_at, s) for s in posts) > 3 * PICK_PX, "away from every post"
        assert pixel(water_at, shown) != pixel(water_at, ()), "a pixel the river is drawn on"
        behind = view.ground_hit(*water_at)
        rib = ribbon(next(r for r in shown if r.id == "across"))
        assert behind is not None and min(math.dist(behind[:2], c) for c in rib.centre) > 0.25, \
            "(the ground under that pixel lies beyond the narrow river: picking by it would miss it)"
        dry = (water[0], water[1] - 1.0, renderer.terrain.surface_at(water[0] * 32, (water[1] - 1.0) * 32)[0] / 32)
        dry_at = d.screen(dry)
        assert pixel(dry_at, shown) == pixel(dry_at, ()), "a dry-floor pixel: no river drawn there"
        d.click(*dry_at)
        assert tool.selected is None, "dry ground beside it: not the river"
        d.key(k.ESCAPE)  # (that click started a river there: dropped)
        d.click(*water_at)
        assert tool.selected == "across" and tool.draft is None and tool.point is None, (tool.selected, studio.message)
        d.key(k.ESCAPE)  # (let go of it)

        # behind the bridge's deck (y 768 px; from this camera the deck hides the water a little north of it): the
        # first place along the other river's course, going north, that the frames show hidden
        look_at((20.0, 21.0, 0.0))
        candidates = [d.screen(surface("under", (640.0, y))) for y in range(776, 1000, 8)]
        hidden_at = next((at for at in candidates if pixel(at, shown) == pixel(at, ())), None)
        assert hidden_at is not None, "the deck stands in front of the water somewhere behind the bridge"
        d.click(*hidden_at)
        assert tool.selected is None, "hidden behind the bridge's deck: not the river"
        d.key(k.ESCAPE)
        assert ops.rivers(studio.project.scene()) == [{"id": rid, "points": pts} for rid, pts in narrow.items()], \
            "nothing changed"
    finally:
        d.close()
