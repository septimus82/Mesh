"""M17-W1: what the waterfall tests and evidence measure in real frames (hidden windows; the glen of
tooling/w1_waterfall_study.py).

``frames(out)``: the game's renderer, its clocks set (frames at the same time are the same frame): where the curtain
is drawn (against the same river without its waterfall), the streaks moving down it, the cliff hiding it from behind
(the depth test on against off), a character in front of it hiding it, the foam at its foot and none far from it, the
spray made only when asked for and drawn near the foot, nothing drawn or made when it's out of the picture or gone,
no GPU allocation a frame, the draw calls it adds; and with the room's haze and bloom, no emission on the water.
``studio(out)``: Mesh Studio's River tool making, tuning, refusing, undoing and removing a waterfall; its view against
the game's path; save, reopen, Play and Stop; ``export_check``: the exported game drawing it.
"""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
import w1_waterfall_study as glen  # noqa: E402
from hd2d_demo import SCENES, HiddenGame  # noqa: E402

PX = 32.0
FRONT = ((20.0, 23.9, 1.4), 48.0, 25.0, 0.0)  # target (m), distance, pitch, yaw: looking at the fall
BEHIND = ((20.0, 23.9, 1.4), 54.0, 30.0, 180.0)  # from the plateau, over its lip
AWAY = ((38.0, 2.0, 0.0), 20.0, 30.0, 0.0)  # the room's south-east corner (the camera outside it): no water seen
WIDE = ((20.0, 16.0, 1.0), 110.0, 30.0, 0.0)  # the lamps south of the pond and the fall beyond it
LIP = (20.0, glen.Y(612.0) / PX)  # m
FOOT = (20.0, glen.Y(676.0) / PX)


def _np() -> Any:
    import numpy as np  # noqa: PLC0415

    return np


def camera(spec: tuple[Any, ...]) -> Any:
    from engine.hd2d.renderer import Camera  # noqa: PLC0415

    target, distance, pitch, yaw = spec
    cam = Camera(pitch, 12.0, distance, False, yaw)
    cam.target = target
    return cam


class Frames:
    """The glen in a hidden game window: frames at a set time, with the room's rivers as given."""

    def __init__(self, project: Path) -> None:
        self.game = HiddenGame(project)
        self.game.load(f"{SCENES}/start.json")
        self.game.step(60)
        self.hd = self.game.window.hd2d_renderer
        self.size = self.game.window.get_framebuffer_size()
        self.rivers = self.hd.settings.rivers

    def shot(self, spec: tuple[Any, ...], t: float, rivers: Any = None) -> Any:
        """The picture (rows top-down, RGB) from ``spec`` at time ``t`` (the water's and the motion's clocks)."""
        np = _np()
        hd, win = self.hd, self.game.window
        hd.settings = dataclasses.replace(hd.settings, rivers=self.rivers if rivers is None else rivers)
        win.water_time = win.motion_time = t
        w, h = self.size
        win.use()
        data = hd.draw(camera=camera(spec), viewport=(0, 0, w, h), read_final=True)
        win.ctx.gc()
        return np.frombuffer(bytes(data), dtype=np.uint8).reshape(h, w, 3)[::-1].copy()

    def screen(self, p: tuple[float, float, float]) -> tuple[float, float]:
        """Where a world point (m) was in the last picture (px, top-down)."""
        vp = self.hd.last_vp
        c = [sum(vp[r][k] * (p[k] if k < 3 else 1.0) for k in range(4)) for r in range(4)]
        w, h = self.size
        return (c[0] / c[3] * 0.5 + 0.5) * w, (1.0 - (c[1] / c[3] * 0.5 + 0.5)) * h

    def without_falls(self, **fall: Any) -> tuple[Any, ...]:
        """The room's rivers with their waterfalls removed, or (``fall``) changed."""
        return tuple(dataclasses.replace(r, falls=tuple(dataclasses.replace(f, **fall) for f in r.falls) if fall else ())
                     for r in self.rivers)

    def close(self) -> None:
        self.game.close()


def _changed(a: Any, b: Any) -> Any:
    np = _np()
    return np.abs(a.astype(int) - b.astype(int)).max(axis=2) > 0


def _lighter(img: Any, base: Any) -> Any:
    """Pixels made at least 40 levels lighter than ``base`` (whitewater over the same water)."""
    return img.astype(int).mean(axis=2) - base.astype(int).mean(axis=2) > 40


def _gl_made(ctx: Any) -> dict[str, int]:
    return {k: getattr(ctx.stats, k)[0] for k in ("buffer", "texture", "framebuffer", "program")}


def frames(out: Path) -> dict[str, Any]:
    np = _np()
    out.mkdir(parents=True, exist_ok=True)
    project = glen.make_project(out, "glen")
    f = Frames(project)
    report: dict[str, Any] = {}
    try:
        hd = f.hd
        report["errors"] = {"hd2d": getattr(f.game.window, "hd2d_error", None), "water": hd.water_error,
                            "rivers": hd.settings.rivers_error}
        report["falls"] = [[dataclasses.asdict(x) for x in r.falls] for r in f.rivers]
        # where the curtain is: the same river with its stretch an ordinary slope, against it falling
        t0 = 3.0
        falling = f.shot(FRONT, t0)
        lip_px, foot_px = f.screen((*LIP, glen.UPPER_PX / PX)), f.screen((*FOOT, 0.0))
        plain = f.shot(FRONT, t0, f.without_falls())
        mask = _changed(falling, plain)
        x0, x1 = int(min(lip_px[0], foot_px[0]) - 40), int(max(lip_px[0], foot_px[0]) + 40)
        band = mask[int(lip_px[1]):int(foot_px[1]), x0:x1]
        report["curtain"] = {"lip_px": lip_px, "foot_px": foot_px, "changed": int(mask.sum()),
                             "between_lip_and_foot": round(float(band.mean()), 3) if band.size else 0.0}
        from PIL import Image  # noqa: PLC0415

        Image.fromarray(falling).save(out / "front.png")
        Image.fromarray(plain).save(out / "front_plain.png")
        # the streaks move down: each frame against the one 1/30 s before, the shift (rows) that matches best
        top, bottom = int(lip_px[1]) + 6, int(foot_px[1]) - 6
        half = int(abs(f.screen((LIP[0] + 1.3, LIP[1], glen.UPPER_PX / PX))[0] - lip_px[0]))
        cols = slice(int(lip_px[0]) - half, int(lip_px[0]) + half)
        shifts = []
        for k in range(6):
            t = 1.0 + 0.37 * k
            a = f.shot(FRONT, t)[top:bottom, cols].astype(float).mean(axis=2)
            b = f.shot(FRONT, t + 1 / 30)[top:bottom, cols].astype(float).mean(axis=2)
            errs = {s: float(np.mean((a[max(0, -s):len(a) - max(0, s)] - b[max(0, s):len(b) - max(0, -s)]) ** 2))
                    for s in range(-12, 13)}
            shifts.append(min(errs, key=lambda s: errs[s]))
        report["motion"] = {"shifts_down_px": shifts, "rows": bottom - top, "still_same": bool(
            np.array_equal(f.shot(FRONT, 2.0), f.shot(FRONT, 2.0)))}
        # flowing into the pond eases only the water below the fall to the pond's: the stream above is as it was
        free = tuple(dataclasses.replace(r, mouth="none") for r in f.rivers)
        above = (slice(max(0, int(lip_px[1]) - 70), int(lip_px[1]) - 2), slice(x0, x1))
        report["above_the_lip"] = {"changed_by_the_join": int(_changed(f.shot(FRONT, t0)[above],
                                                                       f.shot(FRONT, t0, free)[above]).sum())}
        # ... also with its lip near the shore (within the 1.5 m the river eases to the pond's level over)
        (r,) = f.rivers
        pts = [list(p) for p in r.points]
        pts[2][1], pts[3][1] = glen.Y(656.0), glen.Y(684.0)  # (the lip 0.9 m from the shore, the foot 0.1 m)
        shore = (dataclasses.replace(r, points=tuple(tuple(p) for p in pts)),)
        shore_free = (dataclasses.replace(shore[0], mouth="none"),)
        f.shot(FRONT, t0, shore)
        nlip = f.screen((20.0, pts[2][1] / PX, pts[2][3] / PX))
        above = (slice(max(0, int(nlip[1]) - 70), int(nlip[1]) - 2), slice(x0, x1))
        report["above_the_lip"]["near_the_shore_changed"] = int(_changed(f.shot(FRONT, t0, shore)[above],
                                                                         f.shot(FRONT, t0, shore_free)[above]).sum())
        report["above_the_lip"]["near_joined"] = not f.hd.water.mouth_problems
        # from behind, the cliff top hides the curtain: what it changes with the depth test on, and off
        back = f.shot(BEHIND, t0)
        back_plain = f.shot(BEHIND, t0, f.without_falls())
        hd.water.depth_test = False
        try:
            back_seen = f.shot(BEHIND, t0)
            back_seen_plain = f.shot(BEHIND, t0, f.without_falls())
        finally:
            hd.water.depth_test = True
        report["behind"] = {"changed_depth_tested": int(_changed(back, back_plain).sum()),
                            "changed_no_depth_test": int(_changed(back_seen, back_seen_plain).sum())}
        Image.fromarray(back).save(out / "behind.png")
        # a character in front of the curtain hides it: its upper body's pixels the same with or without the fall
        player = f.game.player()
        home = (player.center_x, player.center_y, player.mesh_entity_data.get("elevation", 0.0))
        player.center_x, player.center_y = 640.0, glen.Y(700.0)  # (0.75 m nearer the camera than the foot)
        player.mesh_entity_data["elevation"] = 0.0
        dry = f.without_falls(spray=0.0)  # (the spray drifts in front of them: the curtain alone here)
        with_player = f.shot(FRONT, t0, dry)
        hidden = f.shot(FRONT, t0, f.without_falls())
        w, h = f.size
        f.game.window.use()
        solid = np.frombuffer(bytes(hd.draw(solid=player, camera=camera(FRONT), viewport=(0, 0, w, h), read=True)),
                              dtype=np.uint8).reshape(h, w, 3)[::-1]
        body = (solid[..., 0] > 200) & (solid[..., 1] < 50)  # (what of the character the world's depth lets show)
        rows = np.where(body.any(axis=1))[0]
        if rows.size:  # (above its feet: the pond's water, foaming, lies over those)
            body[int(rows[0] + 0.8 * (rows[-1] - rows[0])):] = False
        player.center_x, player.center_y = home[0], home[1]
        player.mesh_entity_data["elevation"] = home[2]
        report["in_front"] = {"body_pixels": int(body.sum()), "curtain_behind_it": int((mask & body).sum()),
                              "changed_by_the_fall": int((_changed(with_player, hidden) & body).sum())}
        Image.fromarray(with_player).save(out / "in_front.png")
        # foam at its foot (none with foam 0), none far out in the pond
        foamless = f.shot(FRONT, t0, f.without_falls(foam=0.0))
        fy = int(foot_px[1])
        near = (slice(fy + 4, fy + 40), slice(int(foot_px[0]) - 60, int(foot_px[0]) + 60))
        far_y = int(f.screen((FOOT[0], FOOT[1] - 5.5, 0.0))[1])
        far = (slice(far_y - 8, far_y + 8), slice(int(foot_px[0]) + 120, int(foot_px[0]) + 220))
        py0, py1 = (int(f.screen((FOOT[0], y / PX, 0.0))[1]) for y in (glen.Y(712.0), glen.Y(740.0)))
        in_pond = (slice(py0, py1), slice(int(foot_px[0]) - 50, int(foot_px[0]) + 50))  # (past the pond's shore)
        report["foam"] = {"lighter_in_pond": int(_lighter(falling[in_pond], plain[in_pond]).sum()),
                          "lighter_in_pond_foam0": int(_lighter(foamless[in_pond], plain[in_pond]).sum()),
                          "pond_pixels": int(falling[in_pond].shape[0] * falling[in_pond].shape[1]),
                          "lighter_near": int(_lighter(falling[near], plain[near]).sum()),
                          "lighter_near_foam0": int(_lighter(foamless[near], plain[near]).sum()),
                          "near_pixels": int(falling[near].shape[0] * falling[near].shape[1]),
                          "far_changed": int(_changed(falling[far], plain[far]).sum())}
        # spray: made only when asked for, drawn about its foot
        dry = f.shot(FRONT, t0, f.without_falls(spray=0.0))
        made_dry = hd.spray_particles is not None
        sprayed = f.shot(FRONT, t0, f.without_falls(spray=1.0))
        diff = _changed(dry, sprayed)
        ys, xs = np.where(diff)
        report["spray"] = {"made_when_none": made_dry, "made_when_asked": hd.spray_particles is not None,
                           "pixels": int(diff.sum()),
                           "box": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if xs.size else None,
                           "foot_px": foot_px}
        # draw calls, and nothing drawn or made out of the picture or once gone; no allocation a frame
        f.shot(FRONT, t0, f.without_falls())
        calls_plain = hd.draw_calls
        objects_plain = len(hd.gl_objects())
        f.shot(FRONT, t0)
        calls_falls, objects_falls = hd.draw_calls, len(hd.gl_objects())
        made = _gl_made(hd.ctx)
        allocations = hd.water.fall_allocations
        for k in range(20):
            f.shot(FRONT, t0 + k / 60)
        report["draws"] = {"plain": calls_plain, "falls": calls_falls, "objects_plain": objects_plain,
                           "objects_falls": objects_falls, "made_in_20_frames": {
                               k: v - made[k] for k, v in _gl_made(hd.ctx).items()},
                           "fall_buffers_made_in_20_frames": hd.water.fall_allocations - allocations}
        f.shot(AWAY, t0)
        report["away"] = {"draw_calls": hd.draw_calls, "water_draws": hd.water.draw_calls if hd.water else 0,
                          "spray_draws": hd.spray_particles.draw_calls if hd.spray_particles else 0}
        report["walks"] = _walks(f)
        f.shot(FRONT, t0, f.without_falls())
        before = len(hd.gl_objects())  # (after the walks: the player's animation has its own textures by now)
        f.shot(FRONT, t0)
        f.shot(FRONT, t0, f.without_falls())
        report["gone"] = {"fall_program": hd.water.fall_program is not None, "fall_buffers": hd.water.fall_buffers
                          is not None, "spray": hd.spray_particles is not None, "objects": len(hd.gl_objects()),
                          "objects_plain": before}
    finally:
        f.close()
    report["haze_bloom"] = _haze_bloom(out)
    return report


def _walks(f: Frames) -> dict[str, Any]:
    """The player walking at the fall: down the stream to its lip (south), and across the pool to its foot (north),
    with the window's own key events: neither walks into the falling water, nor drops down it."""
    import r3_river_bed_study as walker  # noqa: PLC0415

    game = f.game
    world = game.window.hd2d_world
    hd = f.hd
    hd.settings = dataclasses.replace(hd.settings, rivers=f.rivers)
    keys = game.arcade.key

    def floor(x: float, y: float) -> float:
        return float(min(h for h, _s in world.heights_at(x / PX, y / PX)))

    found: dict[str, Any] = {"lip_y": glen.Y(612.0), "foot_y": glen.Y(676.0)}
    start = (640.0, glen.Y(560.0), floor(640.0, glen.Y(560.0)))  # in the stream above, 1.6 m short of its lip
    south = keys.S if walker.walk(game, start, keys.S, 4)["y"] < start[1] else keys.W
    north = keys.W if south == keys.S else keys.S
    found["from_above"] = {**walker.walk(game, start, south, 180), "start": start}
    start = (640.0, glen.Y(760.0), floor(640.0, glen.Y(760.0)))  # in the pool, 2.6 m out from the foot
    found["from_below"] = {**walker.walk(game, start, north, 180), "start": start}
    player = game.player()
    found["falling_at_end"] = world.rivers.falling_at(player.center_x / PX, player.bottom / PX)
    return found


def _haze_bloom(out: Path) -> dict[str, Any]:
    """The evening glen with the room's haze and warm bloom: the water writes no emission (it dims what glows
    behind it), the lamps do."""
    import hd2d_bloom_study as bloom  # noqa: PLC0415

    f = Frames(glen.make_project(out, "glen_haze_bloom", variant="haze_bloom"))
    try:
        hd = f.hd
        pic = f.shot(WIDE, 3.0)
        lip_px, foot_px = f.screen((*LIP, glen.UPPER_PX / PX)), f.screen((*FOOT, 0.0))
        emission = bloom.floats(hd._bloom.emission)[::-1] if hd._bloom is not None else None
        w, h = f.size
        sx, sy = emission.shape[1] / w if emission is not None else 1, emission.shape[0] / h if emission is not None else 1
        region = (emission[int(lip_px[1] * sy) - 2:int(foot_px[1] * sy) + 6, int((lip_px[0] - 30) * sx):int((lip_px[0] + 30) * sx)]
                  if emission is not None else None)
        from PIL import Image  # noqa: PLC0415

        Image.fromarray(pic).save(out / "haze_bloom.png")
        return {"stage": hd.last_stage, "bloom": hd.last_bloom, "haze": getattr(hd.settings.haze, "preset", None),
                "curtain_emission_max": float(region.max()) if region is not None and region.size else None,
                "room_emission_max": float(emission.max()) if emission is not None else None,
                "fall_count": hd.water.fall_count if hd.water else 0}
    finally:
        f.close()


# ---------------------------------------------------------------------- Mesh Studio
def _stored(d: Any) -> dict[str, Any]:
    from engine import project_ops as ops  # noqa: PLC0415

    return ops.rivers(d.studio.project.scene())[0]


def studio(out: Path) -> dict[str, Any]:
    """A creator making the glen's waterfall in Studio (the room with its stream, no waterfall yet)."""
    from hd2d_bloom_studio import _escape, _parity
    from hd2d_studio_demo import StudioDriver

    from engine.studio_project import Project

    out.mkdir(parents=True, exist_ok=True)
    project = glen.make_project(out, "glen_studio", variant="plain")
    report: dict[str, Any] = {}
    d = StudioDriver(project)
    try:
        k, studio_, view = d.arcade.key, d.studio, d.studio.hd2d
        tool = view.river
        d.button("Terrain")
        d.button("River")
        d.button("Select 'glen_falls'")
        view.camera.target, view.camera.distance, view.camera.pitch = (20.0, 23.9, 1.4), 48.0, 30.0
        view.advance_motion = view.advance_weather = lambda dt: None
        d.advance(2)

        def steps() -> int:
            return len(studio_.project._undo)

        x, y, _w, level = _stored(d)["points"][2]
        d.click(*d.screen((x / PX, y / PX, level / PX)))
        d.advance()
        report["selected"] = {"point": tool.point, "button": d.has_button("Waterfall to next point")}
        undo0 = steps()
        d.button("Waterfall to next point")
        d.advance(2)
        r = d.renderer
        report["made"] = {"stored": _stored(d).get("falls"), "steps": steps() - undo0, "message": studio_.message,
                          "renderer_falls": [dataclasses.asdict(x) for x in r.settings.rivers[0].falls],
                          "curtain_drawn": bool(r.water is not None and r.water.fall_count > 0),
                          "fields": [key for key in ("river_fall_below", "river_fall_foam", "river_fall_spray")
                                     if key in studio_._focusable]}
        d.picture(out / "studio_made.png")
        d.button("Into the pond: off")  # (falling, it now meets the pond's water)
        d.advance(2)
        report["joined"] = {"mouth": _stored(d).get("mouth"), "message": studio_.message,
                            "steps": steps() - undo0}
        terrain_before = list(d.renderer.terrain.heights) if d.renderer.terrain is not None else None
        d.button("Carve the bed")
        d.advance(2)
        after = d.renderer.terrain
        report["carved"] = {"message": studio_.message, "steps": steps() - undo0,
                            "lowered": sum(1 for a, b in zip(terrain_before or [], after.heights) if b < a)
                            if after is not None else 0,
                            "falls": _stored(d).get("falls"), "mouth": _stored(d).get("mouth"),
                            "curtain_drawn": bool(d.renderer.water is not None and d.renderer.water.fall_count > 0)}
        d.type_into("river_fall_foam", "0.3")
        d.type_into("river_fall_spray", "0")
        d.advance(2)
        report["tuned"] = {"stored": _stored(d).get("falls"), "steps": steps() - undo0,
                           "spray_made": r.spray_particles is not None}
        points = [list(p) for p in _stored(d)["points"]]
        too_high = (points[2][3] - 8.0) / PX
        d.type_into("river_fall_below", f"{too_high:.3f}")
        report["refused"] = {"points_same": _stored(d)["points"] == points, "message": studio_.message,
                             "ok": studio_.message_ok, "held": "river_fall_below" in studio_._held,
                             "put_back": _escape(d, "river_fall_below"), "steps": steps() - undo0}
        d.key(k.ESCAPE)
        first = _stored(d)["points"][0]
        d.click(*d.screen((first[0] / PX, first[1] / PX, first[3] / PX)))
        d.key(k.INSERT)  # (upstream of it: the waterfall renumbered with its points, then back)
        renumbered = _stored(d).get("falls")
        d.key(k.DELETE)
        report["renumbered"] = {"inserted": renumbered, "removed": _stored(d).get("falls"),
                                "points": len(_stored(d)["points"])}
        d.key(k.ESCAPE)
        d.click(*d.screen((points[2][0] / PX, points[2][1] / PX, points[2][3] / PX)))
        d.key(k.INSERT)
        report["insert_refused"] = {"points": len(_stored(d)["points"]), "message": studio_.message}
        d.button("Reverse flow")
        report["reverse_refused"] = {"first": _stored(d)["points"][0] == points[0], "message": studio_.message}
        d.key(k.ESCAPE)
        d.key(k.Z, k.MOD_CTRL)
        report["undone"] = _stored(d).get("falls")
        d.key(k.Y, k.MOD_CTRL)
        report["redone"] = _stored(d).get("falls")
        x, y, _w, level = _stored(d)["points"][2]
        d.click(*d.screen((x / PX, y / PX, level / PX)))
        d.advance()
        d.type_into("river_fall_spray", "0.6")
        d.key(k.ESCAPE)
        d.advance(2)
        report["parity"] = _parity(d)
        d.key(k.S, k.MOD_CTRL)
        saved = _stored(d)
        world = json.loads((project / "config.json").read_text(encoding="utf-8"))["world_file"]
        from engine import project_ops as ops  # noqa: PLC0415

        report["reopened_same"] = ops.rivers(Project(project, world).scene(studio_.project.current))[0] == saved
        d.key(k.F4)
        for _ in range(30):
            d.advance()
            time.sleep(1 / 60)
        g = d.window.hd2d_renderer
        report["play"] = {"mode": studio_.mode, "falls": [dataclasses.asdict(x) for x in g.settings.rivers[0].falls],
                          "curtain_drawn": bool(g.water is not None and g.water.fall_count > 0),
                          "feet": len(g.water.feet) if g.water else 0, "water_time": d.window.water_time}
        d.picture(out / "play.png")
        d.key(k.F4)
        d.advance(5)
        report["stopped"] = {"mode": studio_.mode, "same": _stored(d) == saved}
        x, y, _w, level = _stored(d)["points"][2]
        d.click(*d.screen((x / PX, y / PX, level / PX)))
        d.advance()
        d.button("Remove waterfall")  # (refused: without it, it couldn't meet the pond it flows into)
        d.advance(2)
        report["remove_refused"] = {"falls": _stored(d).get("falls"), "message": studio_.message}
        d.button("Into the pond: on")
        d.advance()
        d.click(*d.screen((x / PX, y / PX, level / PX)))
        d.advance()
        d.button("Remove waterfall")
        d.advance(2)
        report["removed"] = {"falls": _stored(d).get("falls"), "fall_program": d.renderer.water.fall_program is not None,
                             "spray": d.renderer.spray_particles is not None}
    finally:
        d.close()
    report["export"] = export_check(project, out)
    return report


def export_check(project: Path, out: Path) -> dict[str, Any]:
    """The project exported and its bundle's own engine run: the waterfall saved (its room's falls) is drawn."""
    bundle = out / "export"
    if bundle.exists():
        shutil.rmtree(bundle)
    built = subprocess.run([sys.executable, "-m", "mesh_cli", "export", "build", "--out", str(bundle)], cwd=project,
                           capture_output=True, text=True, timeout=900, env={**os.environ, "PYTHONPATH": str(REPO)})
    code = f"""
import json, sys
sys.path.insert(0, {str(bundle)!r})
import engine
sys.path.insert(1, {str(REPO / "tooling")!r})
from hd2d_demo import HiddenGame
from pathlib import Path
game = HiddenGame(Path({str(bundle)!r}))
try:
    game.load("{SCENES}/start.json")
    game.step(60)
    game.draw()
    r = game.window.hd2d_renderer
    w = r.water
    print(json.dumps({{"engine_from": engine.__file__, "falls": [len(x.falls) for x in r.settings.rivers],
                      "fall_count": w.fall_count if w else 0, "feet": len(w.feet) if w else 0}}))
finally:
    game.window.close()
"""
    ran = subprocess.run([sys.executable, "-c", code], cwd=bundle, capture_output=True, text=True, timeout=900,
                         env={k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "MESH_REPO_ROOT")})
    try:
        run = json.loads(ran.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        run = {"failed": ran.stdout[-600:] + ran.stderr[-1500:]}
    copied = next((p for p in bundle.rglob("start.json") if p.as_posix().endswith(f"{SCENES}/start.json")), None)
    exported = json.loads(copied.read_text(encoding="utf-8")) if copied is not None else {}
    source = json.loads((project / SCENES / "start.json").read_text(encoding="utf-8"))
    return {"code": built.returncode, "bundle_run": run,
            "same_rivers": ((exported.get("settings") or {}).get("hd2d") or {}).get("rivers")
            == source["settings"]["hd2d"].get("rivers")}


def main() -> None:
    out = Path(sys.argv[1]).resolve()
    which = sys.argv[2] if len(sys.argv) > 2 else "frames"
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    found = frames(out / "frames") if which == "frames" else studio(out / "studio")
    print(json.dumps(found, indent=1, default=str))


if __name__ == "__main__":
    main()
