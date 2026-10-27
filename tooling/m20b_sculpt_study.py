"""Milestone 20B evidence: live terrain sculpting in Mesh Studio (hidden windows, Studio's own window events only).

    py -3.13 tooling/m20b_sculpt_study.py studio OUT    # strokes, cursor, undo/redo/save/reopen, cancels, failures
    py -3.13 tooling/m20b_sculpt_study.py world OUT     # water, shadows, rain, collision following a live edit
    py -3.13 tooling/m20b_sculpt_study.py scale OUT     # 32 x 24, 64 x 64, 128 x 128 m: load, strokes, frames, save
    py -3.13 tooling/m20b_sculpt_study.py flat OUT      # a flat room's first stroke, and its undo
    py -3.13 tooling/m20b_sculpt_study.py rechecks OUT  # QA's findings, checked again in Studio

Projects come from the HD-2D RPG template with the Hills room (tooling/m20a_terrain_study.py), or, for scale, a room
whose ground is sculpted all over.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
import hd2d_visual_study as study  # noqa: E402
import m20a_terrain_study as m20a  # noqa: E402
from hd2d_demo import SCENES, HiddenGame, _gl_counts  # noqa: E402

PX = 32.0
RELEASES: list[float] = []  # each stroke's release: its commit, Studio's panel and the next frame (ms)


def _heights(project: Any) -> list[float]:
    from engine import project_ops as ops
    from engine.hd2d.terrain import Terrain

    return Terrain.from_ground(ops._parsed_ground(project.scene())).heights


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values)
    return {"median": round(statistics.median(ordered), 2), "p95": round(ordered[int(0.95 * (len(ordered) - 1))], 2),
            "max": round(ordered[-1], 2), "n": len(ordered)}


def _driver(project: Path) -> Any:
    import hd2d_studio_demo

    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    d = hd2d_studio_demo.StudioDriver(project)
    d.button("Hills")
    d.frame(3)
    return d


def _stroke(d: Any, points: list[tuple[float, float, float]], *, hold: Callable[[], None] | None = None,
            each: Callable[[int], None] | None = None, release: bool = True) -> list[float]:
    """A stroke with Studio's own mouse events: press at the first point, drag through the rest (a frame each),
    release at the last. Returns each drag frame's time (ms: the event, the edit in place and drawing it)."""
    arcade = d.arcade
    left = arcade.MOUSE_BUTTON_LEFT
    screen = [d.screen(p) for p in points]
    d.window.dispatch_event("on_mouse_motion", *screen[0], 0, 0)
    if hold is not None:
        hold()
    d.window.dispatch_event("on_mouse_press", *screen[0], left, 0)
    times = []
    last = screen[0]
    for i, s in enumerate(screen[1:]):
        start = time.perf_counter()
        d.window.dispatch_event("on_mouse_drag", s[0], s[1], s[0] - last[0], s[1] - last[1], left, 0)
        d.frame()
        times.append((time.perf_counter() - start) * 1000)
        last = s
        if each is not None:
            each(i)
    if release:
        start = time.perf_counter()
        d.window.dispatch_event("on_mouse_release", *screen[-1], left, 0)
        d.frame()
        RELEASES.append((time.perf_counter() - start) * 1000)
    return times


def _path(a: tuple[float, float], b: tuple[float, float], n: int) -> list[tuple[float, float, float]]:
    return [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n, 0.0) for k in range(n + 1)]


def studio(out: Path) -> dict[str, Any]:
    """A creator's strokes in Mesh Studio: a continuous stroke across the hill (its frames timed), live cursor and
    ground, one undo step, redo, save and reopen exactly; Esc, Play and a room change mid-stroke cancel safely; a
    refused GPU upload stops a stroke and puts the ground back; Shift, Alt+click, [ and ] work."""
    import m18_particles_study as m18

    from engine.hd2d.terrain import Terrain

    out.mkdir(parents=True, exist_ok=True)
    project = m20a.make_project(out, "studio", stages=("hill",), pond=False)
    report: dict[str, Any] = {}
    d = _driver(project)
    try:
        s, view, k = d.studio, d.studio.hd2d, d.arcade.key
        d.button("Sculpt ground")
        before = list(_heights(s.project))
        undo_before = len(s.project._undo)
        # 1. a continuous stroke over the hill and down its far side
        clip: list[Any] = []

        def film(i: int) -> None:
            if i % 2 == 0 and len(clip) < 60:
                clip.append(m18.crop_at(d.frame().convert("RGB"), 590, 360, (640, 360)))
                if i == 20:
                    clip[-1].save(out / "stroke_mid.png")

        frames = _stroke(d, _path((6.5, 14.0), (12.0, 20.5), 48), each=film)
        live = list(view.renderer.terrain.heights)
        saved = list(_heights(s.project))
        report["stroke"] = {"frame_ms": _stats(frames), "update_terrain_ms": _stats(view.timings["sculpt_ms"]),
                            "commit_ms": round(view.timings["edit_ms"][-1], 1) if view.timings["edit_ms"] else None,
                            "release_to_next_frame_ms": round(RELEASES[-1], 1) if RELEASES else None,
                            "undo_steps_added": len(s.project._undo) - undo_before,
                            "shown_equals_saved": live == saved,
                            "raised_max_m": round(max(b - a for a, b in zip(before, saved)) / PX, 3),
                            "message": s.message}
        if clip:
            clip[0].save(out / "stroke.webp", save_all=True, append_images=clip[1:], duration=100, loop=0, quality=80,
                         method=6)
        d.picture(out / "stroke_after.png")
        # 2. undo and redo the whole stroke; save; reopen
        d.key(k.Z, k.MOD_CTRL)
        report["undo_gives_before"] = _heights(s.project) == before and view.renderer.terrain.heights == before
        d.key(k.Y, k.MOD_CTRL)
        report["redo_gives_after"] = _heights(s.project) == saved and view.renderer.terrain.heights == saved
        d.key(k.S, k.MOD_CTRL)
        report["saved_dirty_after"] = s.project.is_dirty
        # 3. Esc mid-stroke: the ground as it was, nothing recorded
        undo_n = len(s.project._undo)
        _stroke(d, _path((20.0, 6.0), (24.0, 8.0), 12), release=False)
        moved = view.renderer.terrain.heights != saved
        d.key(k.ESCAPE)
        d.window.dispatch_event("on_mouse_release", *d.screen((24.0, 8.0, 0.0)), d.arcade.MOUSE_BUTTON_LEFT, 0)
        d.frame()
        report["escape"] = {"stroke_had_changed_the_ground": moved, "ground_back": view.renderer.terrain.heights == saved,
                            "nothing_recorded": len(s.project._undo) == undo_n and _heights(s.project) == saved,
                            "message": s.message}
        # 4. Play (F4) mid-stroke, then Stop: nothing recorded, the saved ground back
        _stroke(d, _path((20.0, 6.0), (24.0, 8.0), 8), release=False)
        d.key(k.F4)
        played = s.mode
        d.window.dispatch_event("on_mouse_release", 600, 300, d.arcade.MOUSE_BUTTON_LEFT, 0)
        d.key(k.F4)
        d.frame(3)
        report["play_mid_stroke"] = {"mode": played, "after_stop": s.mode, "nothing_recorded": len(s.project._undo) == undo_n,
                                     "ground_is_saved": view.renderer.terrain.heights == saved}
        # 5. a room change mid-stroke
        _stroke(d, _path((20.0, 6.0), (24.0, 8.0), 8), release=False)
        d.button("Village")
        d.window.dispatch_event("on_mouse_release", 600, 300, d.arcade.MOUSE_BUTTON_LEFT, 0)
        d.frame(2)
        d.button("Hills")
        d.frame(2)
        if view.sculpt is None:
            d.button("Sculpt ground")
        report["room_change_mid_stroke"] = {"nothing_recorded": len(s.project._undo) == undo_n,
                                            "ground_is_saved": view.renderer.terrain.heights == saved}
        # 6. a refused GPU upload mid-stroke
        renderer = view.renderer
        original = renderer.ctx.buffer
        calls = {"n": 0}

        def refusing(*a: Any, **kw: Any) -> Any:
            calls["n"] += 1
            if calls["n"] > 2:
                raise RuntimeError("out of memory (simulated)")
            return original(*a, **kw)

        _stroke(d, _path((20.0, 6.0), (21.0, 6.5), 2), release=False)
        renderer.ctx.buffer = refusing  # (the same stroke goes on: the driver starts refusing buffers)
        try:
            last = d.screen((21.0, 6.5, 0.0))
            for p in _path((21.0, 6.5), (24.0, 8.0), 10)[1:]:
                s_ = d.screen(p)
                d.window.dispatch_event("on_mouse_drag", s_[0], s_[1], s_[0] - last[0], s_[1] - last[1],
                                        d.arcade.MOUSE_BUTTON_LEFT, 0)
                d.frame()
                last = s_
        finally:
            renderer.ctx.buffer = original
        d.frame(2)  # (the drawing catches up once the GPU takes buffers again)
        d.window.dispatch_event("on_mouse_release", 600, 300, d.arcade.MOUSE_BUTTON_LEFT, 0)
        d.frame(2)
        report["refused_upload"] = {"ground_back": view.renderer.terrain.heights == saved,
                                    "nothing_recorded": len(s.project._undo) == undo_n, "message": s.message}
        # 7. Shift lowers; [ ] resize; Alt+click picks a flatten height, then a flatten stroke
        d.window.dispatch_event("on_key_press", k.LSHIFT, 0)
        _stroke(d, _path((14.0, 10.0), (17.0, 10.0), 6))
        d.window.dispatch_event("on_key_release", k.LSHIFT, 0)
        lowered = min(_heights(s.project)) < 0
        r0 = view.sculpt["radius"]
        d.key(k.BRACKETRIGHT)
        r1 = view.sculpt["radius"]
        d.key(k.BRACKETLEFT)
        d.window.dispatch_event("on_key_press", k.LALT, 0)
        d.click(*d.screen((4.5, 19.5, 0.0)))
        d.window.dispatch_event("on_key_release", k.LALT, 0)
        picked = view.sculpt.get("target")
        _stroke(d, _path((8.0, 12.0), (12.0, 12.0), 10))
        flat = Terrain.from_ground(__import__("engine.project_ops", fromlist=["x"])._parsed_ground(s.project.scene()))
        report["controls"] = {"shift_lowered": lowered, "radius_px": [r0, r1, view.sculpt["radius"]],
                              "picked_target_m": round(picked / PX, 3) if picked is not None else None,
                              "flattened_towards_m": round((flat.height(10.0 * PX, 12.0 * PX) or 0.0) / PX, 3),
                              "tool": view.sculpt["tool"]}
        d.picture(out / "studio_controls.png")
        final = list(_heights(s.project))
        d.key(k.S, k.MOD_CTRL)
    finally:
        d.close()
    d = _driver(project)
    try:
        report["reopened_same"] = _heights(d.studio.project) == final
    finally:
        d.close()
    return report


def first_stroke_on_flat(out: Path) -> dict[str, Any]:
    """A room with plain flat ground (the template's village): the first stroke makes it sculpted ground in place;
    its people and structures stay where they are; undo makes it the plain ground again."""
    from engine import project_ops as ops

    project = m20a.make_project(out, "flat", stages=(), pond=False)
    d = _driver(project)
    report: dict[str, Any] = {}
    try:
        s, view, k = d.studio, d.studio.hd2d, d.arcade.key
        d.button("Village")
        d.frame(3)
        terrain_key = lambda: ((s.project.scene().get("settings") or {}).get("hd2d") or {}).get("ground", {}).get("terrain")  # noqa: E731
        report["before"] = {"sculpted": terrain_key() is not None}
        d.button("Sculpt ground")
        frames = _stroke(d, _path((14.0, 13.0), (18.0, 13.0), 16))
        report["after"] = {"sculpted": terrain_key() is not None, "frame_ms": _stats(frames),
                           "walk_world": getattr(d.window, "hd2d_world", None) is not None,
                           "out_of_place": ops.terrain_anchoring(s.project.scene())}
        d.key(k.Z, k.MOD_CTRL)
        report["undo_back_to_plain_ground"] = terrain_key() is None and view.renderer.terrain is None
    finally:
        d.close()
    return report


def rechecks(out: Path) -> dict[str, Any]:
    """QA's findings, checked again in Studio: strength by time (not frame rate), modifiers let go when the window
    loses focus, Ctrl+Z and other buttons mid-stroke, Esc of a tall stroke shrinks the room's box back, the Settle
    list stays in its room, a flat room's cancelled or no-op stroke leaves the plain ground."""
    project = m20a.make_project(out, "rechecks", stages=("hill",), pond=False)
    d = _driver(project)
    report: dict[str, Any] = {}
    try:
        s, view, k = d.studio, d.studio.hd2d, d.arcade.key
        left, right = d.arcade.MOUSE_BUTTON_LEFT, d.arcade.MOUSE_BUTTON_RIGHT
        d.button("Sculpt ground")
        d.type_into("sculpt_rate", "1")
        # strength by time: a 1 m/s brush held still for about a second
        p = d.screen((20.0, 6.0, 0.0))
        before = list(view.renderer.terrain.heights)
        d.window.dispatch_event("on_mouse_motion", *p, 0, 0)
        d.window.dispatch_event("on_mouse_press", *p, left, 0)
        while time.perf_counter() - view.stroke["started"] < 1.0:
            d.frame()
        held = time.perf_counter() - view.stroke["started"]
        d.window.dispatch_event("on_mouse_release", *p, left, 0)
        d.frame()
        moved = max(a - b for a, b in zip(view.renderer.terrain.heights, before)) / PX
        report["held_still"] = {"held_s": round(held, 2), "raised_m": round(moved, 3)}
        # modifiers let go when the window loses the keyboard (Alt+Tab)
        d.window.dispatch_event("on_key_press", k.LALT, k.MOD_ALT)
        d.window.dispatch_event("on_deactivate")
        report["keys_after_focus_lost"] = sorted(s.keys)
        # Ctrl+Z and a right click mid-stroke
        undo = len(s.project._undo)
        _stroke(d, _path((12.0, 12.0), (14.0, 12.0), 4), release=False)
        d.window.dispatch_event("on_mouse_release", *d.screen((14.0, 12.0, 0.0)), right, 0)
        report["right_release_keeps_the_stroke"] = view.stroke is not None
        d.key(k.Z, k.MOD_CTRL)
        report["ctrl_z_mid_stroke"] = {"stroke": view.stroke is not None, "undo_steps": len(s.project._undo) - undo,
                                       "shown_is_saved": view.renderer.terrain.heights == _heights(s.project)}
        # Esc of a tall stroke: the room's box (the sun's shadow map) back as a fresh load has it
        box = view.renderer.world_box()
        d.type_into("sculpt_rate", "8")
        _stroke(d, [(16.0, 12.0, 0.0)] * 90, release=False)  # (taller than the bridge: about 5 m)
        grown = view.renderer.world_box()
        d.key(k.ESCAPE)
        d.frame()
        report["box_top_m"] = {"before": box[1][2], "mid_stroke": grown[1][2], "after_esc": view.renderer.world_box()[1][2]}
        # the Settle list belongs to its room
        view.unsettled, view._unsettled_room = ["structure:bridge"], s.project.current
        d.button("Village")
        d.frame(3)
        report["settle_list_in_another_room"] = list(view.unsettled)
        # a flat room: Esc of the first stroke, and a stroke that changes nothing (smooth on level ground)
        d.type_into("sculpt_rate", "1")
        _stroke(d, _path((14.0, 13.0), (16.0, 13.0), 6), release=False)
        d.key(k.ESCAPE)
        d.frame()
        plain_after_esc = view.renderer.terrain is None
        undo = len(s.project._undo)
        d.button("Smooth")
        _stroke(d, _path((14.0, 13.0), (16.0, 13.0), 6))
        report["flat_room"] = {"plain_after_esc": plain_after_esc, "plain_after_noop": view.renderer.terrain is None,
                               "noop_undo_steps": len(s.project._undo) - undo}
    finally:
        d.close()
    return report


# --- the world follows a live edit (the game, the same in-place path Studio uses) -------------------------------

def _live(game: HiddenGame, tool: str, x: float, y: float, radius: float, strength: float, n: int = 1,
          target: float | None = None) -> set[tuple[int, int]]:
    hd, world = game.window.hd2d_renderer, game.window.hd2d_world
    dirty: set[tuple[int, int]] = set()
    for _ in range(n):
        dirty |= hd.terrain.sculpt(tool, x * PX, y * PX, radius * PX, strength, target)
    hd.update_terrain(hd.terrain, dirty)
    world.update_terrain(hd.terrain)
    return dirty


def world(out: Path) -> dict[str, Any]:
    """After in-place edits (no reload): the pond's shore follows the ground, the sun's shadows follow a new mound
    (and the room's box grows when it rises above it), rain lands on the new surface, the player walks onto it and
    an NPC route changes; chunks meet without cracks."""
    import numpy as np

    report: dict[str, Any] = {}
    project = m20a.make_project(out, "world", rain=True)
    path = project / SCENES / "hills.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    scene["settings"]["hd2d"]["sun"]["direction"] = [0.9, 0.15, 0.32]  # a low sun from the east: long shadows
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    game = HiddenGame(project, size=study.SIZE)
    try:
        game.load(f"{SCENES}/hills.json")
        game.step(30)
        hd, world_ = game.window.hd2d_renderer, game.window.hd2d_world
        game.window.water_time = hd.particles.time = 3.0
        # water: raise the basin's west side: the shore moves
        x, y = m20a.BASIN[0], m20a.BASIN[1] + 0.5
        before = m20a.shot(game, x, y)
        bodies = game.window.water_bodies
        game.window.water_bodies = []
        dry = m20a.shot(game, x, y)
        game.window.water_bodies = bodies
        water_before = int(m20a._mask(before, dry).sum())
        _live(game, "raise", m20a.BASIN[0] - 1.6, m20a.BASIN[1], 1.6, 10.0, n=3)
        after = m20a.shot(game, x, y)
        game.window.water_bodies = []
        dry2 = m20a.shot(game, x, y)
        game.window.water_bodies = bodies
        report["water"] = {"pixels_before": water_before, "pixels_after": int(m20a._mask(after, dry2).sum())}
        m20a.pair([before, after], ["the pond", "its basin's west side raised live: the shore follows"],
                  out / "live_water.png")
        # shadows: a new 2 m mound on open ground east of the cottage casts a shadow at once (no reload)
        mx, my = 12.0, 4.0
        lo0, hi0 = hd.world_box()
        pre = m20a.shot(game, mx - 2.5, my)
        _live(game, "raise", mx, my, 2.0, 16.0, n=4)
        post = m20a.shot(game, mx - 2.5, my)
        hd_lo, hd_hi = hd.world_box()
        darker = (np.asarray(post, dtype=np.int16).sum(axis=2) + 30 < np.asarray(pre, dtype=np.int16).sum(axis=2))
        report["shadow"] = {"pixels_darkened_west_of_the_mound": int(darker.sum()),
                            "mound_top_m": round(hd.terrain.height(mx * PX, my * PX) / PX, 3)}
        m20a.pair([pre, post], ["before", "a 2 m mound raised live: its shadow at once"], out / "live_shadow.png")
        # a tall spike above the room's box: the box (and the sun's shadow box) grows
        _live(game, "raise", 30.0, 3.0, 1.0, 256.0, n=6)
        report["room_box_top_m"] = {"before": round(hi0[2], 2), "after": round(hd.world_box()[1][2], 2),
                                    "spike_m": round(hd.terrain.range_z()[1], 2)}
        # rain lands on the new mound (the precipitation map, made again)
        maps = hd.precipitation_maps()
        m = next(mm for mm in maps if mm is not None)
        import ctypes

        from pyglet import gl as raw

        w_, h_ = m.depth.width, m.depth.height
        buf = (ctypes.c_float * (w_ * h_))()
        previous = game.window.ctx.active_framebuffer
        raw.glBindFramebuffer(raw.GL_READ_FRAMEBUFFER, m.fbo.glo)
        raw.glReadPixels(0, 0, w_, h_, raw.GL_DEPTH_COMPONENT, raw.GL_FLOAT, buf)
        previous.use(force=True)
        depth = np.frombuffer(buf, dtype=np.float32).reshape(h_, w_)
        vp = [[m.vp[c * 4 + r] for c in range(4)] for r in range(4)]

        def clip(p: tuple[float, float, float]) -> tuple[float, float, float]:
            c = [sum(vp[r][k] * (*p, 1.0)[k] for k in range(4)) for r in range(4)]
            return c[0] / c[3], c[1] / c[3], c[2] / c[3]

        u, v, d0 = clip((mx, my, 0.0))
        d1 = clip((mx, my, 1.0))[2]
        stored = float(depth[int((v * 0.5 + 0.5) * h_), int((u * 0.5 + 0.5) * w_)])
        report["rain_stops_on_the_mound_m"] = round((stored - (d0 * 0.5 + 0.5)) / ((d1 - d0) * 0.5), 3)
        # collision: the player walks up onto the mound; a route is planned over the new ground
        from hd2d_floors_demo import _feet, hold_key

        from engine.hd2d.world import elevation_of

        gx, gy = 20.5, 4.5  # (a gentle 1 m mound, 3 m across the radius: walkable, unlike the steep one above)
        _live(game, "raise", gx, gy, 3.0, 8.0, n=4)
        player = m20a._put(game, gx, gy - 3.8)
        hold_key(game, player, game.arcade.key.UP, 1, gy, 300)
        report["walked_onto_the_mound"] = {"feet_m": [round(v, 2) for v in _feet(player)],
                                           "elevation_m": round(elevation_of(player), 3),
                                           "ground_m": round(hd.terrain.height(_feet(player)[0] * PX, _feet(player)[1] * PX) / PX, 3)}
        route = world_.path((gx, 0.8, 0.0), (gx, 8.0, 0.0))  # (south of the mound to north of it)
        report["route_over_or_round_the_mound"] = {"points": len(route), "highest_m": round(max(p[2] for p in route), 3)
                                                   if route else None}
        # cracks: every chunk edge drawn from the same corners (shared vertices equal across neighbouring chunks)
        t = hd.terrain
        cx_n, cy_n = t.chunk_count()
        gaps = 0
        for cj in range(cy_n):
            for ci in range(cx_n - 1):
                a, b = t.chunk_mesh(ci, cj), t.chunk_mesh(ci + 1, cj)
                xa = {(round(arr[k], 4), round(arr[k + 1], 4)): round(arr[k + 2], 5) for arr in a
                      for k in range(0, len(arr), 8) if arr[k + 5] != 0.0}  # (not the border skirt's)
                for arr in b:
                    for k2 in range(0, len(arr), 8):
                        key = (round(arr[k2], 4), round(arr[k2 + 1], 4))
                        if key in xa and abs(xa[key] - round(arr[k2 + 2], 5)) > 1e-4 and arr[k2 + 5] != 0.0:
                            gaps += 1
        report["chunk_edges_not_meeting"] = gaps
        game.window.ctx.gc()
        report["gl_objects"] = _gl_counts(game.window.ctx)
    finally:
        game.close()
    return report


# --- scale ------------------------------------------------------------------------------------------------------------

def scale_project(out: Path, name: str, size_m: tuple[float, float]) -> Path:
    """A template project whose Hills room has a ``size_m`` ground sculpted all over (rolling hills, a few cliffs)."""
    from engine.hd2d.terrain import Terrain

    project: Path = study.new_project(out, name, stage6a=False)
    scene = m20a.base_scene(project)
    w, h = size_m[0] * PX, size_m[1] * PX
    hd2d = scene["settings"]["hd2d"]
    hd2d["ground"]["to"] = [w, h]
    hd2d["camera"]["bounds"] = [0.0, 0.0, w, h]
    scene["settings"]["world_width"], scene["settings"]["world_height"] = w, h
    terrain = Terrain((0.0, 0.0), (w, h), 0.0, 16)
    rng = random.Random(7)
    for _ in range(int(size_m[0] * size_m[1] / 40)):
        terrain.sculpt(rng.choice(["raise", "raise", "lower"]), rng.uniform(0, w), rng.uniform(0, h),
                       rng.uniform(48, 160), rng.uniform(4, 24))
    for _ in range(int(size_m[0] * size_m[1] / 400) + 1):  # a few terraces with cliffs
        tx, ty, z = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(24, 64)
        for dx in range(-64, 65, 16):
            for dy in range(-64, 65, 16):
                terrain.sculpt("flatten", tx + dx, ty + dy, 18, 1.0, target=z)
    hd2d["ground"]["terrain"] = terrain.settings()
    (project / SCENES / "hills.json").write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    world_path = project / "packs" / "core_regions" / "worlds" / "main.json"
    w_doc = json.loads(world_path.read_text(encoding="utf-8"))
    w_doc["scenes"]["hills"] = {"label": "Hills", "path": f"{SCENES}/hills.json", "tags": []}
    world_path.write_text(json.dumps(w_doc, indent=2) + "\n", encoding="utf-8")
    return project


def scale(out: Path) -> dict[str, Any]:
    """Per ground size: room load (game and Studio), a 2 m stroke's frames in Studio (live) and its commit, the
    save, frame times while sculpting and while not, draw calls, the NPC navigation grid, memory."""
    import m19_water_study as m19

    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    for size in ((32.0, 24.0), (64.0, 64.0), (128.0, 128.0)):
        name = f"{int(size[0])}x{int(size[1])}"
        project = scale_project(out, f"scale_{name}", size)
        row: dict[str, Any] = {"stored_chars": len((project / SCENES / "hills.json").read_text(encoding="utf-8"))}
        game = HiddenGame(project, size=study.SIZE)
        try:
            t0 = time.perf_counter()
            game.load(f"{SCENES}/hills.json")
            row["game_room_load_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            game.step(10)
            hd, world_ = game.window.hd2d_renderer, game.window.hd2d_world
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
            row["frame_ms_playing"] = _stats(cpu)
            row["frame_gpu_ms"] = round(m19._frame_gpu_ms(game, 30), 3)
            stats = hd.stats()
            row["draw_calls"] = stats["draw_calls"]
            row["shadow_draws"] = stats["shadow_draws"]
            row["terrain_gpu_bytes"] = stats["terrain_bytes"]
            row["chunks"] = len(hd._terrain_draws)
            t1 = time.perf_counter()
            world_._nav = None
            world_.walkable()
            row["nav_grid_ms"] = round((time.perf_counter() - t1) * 1000, 1)
            # a live stroke in the game's renderer (what Studio does each frame): 30 dabs of a 2 m brush
            cx, cy = size[0] / 2, size[1] / 2
            per = []
            for i in range(30):
                t1 = time.perf_counter()
                _live(game, "raise", cx + i * 0.2, cy, 2.0, 1.0)
                per.append((time.perf_counter() - t1) * 1000)
            row["live_dab_rebuild_ms"] = _stats(per)
        finally:
            game.close()
        d = _driver(project)
        try:
            s, view = d.studio, d.studio.hd2d
            d.button("Sculpt ground")
            t1 = time.perf_counter()
            d.studio._reload()
            row["studio_room_reload_ms"] = round((time.perf_counter() - t1) * 1000, 1)
            frames = _stroke(d, _path((size[0] / 2 - 3, size[1] / 2), (size[0] / 2 + 3, size[1] / 2 + 1), 30))
            row["studio_stroke_frame_ms"] = _stats(frames)
            row["studio_commit_ms"] = round(view.timings["edit_ms"][-1], 1) if view.timings["edit_ms"] else None
            row["studio_release_to_next_frame_ms"] = round(RELEASES[-1], 1) if RELEASES else None
            idle = []
            for _ in range(20):
                t1 = time.perf_counter()
                d.frame()
                idle.append((time.perf_counter() - t1) * 1000)
            row["studio_idle_frame_ms"] = _stats(idle)
            t1 = time.perf_counter()
            s.save()
            row["save_ms"] = round((time.perf_counter() - t1) * 1000, 1)
        finally:
            d.close()
        report[name] = row
        print(name, json.dumps(row), flush=True)
    (out / "scale.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    steps: dict[str, Callable[[Path], Any]] = {"studio": studio, "flat": first_stroke_on_flat, "world": world,
                                               "scale": scale, "rechecks": rechecks}
    parser.add_argument("command", choices=list(steps))
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    print(json.dumps(steps[args.command](args.out), indent=1))


if __name__ == "__main__":
    main()
