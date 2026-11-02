"""Milestone 23B evidence: campfires (hidden windows only; Studio through its own events; silent).

    py -3.13 tooling/m23b_fire_study.py look OUT        # quick: the clearing's fire by day and night
    py -3.13 tooling/m23b_fire_study.py states OUT      # day and night, calm and gusty: stills, clips, the lean
    py -3.13 tooling/m23b_fire_study.py light OUT       # on terrain, a tree and the cottage's wall; the flicker
    py -3.13 tooling/m23b_fire_study.py occlusion OUT   # a fire behind the cottage as the camera turns
    py -3.13 tooling/m23b_fire_study.py perf OUT        # 0, 1, 4 and 16 fires: frame and GPU pass times
    py -3.13 tooling/m23b_fire_study.py compare OUT     # the M20E torch, a static flame, the campfire
    py -3.13 tooling/m23b_fire_study.py studio OUT      # placed and edited in Studio; save, reopen, Play
    py -3.13 tooling/m23b_fire_study.py export OUT      # ``mesh export build`` and the bundle run on its own engine
    py -3.13 tooling/m23b_fire_study.py edges OUT       # a fire on a bridge, 17 fires, a refused GPU, 8 room lamps

The room is Stage 20E's decorated Hills room (tooling/m20e_motion_study.py: a cottage, small trees, a torch, a
meadow) made a woodland clearing: more trees where the scatter rules allow one, and campfires placed only through
``project_ops`` (as Studio and AI do), or in Studio with its own events. Every project's master volume is 0. It is
all made in OUT and thrown away with it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
import engine.optional_arcade  # noqa: E402,F401,I001  # (first: DPI-unaware before anything loads pyglet)
import m20a_terrain_study as m20a  # noqa: E402
import m20e_motion_study as m20e  # noqa: E402
from hd2d_demo import SCENES, HiddenGame  # noqa: E402

PX = 32.0
ROOM = f"{SCENES}/hills.json"
FIRE = (9.6, 2.6)  # m: the clearing's campfire: before the cottage's front wall, a tree to its east
TREES = [(12.5, 3.0), (2.0, 9.0)]  # m: the clearing's trees (with 20E's; where the scatter rules allow one)
TORCH = (3.4, 2.6)  # m: 20E's torch by the cottage (its other was refused there)
HIDDEN = (5.0, 9.6)  # m: a fire behind the cottage (5.6 x 4.6 m about 5, 6; its roof 3.8 m up): 1.3 m behind it
SPOTS = {"terrain": (11.0, 2.0, 0.0), "tree": (12.5, 3.0, 0.6), "wall": (7.0, 3.6, 0.8)}  # m: where the light is read
CALM = {"speed": 0.0, "gust": 0.0}
GUSTY = {"speed": 5.0, "direction": 10.0, "gust": 0.9}


def _silent(project: Path) -> None:
    config = json.loads((project / "config.json").read_text(encoding="utf-8"))
    config["master_volume"] = 0.0  # (nothing reaches the speakers: a play-test's sounds play silently)
    (project / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def make_project(out: Path, name: str, *, night: bool = False, wind: dict | None = None,
                 fires: list[tuple[tuple[float, float], dict[str, Any]]] | None = None) -> Path:
    """The clearing: 20E's room, more trees, the sun (noon or night), the wind, and ``fires`` (where, m, and
    ``set_campfire``'s settings) placed as Studio places them."""
    from engine import project_ops as ops
    from engine.paths import get_content_roots, set_content_roots

    project: Path = m20e.make_project(out, name, decor=True, wind=wind or CALM, motion={"enabled": True})
    _silent(project)
    path = project / ROOM
    scene = json.loads(path.read_text(encoding="utf-8"))
    roots = list(get_content_roots())
    set_content_roots([project])
    try:
        for k, (x, y) in enumerate(TREES):
            scene = ops.scatter_stroke(scene, "Small tree", [[x * PX, y * PX]], radius=10.0, density=4.0, seed=900 + k)
    finally:
        set_content_roots(roots)
    scene = ops.set_hd2d_sun(scene, preset="night" if night else "noon")
    for k, ((x, y), settings) in enumerate(fires if fires is not None else [(FIRE, {})]):
        scene, eid = ops.place_blank(scene, "hills", f"Campfire {k + 1}", x * PX, y * PX)
        scene = ops.set_campfire(scene, eid, **settings)
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    return project


def open_room(out: Path, name: str, **kw: Any) -> HiddenGame:
    game = HiddenGame(make_project(out, name, **kw), size=(1280, 720))
    game.load(ROOM)
    game.step(30)
    return game


def _np(img: Any) -> Any:
    import numpy as np

    return np.asarray(img).astype(np.int32)


def _screen(game: HiddenGame, p: tuple[float, float, float]) -> tuple[int, int]:
    """Where a world point (m) is in the last picture drawn (px from its top left)."""
    vp = game.window.hd2d_renderer.last_vp
    c = [sum(vp[r][k] * (p[k] if k < 3 else 1.0) for k in range(4)) for r in range(4)]
    return round((c[0] / c[3] * 0.5 + 0.5) * 1280), round((0.5 - c[1] / c[3] * 0.5) * 720)


def _crop_at(img: Any, centre: tuple[int, int], w: int = 200, h: int = 150, zoom: int = 2) -> Any:
    from PIL import Image

    x, y = centre
    return img.crop((x - w // 2, y - h + 30, x + w // 2, y + 30)).resize((w * zoom, h * zoom), Image.Resampling.NEAREST)


def _grid(images: list[Any], cols: int, path: Path) -> None:
    from PIL import Image

    w, h = images[0].size
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (w * cols, h * rows), (20, 20, 20))
    for i, im in enumerate(images):
        sheet.paste(im, ((i % cols) * w, (i // cols) * h))
    sheet.save(path)


def _without(game: HiddenGame, names: set[str]) -> Any:
    """The room's fires but those named, for one picture (restore with the returned list)."""
    kept = list(game.window.campfires)
    game.window.campfires = [h for h in kept if getattr(h.entity, "mesh_name", "") not in names]
    return kept


# ---------------------------------------------------------------------- phases
def look(out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    for night in (False, True):
        tag = "night" if night else "day"
        game = open_room(out, f"look_{tag}", night=night)
        try:
            for t in (10.0, 10.3):
                m20e.at(game, t, *FIRE).save(out / f"look_{tag}_{t:.1f}.png")
            hd = game.window.hd2d_renderer
            report[tag] = {"fires": len(game.window.campfires), "lamps": len(hd.lighting.extra_lamps),
                           "error": hd.fire_error}
        finally:
            game.close()
    return report


def _lean(game: HiddenGame, seconds: float = 6.0) -> dict[str, float]:
    """The flames' lean, measured from the pictures: the fire's own flame-coloured pixels (against the room without
    it, at the same moment: its grass sways too) above its logs, their middle's offset across from the fire's foot,
    ten times a second (px; + east, which is downwind here)."""
    import dataclasses

    import numpy as np

    foot = _screen(game, (*FIRE, 0.0))
    offsets = []
    lit = list(game.window.campfires)  # (measured without its light: the ground it lights isn't flame)
    game.window.campfires = [dataclasses.replace(h, fire=dataclasses.replace(h.fire, light=0.0)) for h in lit]
    for k in range(int(seconds * 10)):
        kept = _without(game, {"Campfire 1"})
        plain = _np(m20e.at(game, 30.0 + k / 10, *FIRE))
        game.window.campfires = kept
        img = _np(m20e.at(game, 30.0 + k / 10, *FIRE))
        r, g, b = img[..., 0], img[..., 1], img[..., 2]  # (the flames' own colours: not the light they cast round)
        mask = np.any(np.abs(img - plain) > 40, axis=2) & (r > 170) & (r >= g) & (r > b + 90)
        mask[foot[1] - 22:, :] = False  # (the logs and the ground's light: the flames above them only)
        mask[:, :foot[0] - 70] = False
        mask[:, foot[0] + 70:] = False
        ys, xs = np.nonzero(mask)
        if len(xs) > 20:
            offsets.append(float(xs.mean() - foot[0]))
    game.window.campfires = lit
    return {"mean_px": round(statistics.mean(offsets), 1), "max_px": round(max(offsets), 1),
            "min_px": round(min(offsets), 1), "spread_px": round(statistics.pstdev(offsets), 2)}


def states(out: Path, clips: bool = True) -> dict[str, Any]:
    """Day and night, calm and gusty: a still of each (2x, the fire), a 3 s clip (embers and smoke rising; ``clips``),
    and the flames' lean measured."""
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    stills = []
    for night in (False, True):
        for windy in (False, True):
            tag = f"{'night' if night else 'day'}_{'gusty' if windy else 'calm'}"
            game = open_room(out, tag, night=night, wind=GUSTY if windy else CALM)
            try:
                full = m20e.at(game, 30.0, *FIRE)
                centre = _screen(game, (*FIRE, 0.0))
                full.save(out / f"{tag}.png")
                stills.append(_crop_at(full, centre))
                if clips:
                    frames = [_crop_at(m20e.at(game, 40.0 + k / 15, *FIRE), centre) for k in range(45)]
                    m20e._save_clip(frames, out / f"{tag}_clip.webp", fps=15)
                report[tag] = {"lean": _lean(game), "fire_draws": game.window.hd2d_renderer.fire_sprites.draw_calls}
            finally:
                game.close()
    _grid(stills, 2, out / "states_grid.png")  # (rows: day, night; columns: calm, gusty)
    return report


def light(out: Path) -> dict[str, Any]:
    """At night, the fire lit and put out: the light it adds where SPOTS are (mean RGB over 9 x 9 px), a picture of
    the difference, and the flicker (the terrain spot's brightness over 4 s, 20 a second)."""
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    pictures = {}
    for lit in (True, False):
        game = open_room(out, f"light_{lit}", night=True, fires=[(FIRE, {"enabled": lit})])
        try:
            img = m20e.at(game, 30.0, 8.6, 3.6)
            pictures[lit] = img
            img.save(out / f"night_fire_{'lit' if lit else 'out'}.png")
            spots = {k: _screen(game, p) for k, p in SPOTS.items()}
            a = _np(img)
            report["lit" if lit else "out"] = {k: [round(float(v), 1) for v in a[y - 4:y + 5, x - 4:x + 5].reshape(-1, 3).mean(0)]
                                               for k, (x, y) in spots.items()}
            report[f"lamps_{'lit' if lit else 'out'}"] = len(game.window.hd2d_renderer.lighting.extra_lamps)
            if lit:
                x, y = spots["terrain"]
                series = []
                for k in range(80):
                    v = _np(m20e.at(game, 50.0 + k / 20, 8.6, 3.6))[y - 4:y + 5, x - 4:x + 5].mean()
                    series.append(round(float(v), 2))
                report["flicker_terrain"] = {"min": min(series), "max": max(series), "mean": round(statistics.mean(series), 2),
                                             "series": series}
                report["spots_px"] = spots
        finally:
            game.close()
    report["added"] = {k: [round(a - b, 1) for a, b in zip(report["lit"][k], report["out"][k])] for k in SPOTS}
    diff = (abs(_np(pictures[True]) - _np(pictures[False])) * 3).clip(0, 255).astype("uint8")
    Image.fromarray(diff).save(out / "night_light_difference_x3.png")
    return report


def occlusion(out: Path) -> dict[str, Any]:
    """A fire behind the cottage (its light 0: only its flames, embers and smoke differ), the camera turning round
    the cottage until it looks from the north (180: nothing in the way): its visible pixels (the picture with it
    against the same picture without it) at each turn."""
    import numpy as np

    out.mkdir(parents=True, exist_ok=True)
    game = open_room(out, "occlusion", fires=[(FIRE, {}), (HIDDEN, {"light": 0.0})])
    report: dict[str, Any] = {}
    shots = []
    try:
        for yaw in (0, 30, 60, 90, 120, 150, 180, -90):
            img = m20a.shot(game, 5.0, 6.0, yaw=float(yaw), distance=None)
            kept = _without(game, {"Campfire 2"})
            plain = m20a.shot(game, 5.0, 6.0, yaw=float(yaw), distance=None)
            game.window.campfires = kept
            visible = int(np.any(np.abs(_np(img) - _np(plain)) > 24, axis=2).sum())
            report[f"yaw_{yaw}"] = visible
            img.save(out / f"occlusion_yaw_{yaw:+d}.png")
            shots.append(img.resize((640, 360)))
    finally:
        game.close()
    _grid(shots, 4, out / "occlusion_grid.png")
    return report


def _gpu(game: HiddenGame, target: Any, name: str, found: dict[str, list[float]], repeat: int = 20) -> Any:
    """Time ``target.name`` on the GPU: a timer query round ``repeat`` calls (the pass alone, not the frame)."""
    ctx, original = game.window.ctx, getattr(target, name)

    def run(*a: Any, **kw: Any) -> Any:
        ctx.finish()
        query = ctx.query(samples=False, primitives=False)
        with query:
            for _ in range(repeat):
                result = original(*a, **kw)
        ctx.finish()
        found.setdefault(name, []).append(query.time_elapsed / 1e6 / repeat)
        return result

    setattr(target, name, run)
    return original


def perf(out: Path) -> dict[str, Any]:
    """0, 1, 4 and 16 fires in view (night, gusty), each a fresh room: a frame's wall time (update, draw, the GPU
    finishing), its draw calls and fire lights (at most 8: the nearest), the fires' CPU work a frame, and their two
    GPU passes (sprites, particles) timed alone."""
    import m20d_scatter_study as m20d

    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    grid = [(8.5 + 1.6 * (k % 4), 1.4 + 1.5 * (k // 4)) for k in range(16)]
    for n in (0, 1, 4, 16):
        game = open_room(out, f"perf_{n}", night=True, wind=GUSTY, fires=[(p, {}) for p in grid[:n]])
        try:
            hd = game.window.hd2d_renderer
            game.window.hd2d_renderer.camera.target = (11.0, 1.6, 0.8)
            m20a.shot(game, 11.0, 3.0).save(out / f"perf_{n}_fires.png")
            # (a frame's wall time here swings 5-10 ms with the GPU's clocks: the best of three medians, as a guide;
            # the passes' own GPU and CPU times below are the cost)
            row: dict[str, Any] = {"wall_ms_best_of_3": round(min(statistics.median(m20d._frame(game, 120))
                                                                  for _ in range(3)), 2),
                                   "draw_calls": hd.draw_calls, "lamps": len(hd.lighting.extra_lamps)}
            cpu: list[float] = []
            original = hd._fires

            def fires_timed(*a: Any) -> Any:
                t = time.perf_counter()
                result = original(*a)
                cpu.append((time.perf_counter() - t) * 1000)
                return result

            hd._fires = fires_timed
            found: dict[str, list[float]] = {}
            undo = []
            if n:
                undo.append((hd.fire_sprites, "draw_sprites", _gpu(game, hd.fire_sprites, "draw_sprites", found)))
                undo.append((hd, "_draw_fire_particles", _gpu(game, hd, "_draw_fire_particles", found)))
            try:
                for _ in range(30):
                    game.window.dispatch_event("on_update", 1 / 60)
                    game.window.dispatch_event("on_draw")
            finally:
                hd._fires = original
                for obj, name, fn in undo:
                    setattr(obj, name, fn)
            row["fires_cpu_ms"] = round(statistics.median(cpu), 4)
            row.update({f"{k}_gpu_ms": round(statistics.median(v), 4) for k, v in found.items()})
            report[f"fires_{n}"] = row
        finally:
            game.close()
    return report


def compare(out: Path) -> dict[str, Any]:
    """By day and night, side by side at 2x: 20E's torch, a static flame (the campfire's logs and flames, still: no
    animation, wind, embers, smoke or light) and the campfire."""
    from engine import fire as fire_mod
    from engine.hd2d.motion import OFF

    out.mkdir(parents=True, exist_ok=True)
    tiles = []
    for night in (False, True):
        game = open_room(out, f"compare_{'night' if night else 'day'}", night=night, wind=GUSTY)
        try:
            hd = game.window.hd2d_renderer
            img = m20e.at(game, 30.0, 6.5, 2.6)
            torch, campfire = _screen(game, (*TORCH, 0.0)), _screen(game, (*FIRE, 0.0))
            full = img
            lamps, draw_particles = fire_mod.lamps, hd._draw_fire_particles
            fire_mod.lamps = lambda *_a, **_k: []  # (the static flame: no light, no particles, no motion)
            hd._draw_fire_particles = lambda *_a, **_k: None
            hd.fire_sprites.set_motion(OFF, hd.wind)
            try:
                still = m20e.at(game, 30.0, 6.5, 2.6)
            finally:
                fire_mod.lamps, hd._draw_fire_particles = lamps, draw_particles
                hd.fire_sprites.set_motion(m20e_motion(), hd.wind)
            tiles += [_crop_at(full, torch), _crop_at(still, campfire), _crop_at(full, campfire)]
        finally:
            game.close()
    _grid(tiles, 3, out / "compare_torch_static_campfire.png")  # (rows: day, night)
    return {"tiles": ["torch", "static flame", "campfire"], "rows": ["day (gusty)", "night (gusty)"]}


def m20e_motion() -> Any:
    from engine.hd2d.motion import Motion

    return Motion(enabled=True)


def studio(out: Path) -> dict[str, Any]:
    """The clearing without a fire, in Mesh Studio with its own events: Objects > Campfire, a click on the ground,
    its settings typed and toggled in the inspector, the crackle chosen from Mesh's library; put out and lit again;
    saved; reopened (the same settings, drawn); Play and Stop."""
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops

    out.mkdir(parents=True, exist_ok=True)
    project = make_project(out, "studio", night=True, fires=[])
    report: dict[str, Any] = {}

    def fire_entities(scene: dict[str, Any]) -> list[dict[str, Any]]:
        return [e for e in scene.get("entities", []) if ops.campfire_of(e) is not None]

    def state(d: Any) -> dict[str, Any]:
        hd = d.studio.hd2d.renderer
        return {"campfires": len(getattr(d.window, "campfires", []) or []), "lamps": len(hd.lighting.extra_lamps),
                "fire_draws": hd.fire_sprites.draw_calls if hd.fire_sprites is not None else 0,
                "particle_draws": hd.fire_particles.draw_calls if hd.fire_particles is not None else 0}

    d = StudioDriver(project)
    try:
        key = next(k for k, _l, path in d.studio.project.rooms() if path.endswith("hills.json"))
        d.button(d.studio.project.label(key))  # (the Rooms list)
        d.advance(3)
        report["room"] = d.studio.project.current
        import m20c_material_study as m20c

        m20c._look_at(d, FIRE[0], FIRE[1] + 1.0, 18.0)
        d.studio.set_left_tab("objects")
        d.advance()
        report["objects_list_has_campfire"] = d.has_button("Campfire")
        d.button("Campfire")
        ground = d.renderer.ground_height(FIRE[0] * PX, FIRE[1] * PX) / PX
        d.click(*d.screen((FIRE[0], FIRE[1], ground)))
        d.advance(3)
        eid = d.studio.selected
        report["placed"] = ops.campfire_of(d.studio._entity(eid) or {})
        report["editing_preview"] = state(d)
        d.picture(out / "studio_01_placed.png")
        d.type_into("fire_size", "1.3")
        d.type_into("fire_light", "1.4")
        d.type_into("fire_radius", "7")
        d.button("Smoke: On")
        d.button("Smoke: Off")
        d.button("Crackle sound...")
        d.button("Forest or meadow  (forest_loop.wav)")
        d.advance(3)
        report["edited"] = ops.campfire_of(d.studio._entity(eid) or {})
        d.picture(out / "studio_02_edited.png")
        d.button("Burning: On")
        d.advance(3)
        report["put_out"] = {**state(d), "settings": ops.campfire_of(d.studio._entity(eid) or {}),
                             "crackle_enabled": ((d.studio._entity(eid) or {}).get("behaviour_config") or {})
                             .get("SoundEmitter", {}).get("enabled")}
        d.picture(out / "studio_03_put_out.png")
        d.button("Burning: Off")
        d.advance(3)
        report["lit_again"] = state(d)
        d.key(d.arcade.key.S, d.arcade.key.MOD_CTRL)
        d.advance()
        report["saved_message"] = d.studio.message
    finally:
        d.close()
    room = json.loads((project / ROOM).read_text(encoding="utf-8"))
    saved = [(e["x"], e["y"], ops.campfire_of(e)) for e in fire_entities(room)]
    report["in_the_saved_file"] = saved
    d = StudioDriver(project)
    try:
        key = next(k for k, _l, path in d.studio.project.rooms() if path.endswith("hills.json"))
        d.button(d.studio.project.label(key))  # (the Rooms list)
        d.advance(3)
        import m20c_material_study as m20c

        m20c._look_at(d, FIRE[0], FIRE[1] + 1.0, 18.0)
        again = [(e["x"], e["y"], ops.campfire_of(e)) for e in fire_entities(d.studio.project.scene())]
        report["reopened"] = {"same": again == saved, "unsaved": sorted(d.studio.project.dirty), **state(d)}
        d.picture(out / "studio_04_reopened.png")
        k = d.arcade.key
        cycles = []
        for _ in range(3):
            d.key(k.F4)
            d.advance(20)
            hd = d.window.hd2d_renderer
            cycles.append({"mode": d.studio.mode, "campfires": len(d.window.campfires),
                           "lamps": len(hd.lighting.extra_lamps), "fire_draws": hd.fire_sprites.draw_calls,
                           "master_volume": d.window.audio.master_volume})
            if len(cycles) == 1:
                d.picture(out / "studio_05_play.png")
            d.key(k.F4)
            d.advance(5)
            cycles[-1]["stopped"] = d.studio.mode
        report["play_stop"] = cycles
    finally:
        d.close()
    return report


def export(out: Path) -> dict[str, Any]:
    """The clearing (fire lit, smoke, by night) exported with ``mesh export build``; the bundle run on its own engine
    in a hidden window: its fire registered, lit, drawn; a picture of it."""
    project = make_project(out, "export", night=True, wind=GUSTY)
    bundle = out / "export_bundle"
    if bundle.exists():
        shutil.rmtree(bundle)
    built = subprocess.run([sys.executable, "-m", "mesh_cli", "export", "build", "--out", str(bundle)], cwd=project,
                           capture_output=True, text=True, timeout=900, env={**os.environ, "PYTHONPATH": str(REPO)})
    report: dict[str, Any] = {"export_code": built.returncode, "export_tail": (built.stdout + built.stderr)[-300:],
                              "sheet_in_bundle": (bundle / "assets/hd2d_starter/scatter/foliage_motion.png").is_file()}
    code = f"""
import json, sys
sys.path.insert(0, {str(bundle)!r})
import engine
sys.path.insert(1, {str(REPO / "tooling")!r})
from hd2d_demo import HiddenGame
from pathlib import Path
from PIL import Image
game = HiddenGame(Path({str(bundle)!r}), size=(1280, 720))
try:
    game.load({ROOM!r})
    game.step(60)
    hd = game.window.hd2d_renderer
    hd.camera.target = ({FIRE[0]}, {FIRE[1] - 0.8}, 0.8)
    hd._camera_ready = True
    Image.frombytes("RGB", (1280, 720), hd.draw(read=True)).transpose(Image.Transpose.FLIP_TOP_BOTTOM).save({str(out / "export_frame.png")!r})
    row = {{"engine_from": engine.__file__, "campfires": len(game.window.campfires), "lamps": len(hd.lighting.extra_lamps),
            "fire_draws": hd.fire_sprites.draw_calls, "particle_draws": hd.fire_particles.draw_calls,
            "fire_error": hd.fire_error, "master_volume": game.window.audio.master_volume}}
finally:
    game.close()
print(json.dumps(row))
"""
    ran = subprocess.run([sys.executable, "-c", code], cwd=bundle, capture_output=True, text=True, timeout=900,
                         env={k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "MESH_REPO_ROOT")})
    try:
        report["bundle_run"] = json.loads(ran.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        report["bundle_run"] = {"failed": ran.stdout[-600:] + ran.stderr[-1500:]}
    return report


BRIDGE = (15.0, 15.0)  # m: on the bridge's deck (2 m up, over the valley)


def _room(project: Path) -> dict[str, Any]:
    room: dict[str, Any] = json.loads((project / ROOM).read_text(encoding="utf-8"))
    return room


def _drawn(game: HiddenGame) -> dict[str, Any]:
    """One frame drawn: the fires' rows, heights, lights and particle anchors (m)."""
    hd = game.window.hd2d_renderer
    seen: list[Any] = []
    fp = hd.fire_particles
    original = fp.draw if fp is not None else None

    def watched(vp: Any, cam: Any, anchors: list[Any], *a: Any, **k: Any) -> Any:
        seen.extend(anchors)
        return original(vp, cam, anchors, *a, **k) if original is not None else None

    if fp is not None:
        fp.draw = watched
    try:
        game.window.dispatch_event("on_draw")
        if fp is None and hd.fire_particles is not None:  # (made this frame: once more, watched)
            return _drawn(game)
    finally:
        if fp is not None:
            fp.draw = original
    rows = hd._fire_rows or {}
    return {"logs": len(rows.get("campfire", [])), "flames": len(rows.get("campfire_flame", [])),
            "logs_z_m": sorted({round(z / PX, 3) for z in hd._fire_z.values()}),
            "lamps": len(hd.lighting.extra_lamps), "lamps_z_m": [round(lt.elevation / PX, 3) for lt in hd.lighting.extra_lamps],
            "anchors_z_m": [round(a[2], 3) for a in seen], "fire_error": hd.fire_error}


def edges(out: Path) -> dict[str, Any]:
    """The review's edge cases: a fire on the bridge's deck (placed there in Studio, which gives it the deck's
    height); 17 fires, the first 16 put out; the fires' GPU objects refused (no light without a fire); and a room
    whose own lamps use all 8 lights (Studio says why its fires light nothing)."""
    from pyglet.gl import GLException

    import engine.hd2d.scatter_layer as scatter_layer
    from engine import project_ops as ops

    report: dict[str, Any] = {}
    project = make_project(out, "bridge", night=True, fires=[])
    game = HiddenGame(project, size=(1280, 720))
    try:
        game.load(ROOM)
        from engine.hd2d.world import NAV_HALF

        deck = game.window.hd2d_world.stand(BRIDGE[0], BRIDGE[1], 2.0, *NAV_HALF)
        assert deck is not None, "the bridge's deck"
        ground = game.window.hd2d_renderer.ground_height(BRIDGE[0] * PX, BRIDGE[1] * PX) / PX
    finally:
        game.close()
    scene = _room(project)
    scene, eid = ops.place_blank(scene, "hills", "Bridge fire", BRIDGE[0] * PX, BRIDGE[1] * PX)
    scene = ops.set_entity_fields(ops.set_campfire(scene, eid), eid, elevation=round(deck[0] * PX, 2))
    (project / ROOM).write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    game = open_room_at(project)
    try:
        report["bridge"] = {"deck_m": deck[0], "ground_under_m": round(ground, 3), **_drawn(game)}
        m20a.shot(game, BRIDGE[0], BRIDGE[1], deck[0]).save(out / "edge_bridge_fire.png")
    finally:
        game.close()

    grid = [(1.5 + 1.2 * (k % 9), 0.8 + 1.2 * (k // 9)) for k in range(17)]
    game = open_room(out, "seventeen", night=True, fires=[(p, {"enabled": k == 16}) for k, p in enumerate(grid)])
    try:
        report["seventeen"] = {"registered": len(game.window.campfires), **_drawn(game)}
    finally:
        game.close()

    original = scatter_layer.ScatterLayer.__init__
    refused = [0]

    def refuse(layer: Any, renderer: Any, scatter: Any, height: Any) -> None:
        if not scatter and renderer.scatter is not None and not refused[0]:  # (the fires' layer: not the room's)
            refused[0] += 1
            raise GLException("refused (review)")
        original(layer, renderer, scatter, height)

    setattr(scatter_layer.ScatterLayer, "__init__", refuse)  # noqa: B010  # (the review's refusal)
    try:
        game = open_room(out, "refused", night=True)
        try:
            frames = [_drawn(game) for _ in range(3)]
            report["refused"] = {"refusals": refused[0], "frames": frames}
        finally:
            game.close()
    finally:
        setattr(scatter_layer.ScatterLayer, "__init__", original)  # noqa: B010

    from hd2d_studio_demo import StudioDriver

    project = make_project(out, "eight", night=True)
    scene = _room(project)
    scene["lights"] = [lt for lt in scene.get("lights") or [] if lt.get("type") == "ambient"] + [
        {"id": f"lamp{k}", "type": "point", "x": 64 + 96 * k, "y": 600, "radius": 96, "color": "#ffffff",
         "intensity": 0.5} for k in range(8)]
    (project / ROOM).write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    d = StudioDriver(project)
    try:
        key = next(k for k, _l, path in d.studio.project.rooms() if path.endswith("hills.json"))
        d.button(d.studio.project.label(key))
        d.advance(3)
        d.studio.select(next(e["id"] for e in d.studio.project.scene()["entities"] if ops.campfire_of(e)))
        d.advance(3)
        hd = d.studio.hd2d.renderer
        report["eight_lamps"] = {"room_lamps": len(hd.lighting.lamps), "fire_lamps_made": len(hd.lighting.extra_lamps),
                                 "note": next((t for t in d.texts() if "lights it can show" in t), "")}
        d.picture(out / "edge_eight_lamps_inspector.png")
    finally:
        d.close()
    return report


def open_room_at(project: Path) -> HiddenGame:
    game = HiddenGame(project, size=(1280, 720))
    game.load(ROOM)
    game.step(30)
    return game


PHASES: dict[str, Callable[[Path], dict[str, Any]]] = {
    "look": look, "states": states, "light": light, "occlusion": occlusion, "perf": perf, "compare": compare,
    "studio": studio, "export": export, "edges": edges}


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("phase", choices=sorted(PHASES))
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    report = PHASES[args.phase](args.out)
    print(json.dumps(report, indent=1, default=str))


if __name__ == "__main__":
    main()
