"""Milestone 19A evidence: puddles and ponds in the HD-2D starter village (hidden windows only).

    py -3.13 tooling/m19_water_study.py look OUT       # the village with water, rain and dry, from a few places
    py -3.13 tooling/m19_water_study.py proof OUT      # depth, rain ripples (and shelter), footsteps, pictures, clips
    py -3.13 tooling/m19_water_study.py perf OUT       # no water / puddles / pond / both, in rain; GPU lifecycle

The test village: a project from the HD-2D RPG template, with a puddle beside the cottage and a pond near the bridge,
placed through the same checked operations Studio and AI use (``project_ops.place_blank`` and ``set_water``), at
places worked out from where the cottage and the bridge stand.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
import hd2d_visual_study as study  # noqa: E402
from hd2d_demo import SCENES, HiddenGame, _gl_counts  # noqa: E402

PX = 32.0
RAIN = [{"preset": "rain", "count": 4000, "seed": 2}]


def _structure_centre(scene: dict, word: str) -> tuple[float, float]:
    for st in scene["settings"]["hd2d"]["structures"]:
        if word in Path(st["model"]).stem:
            return float(st["x"]), float(st["y"])
    raise KeyError(word)


def make_project(out: Path, name: str, *, puddle: bool = True, pond: bool = True, rain: bool = True,
                 pond_walkable: bool = True) -> Path:
    """The village with its water (and rain), written through project_ops."""
    from engine import project_ops as ops

    project: Path = study.new_project(out, name, stage6a=False)
    path = project / SCENES / "start.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    cx, cy = _structure_centre(scene, "cottage")
    bx, by = _structure_centre(scene, "bridge")
    if puddle:  # beside the cottage, south-east of its door
        scene, pid = ops.place_blank(scene, "start", "Puddle", cx + 3.2 * PX, cy - 2.7 * PX)
        scene = ops.set_water(scene, pid, preset="puddle", width=88, height=52)
    if pond:  # near the bridge: south-east of it, off the path
        scene, qid = ops.place_blank(scene, "start", "Pond", bx + 4.5 * PX, by - 5.5 * PX)
        scene = ops.set_water(scene, qid, preset="pond", width=224, height=150, walkable=pond_walkable)
    if rain:
        scene = ops.set_particles(scene, RAIN)
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    return project


def water_spots(game: HiddenGame) -> dict[str, tuple[float, float, float]]:
    """Where the water surfaces are (m): camera targets to look at them."""
    out = {}
    for body in getattr(game.window, "water_bodies", None) or []:
        x, y, z = body.place()
        out[str(getattr(body.entity, "mesh_name", "water")).lower()] = (x, y, z)
    return out


def shot(game: HiddenGame, target: tuple[float, float, float]) -> Any:
    from PIL import Image

    hd = game.window.hd2d_renderer
    hd.camera.target = target
    hd._camera_ready = True
    return Image.frombytes("RGB", study.SIZE, hd.draw(read=True)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)


def look(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for rain in (True, False):
        game = HiddenGame(make_project(out, f"look_{'rain' if rain else 'dry'}", rain=rain), size=study.SIZE)
        try:
            game.load(f"{SCENES}/start.json")
            game.step(90)
            for name, (x, y, z) in water_spots(game).items():
                shot(game, (x, y - 0.8, z + 0.8)).save(out / f"{name}_{'rain' if rain else 'dry'}.png")
            print(rain, game.window.hd2d_renderer.stats()["water_surfaces"], game.window.hd2d_renderer.draw_calls)
        finally:
            game.close()


def _mask(a: Any, b: Any) -> Any:
    import numpy as np

    return np.any(np.asarray(a) != np.asarray(b), axis=2)


def _body(game: HiddenGame, name: str) -> Any:
    return next(b for b in game.window.water_bodies if str(getattr(b.entity, "mesh_name", "")).lower() == name)


def _with_ripples(game: HiddenGame, on: bool, only: str | None = None) -> None:
    from dataclasses import replace

    for b in game.window.water_bodies:
        if only is None or str(getattr(b.entity, "mesh_name", "")).lower() == only:
            b.water = replace(b.water, rain_ripples=on)


def depth_and_anchoring(out: Path) -> dict[str, Any]:
    """Water hidden where a structure stands in front of it (the shop's roof over the pond), counted against the same
    water drawn with the depth test off; and the water moving with the world as the camera moves."""
    game = HiddenGame(make_project(out, "proj_depth", rain=False), size=study.SIZE)
    report: dict[str, Any] = {}
    try:
        game.load(f"{SCENES}/start.json")
        game.step(30)
        hd = game.window.hd2d_renderer
        x, y, z = water_spots(game)["pond"]
        target = (x, y - 0.8, z + 0.8)
        wet = shot(game, target)
        bodies = game.window.water_bodies
        game.window.water_bodies = []
        dry = shot(game, target)
        game.window.water_bodies = bodies
        hd.draw(read=True)
        hd.water.depth_test = False
        seen_through = shot(game, target)
        hd.water.depth_test = True
        drawn, unhidden = _mask(wet, dry), _mask(seen_through, dry)
        report["pond_pixels_drawn"] = int(drawn.sum())
        report["pond_pixels_hidden_by_structures"] = int((unhidden & ~drawn).sum())
        # anchoring: the camera moves 0.5 m east, the time held; the water's pixels move with the world
        import numpy as np

        before = drawn
        target2 = (target[0] + 0.5, target[1], target[2])
        moved_wet = shot(game, target2)
        game.window.water_bodies = []
        moved_dry = shot(game, target2)
        game.window.water_bodies = bodies
        moved = _mask(moved_wet, moved_dry)
        vp = hd.camera.view_projection(study.SIZE[0] / study.SIZE[1])
        c = [sum(vp[r][k] * (x, y, z, 1.0)[k] for k in range(4)) for r in range(4)]
        hd.camera.target = target
        vp0 = hd.camera.view_projection(study.SIZE[0] / study.SIZE[1])
        c0 = [sum(vp0[r][k] * (x, y, z, 1.0)[k] for k in range(4)) for r in range(4)]
        shift = round((c[0] / c[3] - c0[0] / c0[3]) * 0.5 * study.SIZE[0])
        report["world_shift_px"] = shift
        shifted = np.roll(before, shift, axis=1)
        both = (shifted & moved).sum() / max(1, moved.sum())
        report["water_pixels_found_where_the_world_moved"] = round(float(both), 3)
        report["water_pixels_found_where_they_were_on_screen"] = round(float((before & moved).sum() / max(1, moved.sum())), 3)
        m18_pair([dry, wet, seen_through], ["no water", "the pond (depth-tested)", "the pond, depth test off"],
                 out / "pond_depth.png")
    finally:
        game.close()
    return report


def m18_pair(images: list[Any], labels: list[str], path: Path) -> None:
    import m18_particles_study as m18

    m18.pair([m18.crop_at(i, study.SIZE[0] / 2, study.SIZE[1] / 2, (640, 360)) for i in images], labels).save(path)


def ripples(out: Path) -> dict[str, Any]:
    """Rain rings the water, and not under shelter: the same moment with the water's rain ripples on and off (the
    rain itself drawn in both), for the open puddle, the open pond, and a puddle under the bridge's deck."""
    from engine import project_ops as ops

    project = make_project(out, "proj_ripples", rain=True)
    path = project / SCENES / "start.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    bx, by = _structure_centre(scene, "bridge")
    scene, sid = ops.place_blank(scene, "start", "Sheltered", bx, by - 0.6 * PX)  # in the underpass, under the deck
    scene = ops.set_water(scene, sid, preset="puddle", width=48, height=40)
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    game = HiddenGame(project, size=study.SIZE)
    report: dict[str, Any] = {}
    try:
        game.load(f"{SCENES}/start.json")
        game.step(30)
        hd = game.window.hd2d_renderer
        spots = water_spots(game)
        hd.draw(read=True)
        hd.water.depth_test = False  # judged without the camera's depth: under the deck the puddle is hidden anyway
        for name, shelter in (("puddle", True), ("pond", True), ("sheltered", True), ("sheltered", False)):
            hd.water.shelter = shelter
            x, y, z = spots[name]
            body = _body(game, name)
            w_px = (body.water.width / PX, body.water.height / PX)
            counts = []
            for t in (3.0, 3.4, 3.8):
                game.window.water_time = t
                hd.particles.time = t
                _with_ripples(game, True)
                on = shot(game, (x, y - 0.5, z + 0.8))
                _with_ripples(game, False, only=name)  # this water's own rings, nothing else's
                off = shot(game, (x, y - 0.5, z + 0.8))
                _with_ripples(game, True)
                counts.append(int(_mask(on, off).sum()))
                if t == 3.0:
                    m18_pair([off, on], [f"{name}: rain, no ripples (water seen through)", f"{name}: rain ripples"],
                             out / f"ripples_{name}{'' if shelter else '_shelter_off'}.png")
            key = name if shelter else f"{name}_negative_control_shelter_off"
            report[key] = {"size_m": [round(v, 2) for v in w_px], "ripple_pixels_per_frame": counts}
        hd.water.depth_test, hd.water.shelter = True, True
        # the rings are the world's: the same moment from a camera 0.5 m to the east
        x, y, z = spots["pond"]
        game.window.water_time = hd.particles.time = 3.0
        a_on, a_off = _ripple_frame(game, (x, y - 0.5, z + 0.8))
        b_on, b_off = _ripple_frame(game, (x + 0.5, y - 0.5, z + 0.8))
        import numpy as np

        ma, mb = _mask(a_on, a_off), _mask(b_on, b_off)
        best = max(range(-40, 1), key=lambda s: int((np.roll(ma, s, axis=1) & mb).sum()))
        report["rings_follow_the_world"] = {"best_shift_px": best,
                                            "overlap_at_best": round(float((np.roll(ma, best, axis=1) & mb).sum() / max(1, mb.sum())), 3),
                                            "overlap_unshifted": round(float((ma & mb).sum() / max(1, mb.sum())), 3)}
    finally:
        game.close()
    return report


def _ripple_frame(game: HiddenGame, target: tuple[float, float, float]) -> tuple[Any, Any]:
    _with_ripples(game, True)
    on = shot(game, target)
    _with_ripples(game, False)
    off = shot(game, target)
    _with_ripples(game, True)
    return on, off


def footsteps(out: Path) -> dict[str, Any]:
    """The player walks through the puddle (the player's own key events): steps, ripples, events; a 1:1 clip."""
    import m18_particles_study as m18
    from hd2d_floors_demo import _feet, hold_key

    game = HiddenGame(make_project(out, "proj_steps", rain=False), size=study.SIZE)
    report: dict[str, Any] = {}
    try:
        game.load(f"{SCENES}/start.json")
        game.step(30)
        player = game.player()
        px, py, _pz = water_spots(game)["puddle"]
        keys = game.arcade.key
        fx, fy = _feet(player)
        hold_key(game, player, keys.DOWN if fy > py else keys.UP, 1, py)
        hold_key(game, player, keys.RIGHT, 0, px + 3.0)
        game.step(20)
        puddle = _body(game, "puddle")
        behaviour = next(b for b in puddle.entity.mesh_behaviours_runtime if type(b).__name__ == "WaterSurface")
        start_steps = behaviour.steps
        clip: list[Any] = []

        def film() -> None:  # while the player is by the puddle: the picture about the puddle, 1:1
            hd = game.window.hd2d_renderer
            fx, fy = _feet(game.player())
            if len(clip) >= 90 or abs(fx - px) > 3.5:
                return
            picture = game.draw().convert("RGB")
            vp = hd.camera.view_projection(study.SIZE[0] / study.SIZE[1])
            c = [sum(vp[r][k] * (px, py, 0.0, 1.0)[k] for k in range(4)) for r in range(4)]
            sx, sy = (c[0] / c[3] * 0.5 + 0.5) * study.SIZE[0], (0.5 - c[1] / c[3] * 0.5) * study.SIZE[1]
            clip.append(m18.crop_at(picture, sx, sy, (480, 270)))

        hold_key(game, game.player(), keys.LEFT, 0, px - 3.0, 400, each_frame=film)
        report["steps_through_the_puddle"] = behaviour.steps - start_steps
        bus = getattr(game.window, "event_bus", None)
        names = bus.get_recent_event_names(200) if bus is not None and hasattr(bus, "get_recent_event_names") else []
        report["water_step_events_seen"] = sum(1 for n in names if n == "water_step")
        report["ripples_alive_after"] = len(game.window.water_steps)
        if clip:
            clip[0].save(out / "puddle_walk.webp", save_all=True, append_images=clip[1::2], duration=66, loop=0,
                         quality=85, method=6)
        report["clip_frames"] = len(clip[::2])
    finally:
        game.close()
    return report


def blocking(out: Path) -> dict[str, Any]:
    """A pond set not walkable stops the player at its edge; a walkable one lets them wade in."""
    from hd2d_floors_demo import _feet, hold_key

    report: dict[str, Any] = {}
    for walkable in (True, False):
        game = HiddenGame(make_project(out, f"proj_block_{walkable}", puddle=False, rain=False, pond_walkable=walkable),
                          size=study.SIZE)
        try:
            game.load(f"{SCENES}/start.json")
            game.step(30)
            x, y, _z = water_spots(game)["pond"]
            half_h = _body(game, "pond").water.height / PX / 2
            player = game.player()
            player.center_x = x * PX
            player.center_y += (y - half_h - 1.5) * PX - player.bottom
            game.step(5)
            hold_key(game, player, game.arcade.key.UP, 1, y, 240)
            fx, fy = _feet(player)
            report["walkable" if walkable else "blocking"] = {"pond_south_edge_m": round(y - half_h, 2),
                                                              "pond_centre_m": round(y, 2), "feet_reached_m": round(fy, 2)}
        finally:
            game.close()
    return report


def two_d(out: Path) -> dict[str, Any]:
    """The same water in an ordinary 2D room (the blank template): drawn under the player, rippled by the rain."""
    from engine import project_ops as ops
    from engine.project_scaffold import create_project

    project = out / "Plain2D"
    create_project(project, "Plain2D", template_id="blank")
    path = project / "packs" / "core_regions" / "scenes" / "start.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    player = next(e for e in scene["entities"] if e.get("tag") == "player" or e.get("prefab_id") == "player")
    scene, pid = ops.place_blank(scene, "start", "Puddle", float(player["x"]), float(player["y"]) - 10)
    scene = ops.set_water(scene, pid, preset="puddle", width=96, height=56)
    scene, qid = ops.place_blank(scene, "start", "Pond", float(player["x"]) + 220, float(player["y"]) + 60)
    scene = ops.set_water(scene, qid, preset="pond", width=200, height=130)
    scene = ops.set_particles(scene, RAIN)
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    game = HiddenGame(project, size=(960, 540))
    report: dict[str, Any] = {}
    try:
        game.load("packs/core_regions/scenes/start.json")
        game.step(60)
        wet = game.draw().convert("RGB")
        bodies = game.window.water_bodies
        game.window.water_bodies = []
        dry = game.draw().convert("RGB")
        game.window.water_bodies = bodies
        mask = _mask(wet, dry)
        p = game.player()
        h = 540
        box = (int(p.left), int(h - p.top), int(p.right), int(h - p.bottom))
        report["water_pixels"] = int(mask.sum())
        report["player_pixels_changed_by_water"] = int(mask[box[1]:box[3], box[0]:box[2]].sum())
        report["player_box"] = box
        from PIL import Image

        sheet = Image.new("RGB", (1920, 540))
        sheet.paste(dry, (0, 0))
        sheet.paste(wet, (960, 0))
        sheet.save(out / "two_d_water.png")
    finally:
        game.close()
    return report


def studio_workflow(out: Path) -> dict[str, Any]:
    """A creator's water in Mesh Studio, through its own buttons, fields and keys (hidden window): choose Water in the
    Objects list and click the ground in the 3D view; make it a pond; type its width; undo and redo; see it drawn
    (and rippled) in the editing view; click it in 3D to select it; save; reopen; play and stop."""
    import os

    import hd2d_studio_demo

    from engine import project_ops as ops

    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    project = make_project(out, "studio_water", puddle=False, pond=False, rain=True)
    report: dict[str, Any] = {}
    d = hd2d_studio_demo.StudioDriver(project)
    try:
        studio, k = d.studio, d.arcade.key
        ctrl = k.MOD_CTRL
        scene = studio.project.scene()
        cx, cy = _structure_centre(scene, "cottage")
        spot = (cx / PX + 3.2, cy / PX - 2.7, 0.0)
        d.button("Water")
        at = d.screen(spot)
        d.window.dispatch_event("on_mouse_motion", *at, 0, 0)
        d.frame()
        d.click(*at)
        new_id = studio.selected
        entity = ops.find_entity(studio.project.scene(), new_id) if new_id else {}
        report["placed"] = {"message": studio.message, "water": ops.water_of(entity) if entity else None,
                            "where_m": [round(entity.get("x", 0) / PX, 2), round(entity.get("y", 0) / PX, 2)] if entity else None}
        d.button("Pond")
        d.type_into("water_w", "180")
        def water_now() -> dict[str, Any]:
            found = ops.water_of(ops.find_entity(studio.project.scene(), new_id))
            assert found is not None, "it is water"
            return found

        water = water_now()
        report["pond_180"] = {"preset": water["preset"], "width": water["width"]}
        d.key(k.Z, ctrl)
        undone = water_now()
        d.key(k.Y, ctrl)
        redone = water_now()
        report["undo_redo_width"] = [undone["width"], redone["width"]]
        frames = [d.frame(2).convert("RGB") for _ in range(2)]
        hd = d.renderer
        report["drawn_in_editing_view"] = {"water_surfaces": hd.stats()["water_surfaces"],
                                           "moving": int(_mask(*frames).sum())}
        frames[-1].save(out / "studio_water.png")
        studio.select(None)
        d.click(*d.screen((*spot[:2], 0.0)))
        report["clicked_in_3d_selects_it"] = studio.selected == new_id
        d.key(k.S, ctrl)
        report["saved_dirty_after"] = studio.project.is_dirty
    finally:
        d.close()
    d = hd2d_studio_demo.StudioDriver(project)
    try:
        entity = ops.find_entity(d.studio.project.scene(), new_id)
        report["reopened"] = ops.water_of(entity)
        d.key(d.arcade.key.F4)
        d.frame(20)
        report["in_play"] = {"mode": d.studio.mode, "water_surfaces": len(getattr(d.window, "water_bodies", []))}
        d.key(d.arcade.key.F4)
        d.frame(3)
        report["after_stop_mode"] = d.studio.mode
    finally:
        d.close()
    return report


def proof(out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    for name, step in (("depth_and_anchoring", depth_and_anchoring), ("ripples", ripples), ("footsteps", footsteps),
                       ("blocking", blocking), ("two_d", two_d)):
        report[name] = step(out)
        print(name, json.dumps(report[name]), flush=True)
    look(out)
    (out / "proof.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def _water_gpu_ms(game: HiddenGame, frames: int = 40) -> float:
    """The water pass's GPU time (a timer query round it; the frame copy for reflections included), median ms."""
    ctx, hd = game.window.ctx, game.window.hd2d_renderer
    layer = hd.water
    if layer is None:
        return 0.0
    original, times = layer.draw_3d, []

    def timed(*args: Any, **kwargs: Any) -> Any:
        query = ctx.query(samples=False, primitives=False)
        with query:
            result = original(*args, **kwargs)
        ctx.finish()
        times.append(query.time_elapsed / 1e6)
        return result

    layer.draw_3d = timed
    try:
        for _ in range(frames):
            game.window.dispatch_event("on_update", 1 / 60)
            game.window.dispatch_event("on_draw")
    finally:
        layer.draw_3d = original
    return round(statistics.median(times), 3) if times else 0.0


def _frame_gpu_ms(game: HiddenGame, frames: int = 30) -> float:
    """The whole frame's GPU time (timer queries), median ms."""
    ctx, times = game.window.ctx, []
    for _ in range(frames):
        game.window.dispatch_event("on_update", 1 / 60)
        query = ctx.query(samples=False, primitives=False)
        with query:
            game.window.dispatch_event("on_draw")
        ctx.finish()
        times.append(query.time_elapsed / 1e6)
    return float(statistics.median(times))


def _water_cpu_ms(game: HiddenGame, frames: int = 60) -> float:
    """The renderer's water step on the CPU (bodies, uniforms, the frame copy and draw issued; no GPU wait)."""
    import time

    hd, times = game.window.hd2d_renderer, []
    original = hd._draw_water

    def timed(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        result = original(*args, **kwargs)
        times.append((time.perf_counter() - start) * 1000)
        return result

    hd._draw_water = timed
    try:
        for _ in range(frames):
            game.window.dispatch_event("on_update", 1 / 60)
            game.window.dispatch_event("on_draw")
    finally:
        hd._draw_water = original
    return round(statistics.median(times), 3)


def perf(out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"method": "per case one game in rain (4,000 drops), the camera between the puddle and the "
                                        "pond; 5 interleaved rounds of 60 frames with the water drawn and taken away "
                                        "(medians); the water pass's GPU time by a timer query", "cases": {}}
    cases = {"no_water": (False, False), "puddle_only": (True, False), "pond_only": (False, True), "both": (True, True)}
    for name, (puddle, pond) in cases.items():
        game = HiddenGame(make_project(out, f"perf_{name}", puddle=puddle, pond=pond), size=study.SIZE)
        try:
            ctx = game.window.ctx
            report.setdefault("gpu", {"renderer": ctx.info.RENDERER, "gl_version": list(ctx.gl_version)})
            game.load(f"{SCENES}/start.json")
            game.step(30)
            hd = game.window.hd2d_renderer
            hd.camera.target = (17.0, 12.0, 0.8)
            hd._camera_ready = True
            bodies = list(game.window.water_bodies)
            game.window.dispatch_event("on_draw")
            rounds: dict[str, list[float]] = {"on": [], "off": [], "gpu_on": [], "gpu_off": []}
            for _ in range(5):
                for on in (True, False):
                    game.window.water_bodies = bodies if on else []
                    rounds["on" if on else "off"].append(study.frame_cost(game, 60)["frame_ms"])
                    rounds["gpu_on" if on else "gpu_off"].append(_frame_gpu_ms(game))
            game.window.water_bodies = bodies
            game.window.dispatch_event("on_draw")
            stats = hd.stats()
            med = statistics.median
            report["cases"][name] = {
                "water_surfaces": len(bodies), "draw_calls": stats["draw_calls"], "water_bytes": stats["water_bytes"],
                "frame_ms_with": round(med(rounds["on"]), 3), "frame_ms_without": round(med(rounds["off"]), 3),
                "added_frame_ms": round(med(rounds["on"]) - med(rounds["off"]), 3),
                "frame_gpu_ms_with": round(med(rounds["gpu_on"]), 3), "frame_gpu_ms_without": round(med(rounds["gpu_off"]), 3),
                "added_frame_gpu_ms": round(med(rounds["gpu_on"]) - med(rounds["gpu_off"]), 3),
                "water_pass_gpu_ms": _water_gpu_ms(game) if bodies else 0.0,
                "water_draw_cpu_ms": _water_cpu_ms(game) if bodies else 0.0}
            print(name, report["cases"][name], flush=True)
        finally:
            game.close()
    # GPU objects: room changes, Studio edits, Play/Stop
    game = HiddenGame(make_project(out, "perf_life"), size=study.SIZE)
    try:
        ctx = game.window.ctx
        game.load(f"{SCENES}/start.json")
        game.step(3)
        game.window.dispatch_event("on_draw")
        ctx.gc()
        before = _gl_counts(ctx)
        for _ in range(10):
            game.load(f"{SCENES}/cottage.json")
            game.step(3)
            game.window.dispatch_event("on_draw")
            game.load(f"{SCENES}/start.json")
            game.step(3)
            game.window.dispatch_event("on_draw")
        ctx.gc()
        report["room_changes_10"] = {"before": before, "after": _gl_counts(ctx)}
    finally:
        game.close()
    report["studio"] = _studio_lifecycle(out)
    (out / "perf.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def _studio_lifecycle(out: Path) -> dict[str, Any]:
    """Mesh Studio on the village with water and rain: 10 water edits (each reloads the room), 5 Play/Stop; GL objects
    (textures, framebuffers, programs) after each."""
    import os

    import hd2d_studio_demo

    from engine import project_ops as ops

    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    driver = hd2d_studio_demo.StudioDriver(make_project(out, "perf_studio"))
    try:
        rows = {"start": driver.gl_counts()}
        pond = next(e["id"] for e in ops.entities(driver.studio.project.scene()) if e.get("name") == "Pond")
        for i in range(10):
            driver.studio._edit(lambda s, i=i: ops.set_water(s, pond, width=200 + 4 * i), "")
            driver.frame(2)
        rows["after_10_edits"] = driver.gl_counts()
        f4 = driver.arcade.key.F4
        for _ in range(5):
            driver.key(f4)
            driver.frame(10)
            driver.key(f4)
            driver.frame(3)
        rows["after_5_play_stop"] = driver.gl_counts()
    finally:
        driver.close()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["look", "proof", "perf"])
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    if args.command == "look":
        look(args.out)
    elif args.command == "perf":
        print(json.dumps({k: v for k, v in perf(args.out).items() if k != "cases"}, indent=1))
    else:
        proof(args.out)


if __name__ == "__main__":
    main()
