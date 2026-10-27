"""Milestone 20D evidence: foliage and landscape composition (hidden windows only; Studio through its own events).

    py -3.13 tooling/m20d_scatter_study.py look OUT      # the 20C room and the composed one, same cameras, dry and rain
    py -3.13 tooling/m20d_scatter_study.py scale OUT     # 100, 1,000, 10,000 instances on 64 x 64 m (run alone)
    py -3.13 tooling/m20d_scatter_study.py studio OUT    # scattering in Studio: strokes, undo/redo/save, cancels, rules
    py -3.13 tooling/m20d_scatter_study.py walks OUT     # 20A's walks in the decorated room, and into the boulder

The room is Stage 20C's painted Hills room (tooling/m20c_material_study.py), decorated only through
``project_ops.scatter_stroke`` (as Studio and AI scatter), deliberately and sparingly:

- grass tufts and flowers in drifts along both sides of the winding path, never on it;
- a few meadow patches in the open grass, plenty of it left plain;
- rocks along the foot and the top edge of the terrace's cliff, breaking its repeated texture, and a boulder at
  its west end, clear of the ramp;
- reeds and cattails on the pond's far banks (the path's side left open), tall grass round them;
- bushes beside the bridge's piers and the cottage's sides, clear of its door;
- dry grass and a fallen branch on the hill's flank.
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
import m20c_material_study as m20c  # noqa: E402
from hd2d_demo import SCENES, HiddenGame  # noqa: E402

PX = 32.0


def _beside(line: list[tuple[float, float]], offset: float, step: float = 0.5) -> list[tuple[float, float]]:
    """A line ``offset`` m to the side of the curve through ``line`` (left positive)."""
    pts = m20c._spline(line, step)
    out = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        n = math.hypot(dx, dy) or 1.0
        out.append((x0 - dy / n * offset, y0 + dx / n * offset))
    return out


def compose(scene: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """The room decorated, stroke by stroke, through the checked operation. Returns it and the strokes."""
    from engine import project_ops as ops

    n = 0

    def stroke(collection: Any, line: list[tuple[float, float]], radius: float, density: float, seed: int,
               **kw: Any) -> None:
        nonlocal scene, n
        scene = ops.scatter_stroke(scene, collection, [[round(x * PX, 1), round(y * PX, 1)] for x, y in line],
                                   radius * PX, density=density, seed=seed, **kw)
        n += 1

    path = m20c.EARTH_PATH
    for side, seed in ((1.35, 11), (-1.35, 12)):  # drifts along both sides of the path
        stroke("Meadow", _beside(path, side, 0.6), 0.7, 1.3, seed, clumping=0.75)
    stroke("Wildflowers", _beside(path[2:7], 1.9, 0.8), 0.6, 0.9, 13, clumping=0.8)
    for (x, y), seed in (((6.0, 12.0), 21), ((22.0, 11.5), 22), ((10.0, 21.5), 23), ((28.5, 11.0), 24)):
        stroke("Meadow", [(x, y), (x + 1.5, y + 0.6)], 1.6, 0.7, seed, clumping=0.8)  # patches in the open grass
    x0, x1, y0, _y1, _h = m20a.TERRACE  # the cliff: its foot and its top edge
    stroke("Rocks", [(x0 + 1.2 + 0.6 * k, y0 - 0.6) for k in range(10)], 0.6, 0.8, 31, on=list(("grass", "earth",
                                                                                                  "stone")))
    stroke("Rocks", [(x0 + 1.5 + 0.8 * k, y0 + 1.1) for k in range(8)], 0.5, 0.5, 32)
    stroke("Boulder", [(x0 + 0.6, y0 - 1.4)], 0.5, 1.5, 33, avoid_structures=True)
    bx, by, br, _d = m20a.BASIN  # the pond's far banks: reeds; the path's side left open
    far_bank = [(bx + br * 0.72 * math.cos(a), by + br * 0.68 * math.sin(a)) for a in
                [math.radians(d) for d in range(-70, 160, 15)]]
    stroke("Pond edge", far_bank, 0.55, 2.4, 41, clumping=0.6)
    stroke({"grass_tall": 3, "flowers_pink": 1}, [(bx + br * 1.05 * math.cos(a), by + br * 1.0 * math.sin(a))
                                                  for a in [math.radians(d) for d in range(-40, 140, 20)]],
           0.6, 1.0, 42, clumping=0.7)
    stroke("Shrubs", [(12.9, 12.8), (17.1, 12.8)], 0.7, 1.2, 51, avoid_structures=False)  # the bridge's piers
    stroke("Shrubs", [(2.4, 5.2), (7.7, 6.4)], 0.6, 1.4, 52, avoid_structures=False)  # beside the cottage
    hx, hy, hr, _hh = m20a.HILL
    stroke("Deadfall", [(hx + hr * 0.7, hy - hr * 0.5), (hx + hr * 0.85, hy - hr * 0.15)], 0.8, 0.9, 61)
    return scene, n


def make_project(out: Path, name: str, *, rain: bool = False, decorated: bool = True) -> Path:
    project = m20c.make_project(out, name, rain=rain)
    if decorated:
        path = project / SCENES / "hills.json"
        scene, _n = compose(json.loads(path.read_text(encoding="utf-8")))
        path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    return project


def open_room(out: Path, name: str, **kw: Any) -> HiddenGame:
    game = HiddenGame(make_project(out, name, **kw), size=study.SIZE)
    game.load(f"{SCENES}/hills.json")
    game.step(30)
    return game


VIEWS = {"path": (9.0, 5.0), "valley": (15.0, 7.0), "pond": (24.0, 6.5), "rock": (26.0, 16.5), "hill": (5.0, 17.5),
         "bridge": (15.0, 12.0), "cottage": (5.5, 4.5)}


def look(out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    for rain in (False, True):
        for decorated in (False, True):
            tag = f"{'rain' if rain else 'dry'}_{'20d' if decorated else '20c'}"
            game = open_room(out, f"look_{tag}", rain=rain, decorated=decorated)
            try:
                m20a.shot(game, 16.0, 12.0, distance=90.0).save(out / f"overview_{tag}.png")
                for name, (x, y) in VIEWS.items():
                    m20a.shot(game, x, y).save(out / f"{name}_{tag}.png")
                stats = game.window.hd2d_renderer.stats()
                report[tag] = {k: stats[k] for k in ("draw_calls", "scatter_instances", "scatter_sprite_draws",
                                                     "scatter_bytes")}
            finally:
                game.close()
    for name in [*VIEWS, "overview"]:
        for weather in ("dry", "rain"):
            from PIL import Image

            m20a.pair([Image.open(out / f"{name}_{weather}_20c.png"), Image.open(out / f"{name}_{weather}_20d.png")],
                      ["Stage 20C", "Stage 20D (decorated)"], out / f"{name}_{weather}_pair.png", crop=None)
    return report


def _instances(n: int, size_m: tuple[float, float], height: Any) -> dict[str, list[list[int]]]:
    """``n`` instances over the ground, a fixed mix (mostly grass and flowers; some bushes, reeds, rocks, branches),
    from a fixed seed: what a large decorated room holds."""
    import random

    from engine.hd2d.scatter import stored

    mix = {"grass_tuft": 40, "grass_tall": 15, "flowers_yellow": 8, "flowers_pink": 8, "grass_dry": 6, "bush": 5,
           "bush_berries": 2, "reeds": 4, "reeds_cattail": 2, "rock_small": 6, "rock_medium": 3, "fallen_branch": 1}
    names, weights = list(mix), list(mix.values())
    rng = random.Random(5)
    out: dict[str, list[tuple[int, int, int, int]]] = {}
    for _ in range(n):
        name = rng.choices(names, weights)[0]
        out.setdefault(name, []).append((round(rng.uniform(16, size_m[0] * PX - 16)),
                                         round(rng.uniform(16, size_m[1] * PX - 16)), rng.randrange(360),
                                         rng.randint(80, 120)))
    return stored(out)


def _frame(game: HiddenGame, n: int = 60) -> list[float]:
    import time

    times = []
    for _ in range(n):
        t = time.perf_counter()
        game.window.dispatch_event("on_update", 1 / 60)
        game.window.dispatch_event("on_draw")
        game.window.ctx.finish()
        times.append((time.perf_counter() - t) * 1000)
    return times


def scale(out: Path) -> dict[str, Any]:
    """100, 1,000 and 10,000 instances (and none) over a 64 x 64 m sculpted room, shadows on, playing at the
    gameplay camera: load, frame (CPU, GPU), draw calls, GPU memory, chunks drawn; then the cost of the models'
    shadows and of distance culling (each switched off), a zoomed-out view, and GPU objects over reloads."""
    import time

    import m19_water_study as m19
    import m20b_sculpt_study as m20b
    from hd2d_demo import _gl_counts

    import engine.hd2d.scatter_layer as layer_mod

    out.mkdir(parents=True, exist_ok=True)
    size = (64.0, 64.0)
    report: dict[str, Any] = {}
    for n in (0, 100, 1000, 10000):
        project = m20b.scale_project(out, f"scale_{n}", size)
        path = project / SCENES / "hills.json"
        scene = json.loads(path.read_text(encoding="utf-8"))
        if n:
            scene["settings"]["hd2d"]["scatter"] = _instances(n, size, None)
        path.write_text(json.dumps(scene) + "\n", encoding="utf-8")
        row: dict[str, Any] = {"stored_chars": len(path.read_text(encoding="utf-8"))}
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
            _frame(game, 120)
            row["frame_ms"] = m20b._stats(_frame(game))
            row["frame_gpu_ms"] = round(m19._frame_gpu_ms(game, 30), 3)
            stats = hd.stats()
            row.update(draw_calls=stats["draw_calls"], shadow_draws=stats["shadow_draws"],
                       scatter_sprite_draws=stats["scatter_sprite_draws"], scatter_bytes=stats["scatter_bytes"],
                       scatter_instances=stats["scatter_instances"],
                       scatter_chunks=len(hd.scatter.boxes) if hd.scatter is not None else 0)
            if hd.scatter is not None:
                kept = hd.scatter.casters
                setattr(hd.scatter, "casters", lambda: [])  # (the models cast no shadow, this once)
                row["frame_gpu_ms_models_cast_no_shadow"] = round(m19._frame_gpu_ms(game, 30), 3)
                setattr(hd.scatter, "casters", kept)
                cam = hd.camera
                kept_d = cam.distance
                cam.distance = 95.0  # (the whole room in view: the overview's worst case)
                _frame(game, 10)
                row["zoomed_out_gpu_ms"] = round(m19._frame_gpu_ms(game, 30), 3)
                row["zoomed_out_sprite_draws"] = hd.scatter.draw_calls
                far = layer_mod.SPRITE_FAR
                layer_mod.SPRITE_FAR = 1e9
                row["zoomed_out_gpu_ms_no_distance_culling"] = round(m19._frame_gpu_ms(game, 30), 3)
                row["zoomed_out_sprite_draws_no_distance_culling"] = hd.scatter.draw_calls
                layer_mod.SPRITE_FAR = far
                cam.distance = kept_d
                counts = []
                for _ in range(3):  # reload the room: nothing of the scatter piles up
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
        if n:
            d = m20b._driver(project)
            try:
                s, view, k = d.studio, d.studio.hd2d, d.arcade.key
                t1 = time.perf_counter()
                s._reload()
                row["studio_room_reload_ms"] = round((time.perf_counter() - t1) * 1000, 1)
                d.button("Scatter")
                m20c._look_at(d, size[0] / 2, size[1] / 2, 18.0)
                m20b.RELEASES.clear()
                view.timings["sculpt_ms"].clear()
                frames = m20b._stroke(d, m20c._on_ground(d, [(size[0] / 2 - 4, size[1] / 2), (size[0] / 2 + 4,
                                                                                              size[1] / 2 + 1)], 0.1))
                row["studio_stroke_frame_ms"] = m20b._stats(frames)
                row["studio_scatter_update_ms"] = m20b._stats(view.timings["sculpt_ms"])
                row["studio_commit_ms"] = round(view.timings["edit_ms"][-1], 1) if view.timings["edit_ms"] else None
                row["studio_release_to_next_frame_ms"] = round(m20b.RELEASES[-1], 1) if m20b.RELEASES else None
                t1 = time.perf_counter()
                d.key(k.Z, k.MOD_CTRL)
                row["studio_undo_ms"] = round((time.perf_counter() - t1) * 1000, 1)
                t1 = time.perf_counter()
                s.save()
                row["save_ms"] = round((time.perf_counter() - t1) * 1000, 1)
            finally:
                d.close()
        report[str(n)] = row
        print(n, json.dumps(row), flush=True)
    return report


def walks(out: Path) -> dict[str, Any]:
    """Stage 20A's walks (the game's own key events), in the decorated room: over the hill, up the ramp, into the
    cliff, along the valley under the bridge, up the stairs and across, into the pond; then into the boulder."""
    from hd2d_floors_demo import _feet, hold_key

    kept = m20a.open_room
    m20a.open_room = lambda o, name, **kw: open_room(o, name)  # (the same walks, this room)
    try:
        report = m20a.walking(out)
    finally:
        m20a.open_room = kept
    game = open_room(out, "boulder")
    try:
        scene = game.window.hd2d_renderer.settings
        bx, by, _t, _s = scene.scatter["boulder"][0]
        player = m20a._put(game, bx / PX - 2.5, by / PX)
        reached = hold_key(game, player, game.arcade.key.RIGHT, 0, bx / PX + 2.0, 600)
        report["into_the_boulder"] = {"boulder_m": [round(bx / PX, 2), round(by / PX, 2)], "reached": reached,
                                      "stopped_at_m": round(_feet(player)[0], 2)}
    finally:
        game.close()
    return report


def _count(view: Any) -> int:
    layer = view.renderer.scatter if view.renderer is not None else None
    return int(layer.count()) if layer is not None else 0


def _rows(view: Any) -> dict[str, Any]:
    layer = view.renderer.scatter if view.renderer is not None else None
    return dict(layer.instances) if layer is not None else {}


def _paint(project: Any) -> dict[str, Any]:
    return dict(((project.scene().get("settings") or {}).get("hd2d") or {}).get("scatter") or {})


def studio(out: Path) -> dict[str, Any]:
    """A creator scattering in Mesh Studio with its own window events: Meadow drifts along the path in one stroke
    (frames timed, filmed); one undo step, redo, save and reopen exactly; Shift removes, Ctrl thins; Esc, Play, a
    room change, focus loss and a refused upload mid-stroke; the rules (materials off, out of water, off buildings);
    a boulder dropped on the player's start (said); sculpting under scatter (it follows the ground, nothing moves
    sideways, what now breaks its rules is said)."""
    import m18_particles_study as m18
    import m20b_sculpt_study as m20b

    import engine.hd2d.scatter_layer as layer_mod

    out.mkdir(parents=True, exist_ok=True)
    project = m20c.make_project(out, "studio")
    report: dict[str, Any] = {}
    d = m20b._driver(project)
    try:
        s, view, k = d.studio, d.studio.hd2d, d.arcade.key
        d.button("Scatter")
        d.picture(out / "studio_scatter_panel.png")
        m20c._look_at(d, 13.0, 5.5, 27.0)
        undo0 = len(s.project._undo)
        clip: list[Any] = []

        def film(i: int) -> None:
            if i % 3 == 0 and len(clip) < 60:
                clip.append(m18.crop_at(d.frame().convert("RGB"), 590, 360, (720, 405)))

        m20b.RELEASES.clear()
        view.timings["sculpt_ms"].clear()
        frames = m20b._stroke(d, m20c._on_ground(d, _beside(m20c.EARTH_PATH[:8], 1.3, 0.6), 0.08), each=film)
        shown = view.renderer.scatter.instances
        saved = _paint(s.project)
        report["stroke"] = {"frame_ms": m20b._stats(frames), "update_ms": m20b._stats(view.timings["sculpt_ms"]),
                            "commit_ms": round(view.timings["edit_ms"][-1], 1) if view.timings["edit_ms"] else None,
                            "release_to_next_frame_ms": round(m20b.RELEASES[-1], 1) if m20b.RELEASES else None,
                            "undo_steps_added": len(s.project._undo) - undo0, "instances": sum(map(len, saved.values())),
                            "shown_equals_saved": {a: [list(r) for r in sorted(v, key=lambda r: (r[1], r[0], r[2], r[3]))]
                                                   for a, v in shown.items()} == saved,
                            "message": s.message}
        if clip:
            clip[0].save(out / "scatter_stroke.webp", save_all=True, append_images=clip[1:], duration=100, loop=0,
                         quality=80, method=6)
        d.picture(out / "scatter_after.png")
        d.key(k.Z, k.MOD_CTRL)
        report["undo_gives_none"] = _paint(s.project) == {} and _count(view) == 0
        d.key(k.Y, k.MOD_CTRL)
        report["redo_gives_it_back"] = _paint(s.project) == saved
        d.key(k.S, k.MOD_CTRL)
        n_saved = sum(map(len, saved.values()))
        undo_n = len(s.project._undo)
        mid = _beside(m20c.EARTH_PATH[3:7], -1.3, 0.6)

        def unchanged() -> dict[str, bool]:
            return {"nothing_recorded": len(s.project._undo) == undo_n,
                    "scatter_is_saved": _count(view) == n_saved and _paint(s.project) == saved}

        m20b._stroke(d, m20c._on_ground(d, mid, 0.1), release=False)
        added_live = _count(view) - n_saved
        d.key(k.ESCAPE)
        d.window.dispatch_event("on_mouse_release", 600, 300, d.arcade.MOUSE_BUTTON_LEFT, 0)
        d.frame()
        report["escape"] = {"stroke_had_added": added_live, **unchanged(), "message": s.message}
        m20b._stroke(d, m20c._on_ground(d, mid, 0.1), release=False)
        d.key(k.F4)
        d.window.dispatch_event("on_mouse_release", 600, 300, d.arcade.MOUSE_BUTTON_LEFT, 0)
        d.key(k.F4)
        d.frame(3)
        report["play_mid_stroke"] = unchanged()
        m20b._stroke(d, m20c._on_ground(d, mid, 0.1), release=False)
        d.button("Village")
        d.window.dispatch_event("on_mouse_release", 600, 300, d.arcade.MOUSE_BUTTON_LEFT, 0)
        d.frame(2)
        d.button("Hills")
        d.frame(2)
        if view.sculpt is None:
            d.button("Scatter")
        m20c._look_at(d, 13.0, 5.5, 27.0)
        report["room_change_mid_stroke"] = unchanged()
        layer = view.renderer.ensure_scatter()
        kept_apply = layer.apply

        def refusing(*a: Any, **kw: Any) -> Any:
            raise RuntimeError("out of memory (simulated)")

        m20b._stroke(d, m20c._on_ground(d, mid[:3], 0.1), release=False)
        setattr(layer, "apply", refusing)
        try:
            pts = m20c._on_ground(d, mid[3:], 0.1)
            last = d.screen(pts[0])
            for p in pts[1:]:
                s_ = d.screen(p)
                d.window.dispatch_event("on_mouse_drag", s_[0], s_[1], s_[0] - last[0], s_[1] - last[1],
                                        d.arcade.MOUSE_BUTTON_LEFT, 0)
                d.frame()
                last = s_
        finally:
            setattr(layer, "apply", kept_apply)
        d.window.dispatch_event("on_mouse_release", 600, 300, d.arcade.MOUSE_BUTTON_LEFT, 0)
        d.frame(2)
        report["refused_upload"] = {**unchanged(), "message": s.message}
        m20b._stroke(d, m20c._on_ground(d, mid, 0.1), release=False)
        d.window.dispatch_event("on_deactivate")
        held = _count(view)
        d.frame(10)
        report["focus_lost_mid_stroke"] = {"stroke_ended": view.stroke is None,
                                           "undo_steps_added": len(s.project._undo) - undo_n,
                                           "no_more_after": _count(view) == held}
        d.key(k.Z, k.MOD_CTRL)
        d.window.dispatch_event("on_mouse_release", 600, 300, d.arcade.MOUSE_BUTTON_LEFT, 0)
        # Shift removes, Ctrl thins (over the first stroke's drift)
        first = _beside(m20c.EARTH_PATH[:8], 1.3, 0.6)
        n0 = _count(view)
        d.window.dispatch_event("on_key_press", k.LCTRL, 0)
        m20b._stroke(d, m20c._on_ground(d, first[: len(first) // 2], 0.1))
        d.window.dispatch_event("on_key_release", k.LCTRL, 0)
        n1 = _count(view)
        d.window.dispatch_event("on_key_press", k.LSHIFT, 0)
        m20b._stroke(d, m20c._on_ground(d, first[len(first) // 2:], 0.1))
        d.window.dispatch_event("on_key_release", k.LSHIFT, 0)
        report["thin_and_remove"] = {"before": n0, "after_ctrl_thin": n1, "after_shift_remove": _count(view)}
        # rules: grass off (only on earth: the path), so the meadow lands nowhere off the path
        view.set_scatter_rule(toggle_on="earth")  # (earth on, then grass off: one always stays on)
        view.set_scatter_rule(toggle_on="grass")
        before_rows = {(n, tuple(r)) for n, rows in _rows(view).items() for r in rows}
        m20b._stroke(d, m20c._on_ground(d, m20c.EARTH_PATH[2:6], 0.1))  # (along the path)
        new = [r for n, rows in _rows(view).items() for r in rows if (n, tuple(r)) not in before_rows]
        report["materials_only_earth"] = {"on": list(view.sculpt["on"]), "added": len(new),
                                          "all_on_earth": bool(new) and all(
                                              view.renderer.terrain.material_at(x, y) == "earth" for x, y, _t, _s in new)}
        view.set_scatter_rule(collection="Pond edge")
        bx, by, br, _d = m20a.BASIN
        m20c._look_at(d, bx, by, 16.0)
        m20b._stroke(d, m20c._on_ground(d, [(bx - br * 0.6, by + 0.5), (bx, by + br * 0.6)], 0.1))
        from engine import project_ops as ops

        g, _spots, _routes = ops.scatter_context(s.project.scene())
        wet = set()
        for name, rows in _rows(view).items():
            for x, y, _t, _s in rows:
                level, here = g.water(x, y), g.surface(x, y)
                if level is not None and here is not None and here[0] < level - 2:
                    wet.add(name)
        report["out_of_water"] = {"in_water": sorted(wet), "message": s.message}
        d.picture(out / "scatter_pond.png")
        view.set_scatter_rule(collection="Boulder")
        start = s.project.scene("hills")["entities"]
        report["room_at_boulder"] = s.project.current
        player = next(e for e in start if e.get("prefab_id") == "player" or e.get("tag") == "player")
        m20c._look_at(d, player["x"] / PX, player["y"] / PX, 14.0)
        spot = (player["x"] / PX + 0.6, player["y"] / PX)
        d.window.dispatch_event("on_key_press", k.LSHIFT, 0)  # (clear the spot first, as a creator would)
        m20b._stroke(d, m20c._on_ground(d, [spot], 0.1))
        d.window.dispatch_event("on_key_release", k.LSHIFT, 0)
        view.set_sculpt(density=2.0, radius=24.0)
        m20b._stroke(d, m20c._on_ground(d, [spot], 0.1))
        report["boulder_on_the_player_start"] = {"message": s.message, "warned": "In the way" in s.message}
        d.picture(out / "scatter_boulder_warning.png")
        # sculpting under scatter: up with the ground, never sideways; what breaks its rules said
        d.button("Sculpt")
        m20c._look_at(d, 9.0, 6.0, 16.0)
        rows_before = _paint(s.project)
        layer = view.renderer.scatter
        stood = {(x, y): view.renderer.ground_height(x, y) for rows in _rows(view).values() for x, y, _t, _s in rows}
        drawn = {key: id(g) for key, (g, _b) in layer.sprite_draws.items()}
        m20b._stroke(d, m20c._on_ground(d, [(8.0, 6.2), (11.0, 6.6)], 0.1))
        risen = [xy for xy, h in stood.items() if view.renderer.ground_height(*xy) > h + 1.0]
        rebuilt = {key for key, (g, _b) in view.renderer.scatter.sprite_draws.items() if drawn.get(key) != id(g)}
        report["sculpt_under_scatter"] = {
            "instances_unmoved": _paint(s.project) == rows_before, "instances_risen_with_the_ground": len(risen),
            "their_chunks_rebuilt": all(layer_mod._chunk(*xy) in rebuilt for xy in risen),
            "message": s.message}
        d.picture(out / "scatter_after_sculpt.png")
        final = _paint(s.project)
        d.key(k.S, k.MOD_CTRL)
    finally:
        d.close()
    d = m20b._driver(project)
    try:
        report["reopened_same"] = _paint(d.studio.project) == final and (
            d.studio.hd2d.renderer.scatter is not None
            and _count(d.studio.hd2d) == sum(map(len, final.values())))
    finally:
        d.close()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands: dict[str, Any] = {"look": look, "scale": scale, "studio": studio, "walks": walks}
    parser.add_argument("what", choices=list(commands))
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    result = commands[args.what](args.out)
    if result is not None:
        (args.out / f"{args.what}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
