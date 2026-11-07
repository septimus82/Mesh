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
import review_media  # noqa: E402
from hd2d_demo import SCENES, HiddenGame  # noqa: E402

PX = 32.0
BLENDER = Path("D:/program/blender.exe")  # (headless only)
# where the new decoration goes (m): torches either side of the cottage's door, a banner by the bridge, small trees on
# the meadow, west of the cottage and on the hill (clear of the stairs and bridge: their canopies spread), glowcaps
# and bellflowers near them, a dripping rock at the cliff's foot
DECOR = [("Torch", (3.4, 2.6)), ("Torch", (7.6, 2.6)), ("Banner", (13.4, 10.6)), ("Small tree", (17.2, 8.4)),
         ("Small tree", (6.5, 12.0)), ("Small tree", (3.2, 16.5)), ("Glowcaps", (15.4, 8.8)), ("Glowcaps", (5.0, 15.7)),
         ("Glowcaps", (8.2, 11.4)), ("Bellflowers", (10.6, 7.6)), ("Bellflowers", (19.4, 7.4)),
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
    review_media.save_clip(frames, path, duration=round(1000 / fps), quality=65, method=6)


def _film_still_camera(game: HiddenGame, x: float, y: float, seconds: float, fps: int = 10,
                       start: float = 20.0) -> list[Any]:
    """The motion clock stepped at ``fps`` (as the game's frames would advance it), one picture a step."""
    return [_crop(at(game, start + k / fps, x, y)) for k in range(int(seconds * fps))]


WINDS = {  # the demonstrations: set_wind's arguments (m/s, toward degrees, gust); the last two: stills and lean only
    "calm": {"speed": 0.0},
    "breeze": {"speed": 3.0, "direction": 15.0, "gust": 0.3},
    "strong": {"speed": 11.0, "direction": 15.0, "gust": 0.15},
    "gusts": {"speed": 5.0, "direction": 15.0, "gust": 0.95},
    "rain_wind": {"speed": 8.0, "direction": 195.0, "gust": 0.5},
    "away": {"speed": 9.0, "direction": 90.0, "gust": 0.3},  # (into the picture)
    "toward": {"speed": 9.0, "direction": 270.0, "gust": 0.3},  # (out of it, toward the camera)
}
WIND_VIEW = (14.5, 8.6)  # the meadow below the bridge: grass, flowers, a tree, the banner
REED_AT = (15.0, 4.0)  # (open grass by the path: one reed alone, measured)


def measured_lean(game: HiddenGame, wind: Any, seconds: float = 6.0) -> dict[str, float]:
    """A single tall reed in this wind, its lean measured from the pictures (not the formula): how far its top's
    middle is across from its foot, against its height, as drawn, ten times a second; and its height on screen
    against still air's (squashed or stretched?)."""
    import numpy as np

    layer = game.window.hd2d_renderer.scatter
    kept = {k: list(v) for k, v in layer.instances.items()}
    x, y = REED_AT
    try:
        layer.set_instances({})
        plain = np.asarray(at(game, 1.0, x, y))
        layer.set_instances({"reeds": [(round(x * PX), round(y * PX), 0, 160)]})
        leans, heights = [], []
        for k in range(int(seconds * 10)):
            mask = np.any(np.asarray(at(game, 30.0 + k / 10, x, y)) != plain, axis=2)
            ys, xs = np.nonzero(mask)
            if len(ys) < 20:
                continue
            top, bottom = ys.min(), ys.max()
            height = bottom - top
            foot, tip = xs[ys >= bottom - 2].mean(), xs[ys <= top + 3].mean()
            leans.append(math.degrees(math.atan2(tip - foot, max(1.0, height))))
            heights.append(height)
    finally:
        layer.set_instances(kept)
    return {"mean_deg": round(float(np.mean(leans)), 1), "max_deg": round(float(np.max(np.abs(leans))), 1),
            "height_px_mean": round(float(np.mean(heights)), 1), "height_px_min": int(np.min(heights)),
            "height_px_max": int(np.max(heights))}


def winds(out: Path) -> dict[str, Any]:
    """Each wind at one camera: four seconds' clip (ten for the gusts: a swell and its quick gusts), its first
    picture; a lone reed's lean measured from the pictures (``measured_lean``, still air's height to compare); and
    how far the grass, a bush and the tree's canopy lean by the shader's twin (across the picture), over the same
    seconds. In the breeze, the torch's flame filmed at 30 frames a second, lossless (a strip)."""
    from PIL import Image

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
            if name in ("away", "toward"):
                _crop(at(game, 20.0, *WIND_VIEW)).save(out / f"wind_{name}_first.png")
            else:
                frames = _film_still_camera(game, *WIND_VIEW, 10.0 if name == "gusts" else 4.0)
                _save_clip(frames, out / f"wind_{name}.webp")
                frames[0].save(out / f"wind_{name}_first.png")
            if name == "breeze":
                import numpy as np

                first = np.asarray(at(game, 40.0, 3.4, 2.6)).astype(int)  # (where the flame is: its bright orange)
                ys, xs = np.nonzero((first[..., 0] > 230) & (first[..., 1] > 100) & (first[..., 2] < 110))
                fx, fy = int(np.median(xs)), int(np.median(ys))
                flame = [at(game, 40.0 + k / 30, 3.4, 2.6).crop((fx - 60, fy - 70, fx + 60, fy + 50))
                         for k in range(30)]
                strip = Image.new("RGB", (120 * 10, 120 * 3))
                for k, img in enumerate(flame):
                    strip.paste(img, ((k % 10) * 120, (k // 10) * 120))
                strip.save(out / "torch_30fps_strip.png")
            w = parse_wind(wind if wind["speed"] else None)
            row: dict[str, Any] = {"reed_measured": measured_lean(game, w)}
            for label, flex in (("grass", ASSETS["grass_tall"].flex), ("bush", ASSETS["bush"].flex),
                                ("tree_canopy", ASSETS["tree_small"].parts[0].flex)):
                angles = [m.angle(11.0, 8.0, 20 + k / 30, flex, 0.37, w, on) for k in range(300)]
                across = [a for a, _d in angles]
                row[label] = {"mean_deg": round(math.degrees(sum(across) / len(across)), 1),
                              "max_deg": round(math.degrees(max(map(abs, across))), 1),
                              "depth_max_deg": round(math.degrees(max(abs(d) for _a, d in angles)), 1)}
            hd = game.window.hd2d_renderer
            row["rain_wind"] = [list(e.wind) for e in (hd.particles.effects if hd.particles is not None else ())]
            report[name] = row
            print(name, json.dumps(row), flush=True)
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
                at(game, 30.0, 16.5, row_y + 1.0, yaw=yaw).crop((0, 0, 1280, 520)).save(out / f"trees_{label}.png")
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
        report["still_while_off"] = bool(np.array_equal(canvas(), (d.advance(20), canvas())[1]))
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
                                   "still": bool(np.array_equal(canvas(), (d.advance(20), canvas())[1]))}
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


def _scale_room(out: Path, side: float, n: int, mix: str) -> tuple[HiddenGame, dict[str, Any]]:
    """A 64 or 128 m sculpted room with ``n`` instances of a mix ("20e": swaying and animated things, trees; "20d":
    20D's own mix, no motion settings: runs on the base too), the player in the middle. Returns it, and its load."""
    import time

    import m20b_sculpt_study as m20b

    size = (side, side)
    project = m20b.scale_project(out, f"scale_{mix}_{int(side)}_{n}", size)
    path = project / SCENES / "hills.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    scene["settings"]["hd2d"]["scatter"] = _mixed(n, size) if mix == "20e" else m20d._instances(n, size, None)
    if mix == "20e":
        scene["settings"]["hd2d"]["motion"] = {}
        scene["settings"]["wind"] = {"speed": 6.0, "direction": 20.0, "gust": 0.7}
    path.write_text(json.dumps(scene) + "\n", encoding="utf-8")
    game = HiddenGame(project, size=study.SIZE)
    t0 = time.perf_counter()
    game.load(f"{SCENES}/hills.json")
    row: dict[str, Any] = {"room_load_ms": round((time.perf_counter() - t0) * 1000, 1)}
    game.step(10)
    hd = game.window.hd2d_renderer
    player = game.player()
    player.center_x = side / 2 * PX
    player.center_y += side / 2 * PX - player.bottom
    player.mesh_entity_data["elevation"] = hd.terrain.height(player.center_x, side / 2 * PX) or 0.0
    m20d._frame(game, 600)  # (warm: the first frames of a room cost twice what later ones do)
    return game, row


def _passes(game: HiddenGame, frames: int = 30, repeat: int = 20) -> dict[str, float]:
    """The GPU time (ms) of the scatter's own passes, each timed alone: a timer query round ``repeat`` draws of
    the sprite pass (and of the canopies' shadow pass, where there is one), median over ``frames`` frames. (A query
    round a whole frame also counts the GPU waiting on Python: not the passes' cost.)"""
    import statistics

    ctx, layer = game.window.ctx, game.window.hd2d_renderer.scatter
    found: dict[str, list[float]] = {}
    kept = {name: getattr(layer, name) for name in ("draw_sprites", "draw_casters") if hasattr(layer, name)}

    def timed(name: str, original: Any) -> Any:
        def run(*a: Any, **kw: Any) -> Any:
            ctx.finish()
            query = ctx.query(samples=False, primitives=False)
            with query:
                for _ in range(repeat):
                    result = original(*a, **kw)
            ctx.finish()
            found.setdefault(name, []).append(query.time_elapsed / 1e6 / repeat)
            return result
        return run

    for name, original in kept.items():
        setattr(layer, name, timed(name, original))
    try:
        for _ in range(frames):
            game.window.dispatch_event("on_update", 1 / 60)
            game.window.dispatch_event("on_draw")
    finally:
        for name, original in kept.items():
            setattr(layer, name, original)
    return {f"{'sprite' if k == 'draw_sprites' else 'canopy_shadow'}_pass_gpu_ms": round(statistics.median(v), 4)
            for k, v in found.items()}


def _wall(game: HiddenGame) -> float:
    """A frame's wall time (ms: update, draw and the GPU finishing it), median of 60."""
    import statistics

    return round(float(statistics.median(m20d._frame(game, 60))), 2)


ROOMS = ((64.0, 100), (64.0, 1000), (64.0, 10000), (128.0, 10000))


def scale(out: Path) -> dict[str, Any]:
    """100, 1,000 and 10,000 instances over a 64 x 64 m sculpted room (and 10,000 over 128 x 128 m), shadows on,
    at the gameplay camera, in a gusty wind, after 600 frames' warm-up: still (animation off) and moving, in the order
    still, moving, moving, still, three times; each block's frame wall time and the scatter passes' own GPU time
    (``_passes``); the differences moving minus still of each neighbouring pair (their median is the cost of
    motion); draw calls, shadow draws, GPU memory; then 600 frames moving: any chunk rebuilt, memory grown; GPU
    objects over reloads and after release. Run it alone (timings); ``baseline`` gives 20D's own cost to compare."""
    import statistics

    from hd2d_demo import _gl_counts

    from engine.hd2d.motion import Motion, parse_motion

    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    for side, n in ROOMS:
        game, row = _scale_room(out, side, n, "20e")
        try:
            hd = game.window.hd2d_renderer
            layer = hd.scatter
            blocks: list[tuple[str, float, dict[str, float]]] = []
            for _ in range(3):
                for label in ("still", "moving", "moving", "still"):
                    layer.set_motion(parse_motion({}) if label == "moving" else Motion(), hd.wind)
                    m20d._frame(game, 30)
                    blocks.append((label, _wall(game), _passes(game)))
            stats = hd.stats()
            pairs = [(blocks[i], blocks[i + 1]) for i in range(0, len(blocks), 2)]
            for label in ("still", "moving"):
                mine = [b for b in blocks if b[0] == label]
                row[label] = {"frame_wall_ms": round(statistics.median(b[1] for b in mine), 2),
                              **{k: round(statistics.median(b[2][k] for b in mine), 4) for k in mine[0][2]}}
            diff = [(m[1] - s_[1], {k: m[2][k] - s_[2][k] for k in m[2]}) for a, b in pairs
                    for s_, m in [(a, b) if a[0] == "still" else (b, a)]]
            row["moving_minus_still"] = {"frame_wall_ms": round(statistics.median(d[0] for d in diff), 2),
                                         **{k: round(statistics.median(d[1][k] for d in diff), 4) for k in diff[0][1]}}
            row.update(draw_calls=stats["draw_calls"], shadow_draws=stats["shadow_draws"],
                       scatter_bytes=stats["scatter_bytes"])
            layer.set_motion(parse_motion({}), hd.wind)
            builds, size_b = dict(layer.builds), layer.memory_bytes()
            m20d._frame(game, 600)
            row["moving_600_frames"] = {"chunks_rebuilt": sum(layer.builds[k] - builds.get(k, 0) for k in layer.builds),
                                        "bytes_grew": layer.memory_bytes() - size_b,
                                        "draw_calls_same": hd.stats()["draw_calls"] == stats["draw_calls"]}
            row.update(instances=layer.count(), chunks=len(layer.boxes), casting_chunks=len(layer.cast_quads),
                       canopy_shadow_draws=len(layer.canopy_blocks))
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


def baseline(out: Path) -> dict[str, Any]:
    """20D's mix in the same rooms, no motion settings: run here and on the base checkout, what 20E costs a room
    that doesn't move (its larger vertices, its second sheet, its uniforms). Frame wall time (three blocks), the
    sprite pass's GPU time, draw calls, shadow draws, GPU memory."""
    import statistics

    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    for side, n in ROOMS:
        game, row = _scale_room(out, side, n, "20d")
        try:
            hd = game.window.hd2d_renderer
            walls, passes = [], []
            for _ in range(3):
                walls.append(_wall(game))
                passes.append(_passes(game))
            stats = hd.stats()
            row.update(frame_wall_ms=round(statistics.median(walls), 2),
                       sprite_pass_gpu_ms=round(statistics.median(p["sprite_pass_gpu_ms"] for p in passes), 4),
                       draw_calls=stats["draw_calls"], shadow_draws=stats["shadow_draws"],
                       scatter_bytes=stats["scatter_bytes"])
        finally:
            game.close()
        report[f"{int(side)}m_{n}"] = row
        print(f"{int(side)}m_{n}", json.dumps(row), flush=True)
    return report

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("what", choices=["identity", "smoke", "winds", "gameplay", "trees", "studio", "scale", "baseline"])
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    result = {"identity": identity, "smoke": smoke, "winds": winds, "gameplay": gameplay,
              "trees": trees, "studio": studio, "scale": scale,
              "baseline": baseline}[args.what](args.out)
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
