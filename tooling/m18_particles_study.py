"""Milestone 18A evidence: environmental particles in the HD-2D starter village, in Mesh's own renderer (hidden
windows only).

    py -3.13 tooling/m18_particles_study.py proof OUT   # depth and camera proof, screenshots, gameplay clips
    py -3.13 tooling/m18_particles_study.py perf OUT    # the cost: 100 .. 10,000 particles, lifecycle

proof: for rain, snow and wind, the same frame drawn with the particles, without them, and with them but no depth test,
at six places (in front of and behind the cottage, by the player, the hills' cliff, in front of and behind the
bridge). The occlusion map colours each particle pixel: cyan drawn, magenta hidden by what stands in front of it
(buildings, hills, the bridge, characters). Also: a walking clip per preset (1:1 crops: the game's own scale), 4x
close-ups of the pixel art, and the world-anchoring measure (the camera moved, time held still: the particles move
with the world, not with the picture).

perf: rain at 0, 100, 1,000, 5,000, 10,000 and 20,000 particles, snow and wind at 10,000, all three together: frame
cost (CPU update and draw, GPU wait), the particle pass's GPU time (a timer query), draw calls, GPU memory, the
seconds to make a layer; walking with 5,000; shadows on and off; and 200 enable/disable toggles and 20 room changes
(GL objects, Python memory).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
import hd2d_visual_study as study  # noqa: E402
import review_media  # noqa: E402
from hd2d_demo import SCENES, HiddenGame, _gl_counts  # noqa: E402
from hd2d_floors_demo import _feet, hold_key  # noqa: E402

PX = 32.0
CROP = (640, 360)
# name: (description, camera target (x, y, z) m or None to follow the player, player route)
PLACES: dict[str, tuple[str, tuple[float, float, float] | None, list[tuple[str, int, float]]]] = {
    "cottage_front": ("in front of the cottage, the player beside its door", None, [("UP", 1, 8.5), ("LEFT", 0, 11.5)]),
    "behind_cottage": ("behind the cottage (its cutaway open), the player north of it", None,
                       [("RIGHT", 0, 14.0), ("UP", 1, 15.0), ("LEFT", 0, 10.0)]),
    "by_the_player": ("passing by the player, close", None, [("UP", 1, 8.5), ("LEFT", 0, 15.5)]),
    "hills": ("the hills' cliff: particles behind it hidden, above it seen", (10.0, 22.0, 1.5), []),
    "bridge_front": ("in front of the bridge, the player under it", None, [("RIGHT", 0, 20.0), ("UP", 1, 21.0)]),
    "bridge_behind": ("behind the bridge, looking at its deck", (20.0, 26.0, 2.5), []),
}
PRESETS = ("rain", "snow", "wind")


def make_project(out: Path, name: str, effects: list[dict]) -> Path:
    project: Path = study.new_project(out, name, stage6a=False)
    path = project / SCENES / "start.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    scene["settings"]["particles"] = effects
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    return project


def go(game: HiddenGame, route: list[tuple[str, int, float]]) -> None:
    keys = game.arcade.key
    for key, axis, target in route:
        hold_key(game, game.player(), getattr(keys, key), axis, target)
    game.step(60)


def three(game: HiddenGame, target: tuple[float, float, float] | None) -> tuple[Any, Any, Any]:
    """The same frame with the particles, without them, and with them but no depth test."""
    hd = game.window.hd2d_renderer
    layer = hd.particles
    keep = hd.camera.target
    if target is not None:
        hd.camera.target = target
    try:
        wet = game.draw().convert("RGB")
        for i in range(len(layer.effects)):
            layer.set_enabled(i, False)
        dry = game.draw().convert("RGB")
        for i in range(len(layer.effects)):
            layer.set_enabled(i, True)
        layer.depth_test = False
        flat = game.draw().convert("RGB")
        layer.depth_test = True
    finally:
        hd.camera.target = keep
    return wet, dry, flat


def occlusion(wet: Any, dry: Any, flat: Any) -> tuple[Any, dict[str, int]]:
    """``dry`` with each particle pixel marked: cyan where drawn, magenta where depth testing hid it."""
    shown = [a != b for a, b in zip(wet.getdata(), dry.getdata())]
    would = [a != b for a, b in zip(flat.getdata(), dry.getdata())]
    image = dry.copy()
    px = image.load()
    w = image.width
    hidden = 0
    for i, (s, f) in enumerate(zip(shown, would)):
        if s:
            px[i % w, i // w] = (0, 230, 255)
        elif f:
            px[i % w, i // w] = (255, 0, 255)
            hidden += 1
    return image, {"drawn_px": sum(shown), "hidden_by_depth_px": hidden}


def pair(images: list[Any], labels: list[str]) -> Any:
    from PIL import Image, ImageDraw

    w, h = images[0].size
    sheet = Image.new("RGB", (w * len(images) + 8 * (len(images) - 1), h + 20), (20, 22, 28))
    draw = ImageDraw.Draw(sheet)
    for i, (image, label) in enumerate(zip(images, labels)):
        sheet.paste(image, (i * (w + 8), 20))
        draw.text((i * (w + 8) + 4, 4), label, fill=(235, 235, 235))
    return sheet


def crop_at(image: Any, x: float, y: float, size: tuple[int, int] = CROP) -> Any:
    left = min(max(0, round(x - size[0] / 2)), image.width - size[0])
    top = min(max(0, round(y - size[1] / 2)), image.height - size[1])
    return image.crop((left, top, left + size[0], top + size[1]))


def anchoring(game: HiddenGame) -> dict[str, float]:
    """Time held still, the camera moved 0.15 m east: the share of particle pixels found again where the world moved
    (within 3 px: perspective), against where they were on screen (a screen overlay)."""
    hd = game.window.hd2d_renderer
    camera, layer = hd.camera, hd.particles
    base = camera.target

    def frame(dx: float) -> tuple[list[bool], float]:
        camera.target = (base[0] + dx, base[1], base[2])
        for i in range(len(layer.effects)):
            layer.set_enabled(i, False)
        dry = game.draw().convert("RGB")
        for i in range(len(layer.effects)):
            layer.set_enabled(i, True)
        wet = game.draw().convert("RGB")
        vp = camera.view_projection(study.SIZE[0] / study.SIZE[1])
        c = [sum(vp[r][k] * v for k, v in enumerate((base[0], base[1], 2.0, 1.0))) for r in range(4)]
        return [a != b for a, b in zip(wet.getdata(), dry.getdata())], (c[0] / c[3] * 0.5 + 0.5) * study.SIZE[0]

    try:
        (a, xa), (b, xb) = frame(0.0), frame(0.15)
    finally:
        camera.target = base
    shift, w = round(xb - xa), study.SIZE[0]

    def overlap(dx: int, slack: int = 3) -> float:
        hits = total = 0
        for i, on in enumerate(a):
            x = i % w + dx
            if on and slack <= x < w - slack:
                total += 1
                hits += any(b[i - i % w + x + d] for d in range(-slack, slack + 1))
        return hits / max(1, total)

    return {"world_shift_px": shift, "found_where_the_world_moved": round(overlap(shift), 3),
            "found_where_they_were_on_screen": round(overlap(0), 3)}


def proof(out: Path) -> dict[str, Any]:
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"places": {k: v[0] for k, v in PLACES.items()}, "presets": {}}
    for preset in PRESETS:
        project = make_project(out, f"proj_{preset}", [{"preset": preset, "seed": 11}])
        game = HiddenGame(project, size=study.SIZE)
        result: dict[str, Any] = {}
        try:
            for place, (_text, target, route) in PLACES.items():
                game.load(f"{SCENES}/start.json")
                game.step(60)
                go(game, route)
                wet, dry, flat = three(game, target)
                marked, counts = occlusion(wet, dry, flat)
                wet.save(out / f"{preset}_{place}.png")
                marked.save(out / f"{preset}_{place}_occlusion.png")
                result[place] = counts
            # the camera follows the player: a walk east along the path, filmed at 1:1 (the game's own scale)
            game.load(f"{SCENES}/start.json")
            game.step(60)
            go(game, [("UP", 1, 8.5), ("LEFT", 0, 9.0)])
            clip = []
            walk = study.Walk(game, out, preset)

            def film() -> None:
                if len(walk.track) % 3 == 0:
                    fx, fy = _feet(game.player())
                    sx, sy = walk._screen(fx, fy, 0.8)
                    clip.append(crop_at(game.draw().convert("RGB"), sx, study.SIZE[1] - sy))
                walk.track.append(1)

            hold_key(game, game.player(), game.arcade.key.RIGHT, 0, 17.0, 600, each_frame=film)
            review_media.save_clip(clip, out / f"{preset}_walk.webp", duration=50, quality=90)
            result["walk_frames"] = len(clip)
            result["anchoring"] = anchoring(game)
            # pixel art: the player and the cottage close up, 4x without filtering
            game.load(f"{SCENES}/start.json")
            game.step(60)
            go(game, PLACES["cottage_front"][2])
            image = game.draw().convert("RGB")
            fx, fy = _feet(game.player())
            sx, sy = walk._screen(fx, fy, 0.8)
            close = crop_at(image, sx - 60, study.SIZE[1] - sy, (240, 160)).resize((960, 640), Image.Resampling.NEAREST)
            close.save(out / f"{preset}_close_4x.png")
        finally:
            game.close()
        report["presets"][preset] = result
        for place in PLACES:
            pair([Image.open(out / f"{preset}_{place}.png"), Image.open(out / f"{preset}_{place}_occlusion.png")],
                 [f"{preset}: {place}", "cyan drawn, magenta hidden by depth (it stands behind something)"]
                 ).save(out / f"compare_{preset}_{place}.png")
    (out / "proof.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def gpu_ms(game: HiddenGame, frames: int = 60) -> dict[str, float]:
    """The particle pass's GPU time and the whole frame's, from timer queries (median, ms). Timer queries can't nest,
    so the two are measured in separate runs of frames."""
    ctx, hd = game.window.ctx, game.window.hd2d_renderer
    layer = hd.particles
    whole: list[float] = []
    for _ in range(frames):
        game.window.dispatch_event("on_update", 1 / 60)
        query = ctx.query(samples=False, primitives=False)
        with query:
            game.window.dispatch_event("on_draw")
        ctx.finish()
        whole.append(query.time_elapsed / 1e6)
    parts: list[float] = []
    if layer is not None:
        original = layer.draw_3d

        def timed(*args: Any, **kwargs: Any) -> Any:
            query = ctx.query(samples=False, primitives=False)
            with query:
                result = original(*args, **kwargs)
            ctx.finish()
            parts.append(query.time_elapsed / 1e6)
            return result

        layer.draw_3d = timed
        try:
            for _ in range(frames):
                game.window.dispatch_event("on_update", 1 / 60)
                game.window.dispatch_event("on_draw")
        finally:
            del layer.draw_3d
    return {"particle_pass_gpu_ms": round(statistics.median(parts), 3) if parts else 0.0,
            "frame_gpu_ms": round(statistics.median(whole), 3)}


def _rounds(game: HiddenGame, layer_on: Any, rounds: int = 5, frames: int = 60) -> dict[str, Any]:
    """Interleaved rounds in one game: the frame with the particles drawn, then without (the layer kept, switched off),
    so the machine's own drift (clocks, warm-up) falls on both alike. Medians of the rounds."""
    on: dict[str, list[float]] = {"frame_ms": [], "draw_cpu_ms": [], "frame_gpu_ms": [], "particle_pass_gpu_ms": []}
    off: dict[str, list[float]] = {"frame_ms": [], "draw_cpu_ms": [], "frame_gpu_ms": []}
    for _ in range(rounds):
        for enabled, into in ((True, on), (False, off)):
            layer_on(enabled)
            cost = study.frame_cost(game, frames)
            gpu = gpu_ms(game, frames // 2)
            into["frame_ms"].append(cost["frame_ms"])
            into["draw_cpu_ms"].append(cost["draw_cpu_ms"])
            into["frame_gpu_ms"].append(gpu["frame_gpu_ms"])
            if enabled:
                into["particle_pass_gpu_ms"].append(gpu["particle_pass_gpu_ms"])
    layer_on(True)
    med = statistics.median
    out = {f"{k}_on": round(med(v), 3) for k, v in on.items()}
    out.update({f"{k}_off": round(med(v), 3) for k, v in off.items()})
    out["added_frame_ms"] = round(out["frame_ms_on"] - out["frame_ms_off"], 3)
    out["added_frame_gpu_ms"] = round(out["frame_gpu_ms_on"] - out["frame_gpu_ms_off"], 3)
    return out


def _room_changes(game: HiddenGame, times: int = 20) -> dict[str, Any]:
    ctx = game.window.ctx
    ctx.gc()
    before = _gl_counts(ctx)
    tracemalloc.start()
    snap = tracemalloc.take_snapshot()
    for _ in range(times):
        game.load(f"{SCENES}/cottage.json")
        game.step(3)
        game.window.dispatch_event("on_draw")
        game.load(f"{SCENES}/start.json")
        game.step(3)
        game.window.dispatch_event("on_draw")
    ctx.gc()
    grown = sum(s.size_diff for s in tracemalloc.take_snapshot().compare_to(snap, "filename"))
    tracemalloc.stop()
    return {"gl_before": before, "gl_after": _gl_counts(ctx), "python_heap_growth_kb": round(grown / 1024, 1)}


def perf(out: Path) -> dict[str, Any]:
    from engine.scene_particles import parse_particles

    out.mkdir(parents=True, exist_ok=True)
    cases: dict[str, list[dict]] = {f"rain_{n}": [{"preset": "rain", "count": n}] for n in (100, 1000, 5000, 10000, 20000)}
    cases.update({"snow_10000": [{"preset": "snow", "count": 10000}], "wind_10000": [{"preset": "wind", "count": 10000}],
                  "all_three_10000": [{"preset": "rain", "count": 6000}, {"preset": "snow", "count": 2000},
                                      {"preset": "wind", "count": 2000}]})
    report: dict[str, Any] = {"method": "one game; per case the renderer's particles set, then 5 interleaved rounds "
                                        "of 60 frames with them drawn and switched off (medians)", "cases": {}}
    project = make_project(out, "proj", [])
    game = HiddenGame(project, size=study.SIZE)
    try:
        ctx = game.window.ctx
        report["gpu"] = {"renderer": ctx.info.RENDERER, "vendor": ctx.info.VENDOR, "gl_version": list(ctx.gl_version)}
        game.load(f"{SCENES}/start.json")
        game.step(60)
        go(game, PLACES["cottage_front"][2])
        hd = game.window.hd2d_renderer
        for name, effects in cases.items():
            t = time.perf_counter()
            hd.set_particles(parse_particles(effects))
            make_ms = (time.perf_counter() - t) * 1000
            layer = hd.particles

            def switch(on: bool, layer: Any = layer) -> None:
                for i in range(len(layer.effects)):
                    layer.set_enabled(i, on)

            game.window.dispatch_event("on_draw")
            stats = hd.stats()
            row = {"particles": stats["particles"], "particle_bytes": stats["particle_bytes"],
                   "draw_calls": stats["draw_calls"], "shadow_draws": stats["shadow_draws"],
                   "make_layer_ms": round(make_ms, 2), **_rounds(game, switch)}
            report["cases"][name] = row
            print(name, {k: row[k] for k in ("added_frame_ms", "particle_pass_gpu_ms_on", "added_frame_gpu_ms",
                                             "draw_calls", "particle_bytes", "make_layer_ms")}, flush=True)
        # the camera following the player: walking east and west with 5,000 raindrops, drawn and switched off
        hd.set_particles(parse_particles([{"preset": "rain", "count": 5000}]))
        keys = game.arcade.key
        walking: dict[str, list[float]] = {"on": [], "off": []}
        for i in range(6):
            key = keys.RIGHT if i % 2 == 0 else keys.LEFT
            for on in (True, False):
                hd.particles.set_enabled(0, on)
                game.window.dispatch_event("on_key_press", key, 0)
                walking["on" if on else "off"].append(study.frame_cost(game, 40)["frame_ms"])
                game.window.dispatch_event("on_key_release", key, 0)
        hd.particles.set_enabled(0, True)
        report["walking_rain_5000"] = {k: round(statistics.median(v), 3) for k, v in walking.items()}
        hd.lighting.enabled = False
        report["shadows_off_rain_5000_frame_ms"] = study.frame_cost(game, 120)["frame_ms"]
        hd.lighting.enabled = True
        # the GPU objects (counted after a GL garbage collection): one layer live, 200 enable/disable toggles (nothing
        # is made or freed), released, then 20 layers made and released
        hd.set_particles(())
        ctx.gc()
        life: dict[str, Any] = {"none": _gl_counts(ctx)}
        hd.set_particles(parse_particles([{"preset": "rain", "count": 5000}]))
        game.window.dispatch_event("on_draw")
        ctx.gc()
        life["one_layer"] = _gl_counts(ctx)
        for i in range(200):
            hd.particles.set_enabled(0, i % 2 == 1)
            game.window.dispatch_event("on_draw")
        ctx.gc()
        life["after_200_toggles"] = _gl_counts(ctx)
        hd.set_particles(())
        ctx.gc()
        life["released"] = _gl_counts(ctx)
        for _ in range(20):
            hd.set_particles(parse_particles(cases["all_three_10000"]))
            game.window.dispatch_event("on_draw")
            hd.set_particles(())
        ctx.gc()
        life["after_20_made_and_released"] = _gl_counts(ctx)
        report["gl_lifecycle"] = life
    finally:
        game.close()
    for label, effects in (("no_particles", []), ("all_three", cases["all_three_10000"])):  # 20 room changes each
        game = HiddenGame(make_project(out, f"proj_{label}", effects), size=study.SIZE)
        try:
            game.load(f"{SCENES}/start.json")
            game.step(30)
            report[f"room_changes_{label}"] = _room_changes(game)
        finally:
            game.close()
    (out / "perf.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["proof", "perf"])
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    report = proof(args.out) if args.command == "proof" else perf(args.out)
    print(json.dumps(report if args.command == "perf" else {p: {k: v for k, v in r.items()}
                                                              for p, r in report["presets"].items()}, indent=1))


if __name__ == "__main__":
    main()
