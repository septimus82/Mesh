"""Milestone 20E evidence: environmental animation (hidden windows only; Studio through its own events).

    py -3.13 tooling/m20e_motion_study.py identity OUT   # animation off draws exactly what 20D drew (run here and in
                                                         # a checkout of the base: the same pictures)
    py -3.13 tooling/m20e_motion_study.py smoke OUT      # quick: the decorated room moving, anchors fixed

The room is Stage 20D's decorated Hills room (tooling/m20d_scatter_study.py), its wind and motion set and its new
decoration placed only through ``project_ops`` (as Studio and AI do).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
import hd2d_visual_study as study  # noqa: E402
import m20a_terrain_study as m20a  # noqa: E402
import m20d_scatter_study as m20d  # noqa: E402
from hd2d_demo import SCENES, HiddenGame  # noqa: E402

PX = 32.0
BLENDER = Path("D:/program/blender.exe")  # (headless only)
# where the new decoration goes (m): torches either side of the cottage's path, a banner by the bridge, small trees
# on the meadow and the hill, glowcaps and bellflowers under them, a dripping rock at the cliff's foot
DECOR = [("Torch", (3.5, 3.7)), ("Torch", (7.4, 2.3)), ("Banner", (13.4, 10.6)), ("Small tree", (9.5, 9.5)),
         ("Small tree", (3.2, 16.5)), ("Small tree", (19.5, 9.8)), ("Glowcaps", (11.3, 10.3)), ("Glowcaps", (5.0, 15.7)),
         ("Glowcaps", (17.7, 10.4)), ("Bellflowers", (10.6, 7.6)), ("Bellflowers", (18.6, 8.8)),
         ("Dripping rock", (21.8, 14.4))]


def decorate(scene: dict[str, Any]) -> dict[str, Any]:
    """The 20E decoration, one asset a dab, through the checked operation."""
    from engine import project_ops as ops

    for k, (name, (x, y)) in enumerate(DECOR):  # (one thing a dab: a density that asks for one in its circle)
        radius, density = {"Glowcaps": (20.0, 1.6), "Bellflowers": (36.0, 1.6)}.get(name, (10.0, 4.0))
        scene = ops.scatter_stroke(scene, name, [[x * PX, y * PX]], radius=radius, density=density, seed=700 + k)
    return scene


def make_project(out: Path, name: str, *, rain: bool = False, decor: bool = False, wind: dict | None = None,
                 motion: dict | None = None) -> Path:
    """The 20D room (``decor``: 20E's decoration placed first, 20D's strokes then laid round it, as a creator
    would), ``wind`` and ``motion`` (set_wind / set_motion's arguments) if given."""
    from engine import project_ops as ops
    from engine.paths import get_content_roots, set_content_roots

    project: Path = m20d.make_project(out, name, rain=rain, decorated=False)
    path = project / SCENES / "hills.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    roots = list(get_content_roots())
    # The ops read the room's models from its project, as in Studio; a process that hasn't opened the project finds
    # none and scatters as if every building were 2 m square (so the same room came out differently by order).
    set_content_roots([project])
    try:
        scene, _n = m20d.compose(decorate(scene) if decor else scene)
    finally:
        set_content_roots(roots)
    if wind or motion:
        if wind:
            scene = ops.set_wind(scene, **wind)
        if motion:
            scene = ops.set_motion(scene, **motion)
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    return project


def open_room(out: Path, name: str, size: tuple[int, int] = study.SIZE, **kw: Any) -> HiddenGame:
    game = HiddenGame(make_project(out, name, **kw), size=size)
    game.load(f"{SCENES}/hills.json")
    game.step(30)
    return game


def at(game: HiddenGame, t: float, x: float, y: float, **kw: Any) -> Any:
    """The picture at motion time ``t`` s."""
    game.window.motion_time = t
    return m20a.shot(game, x, y, **kw)


def identity(out: Path) -> dict[str, Any]:
    """The decorated room with no motion settings, and with motion set but off, from 20D's cameras (runs on the
    base too, where it has no motion: the three sets must match pixel for pixel)."""
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    cases: list[tuple[str, dict | None]] = [("none", None)]
    if (REPO / "engine" / "hd2d" / "motion.py").exists():
        cases.append(("off", {"enabled": False, "sway": 1.5, "wind": 1.2, "speed": 2.0}))
    for case, motion in cases:
        for rain in (False, True):
            tag = f"{case}_{'rain' if rain else 'dry'}"
            game = open_room(out, f"id_{tag}", rain=rain,
                             wind={"speed": 6.0, "direction": 20.0, "gust": 0.6} if motion else None, motion=motion)
            try:
                game.window.motion_time = 37.0
                for view, (x, y) in [("overview", (16.0, 12.0)), *m20d.VIEWS.items()]:
                    m20a.shot(game, x, y, distance=90.0 if view == "overview" else None).save(out / f"{view}_{tag}.png")
                report[tag] = sorted(p.name for p in out.glob(f"*_{tag}.png"))
            finally:
                game.close()
    return report


def smoke(out: Path) -> dict[str, Any]:
    import numpy as np

    out.mkdir(parents=True, exist_ok=True)
    game = open_room(out, "smoke", decor=True, wind={"speed": 6.0, "direction": 10.0, "gust": 0.6},
                     motion={"enabled": True})
    try:
        frames = [np.asarray(at(game, t, 9.0, 7.0)) for t in (10.0, 10.5, 11.0)]
        for t, f in zip((10.0, 10.5, 11.0), frames):
            from PIL import Image

            Image.fromarray(f).save(out / f"smoke_{t:.1f}.png")
        stats = game.window.hd2d_renderer.stats()
        return {"changed_px": int(np.any(frames[0] != frames[1], axis=2).sum()),
                "draw_calls": stats["draw_calls"], "instances": stats["scatter_instances"]}
    finally:
        game.close()


# ---------------------------------------------------------------------- clips
CROP = (480, 270)  # (a clip's frame: the middle of the picture, full size: pixels never scaled)


def _crop(img: Any, cx: int = 640, cy: int = 380, size: tuple[int, int] = CROP) -> Any:
    w, h = size
    return img.crop((cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2))


def _game_frame(game: HiddenGame) -> Any:
    from PIL import Image

    hd = game.window.hd2d_renderer
    return Image.frombytes("RGB", study.SIZE, hd.draw(read=True)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)


def _save_clip(frames: list[Any], path: Path, fps: float = 10) -> None:
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=round(1000 / fps), loop=0, quality=65,
                   method=6)


def _film_still_camera(game: HiddenGame, x: float, y: float, seconds: float, fps: int = 10,
                       start: float = 20.0) -> list[Any]:
    """The motion clock stepped at ``fps`` (as the game's frames would advance it), one picture a step."""
    return [_crop(at(game, start + k / fps, x, y)) for k in range(int(seconds * fps))]


WINDS = {  # the five demonstrations: set_wind's arguments (m/s, toward degrees, gust)
    "calm": {"speed": 0.0},
    "breeze": {"speed": 3.0, "direction": 15.0, "gust": 0.3},
    "strong": {"speed": 11.0, "direction": 15.0, "gust": 0.15},
    "gusts": {"speed": 5.0, "direction": 15.0, "gust": 0.95},
    "rain_wind": {"speed": 8.0, "direction": 195.0, "gust": 0.5},
}
WIND_VIEW = (11.5, 8.6)  # the meadow below the bridge: grass, flowers, a tree, the banner


def winds(out: Path) -> dict[str, Any]:
    """Each wind for four seconds at one camera (clips), and how far the grass and the tree's canopy lean on average and
    at most in it (the shader's twin over the same seconds)."""
    from engine.hd2d import motion as m
    from engine.hd2d.scatter import ASSETS
    from engine.wind import parse_wind

    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    on = m.Motion(enabled=True)
    for name, wind in WINDS.items():
        game = open_room(out, f"wind_{name}", decor=True, rain=name == "rain_wind", wind=wind if wind["speed"] else None,
                         motion={"enabled": True})
        try:
            frames = _film_still_camera(game, *WIND_VIEW, 4.0)
            _save_clip(frames, out / f"wind_{name}.webp")
            frames[0].save(out / f"wind_{name}_first.png")
            w = parse_wind(wind if wind["speed"] else None)
            row: dict[str, Any] = {}
            for label, flex in (("grass", ASSETS["grass_tall"].flex), ("reeds", ASSETS["reeds"].flex),
                                ("bush", ASSETS["bush"].flex), ("tree_canopy", ASSETS["tree_small"].parts[0].flex)):
                angles = [m.angle(11.0, 8.0, 20 + k / 30, flex, 0.37, w, on) for k in range(180)]
                row[label] = {"mean_deg": round(math.degrees(sum(angles) / len(angles)), 1),
                              "max_deg": round(math.degrees(max(map(abs, angles))), 1)}
            hd = game.window.hd2d_renderer
            effects = hd.particles.effects if hd.particles is not None else ()
            row["rain_wind"] = [list(e.wind) for e in effects]
            report[name] = row
        finally:
            game.close()
    return report


def gameplay(out: Path) -> dict[str, Any]:
    """Playing: the player walks the path past the torches, the meadow and the tree in a gusty wind, then in rain
    with wind; the game's own loop at 60 frames a second, every eighth filmed (7.5 a second)."""
    import time

    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    for name, rain in (("walk_gusty", False), ("walk_rain", True)):
        game = open_room(out, name, decor=True, rain=rain, wind=WINDS["gusts" if not rain else "rain_wind"],
                         motion={"enabled": True})
        try:
            key = game.arcade.key
            frames, times = [], []
            for direction, steps in ((key.RIGHT, 150), (key.UP, 60), (key.RIGHT, 90)):
                game.window.dispatch_event("on_key_press", direction, 0)
                for i in range(steps):
                    t = time.perf_counter()
                    game.window.dispatch_event("on_update", 1 / 60)
                    if i % 8 == 0:
                        frames.append(_crop(_game_frame(game), 640, 400, (640, 360)))
                    else:
                        game.window.dispatch_event("on_draw")
                    times.append((time.perf_counter() - t) * 1000)
                game.window.dispatch_event("on_key_release", direction, 0)
            _save_clip(frames, out / f"{name}.webp", 7.5)
            frames[len(frames) // 2].save(out / f"{name}_mid.png")
            report[name] = {"frames": len(frames), "motion_time_s": round(game.window.motion_time, 2),
                            "player_end_m": [round(game.player().center_x / PX, 2), round(game.player().bottom / PX, 2)]}
        finally:
            game.close()
    return report


# ---------------------------------------------------------------------- trees
def _variant_assets() -> None:
    """Two more ways to draw the small tree, for comparing (never in the kit): all camera-facing planes (a trunk
    sprite and the same canopy), and layered geometry (a trunk and lumps of leaves, all 3D, still). Registered before
    the scatter layer is first imported (the shader's tables are sized by them)."""
    import dataclasses

    from engine.hd2d import scatter

    tree = scatter.ASSETS["tree_small"]
    scatter.ASSETS["tree_planes"] = dataclasses.replace(tree, id="tree_planes", name="Tree (planes)", model=None,
                                                         cell=(36,), blocks=False, shadow=False)
    scatter.ASSETS["tree_layered"] = dataclasses.replace(tree, id="tree_layered", name="Tree (layered)",
                                                          model=f"{scatter.KIT}/tree_layered.glb", parts=())
    scatter.SLOTS.clear()
    scatter.SLOTS.update({(a.id, k): n for n, (a, k) in enumerate(
        (a, k) for a in scatter.ASSETS.values() for k, _p in a.sprite_parts())})


def trees(out: Path) -> dict[str, Any]:
    """The three side by side in open grass, from the gameplay camera turned 0, 45 and 90 degrees and tilted, in a
    breeze (clips of each), with their costs. The layered model is built by Blender (headless) into the project."""
    import subprocess

    import numpy as np

    if "engine.hd2d.scatter_layer" in sys.modules:
        raise SystemExit("trees: run it in its own process (the shader's tables are fixed on first import)")
    _variant_assets()
    out.mkdir(parents=True, exist_ok=True)
    built = out / "glb_study"
    if not (built / "tree_layered.glb").exists():
        subprocess.run([str(BLENDER), "--factory-startup", "-noaudio", "--background", "--python",
                        str(REPO / "tooling" / "hd2d_assets" / "build_scatter_models.py"), "--", str(built), "--study"],
                       check=True, capture_output=True)
    project = make_project(out, "trees", wind=WINDS["breeze"], motion={"enabled": True})
    (project / "assets" / "hd2d_starter" / "scatter").mkdir(parents=True, exist_ok=True)
    (project / "assets" / "hd2d_starter" / "scatter" / "tree_layered.glb").write_bytes(
        (built / "tree_layered.glb").read_bytes())
    path = project / SCENES / "hills.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    from engine import project_ops as ops

    row_y = 3.0  # (open grass south of the path, east of the cottage)
    spots = {"tree_planes": 13.0, "tree_layered": 16.5, "tree_small": 20.0}
    scatter = {k: v for k, v in scene["settings"]["hd2d"].get("scatter", {}).items()
               if k not in ("bush", "bush_berries")}
    for name, x in spots.items():
        scatter[name] = [[round(x * PX), round(row_y * PX), 0, 110]]
        for rows in scatter.values():  # (clear round them: nothing between the trees and the camera)
            rows[:] = [r for r in rows if not (abs(r[0] / PX - x) < 1.8 and -2.5 < r[1] / PX - row_y < 1.2)
                       or r == [round(x * PX), round(row_y * PX), 0, 110]]
    scene = ops.set_scatter(scene, scatter)
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    game = HiddenGame(project, size=study.SIZE)
    report: dict[str, Any] = {}
    try:
        game.load(f"{SCENES}/hills.json")
        game.step(30)
        hd = game.window.hd2d_renderer
        for label, yaw, pitch in (("front", 0.0, None), ("turned45", 45.0, None), ("turned90", 90.0, None),
                                  ("high", 0.0, 55.0)):
            kept = hd.camera.pitch
            if pitch is not None:
                hd.camera.pitch = pitch
            try:
                at(game, 30.0, 16.5, row_y + 1.0, yaw=yaw).save(out / f"trees_{label}.png")
                if label in ("front", "turned45"):
                    frames = [_crop(at(game, 30.0 + k / 10, 16.5, row_y + 1.0, yaw=yaw), 640, 330, (720, 300)) for k in range(40)]
                    _save_clip(frames, out / f"trees_{label}.webp")
            finally:
                hd.camera.pitch = kept
        # an orbit: the camera turning round them (what a creator sees turning the view)
        orbit = [_crop(at(game, 30.0 + k / 10, 16.5, row_y + 1.0, yaw=k * 4.5), 640, 330, (720, 300)) for k in range(40)]
        _save_clip(orbit, out / "trees_orbit.webp")
        layer = hd.scatter
        from engine.hd2d.scatter import ASSETS

        for name in spots:
            report[name] = {"sprite_quads": len(ASSETS[name].sprite_parts()), "casts": name != "tree_planes",
                            "blocks": any(w.name == f"scatter:{name}" for w in game.window.hd2d_world.walls)}
        report["frames_differ_front"] = bool(np.any(np.asarray(at(game, 30.0, 16.5, row_y + 1.0))
                                                    != np.asarray(at(game, 31.0, 16.5, row_y + 1.0))))
        report["scatter_bytes"] = layer.memory_bytes() if layer is not None else 0
    finally:
        game.close()
    return report


# ---------------------------------------------------------------------- Studio
def studio(out: Path) -> dict[str, Any]:
    """A creator in Mesh Studio, with its own window events: a breeze (preset button), animation on (it moves in the
    editing view: a live preview), sway and the wind's direction typed in, a bad number refused, one undo step each,
    undo and redo, save and the file read back, the change review's words, animation off (still again)."""
    import time

    import m20b_sculpt_study as m20b
    import m20c_material_study as m20c
    import numpy as np

    from engine import authoring

    out.mkdir(parents=True, exist_ok=True)
    project = make_project(out, "studio", decor=True)
    path = project / SCENES / "hills.json"
    before = json.loads(path.read_text(encoding="utf-8"))
    report: dict[str, Any] = {}
    d = m20b._driver(project)

    def canvas() -> Any:
        return np.asarray(d.frame().convert("RGB").crop((420, 140, 860, 520)))

    def settings() -> dict[str, Any]:
        room = d.studio.project.scene().get("settings") or {}
        return {"wind": room.get("wind"), "motion": (room.get("hd2d") or {}).get("motion")}

    try:
        s, k = d.studio, d.arcade.key
        m20c._look_at(d, *WIND_VIEW, 18.0)
        d.picture(out / "studio_panel_before.png")
        report["still_while_off"] = bool(np.array_equal(canvas(), (d.frame(20), canvas())[1]))
        undo0 = len(s.project._undo)
        t = time.perf_counter()
        d.button("Breeze")
        report["breeze"] = {"ms": round((time.perf_counter() - t) * 1000, 1), "message": s.message, **settings()}
        t = time.perf_counter()
        d.button("Animation: off")
        report["animation_on"] = {"ms": round((time.perf_counter() - t) * 1000, 1), "message": s.message,
                                  **settings()}
        m20c._look_at(d, *WIND_VIEW, 18.0)
        clock = d.window.motion_time
        a = canvas()
        clip = [d.frame(6).convert("RGB").crop((280, 120, 1000, 525)) for _ in range(30)]
        _save_clip(clip, out / "studio_live_preview.webp")
        report["live_preview"] = {"clock_advanced_s": round(d.window.motion_time - clock, 2),
                                  "canvas_changed": bool(np.any(a != canvas()))}
        d.type_into("motion_sway", "1.6")
        d.type_into("wind_direction", "200")
        typed = settings()
        report["typed"] = {"message": s.message, **typed}
        d.type_into("motion_speed", "fast")
        report["bad_number"] = {"message": s.message, "unchanged": settings() == typed}
        report["undo_steps_added"] = len(s.project._undo) - undo0
        d.key(k.Z, k.MOD_CTRL)
        report["undo"] = settings()
        d.key(k.Y, k.MOD_CTRL)
        report["redo"] = settings()
        d.picture(out / "studio_panel_on.png")
        d.key(k.S, k.MOD_CTRL)
        saved = json.loads(path.read_text(encoding="utf-8"))
        hd2d_saved = saved["settings"]["hd2d"]
        report["saved"] = {"wind": saved["settings"].get("wind"), "motion": hd2d_saved.get("motion"),
                           "scatter_unchanged": hd2d_saved["scatter"] == before["settings"]["hd2d"]["scatter"]}
        report["review"] = authoring.summarize({"rooms": {"hills": before}}, {"rooms": {"hills": saved}})
        d.button("Animation: on")
        m20c._look_at(d, *WIND_VIEW, 18.0)
        report["animation_off"] = {"message": s.message, **settings(),
                                   "still": bool(np.array_equal(canvas(), (d.frame(20), canvas())[1]))}
    finally:
        d.close()
    return report


# ---------------------------------------------------------------------- performance
MIX = {"grass_tuft": 36, "grass_tall": 14, "flowers_yellow": 7, "flowers_pink": 7, "bellflowers": 4, "glowcap": 3,
       "grass_dry": 5, "bush": 5, "bush_berries": 2, "reeds": 5, "reeds_cattail": 2, "torch": 1, "banner": 1,
       "dripping_rock": 1, "tree_small": 1, "rock_small": 5, "rock_medium": 1}


def _mixed(n: int, size_m: tuple[float, float]) -> dict[str, list[list[int]]]:
    """``n`` instances, a fixed mix (mostly grass and flowers that sway; some torches, banners, trees), fixed seed."""
    import random

    from engine.hd2d.scatter import stored

    names, weights = list(MIX), list(MIX.values())
    rng = random.Random(7)
    rows: dict[str, list[tuple[int, int, int, int]]] = {}
    for _ in range(n):
        name = rng.choices(names, weights)[0]
        rows.setdefault(name, []).append((round(rng.uniform(16, size_m[0] * PX - 16)),
                                          round(rng.uniform(16, size_m[1] * PX - 16)), rng.randrange(360),
                                          rng.randint(85, 115)))
    return stored(rows)


def scale(out: Path) -> dict[str, Any]:
    """100, 1,000 and 10,000 instances over a 64 x 64 m sculpted room (and 10,000 over 128 x 128 m), shadows on,
    at the gameplay camera, in a gusty wind: each room measured still (animation off) and moving, alternately, twice:
    the frame's CPU and GPU time, draw calls, shadow draws, GPU memory; and over 600 frames moving, whether any chunk
    was rebuilt or memory grew; GPU objects over reloads and after release. Run it alone (timings)."""
    import time

    import m19_water_study as m19
    import m20b_sculpt_study as m20b
    from hd2d_demo import _gl_counts

    from engine.hd2d.motion import Motion, parse_motion

    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    for side, n in ((64.0, 100), (64.0, 1000), (64.0, 10000), (128.0, 10000)):
        size = (side, side)
        project = m20b.scale_project(out, f"scale_{int(side)}_{n}", size)
        path = project / SCENES / "hills.json"
        scene = json.loads(path.read_text(encoding="utf-8"))
        scene["settings"]["hd2d"]["scatter"] = _mixed(n, size)
        scene["settings"]["hd2d"]["motion"] = {}
        scene["settings"]["wind"] = {"speed": 6.0, "direction": 20.0, "gust": 0.7}
        path.write_text(json.dumps(scene) + "\n", encoding="utf-8")
        row: dict[str, Any] = {}
        game = HiddenGame(project, size=study.SIZE)
        try:
            t0 = time.perf_counter()
            game.load(f"{SCENES}/hills.json")
            row["room_load_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            game.step(10)
            hd = game.window.hd2d_renderer
            player = game.player()
            player.center_x = size[0] / 2 * PX
            player.center_y += size[1] / 2 * PX - player.bottom
            player.mesh_entity_data["elevation"] = hd.terrain.height(player.center_x, size[1] / 2 * PX) or 0.0
            layer = hd.scatter
            moving, still = parse_motion({}), Motion()
            m20d._frame(game, 60)
            for label, motion in (("still", still), ("moving", moving), ("still_2", still), ("moving_2", moving)):
                layer.set_motion(motion, hd.wind)
                m20d._frame(game, 30)
                stats = hd.stats()
                row[label] = {"frame_ms": m20b._stats(m20d._frame(game)), "gpu_ms": round(m19._frame_gpu_ms(game, 30), 3),
                              "draw_calls": stats["draw_calls"], "shadow_draws": stats["shadow_draws"],
                              "scatter_bytes": stats["scatter_bytes"]}
            builds, size_b = dict(layer.builds), layer.memory_bytes()
            m20d._frame(game, 600)
            row["moving_600_frames"] = {"chunks_rebuilt": sum(layer.builds[k] - builds.get(k, 0) for k in layer.builds),
                                        "bytes_grew": layer.memory_bytes() - size_b,
                                        "motion_time_s": round(game.window.motion_time, 2)}
            row.update(instances=layer.count(), chunks=len(layer.boxes), casting_chunks=len(layer.cast_draws))
            counts = []
            for _ in range(3):
                game.load(f"{SCENES}/hills.json")
                game.step(2)
                game.window.dispatch_event("on_draw")
                game.window.ctx.gc()
                counts.append(_gl_counts(game.window.ctx))
            row["gl_objects_stable_over_reloads"] = counts[1:] == counts[:-1]
            objects = game.window.hd2d_renderer.gl_objects()
            game.window.hd2d_renderer.release()
            row["release_frees_all"] = all(getattr(getattr(o, "_glo", None), "value", 0) == 0 for o in objects)
            game.window.hd2d_renderer = None
        finally:
            game.close()
        report[f"{int(side)}m_{n}"] = row
        print(f"{int(side)}m_{n}", json.dumps(row), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("what", choices=["identity", "smoke", "winds", "gameplay", "trees", "studio", "scale"])
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    result = {"identity": identity, "smoke": smoke, "winds": winds, "gameplay": gameplay,
              "trees": trees, "studio": studio, "scale": scale}[args.what](args.out)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
