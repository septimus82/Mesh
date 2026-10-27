"""Milestone 20A evidence: sculpted terrain in a disposable HD-2D room (hidden windows only).

    py -3.13 tooling/m20a_terrain_study.py look OUT      # the room from a few places, dry and in rain
    py -3.13 tooling/m20a_terrain_study.py proof OUT     # sculpting, walking, anchoring, water, environment, Studio
    py -3.13 tooling/m20a_terrain_study.py perf OUT      # rebuild, collision-query, memory and drawing cost

The room ("Hills", ``hills.json``) is added to a project from the HD-2D RPG template; the template's village is left
as it is. Its ground (32 x 24 m) is sculpted only through ``project_ops.sculpt_terrain`` (as Studio and AI edit):

- a gentle hill in the west (1.5 m), an Elder on its top;
- a terrace in the north-east (1.5 m): a ramp up from the west, a cliff on its south side;
- the template's bridge between two platforms (stairs up to the west one), a shallow valley running under the bridge;
- a basin in the south-east (1.2 m deep) holding a natural pond (Stage 19B) whose shore is the ground itself, its
  water 0.6 m below the ground;
- the cottage on the flat ground; the player starts in the south-west.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
import hd2d_visual_study as study  # noqa: E402
from hd2d_demo import SCENES, HiddenGame, _gl_counts  # noqa: E402

PX = 32.0
SIZE_M = (32.0, 24.0)
HILL = (4.5, 19.5, 4.0, 1.5)  # x, y, radius, height (m)
TERRACE = (24.5, 31.5, 15.5, 22.5, 1.5)  # x0, x1, y0, y1, height (m)
RAMP = ((20.5, 19.0), (24.5, 19.0))  # from, to (m): the ramp up onto the terrace's west side
VALLEY = ((15.0, 3.0), (15.0, 23.0), 1.5, 0.6)  # from, to, half width, depth (m)
BASIN = (26.0, 6.0, 3.5, 1.2)  # x, y, radius, depth (m)
WATER_LEVEL = -0.6  # m: the pond's surface
STRUCTURES = [("platform_w", "platform_4m", 11.0, 15.0, 0.0), ("platform_e", "platform_4m", 19.0, 15.0, 0.0),
              ("bridge", "bridge_6m", 15.0, 15.0, 0.0), ("stairs", "stairs", 11.0, 9.5, 0.0),
              ("cottage", "cottage", 5.0, 6.0, 0.0)]
RAIN = [{"preset": "rain", "count": 4000, "seed": 2}]
STAGES = ("hill", "terrace", "valley", "basin")


def strokes(scene: dict[str, Any], stages: tuple[str, ...] = STAGES) -> tuple[dict[str, Any], int]:
    """The room's ground sculpted, stroke by stroke, through the checked operation. Returns it and the strokes."""
    from engine import project_ops as ops

    n = 0

    def stroke(tool: str, x: float, y: float, radius: float, strength: float, target: float | None = None) -> None:
        nonlocal scene, n
        kw = {} if target is None else {"target": target * PX}
        scene = ops.sculpt_terrain(scene, tool, x * PX, y * PX, radius * PX, strength, **kw)
        n += 1

    if "hill" in stages:  # a gentle hill: raised in a few strokes, smoothed
        x, y, r, h = HILL
        for _ in range(6):
            stroke("raise", x, y, r, h * PX / 6)
        stroke("smooth", x, y, r, 0.5)
    if "terrace" in stages:  # a terrace flattened up to its height (its edges steep), and a ramp up to it
        x0, x1, y0, y1, h = TERRACE
        for yy in [y0 + 0.5 + 0.5 * k for k in range(int((y1 - y0) / 0.5))]:
            for xx in [x0 + 0.5 + 0.5 * k for k in range(int((x1 - x0) / 0.5))]:
                stroke("flatten", xx, yy, 0.75, 1.0, target=h)
        (ax, ay), (bx, by) = RAMP
        for k in range(17):
            f = k / 16
            for off in (-1.0, -0.5, 0.0, 0.5, 1.0):
                stroke("flatten", ax + (bx - ax) * f, ay + (by - ay) * f + off, 0.9, 1.0, target=h * f)
    if "valley" in stages:  # a shallow valley, flattened down along its line (overlapping strokes don't dig deeper)
        (vx0, vy0), (vx1, vy1), half, depth = VALLEY
        length = math.hypot(vx1 - vx0, vy1 - vy0)
        for k in range(int(length / 0.5) + 1):
            f = k * 0.5 / length
            stroke("flatten", vx0 + (vx1 - vx0) * f, vy0 + (vy1 - vy0) * f, half, 0.6, target=-depth)
        stroke("smooth", (vx0 + vx1) / 2, (vy0 + vy1) / 2, length / 2, 0.3)
    if "basin" in stages:  # a pond's basin: lowered, flattened at its floor, smoothed
        x, y, r, d = BASIN
        for _ in range(4):
            stroke("lower", x, y, r, d * PX / 4)
        stroke("flatten", x, y, r * 0.6, 1.0, target=-d)
        stroke("smooth", x, y, r * 1.1, 0.6)
    return scene, n


def base_scene(project: Path, with_elder_up: bool = True) -> dict[str, Any]:
    """The Hills room before any sculpting: flat ground, the structures, the player and the Elder."""
    start = json.loads((project / SCENES / "start.json").read_text(encoding="utf-8"))
    models = {Path(s["model"]).stem: s["model"] for s in start["settings"]["hd2d"]["structures"]}
    hd2d = {k: v for k, v in start["settings"]["hd2d"].items() if k not in ("structures", "ground", "camera")}
    w, h = SIZE_M[0] * PX, SIZE_M[1] * PX
    hd2d["ground"] = {"texture": start["settings"]["hd2d"]["ground"]["texture"], "from": [0, 0], "to": [w, h]}
    hd2d["camera"] = {**start["settings"]["hd2d"]["camera"], "bounds": [0.0, 0.0, w, h]}
    hd2d["structures"] = [{"id": sid, "model": models[model], "x": x * PX, "y": y * PX, "elevation": z * PX}
                          for sid, model, x, y, z in STRUCTURES]
    player = next(e for e in start["entities"] if e.get("prefab_id") == "player")
    elder = next(e for e in start["entities"] if e.get("name") == "Elder")
    scene: dict[str, Any] = {**{k: v for k, v in start.items() if k not in ("entities", "settings", "lights")},
                             "settings": {**{k: v for k, v in start["settings"].items() if k != "hd2d"},
                                          "world_width": w, "world_height": h, "hd2d": hd2d},
                             "entities": [{**player, "x": 8.0 * PX, "y": 4.0 * PX},
                                          {**elder, "x": HILL[0] * PX, "y": HILL[1] * PX + 16,
                                           "elevation": HILL[3] * PX if with_elder_up else 0.0}]}
    scene["settings"].pop("weather_exposure", None)
    return scene


def make_project(out: Path, name: str = "terrain", *, rain: bool = False, stages: tuple[str, ...] = STAGES,
                 pond: bool = True, shore: str = "terrain") -> Path:
    """A template project with the Hills room (``hills.json``, listed in its world)."""
    from engine import project_ops as ops

    project: Path = study.new_project(out, name, stage6a=False)
    scene, _n = strokes(base_scene(project, "hill" in stages), stages)
    if pond:
        scene, pid = ops.place_blank(scene, "hills", "Pond", BASIN[0] * PX, BASIN[1] * PX)
        scene = ops.set_water(scene, pid, preset="natural_pond", width=224, height=200, shore=shore)  # over the basin
        scene = ops.set_entity_fields(scene, pid, elevation=round(WATER_LEVEL * PX, 2))
    if rain:
        scene = ops.set_particles(scene, RAIN)
    (project / SCENES / "hills.json").write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    world_path = project / "packs" / "core_regions" / "worlds" / "main.json"
    world = json.loads(world_path.read_text(encoding="utf-8"))
    world["scenes"]["hills"] = {"label": "Hills", "path": f"{SCENES}/hills.json", "tags": []}
    world_path.write_text(json.dumps(world, indent=2) + "\n", encoding="utf-8")
    return project


def shot(game: HiddenGame, x: float, y: float, z: float = 0.0, *, distance: float | None = None,
         yaw: float | None = None) -> Any:
    """The game's camera (or a pulled-back or turned one) looking at (x, y, z) m."""
    from PIL import Image

    hd = game.window.hd2d_renderer
    cam = hd.camera
    kept = (cam.distance, getattr(cam, "yaw", 0.0))
    try:
        if distance is not None:
            cam.distance = distance
        if yaw is not None:
            cam.yaw = yaw
        cam.target = (x, y - 0.8, z + 0.8)
        hd._camera_ready = True
        return Image.frombytes("RGB", study.SIZE, hd.draw(read=True)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    finally:
        cam.distance = kept[0]
        if yaw is not None:
            cam.yaw = kept[1]


def open_room(out: Path, name: str = "terrain", size: tuple[int, int] = study.SIZE, **kw: Any) -> HiddenGame:
    game = HiddenGame(make_project(out, name, **kw), size=size)
    game.load(f"{SCENES}/hills.json")
    game.step(30)
    return game


def _mask(a: Any, b: Any) -> Any:
    import numpy as np

    return np.any(np.asarray(a) != np.asarray(b), axis=2)


def pair(images: list[Any], labels: list[str], path: Path, crop: tuple[int, int] | None = (640, 360)) -> None:
    import m18_particles_study as m18

    if crop:
        images = [m18.crop_at(i, study.SIZE[0] / 2, study.SIZE[1] / 2, crop) for i in images]
    m18.pair(images, labels).save(path)


def look(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for rain in (False, True):
        game = open_room(out, f"look_{rain}", rain=rain)
        try:
            tag = "rain" if rain else "dry"
            shot(game, 16.0, 12.0, distance=90.0).save(out / f"overview_{tag}.png")
            for name, (x, y) in {"hill": (5.0, 17.0), "terrace": (24.0, 18.5), "bridge": (15.0, 13.0),
                                 "pond": (26.0, 6.5)}.items():
                shot(game, x, y).save(out / f"{name}_{tag}.png")
        finally:
            game.close()


# --- B. sculpting, step by step ------------------------------------------------------------------------------------

def sculpting(out: Path) -> dict[str, Any]:
    """The same room flat, then with each part sculpted in turn (the operation's strokes), from above."""
    from PIL import Image

    report: dict[str, Any] = {}
    frames = []
    for k in range(len(STAGES) + 1):
        stages = STAGES[:k]
        game = open_room(out, f"stage_{k}", stages=stages, pond=k == len(STAGES))
        try:
            picture = shot(game, 16.0, 12.0, distance=90.0)
            picture.save(out / f"sculpt_{k}_{'_'.join(stages) or 'flat'}.png")
            frames.append(picture)
            hd = game.window.hd2d_renderer
            report[" + ".join(stages) or "flat"] = {"sculpted_ground": hd.terrain is not None,
                                                     "terrain_draws": hd.stats()["terrain_draws"]}
        finally:
            game.close()
    sheet = Image.new("RGB", (640 * 3, 360 * 2), (20, 22, 28))
    for i, f in enumerate(frames[:6]):
        sheet.paste(f.resize((640, 360), Image.Resampling.LANCZOS), ((i % 3) * 640, (i // 3) * 360))
    sheet.save(out / "sculpt_steps.png")
    project = study.new_project(out, "strokes", stage6a=False)
    t = time.perf_counter()
    scene, n = strokes(base_scene(project))
    report["strokes"] = n
    report["strokes_ms_each"] = round((time.perf_counter() - t) * 1000 / n, 2)
    terrain = scene["settings"]["hd2d"]["ground"]["terrain"]
    report["stored"] = {"cell_px": terrain["cell"], "chunks": len(terrain["chunks"]),
                        "chars": sum(len(v) for v in terrain["chunks"].values())}
    again, _n = strokes(base_scene(project))
    report["the_same_strokes_store_the_same_text"] = (json.dumps(again["settings"]["hd2d"]["ground"]["terrain"])
                                                      == json.dumps(terrain))
    return report


# --- B. walking ------------------------------------------------------------------------------------------------------

def _put(game: HiddenGame, x: float, y: float) -> Any:
    """The player's feet at (x, y) m, standing on the ground there."""
    player = game.player()
    hd = game.window.hd2d_renderer
    player.center_x = x * PX
    player.center_y += y * PX - player.bottom
    player.mesh_entity_data["elevation"] = hd.terrain.height(x * PX, y * PX) if hd.terrain else 0.0
    game.step(3)
    return player


def walking(out: Path) -> dict[str, Any]:
    """The player walks with the game's own key events: over the hill, up the ramp, into the terrace's cliff, along
    the valley under the bridge, up the stairs and across the bridge, into the pond's basin."""
    import m18_particles_study as m18
    from hd2d_floors_demo import _feet, hold_key

    from engine.hd2d.world import elevation_of

    report: dict[str, Any] = {}
    game = open_room(out, "walk")
    try:
        keys = game.arcade.key
        hd = game.window.hd2d_renderer

        def walk(name: str, start: tuple[float, float], legs: list[tuple[int, int, float]],
                 film: bool = False) -> dict[str, Any]:
            player = _put(game, *start)
            trace: list[tuple[float, float, float]] = []
            clip: list[Any] = []

            def each() -> None:
                fx, fy = _feet(player)
                trace.append((round(fx, 3), round(fy, 3), round(elevation_of(player), 3)))
                if film and len(trace) % 2 == 0 and len(clip) < 120:
                    picture = game.draw().convert("RGB")
                    clip.append(m18.crop_at(picture, study.SIZE[0] / 2, study.SIZE[1] / 2, (640, 360)))

            reached = [hold_key(game, player, key, axis, target, 900, each_frame=each) for key, axis, target in legs]
            fx, fy = _feet(player)
            under = hd.terrain.height(fx * PX, fy * PX)
            row = {"reached": reached, "end_feet_m": [round(fx, 2), round(fy, 2)],
                   "end_elevation_m": round(elevation_of(player), 3),
                   "ground_there_m": round(under / PX, 3) if under is not None else None,
                   "lowest_m": min(t[2] for t in trace) if trace else None,
                   "highest_m": max(t[2] for t in trace) if trace else None,
                   "floor": getattr(player, "mesh_hd2d_floor", None)}
            if clip:
                clip[0].save(out / f"walk_{name}.webp", save_all=True, append_images=clip[1:], duration=66, loop=0,
                             quality=85, method=6)
                row["clip_frames"] = len(clip)
            (out / f"walk_{name}.json").write_text(json.dumps(trace) + "\n", encoding="utf-8")
            return row

        report["over_the_hill"] = walk("hill", (HILL[0], 13.0), [(keys.UP, 1, 23.0)], film=True)
        report["up_the_ramp"] = walk("ramp", (19.5, 19.0), [(keys.RIGHT, 0, 28.0)], film=True)
        report["into_the_cliff"] = walk("cliff", (28.0, 12.0), [(keys.UP, 1, 19.0)])
        report["along_the_valley_under_the_bridge"] = walk("valley", (15.0, 6.0), [(keys.UP, 1, 21.0)], film=True)
        report["stairs_and_bridge"] = walk("bridge", (11.0, 6.5), [(keys.UP, 1, 15.0), (keys.RIGHT, 0, 19.0)],
                                           film=True)
        report["into_the_pond"] = walk("pond", (21.5, 6.0), [(keys.RIGHT, 0, 26.0)], film=True)
    finally:
        game.close()
    return report


# --- B. anchoring: sculpting never moves what stands on the ground --------------------------------------------------

def anchoring(out: Path) -> dict[str, Any]:
    from engine import project_ops as ops

    project = make_project(out, "anchor")
    path = project / SCENES / "hills.json"
    scene = json.loads(path.read_text(encoding="utf-8"))

    def where() -> dict[str, Any]:
        return {"cottage": dict(next(s for s in ops.structures(scene) if s["id"] == "cottage")),
                "Elder": {k: v for k, v in next(e for e in scene["entities"] if e.get("name") == "Elder").items()
                          if k in ("x", "y", "elevation")}}

    before, original = where(), json.loads(json.dumps(scene))
    report: dict[str, Any] = {"out_of_place_before": ops.terrain_anchoring(scene)}
    scene = ops.sculpt_terrain(scene, "raise", 5.0 * PX, 6.0 * PX, 3.0 * PX, 0.6 * PX)  # under the cottage
    for _ in range(4):  # the hill under the Elder, flattened away
        scene = ops.sculpt_terrain(scene, "flatten", HILL[0] * PX, HILL[1] * PX, 5.0 * PX, 1.0, target=0.0)
    report["moved"] = {k: before[k] != v for k, v in where().items()}
    report["out_of_place_after"] = ops.terrain_anchoring(scene)
    report["left_out_of_place_by_the_edits"] = ops.terrain_anchoring(scene, original)
    report["settle_would_stand"] = ops.anchoring_ids(scene, original)
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    game = HiddenGame(project, size=study.SIZE)
    try:  # in the game the Elder keeps his 1.5 m, nothing under him: until moved down he can't step anywhere
        game.load(f"{SCENES}/hills.json")
        game.step(10)
        from engine.hd2d.world import NAV_HALF

        world = game.window.hd2d_world
        report["elder_can_stand_where_he_is"] = world.stand(HILL[0], HILL[1], HILL[3], *NAV_HALF) is not None
        shot(game, 5.0, 12.0, distance=70.0).save(out / "anchoring.png")
    finally:
        game.close()
    return report


# --- C. water in the basin -------------------------------------------------------------------------------------------

def _water_body(game: HiddenGame) -> Any:
    return next(b for b in game.window.water_bodies if str(getattr(b.entity, "mesh_name", "")) == "Pond")


def water(out: Path) -> dict[str, Any]:
    report: dict[str, Any] = {}
    x, y = BASIN[0], BASIN[1] + 0.5
    game = open_room(out, "water", rain=True)
    try:
        hd = game.window.hd2d_renderer
        body = _water_body(game)
        bodies = game.window.water_bodies
        game.window.water_time = hd.particles.time = 3.0

        def without() -> Any:
            game.window.water_bodies = []
            try:
                return shot(game, x, y)
            finally:
                game.window.water_bodies = bodies

        dry = without()
        levels, pictures = {}, []
        for level in (-0.9, -0.6, -0.3):  # the water's own level is its object's elevation: the shore moves with it
            body.entity.mesh_entity_data["elevation"] = level * PX
            wet = shot(game, x, y)
            pictures.append(wet)
            levels[str(level)] = int(_mask(wet, dry).sum())
        body.entity.mesh_entity_data["elevation"] = WATER_LEVEL * PX
        report["water_pixels_by_level_m"] = levels
        pair(pictures, ["water at -0.9 m", "-0.6 m (as placed)", "-0.3 m"], out / "water_levels.png")
        wet = shot(game, x, y)  # submerged ground never hides it: with its depth test off, no more water is drawn
        hd.water.depth_test = False
        seen = shot(game, x, y)
        hd.water.depth_test = True
        report["drawn"] = int(_mask(wet, dry).sum())
        report["drawn_with_its_depth_test_off"] = int(_mask(seen, dry).sum())
        kept = body.water  # the procedural bank, optional: the same pond with its grass bank (its outline its shore)
        body.water = replace(kept, shore="grass", shore_width=14.0, width=160.0, height=112.0)
        banked = shot(game, x, y)
        body.water = kept
        pair([wet, banked], ["shore: the sculpted ground", "shore: Stage 19B's grass bank (its own outline)"],
             out / "water_shores.png")
        body.water = replace(kept, rain_ripples=False)  # rain rings it
        calm = shot(game, x, y)
        body.water = kept
        report["rain_ring_pixels"] = int(_mask(wet, calm).sum())
        player = _put(game, 25.0, 5.6)  # the player wades in, partly under its surface
        game.step(2)
        wading = shot(game, 25.0, 6.0)
        game.window.water_bodies = []
        no_water = shot(game, 25.0, 6.0)
        game.window.water_bodies = bodies
        cx, cy = study.SIZE[0] // 2, study.SIZE[1] // 2
        box = (cx - 40, cy - 90, cx + 40, cy + 50)
        report["player_feet_m"] = round(player.mesh_entity_data["elevation"] / PX, 3)
        report["pixels_round_the_player_changed_by_water"] = int(_mask(wading.crop(box), no_water.crop(box)).sum())
        pair([no_water, wading], ["the player in the basin, no water", "with the water: wading"], out / "water_wading.png")
    finally:
        game.close()
    game = open_room(out, "water_refl", rain=False)
    try:  # reflections: the Elder on the far shore, the mirror at 0 and 0.8
        hd = game.window.hd2d_renderer
        elder = next(s for s in game.window.scene_controller.all_sprites if getattr(s, "mesh_name", "") == "Elder")
        elder.center_x = BASIN[0] * PX
        elder.center_y += (BASIN[1] + 2.9) * PX - elder.bottom
        elder.mesh_entity_data["elevation"] = hd.terrain.height(BASIN[0] * PX, (BASIN[1] + 2.9) * PX)
        body = _water_body(game)
        kept = body.water
        shots = []
        for value in (0.0, 0.8):
            body.water = replace(kept, reflection=value)
            shots.append(shot(game, x, y))
        body.water = kept
        report["mirrored_pixels_at_0_8"] = int(_mask(shots[0], shots[1]).sum())
        pair(shots, ["reflection 0", "reflection 0.8: the Elder on the far shore"], out / "water_reflection.png")
    finally:
        game.close()
    return report


# --- D. sun, rain, picking ------------------------------------------------------------------------------------------

def environment(out: Path) -> dict[str, Any]:
    import numpy as np

    report: dict[str, Any] = {}
    project = make_project(out, "env_low_sun", rain=True)  # a low evening sun from the east: long shadows
    path = project / SCENES / "hills.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    scene["settings"]["hd2d"]["sun"]["direction"] = [0.9, 0.15, 0.32]
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    game = HiddenGame(project, size=study.SIZE)
    game.load(f"{SCENES}/hills.json")
    game.step(30)
    try:
        hd, world = game.window.hd2d_renderer, game.window.hd2d_world
        terrain = hd.terrain
        light = hd.lighting  # shadows: the ground's hills cast them (with, against without it among the casters)
        original = light.render_shadows
        ground = {id(d[0]) for d in hd._terrain_casters()}  # (the ground's one caster geometry, Milestone 20B)
        with_shadow = shot(game, 5.0, 18.0)

        def without(statics: Any, *a: Any, **k: Any) -> Any:
            return original([d for d in statics if id(d[0]) not in ground], *a, **k)

        light.render_shadows = without
        try:
            no_cast = shot(game, 5.0, 18.0)
        finally:
            light.render_shadows = original
        darker = (np.asarray(with_shadow, dtype=np.int16).sum(axis=2) + 30 < np.asarray(no_cast, dtype=np.int16).sum(axis=2))
        report["pixels_darkened_by_the_ground_s_own_shadows"] = int(darker.sum())
        pair([no_cast, with_shadow], ["low sun, the ground casting no shadow", "the hill casting its shadow"], out / "shadows.png")
        # rain stops on the ground's real surface: the precipitation map's surface against the terrain's height
        maps = hd.precipitation_maps()
        m = next(mm for mm in maps if mm is not None)
        import ctypes

        from pyglet import gl as raw  # (arcade reads no depth textures: the map's framebuffer, read directly)

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

        rows = []
        for name, (px, py) in {"hill top": (HILL[0], HILL[1]), "terrace": (28.0, 19.0), "ramp": (22.5, 19.0),
                               "valley": (15.0, 6.0), "basin floor": (BASIN[0], BASIN[1]),
                               "under the bridge's deck": (15.0, 15.0), "flat ground": (12.0, 3.0)}.items():
            u, v, d0 = clip((px, py, 0.0))
            d1 = clip((px, py, 1.0))[2]
            stored = float(depth[int((v * 0.5 + 0.5) * m.depth.height), int((u * 0.5 + 0.5) * m.depth.width)])
            z = (stored - (d0 * 0.5 + 0.5)) / ((d1 - d0) * 0.5)  # depth is linear in z (orthographic, falling straight)
            rows.append({"where": name, "rain_stops_at_m": round(z, 3),
                         "ground_m": round(terrain.height(px * PX, py * PX) / PX, 3)})
        report["rain_surface"] = rows
        errors = []  # picking: a click's ray meets the sculpted ground where it is
        cam = hd.camera
        cam.target = (16.0, 11.2, 0.8)
        for sx in (-0.6, -0.2, 0.2, 0.6):
            for sy in (-0.5, 0.0, 0.5):
                origin, direction = cam.ray(sx, sy, study.SIZE[0] / study.SIZE[1])
                hit = terrain.ray(origin, direction)
                if hit is not None:
                    errors.append(abs(hit[2] - terrain.height(hit[0] * PX, hit[1] * PX) / PX))
                walk = world.walkable_hit(origin, direction)
                if walk is not None and walk[1] == "ground":
                    errors.append(abs(walk[0][2] - terrain.height(walk[0][0] * PX, walk[0][1] * PX) / PX))
        report["picking_height_error_m_max"] = round(max(errors), 4) if errors else None
        report["picking_rays"] = len(errors)
    finally:
        game.close()
    return report


# --- E. Studio: the sculpt tool prototype -------------------------------------------------------------------------

def studio(out: Path) -> dict[str, Any]:
    import os

    import hd2d_studio_demo

    from engine import project_ops as ops
    from engine.hd2d.terrain import Terrain

    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    project = make_project(out, "studio", stages=("hill",), pond=False)
    report: dict[str, Any] = {}

    def heights(s: Any) -> str:
        return json.dumps(((s.project.scene().get("settings") or {}).get("hd2d") or {}).get("ground", {}).get("terrain"),
                          sort_keys=True)

    d = hd2d_studio_demo.StudioDriver(project)
    try:
        s, k = d.studio, d.arcade.key
        d.button("Hills")
        d.frame(3)
        before = heights(s)
        d.button("Sculpt ground")
        spot = (20.0, 6.0, 0.0)
        at = d.screen(spot)
        d.window.dispatch_event("on_mouse_motion", *at, 0, 0)
        d.frame(2)
        view = d.studio.hd2d
        report["cursor_on_the_ground_m"] = [round(v, 2) for v in view.sculpt_at] if view.sculpt_at else None
        d.picture(out / "studio_1_brush.png")
        for _ in range(4):  # (Stage 20B: held a moment each, as strength now goes by time; one undo step each)
            d.drag(at, at, steps=30)
        raised = heights(s)
        raised_h = Terrain.from_ground(ops._parsed_ground(s.project.scene())).height(spot[0] * PX, spot[1] * PX)
        report["raised_m"] = round((raised_h or 0.0) / PX, 3)
        d.button("Flatten")
        d.key(d.arcade.key.BRACKETRIGHT)  # (a bigger brush: the ] key, Stage 20B)
        d.drag(d.screen((18.0, 6.0, 0.0)), d.screen((18.0, 6.0, 0.0)), steps=10)
        d.frame(2)
        d.picture(out / "studio_2_sculpted.png")
        report["sculpt_click_ms"] = [round(v, 1) for v in view.timings["sculpt_ms"]]
        for _ in range(5):
            d.key(k.Z, k.MOD_CTRL)
        report["undone_to_before"] = heights(s) == before
        for _ in range(4):
            d.key(k.Y, k.MOD_CTRL)
        report["redone_to_raised"] = heights(s) == raised
        d.key(k.S, k.MOD_CTRL)
        report["saved_dirty_after"] = s.project.is_dirty
        expected = heights(s)
    finally:
        d.close()
    d = hd2d_studio_demo.StudioDriver(project)
    try:
        d.button("Hills")
        d.frame(3)
        report["reopened_same"] = heights(d.studio) == expected
        d.key(d.arcade.key.F4)
        d.frame(20)
        report["play"] = {"mode": d.studio.mode, "sculpted_ground": d.renderer.terrain is not None if d.renderer else None}
        d.key(d.arcade.key.F4)
        d.frame(3)
        report["after_stop"] = d.studio.mode
    finally:
        d.close()
    return report


def proof(out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    for name, step in (("sculpting", sculpting), ("walking", walking), ("anchoring", anchoring), ("water", water),
                       ("environment", environment), ("studio", studio)):
        report[name] = step(out)
        print(name, json.dumps(report[name]), flush=True)
    (out / "proof.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


# --- performance ------------------------------------------------------------------------------------------------------

def _timed(fn: Callable[[], Any], n: int = 5) -> float:
    times = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t) * 1000)
    return round(statistics.median(times), 3)


def perf(out: Path) -> dict[str, Any]:
    import random

    import m19_water_study as m19

    from engine import project_ops as ops
    from engine.hd2d.terrain import CHUNK, Terrain
    from engine.hd2d.world import NAV_HALF, World

    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    game = open_room(out, "perf")
    try:
        hd, world, ctx = game.window.hd2d_renderer, game.window.hd2d_world, game.window.ctx
        terrain = hd.terrain
        report["gpu"] = {"renderer": ctx.info.RENDERER}
        cx_n, cy_n = terrain.chunk_count()
        chunks = [(i, j) for j in range(cy_n) for i in range(cx_n)]
        meshes = [terrain.chunk_mesh(*c) for c in chunks]
        report["terrain"] = {"cells": terrain.nx * terrain.ny, "cell_m": terrain.cell / PX, "chunks": len(chunks),
                             "chunk_cells": CHUNK, "triangles_drawn": sum(len(part) for mesh in meshes for part in mesh) // 24,
                             "collision_surfaces_stored_for_the_ground": sum(1 for s in world.surfaces if s.floor == "ground"),
                             "gpu_bytes": hd.stats()["terrain_bytes"], "cpu_heights": len(terrain.heights),
                             "stored_chars": sum(len(v) for v in terrain.chunks().values())}
        scene = json.loads((out / "perf" / SCENES / "hills.json").read_text(encoding="utf-8"))
        report["sculpt_op_ms"] = _timed(lambda: ops.sculpt_terrain(scene, "raise", 16 * PX, 6 * PX, 2 * PX, 8.0))
        dirty = terrain.sculpt("raise", 16 * PX, 6 * PX, 2 * PX, 8.0)
        report["stroke_dirty_chunks"] = len(dirty)
        report["rebuild_dirty_chunks_ms"] = {"draw": _timed(lambda: hd.update_terrain(terrain, dirty)),
                                             "collision": _timed(lambda: world.update_terrain(terrain, dirty))}
        report["rebuild_every_chunk_ms"] = {"draw": _timed(lambda: hd.update_terrain(terrain, chunks), 3),
                                            "collision": _timed(lambda: world.update_terrain(terrain, chunks), 3),
                                            "collision_world_from_scratch": _timed(lambda: World(hd.settings, hd.models), 3)}
        report["one_chunk_mesh_ms"] = _timed(lambda: terrain.chunk_mesh(1, 0), 10)

        def nav() -> None:
            world._nav = None
            world.walkable()

        report["nav_grid_build_ms"] = _timed(nav, 3)
        rng = random.Random(4)  # collision queries: standing on sculpted ground against the plain flat ground
        pts = [(rng.uniform(1, 31), rng.uniform(1, 23)) for _ in range(2000)]
        zs = [terrain.height(x * PX, y * PX) / PX for x, y in pts]
        t = time.perf_counter()
        for (x, y), z in zip(pts, zs):
            world.stand(x, y, z, *NAV_HALF)
        sculpted_us = (time.perf_counter() - t) / len(pts) * 1e6
        flat_world = World(replace(hd.settings, ground=replace(hd.settings.ground, terrain=None)), hd.models)
        t = time.perf_counter()
        for x, y in pts:
            flat_world.stand(x, y, 0.0, *NAV_HALF)
        flat_us = (time.perf_counter() - t) / len(pts) * 1e6
        report["stand_query_us"] = {"sculpted": round(sculpted_us, 2), "flat_ground": round(flat_us, 2)}
        report["height_query_us"] = round(_timed(lambda: [terrain.height(x * PX, y * PX) for x, y in pts], 3)
                                          / len(pts) * 1000, 3)
        flat = Terrain(terrain.origin, terrain.size, terrain.base, terrain.cell)  # drawing: sculpted against flat
        player = game.player()
        player.center_x, player.center_y = 16 * PX, player.center_y + 8 * PX - player.bottom
        for _ in range(200):
            game.window.dispatch_event("on_update", 1 / 60)
            game.window.dispatch_event("on_draw")
        rounds: dict[str, list[float]] = {"sculpted": [], "flat": []}
        for _ in range(5):
            for name, tt in (("sculpted", terrain), ("flat", flat)):
                hd.update_terrain(tt, chunks)
                for _ in range(10):
                    game.window.dispatch_event("on_update", 1 / 60)
                    game.window.dispatch_event("on_draw")
                rounds[name].append(m19._frame_gpu_ms(game, 20))
        hd.update_terrain(terrain, chunks)
        report["frame_gpu_ms"] = {k: round(statistics.median(v), 3) for k, v in rounds.items()}
        report["frame_gpu_ms_rounds"] = {k: [round(v, 3) for v in vs] for k, vs in rounds.items()}
        game.window.dispatch_event("on_draw")
        report["draw_calls"] = hd.stats()["draw_calls"]
        ctx.gc()  # GPU objects over in-place rebuilds and room changes
        counts = [_gl_counts(ctx)]
        for _ in range(5):
            hd.update_terrain(terrain, chunks)
            game.window.dispatch_event("on_draw")
        ctx.gc()
        counts.append(_gl_counts(ctx))
        for _ in range(5):
            game.load(f"{SCENES}/start.json")
            game.step(2)
            game.window.dispatch_event("on_draw")
            game.load(f"{SCENES}/hills.json")
            game.step(2)
            game.window.dispatch_event("on_draw")
        ctx.gc()
        counts.append(_gl_counts(ctx))
        report["gl_objects"] = {"start": counts[0], "after_5_rebuilds_of_every_chunk": counts[1],
                                "after_5_room_changes": counts[2]}
        t = time.perf_counter()
        game.load(f"{SCENES}/hills.json")
        report["room_load_ms"] = round((time.perf_counter() - t) * 1000, 1)
    finally:
        game.close()
    (out / "perf.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    steps: dict[str, Callable[[Path], Any]] = {"look": look, "proof": proof, "perf": perf, "sculpting": sculpting,
                                               "walking": walking, "anchoring": anchoring, "water": water,
                                               "environment": environment, "studio": studio}
    parser.add_argument("command", choices=list(steps))
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    result = steps[args.command](args.out)
    if result is not None and args.command != "proof":
        print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
