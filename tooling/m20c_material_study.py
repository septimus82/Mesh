"""Milestone 20C evidence: painted terrain materials (hidden windows only; Studio through its own window events).

    py -3.13 tooling/m20c_material_study.py look OUT     # the study room at the gameplay camera, dry and in rain
    py -3.13 tooling/m20c_material_study.py edges OUT    # the cliff-top fringe and path borders: 20B's, hard, soft
    py -3.13 tooling/m20c_material_study.py studio OUT   # painting in Studio: strokes, undo/redo/save/reopen, cancels
    py -3.13 tooling/m20c_material_study.py flat OUT     # a plain room's first paint stroke, its undo and Esc
    py -3.13 tooling/m20c_material_study.py scale OUT    # 32 x 24, 64 x 64, 128 x 128 m, unpainted and painted (run alone)

The room is Milestone 20A's Hills room (tooling/m20a_terrain_study.py: a hill, a terrace with a cliff, the bridge
over a valley, a pond in a basin, the cottage), painted only through ``project_ops.paint_terrain_stroke`` (as Studio
and AI paint):

- a winding earth path from the cottage, down into the valley south of the bridge and up again, to the pond;
- a stone path up the ramp onto the terrace, and the terrace's cliff and its top edge bare rock;
- mud around the pond, a little sand on its far side;
- the hill left grass.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
import hd2d_visual_study as study  # noqa: E402
import m20a_terrain_study as m20a  # noqa: E402
import review_media  # noqa: E402
from hd2d_demo import SCENES, HiddenGame  # noqa: E402

PX = 32.0
# the winding earth path (m): from the cottage's door east, down into the valley south of the bridge, up to the pond
EARTH_PATH = [(5.6, 3.4), (7.0, 3.6), (9.2, 4.4), (11.0, 6.0), (12.6, 6.4), (14.2, 5.6), (15.6, 6.2), (17.2, 7.4),
              (19.0, 7.0), (20.6, 6.0), (22.0, 6.4)]
STONE_PATH = [(18.6, 17.4), (20.0, 18.6), (21.6, 19.2), (23.2, 18.8), (24.6, 19.0), (26.0, 19.6), (27.4, 19.2)]


def _spline(points: list[tuple[float, float]], step: float) -> list[tuple[float, float]]:
    """A Catmull-Rom curve through the points, a point every ``step`` m or so: an organic line, not a polyline."""
    def at(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
        return 0.5 * (2 * p1 + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                      + (3 * p1 - p0 - 3 * p2 + p3) * t * t * t)

    out = []
    pts = [points[0], *points, points[-1]]
    for k in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[k - 1], pts[k], pts[k + 1], pts[k + 2]
        n = max(1, math.ceil(math.dist(p1, p2) / step))
        for i in range(n):
            out.append((at(p0[0], p1[0], p2[0], p3[0], i / n), at(p0[1], p1[1], p2[1], p3[1], i / n)))
    out.append(points[-1])
    return out


def paint(scene: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """The room painted, stroke by stroke, through the checked operation. Returns it and the strokes."""
    from engine import project_ops as ops

    n = 0

    def stroke(material: str, line: list[tuple[float, float]], radius: float, strength: float,
               wobble: float = 0.0) -> None:
        nonlocal scene, n
        dabs = []
        for k, (x, y) in enumerate(_spline(line, radius / 4) if len(line) > 1 else line):
            r = radius * (1.0 + wobble * math.sin(k * 0.7) * math.sin(k * 0.23))  # (a path's width breathes)
            dabs.append([round(x * PX, 2), round(y * PX, 2), strength])
            if wobble:
                scene = ops.paint_terrain_stroke(scene, material, dabs, r * PX)
                dabs, n = [], n + 1
        if dabs:
            scene = ops.paint_terrain_stroke(scene, material, dabs, radius * PX)
            n += 1

    stroke("earth", EARTH_PATH, 0.75, 0.5, wobble=0.25)
    stroke("stone", STONE_PATH, 0.7, 0.5, wobble=0.2)
    x0, x1, y0, _y1, _h = m20a.TERRACE  # the terrace's cliff (its south side) and its top edge: bare rock
    stroke("stone", [(x0 + 1.0 + 0.5 * k, y0 + 0.1 * math.sin(k)) for k in range(int((x1 - x0 - 1.0) / 0.5))], 1.1, 0.6)
    bx, by, br, _d = m20a.BASIN  # the pond's banks mud, wider on its west (the path's) side; a little sand east
    stroke("mud", [(bx + br * 0.7 * math.cos(a / 20 * math.tau) * (1.15 if math.cos(a / 20 * math.tau) < 0 else 1.0),
                    by + br * 0.65 * math.sin(a / 20 * math.tau)) for a in range(21)], 0.9, 0.5)
    stroke("sand", [(bx + br * 0.8, by - 1.2), (bx + br * 0.95, by + 0.2), (bx + br * 0.75, by + 1.4)], 0.7, 0.45)
    return scene, n


def make_project(out: Path, name: str, *, rain: bool = False, painted: bool = True, edges: str = "soft") -> Path:
    """The Hills room (20A), painted (or not), with soft or hard edges."""
    from engine import project_ops as ops

    project: Path = m20a.make_project(out, name, rain=rain)
    path = project / SCENES / "hills.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    if painted:
        scene, _n = paint(scene)
    if edges != "soft":
        scene = ops.set_terrain_edges(scene, edges)
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    return project


def open_room(out: Path, name: str, **kw: Any) -> HiddenGame:
    game = HiddenGame(make_project(out, name, **kw), size=study.SIZE)
    game.load(f"{SCENES}/hills.json")
    game.step(30)
    return game


VIEWS = {"path": (9.0, 5.0), "valley": (15.0, 7.0), "pond": (24.0, 6.5), "rock": (26.0, 16.5), "hill": (5.0, 17.5),
         "bridge": (15.0, 13.0)}


def look(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for rain in (False, True):
        for painted in (False, True):
            tag = f"{'rain' if rain else 'dry'}_{'painted' if painted else 'unpainted'}"
            game = open_room(out, f"look_{tag}", rain=rain, painted=painted)
            try:
                m20a.shot(game, 16.0, 12.0, distance=90.0).save(out / f"overview_{tag}.png")
                for name, (x, y) in VIEWS.items():
                    m20a.shot(game, x, y).save(out / f"{name}_{tag}.png")
            finally:
                game.close()


def _paint(project: Any) -> bytes | None:
    from engine import project_ops as ops
    from engine.hd2d.terrain import Terrain

    paint = Terrain.from_ground(ops._parsed_ground(project.scene())).paint
    return bytes(paint) if paint is not None else None


def _whole(paint: Any, terrain: Any) -> bytes:
    return bytes(paint) if paint is not None else bytes(4 * (terrain.nx + 1) * (terrain.ny + 1))


def _on_ground(d: Any, line: list[tuple[float, float]], step: float = 0.05) -> list[tuple[float, float, float]]:
    """A line of points on the ground as drawn (m), for Studio's mouse: the curve through ``line``."""
    terrain = d.studio.hd2d.renderer.terrain
    out = []
    for x, y in _spline(line, step) if len(line) > 1 else line:
        h = terrain.height(x * PX, y * PX) if terrain is not None else None
        out.append((x, y, (h if h is not None else 0.0) / PX))
    return out


def _look_at(d: Any, x: float, y: float, distance: float = 16.0) -> None:
    """Studio's view on (x, y) m from ``distance`` m: where a creator would pan and zoom to before painting there."""
    camera = d.studio.hd2d.camera
    camera.target, camera.distance = (x, y, 0.0), distance
    d.advance(2)


def studio(out: Path) -> dict[str, Any]:
    """A creator painting in Mesh Studio, with its own window events: a winding earth path drawn in one continuous
    stroke down into the valley and up again (its frames timed, filmed); one undo step, redo, save and reopen
    exactly; heights and collision untouched; Esc, Play, a room change and a refused upload mid-stroke; Shift paints
    grass back, Alt+click picks a material, [ ] resize, the material and edge buttons; then the rest of the study
    room painted the same way (stone on the rocky slope, mud by the pond)."""
    import m18_particles_study as m18
    import m20b_sculpt_study as m20b

    out.mkdir(parents=True, exist_ok=True)
    project = m20a.make_project(out, "studio")
    report: dict[str, Any] = {}
    d = m20b._driver(project)
    try:
        s, view, k = d.studio, d.studio.hd2d, d.arcade.key
        d.button("Paint")
        d.button("Earth")
        terrain = view.renderer.terrain
        heights = list(terrain.heights)
        world = d.window.hd2d_world
        probes = [(x, y) for x in (9.0, 12.5, 15.0, 17.5) for y in (4.0, 6.0, 7.0)]
        walk_before = [world.heights_at(x, y) for x, y in probes]
        undo_before = len(s.project._undo)
        before = _paint(s.project)
        clip: list[Any] = []

        def film(i: int) -> None:
            if i % 6 == 0 and len(clip) < 60:
                clip.append(m18.crop_at(d.frame().convert("RGB"), 640, 400, (720, 405)))
                if i == 180:
                    clip[-1].save(out / "paint_mid.png")

        m20b.RELEASES.clear()
        view.timings["sculpt_ms"].clear()
        _look_at(d, 12.0, 6.0, 30.0)
        frames = m20b._stroke(d, _on_ground(d, EARTH_PATH, 0.05), each=film)  # (about 3 m a second)
        shown = _whole(view.renderer.terrain.paint, terrain)
        saved = _whole(_paint(s.project), terrain)
        report["stroke"] = {"frame_ms": m20b._stats(frames), "paint_upload_ms": m20b._stats(view.timings["sculpt_ms"]),
                            "commit_ms": round(view.timings["edit_ms"][-1], 1) if view.timings["edit_ms"] else None,
                            "release_to_next_frame_ms": round(m20b.RELEASES[-1], 1) if m20b.RELEASES else None,
                            "dabs": len(frames), "undo_steps_added": len(s.project._undo) - undo_before,
                            "shown_equals_saved": shown == saved, "heights_unchanged": terrain.heights == heights,
                            "collision_unchanged": [world.heights_at(x, y) for x, y in probes] == walk_before,
                            "chunks_stored": len(s.project.scene()["settings"]["hd2d"]["ground"]["terrain"]
                                                 .get("materials", {})),
                            "message": s.message}
        if clip:
            review_media.save_clip(clip, out / "paint_stroke.webp", duration=100, quality=80, method=6)
        d.picture(out / "paint_after.png")
        # undo and redo the whole stroke; save; reopen (below)
        d.key(k.Z, k.MOD_CTRL)
        report["undo_gives_before"] = (_paint(s.project) == before
                                       and _whole(view.renderer.terrain.paint, terrain) == _whole(before, terrain))
        d.key(k.Y, k.MOD_CTRL)
        report["redo_gives_after"] = (_whole(_paint(s.project), terrain) == saved
                                      and _whole(view.renderer.terrain.paint, view.renderer.terrain) == saved)
        d.key(k.S, k.MOD_CTRL)
        report["saved_dirty_after"] = s.project.is_dirty
        undo_n = len(s.project._undo)
        mid = [(17.0, 8.5), (19.5, 9.5)]

        def unchanged() -> dict[str, bool]:
            return {"nothing_recorded": len(s.project._undo) == undo_n,
                    "paint_is_saved": _whole(view.renderer.terrain.paint, view.renderer.terrain) == saved}

        # Esc mid-stroke
        m20b._stroke(d, _on_ground(d, mid), release=False)
        moved = _whole(view.renderer.terrain.paint, view.renderer.terrain) != saved
        d.key(k.ESCAPE)
        d.window.dispatch_event("on_mouse_release", *d.screen((19.5, 9.5, 0.0)), d.arcade.MOUSE_BUTTON_LEFT, 0)
        d.advance()
        report["escape"] = {"stroke_had_painted": moved, **unchanged(), "message": s.message}
        # Play (F4) mid-stroke, then Stop
        m20b._stroke(d, _on_ground(d, mid), release=False)
        d.key(k.F4)
        played = s.mode
        d.window.dispatch_event("on_mouse_release", 600, 300, d.arcade.MOUSE_BUTTON_LEFT, 0)
        d.key(k.F4)
        d.advance(3)
        report["play_mid_stroke"] = {"mode": played, "after_stop": s.mode, **unchanged()}
        # a room change mid-stroke
        m20b._stroke(d, _on_ground(d, mid), release=False)
        d.button("Village")
        d.window.dispatch_event("on_mouse_release", 600, 300, d.arcade.MOUSE_BUTTON_LEFT, 0)
        d.advance(2)
        d.button("Hills")
        d.advance(2)
        if view.sculpt is None:
            d.button("Paint")
        _look_at(d, 12.0, 6.0, 30.0)
        report["room_change_mid_stroke"] = unchanged()
        # a refused upload mid-stroke (the paint's texture write fails)
        renderer = view.renderer
        m20b._stroke(d, _on_ground(d, mid), release=False)
        original = renderer.update_paint  # (the texture's write is the driver's: refused at the renderer's call to it)

        def refusing(*a: Any, **kw: Any) -> Any:
            raise RuntimeError("out of memory (simulated)")

        renderer.update_paint = refusing
        try:
            last = d.screen(_on_ground(d, [(19.5, 9.5)])[0])
            for p in _on_ground(d, [(19.5, 9.5), (21.0, 10.0)])[1:]:
                s_ = d.screen(p)
                d.window.dispatch_event("on_mouse_drag", s_[0], s_[1], s_[0] - last[0], s_[1] - last[1],
                                        d.arcade.MOUSE_BUTTON_LEFT, 0)
                d.advance()
                last = s_
        finally:
            renderer.update_paint = original
        d.advance(2)
        d.window.dispatch_event("on_mouse_release", 600, 300, d.arcade.MOUSE_BUTTON_LEFT, 0)
        d.advance(2)
        report["refused_upload"] = {**unchanged(), "message": s.message}
        # focus lost mid-stroke (Alt+Tab): the stroke ends there, as one undo step, and paints no more
        m20b._stroke(d, _on_ground(d, mid), release=False)
        d.window.dispatch_event("on_deactivate")
        held = _paint(s.project)
        d.advance(20)
        report["focus_lost_mid_stroke"] = {"stroke_ended": view.stroke is None,
                                           "undo_steps_added": len(s.project._undo) - undo_n,
                                           "paints_no_more": _paint(s.project) == held and _whole(
                                               view.renderer.terrain.paint, view.renderer.terrain) == _whole(
                                               held, view.renderer.terrain)}
        d.key(k.Z, k.MOD_CTRL)
        d.window.dispatch_event("on_mouse_release", 600, 300, d.arcade.MOUSE_BUTTON_LEFT, 0)
        # Shift paints grass back over part of the path; Alt+click picks; [ ] resize; edges
        d.window.dispatch_event("on_key_press", k.LSHIFT, 0)
        m20b._stroke(d, _on_ground(d, [(10.6, 5.6), (11.4, 6.4)]))
        d.window.dispatch_event("on_key_release", k.LSHIFT, 0)
        t_now = view.renderer.terrain
        report["shift_paints_grass"] = t_now.material_at(11.0 * PX, 6.0 * PX)
        d.button("Stone")
        d.window.dispatch_event("on_key_press", k.LALT, 0)
        d.click(*d.screen(_on_ground(d, [(9.2, 4.4)])[0]))
        d.window.dispatch_event("on_key_release", k.LALT, 0)
        picked = view.sculpt["material"]
        r0 = view.sculpt["radius"]
        d.key(k.BRACKETRIGHT)
        r1 = view.sculpt["radius"]
        d.key(k.BRACKETLEFT)
        undo_e = len(s.project._undo)
        d.button("Soft")  # (soft already: no edit, no undo step)
        soft_again = len(s.project._undo) - undo_e
        d.button("Hard")
        hard = view.renderer.terrain.edges
        d.picture(out / "studio_paint_controls.png")
        d.key(k.Z, k.MOD_CTRL)
        report["controls"] = {"alt_click_picked": picked, "radius_px": [r0, r1, view.sculpt["radius"]],
                              "hard_edges": hard, "edges_one_undo_step": len(s.project._undo) == undo_e,
                              "soft_when_soft_adds_undo_steps": soft_again,
                              "edges_after_undo": view.renderer.terrain.edges}
        if view.sculpt is None:
            d.button("Paint")
        # the rest of the study room, painted in Studio: stone up the ramp and over the cliff, mud by the pond
        x0, x1, y0, _y1, _h = m20a.TERRACE
        d.button("Stone")
        _look_at(d, 23.0, 16.5, 16.0)
        for line in (STONE_PATH, [(x0 + 1.0, y0 + 0.2), (x1 - 0.5, y0 + 0.2)]):
            m20b._stroke(d, _on_ground(d, line))
        d.button("Mud")
        bx, by, br, _d = m20a.BASIN
        _look_at(d, bx, by, 14.0)
        ring = [(bx + br * 0.75 * math.cos(a / 16 * math.tau), by + br * 0.7 * math.sin(a / 16 * math.tau))
                for a in range(17)]
        m20b._stroke(d, _on_ground(d, ring))
        d.advance(2)
        d.picture(out / "studio_painted_pond.png")
        _look_at(d, 16.0, 11.0, 34.0)
        d.picture(out / "studio_painted.png")
        # the path is still editable after sculpting: a mound raised across it keeps the paint (it follows the new
        # shape), and a branch painted up over the mound
        _look_at(d, 13.5, 5.0, 18.0)
        paint_before = _paint(s.project)
        d.button("Sculpt")
        m20b._stroke(d, _on_ground(d, [(12.6, 5.2), (13.2, 6.0), (13.8, 6.8)]))
        mound = view.renderer.terrain
        report["sculpt_over_the_path"] = {
            "paint_kept": _paint(s.project) == paint_before,
            "path_raised_m": round((mound.height(13.2 * PX, 6.0 * PX) or 0.0) / PX, 3),
            "still_earth_there": mound.material_at(13.2 * PX, 6.0 * PX)}
        d.button("Paint")
        d.button("Earth")
        m20b._stroke(d, _on_ground(d, [(13.2, 6.0), (13.6, 4.4), (14.6, 3.2)]))  # (towards the camera: in view)
        report["branch_over_the_mound"] = view.renderer.terrain.material_at(13.6 * PX, 4.4 * PX)
        d.picture(out / "studio_path_after_sculpt.png")
        report["undo_steps_for_the_room"] = len(s.project._undo)
        final = _paint(s.project)
        d.key(k.S, k.MOD_CTRL)
    finally:
        d.close()
    d = m20b._driver(project)
    try:
        report["reopened_same"] = _paint(d.studio.project) == final and _whole(
            d.studio.hd2d.renderer.terrain.paint, d.studio.hd2d.renderer.terrain) == _whole(final,
                                                                                           d.studio.hd2d.renderer.terrain)
    finally:
        d.close()
    return report


def first_paint_on_flat(out: Path) -> dict[str, Any]:
    """A room with plain flat ground (the template's village): the first paint stroke makes it painted ground in
    place; nothing moves; undo makes it the plain ground again."""
    import m20b_sculpt_study as m20b

    project = m20a.make_project(out, "flat", stages=(), pond=False)
    d = m20b._driver(project)
    report: dict[str, Any] = {}
    try:
        s, view, k = d.studio, d.studio.hd2d, d.arcade.key
        d.button("Village")
        d.advance(3)

        def terrain_key() -> Any:
            return ((s.project.scene().get("settings") or {}).get("hd2d") or {}).get("ground", {}).get("terrain")

        report["before"] = {"terrain": terrain_key() is not None}
        d.button("Paint")
        frames = m20b._stroke(d, _on_ground(d, [(14.0, 13.0), (18.0, 13.5)]))
        t = terrain_key() or {}
        report["after"] = {"materials_stored": bool(t.get("materials")), "heights_stored": bool(t.get("chunks")),
                           "frame_ms": m20b._stats(frames)}
        d.picture(out / "flat_first_paint.png")
        d.key(k.Z, k.MOD_CTRL)
        report["undo_back_to_plain_ground"] = terrain_key() is None and view.renderer.terrain is None
        d.button("Paint")
        m20b._stroke(d, _on_ground(d, [(14.0, 13.0), (18.0, 13.5)]), release=False)
        d.key(k.ESCAPE)
        d.window.dispatch_event("on_mouse_release", 600, 300, d.arcade.MOUSE_BUTTON_LEFT, 0)
        d.advance(2)
        report["escape_back_to_plain_ground"] = terrain_key() is None and view.renderer.terrain is None
    finally:
        d.close()
    return report


def _paint_all_over(scene: dict[str, Any], size_m: tuple[float, float]) -> dict[str, Any]:
    """The scale room painted about half over, every material showing: winding paths, patches, banks."""
    import random

    from engine import project_ops as ops
    from engine.hd2d.terrain import MATERIALS, Terrain

    ground = ops._parsed_ground(scene)
    terrain = Terrain.from_ground(ground)
    rng = random.Random(11)
    w, h = size_m
    for _ in range(int(w * h / 12)):
        material = rng.choice(MATERIALS[1:])
        x, y, a = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(0, math.tau)
        for k in range(12):  # a short winding stroke
            a += rng.uniform(-0.5, 0.5)
            x, y = x + 0.4 * math.cos(a), y + 0.4 * math.sin(a)
            terrain.paint_dab(material, x * PX, y * PX, rng.uniform(0.6, 1.6) * PX, 0.6)
    raw = scene["settings"]["hd2d"]["ground"]
    raw["terrain"] = terrain.settings(raw.get("terrain"))
    return scene


def scale(out: Path) -> dict[str, Any]:
    """Per ground size (32 x 24, 64 x 64, 128 x 128 m, sculpted all over, raining), unpainted and painted about half
    over with every material: what is stored, room load, frames playing (CPU and GPU), draw calls, GPU memory; then
    in Studio a 6 m paint stroke's frames, its upload, commit and release, undo, the idle frame and the save."""
    import m19_water_study as m19
    import m20b_sculpt_study as m20b

    from engine import project_ops as ops

    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    for size in ((32.0, 24.0), (64.0, 64.0), (128.0, 128.0)):
        name = f"{int(size[0])}x{int(size[1])}"
        for painted in (False, True):
            tag = f"{name}_{'painted' if painted else 'unpainted'}"
            project = m20b.scale_project(out, f"scale_{tag}", size)
            path = project / SCENES / "hills.json"
            scene = ops.set_particles(json.loads(path.read_text(encoding="utf-8")), m20a.RAIN)
            if painted:
                scene = _paint_all_over(scene, size)
            path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
            terrain_raw = scene["settings"]["hd2d"]["ground"]["terrain"]
            row: dict[str, Any] = {"stored_chars": len(path.read_text(encoding="utf-8")),
                                   "materials_chars": sum(len(v) for v in terrain_raw.get("materials", {}).values()),
                                   "materials_chunks": len(terrain_raw.get("materials", {})),
                                   "heights_chars": sum(len(v) for v in terrain_raw.get("chunks", {}).values())}
            game = HiddenGame(project, size=study.SIZE)
            try:
                t0 = time.perf_counter()
                game.load(f"{SCENES}/hills.json")
                row["game_room_load_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                game.step(10)
                hd = game.window.hd2d_renderer
                player = game.player()
                player.center_x = size[0] / 2 * PX
                player.center_y += size[1] / 2 * PX - player.bottom
                player.mesh_entity_data["elevation"] = hd.terrain.height(player.center_x, size[1] / 2 * PX) or 0.0
                for _ in range(120):
                    game.window.dispatch_event("on_update", 1 / 60)
                    game.window.dispatch_event("on_draw")
                cpu = []
                for _ in range(60):
                    t1 = time.perf_counter()
                    game.window.dispatch_event("on_update", 1 / 60)
                    game.window.dispatch_event("on_draw")
                    game.window.ctx.finish()
                    cpu.append((time.perf_counter() - t1) * 1000)
                row["frame_ms_playing"] = m20b._stats(cpu)
                row["frame_gpu_ms"] = round(m19._frame_gpu_ms(game, 30), 3)
                stats = hd.stats()
                row["draw_calls"] = stats["draw_calls"]
                row["terrain_draws"] = stats["terrain_draws"]
                row["terrain_mesh_gpu_bytes"] = stats["terrain_bytes"]
                row["paint_texture_bytes"] = (hd._paint_texture.width * hd._paint_texture.height * 4
                                              if hd._paint_texture is not None else 0)
                row["material_tiles_bytes"] = hd._material_atlas.width * hd._material_atlas.height * 4
                row["particles"] = stats["particles"]
                row["shadows"] = stats["shadows"]
            finally:
                game.close()
            d = m20b._driver(project)
            try:
                s, view, k = d.studio, d.studio.hd2d, d.arcade.key
                d.button("Paint")
                d.button("Stone")
                t1 = time.perf_counter()
                d.studio._reload()
                row["studio_room_reload_ms"] = round((time.perf_counter() - t1) * 1000, 1)
                cx, cy = size[0] / 2, size[1] / 2
                _look_at(d, cx, cy, 16.0)
                m20b.RELEASES.clear()
                view.timings["sculpt_ms"].clear()
                frames = m20b._stroke(d, _on_ground(d, [(cx - 3, cy), (cx, cy + 0.8), (cx + 3, cy)]))
                row["studio_paint_frame_ms"] = m20b._stats(frames)
                row["studio_paint_upload_ms"] = m20b._stats(view.timings["sculpt_ms"])
                row["studio_commit_ms"] = round(view.timings["edit_ms"][-1], 1) if view.timings["edit_ms"] else None
                row["studio_release_to_next_frame_ms"] = round(m20b.RELEASES[-1], 1) if m20b.RELEASES else None
                idle = []
                for _ in range(20):
                    t1 = time.perf_counter()
                    d.frame()  # (timed: the frame as it was measured, read-back included)
                    idle.append((time.perf_counter() - t1) * 1000)
                row["studio_idle_frame_ms"] = m20b._stats(idle)
                # the widest brush (16 m) held still for 3 s, then let go: what it costs live, and the release
                reloads: list[int] = []
                original_reload = s._reload

                def counted(*a: Any, **kw: Any) -> Any:
                    reloads.append(1)
                    return original_reload(*a, **kw)

                s._reload = counted
                view.set_sculpt(radius=16.0 * PX, material="mud")  # (the panel's "Mud" can be shadowed by an
                # object of that name further down, which the driver may click instead)
                point = _on_ground(d, [(cx, cy)])[0]
                held = []
                m20b.RELEASES.clear()

                def hold() -> None:
                    end = time.perf_counter() + 3.0
                    while time.perf_counter() < end:
                        t2 = time.perf_counter()
                        d.frame()  # (timed: the frame as it was measured, read-back included)
                        held.append((time.perf_counter() - t2) * 1000)

                m20b._stroke(d, [point, point], hold=None, each=lambda i: hold())
                row["studio_wide_brush_held_frame_ms"] = m20b._stats(held)
                row["studio_wide_brush_release_to_next_frame_ms"] = (round(m20b.RELEASES[-1], 1) if m20b.RELEASES
                                                                     else None)
                row["studio_mismatch_reloads"] = len(reloads)
                s._reload = original_reload
                t1 = time.perf_counter()
                d.key(k.Z, k.MOD_CTRL)
                row["studio_undo_ms"] = round((time.perf_counter() - t1) * 1000, 1)
                d.key(k.Y, k.MOD_CTRL)
                t1 = time.perf_counter()
                s.save()
                row["save_ms"] = round((time.perf_counter() - t1) * 1000, 1)
            finally:
                d.close()
            report[tag] = row
            print(tag, json.dumps(row), flush=True)
    return report


def identity(out: Path) -> dict[str, Any]:
    """Rooms without sculpted or painted ground, pictured for comparison with another tree (run there too): the
    template's village and cottage, and Milestone 19's water village dry and in rain (its pond and puddle)."""
    import m19_water_study as m19

    out.mkdir(parents=True, exist_ok=True)
    names = []
    game = HiddenGame(study.new_project(out, "template", stage6a=False), size=study.SIZE)
    try:
        for room in ("start", "cottage"):
            game.load(f"{SCENES}/{room}.json")
            game.step(60)
            hd = game.window.hd2d_renderer
            hd._camera_ready = False
            hd.update(0.0)
            from PIL import Image

            Image.frombytes("RGB", study.SIZE, hd.draw(read=True)).transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(
                out / f"{room}.png")
            names.append(room)
    finally:
        game.close()
    for rain in (False, True):
        game = HiddenGame(m19.make_project(out, f"water_{rain}", rain=rain), size=study.SIZE)
        try:
            game.load(f"{SCENES}/start.json")
            game.step(90)
            for name, (x, y, z) in sorted(m19.water_spots(game).items()):
                m19.shot(game, (x, y - 0.8, z + 0.8)).save(out / f"water_{name}_{'rain' if rain else 'dry'}.png")
                names.append(f"water_{name}_{'rain' if rain else 'dry'}")
        finally:
            game.close()
    return {"pictures": names}


EDGE_VIEWS = {"path": (10.5, 5.2), "pond": (23.5, 6.0), "cliff": (27.0, 15.8), "hill": (4.5, 17.0)}


def edges(out: Path) -> dict[str, Any]:
    """The same places with soft and hard edges, painted and not (the cliff tops' bare earth is soft edges' only):
    gameplay camera, the middle of the picture, side by side. 20B's fringe is rendered from its own tree
    (``base`` below: a ``git archive`` of the accepted 20B commit, run with ``edges-base``)."""
    out.mkdir(parents=True, exist_ok=True)
    shots: dict[str, dict[str, Any]] = {}
    for painted in (True, False):
        for edge in ("soft", "hard"):
            tag = f"{edge}_{'painted' if painted else 'unpainted'}"
            game = open_room(out, f"edges_{tag}", painted=painted, edges=edge)
            try:
                for name, (x, y) in EDGE_VIEWS.items():
                    image = m20a.shot(game, x, y)
                    image.save(out / f"{name}_{tag}.png")
                    shots.setdefault(name, {})[tag] = image
            finally:
                game.close()
    for name, by in shots.items():
        m20a.pair([by["hard_painted"], by["soft_painted"]], ["hard edges", "soft edges"], out / f"{name}_edges.png")
        m20a.pair([by["hard_unpainted"], by["soft_unpainted"]], ["hard (as 20A)", "soft (cliff-top earth)"],
                  out / f"{name}_fringe.png")
    return {"views": list(EDGE_VIEWS)}


def edges_base(out: Path) -> dict[str, Any]:
    """The edge views of the unpainted room as this tree draws it (run from the 20B tree: its speckled fringe)."""
    out.mkdir(parents=True, exist_ok=True)
    game = HiddenGame(m20a.make_project(out, "edges_base"), size=study.SIZE)
    game.load(f"{SCENES}/hills.json")
    game.step(30)
    try:
        for name, (x, y) in EDGE_VIEWS.items():
            m20a.shot(game, x, y).save(out / f"{name}_20b.png")
    finally:
        game.close()
    return {"views": list(EDGE_VIEWS)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands: dict[str, Any] = {"look": look, "edges": edges, "edges-base": edges_base, "studio": studio,
                                "flat": first_paint_on_flat, "scale": scale, "identity": identity}
    parser.add_argument("what", choices=list(commands))
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    result = commands[args.what](args.out)
    if result is not None:
        (args.out / f"{args.what}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
