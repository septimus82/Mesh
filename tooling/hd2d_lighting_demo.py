"""HD-2D lighting checks and benchmark (Milestone 16 Stage 4), in a hidden window.

    py -3.13 tooling/hd2d_lighting_demo.py check FLOORS_PROJECT OUT_DIR   # the lit crossing (hd2d_floors_demo build)
    py -3.13 tooling/hd2d_lighting_demo.py bench VILLAGE_PROJECT OUT_DIR  # 20 buildings (hd2d_demo build)
    py -3.13 tooling/hd2d_lighting_demo.py studio FLOORS_PROJECT OUT_DIR  # play-test the lit room in Mesh Studio

``check`` proves the shadows geometric rather than trusting a picture: for every spot a character can stand on
(a 0.5 m grid over the crossing's floors) it asks the GPU how much sunlight, and how much of each lamp's light,
arrives there with shadows on and off (``Lighting.probe``: the scene's own shader functions and shadow maps), and
casts the same rays on the CPU through the crossing's actual triangles. Spots whose CPU answer is unambiguous
(the same for small shifts of the spot) must agree. It also walks the player (held arrow keys) under the bridge
and into the open and measures the light on it, follows the warden between light and shade, checks that a
shadow stays put when the camera moves, and saves comparable pictures with shadows on and off.

``bench`` draws the village of 20 separate buildings with 0 to 8 lamps (2 casting shadows), shadows on and off,
at shadow resolutions 1024 to 4096: CPU and GPU time, draw calls and shadow passes, shadow-map memory; and checks
that frames allocate no GPU objects.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
from hd2d_demo import SCENES, HiddenGame  # noqa: E402
from hd2d_floors_demo import _feet, hold_key  # noqa: E402

PX = 32.0
Vec = tuple[float, float, float]


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------- CPU rays through the real triangles
class Triangles:
    """The room's structures' drawn triangles (world metres), grouped per part with a bounding box."""

    def __init__(self, renderer: Any) -> None:
        from engine.hd2d.renderer import _placement

        self.parts: list[tuple[Vec, Vec, list[tuple[Vec, Vec, Vec]]]] = []
        for st in renderer.settings.structures:
            m = _placement(st.x / PX, st.y / PX, st.elevation / PX, st.rotation, st.scale)
            for part in renderer.models[st.model].parts:
                v = part.vertices
                pts: list[Vec] = []
                for i in range(0, len(v), 8):
                    x, y, z = v[i], v[i + 1], v[i + 2]
                    pts.append((m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
                                m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
                                m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3]))
                tris = [(pts[part.indices[i]], pts[part.indices[i + 1]], pts[part.indices[i + 2]])
                        for i in range(0, len(part.indices), 3)]
                lo = (min(p[0] for p in pts), min(p[1] for p in pts), min(p[2] for p in pts))
                hi = (max(p[0] for p in pts), max(p[1] for p in pts), max(p[2] for p in pts))
                self.parts.append((lo, hi, tris))

    def blocked(self, origin: Vec, direction: Vec, length: float) -> bool:
        for lo, hi, tris in self.parts:
            if not _slab(origin, direction, length, lo, hi):
                continue
            for a, b, c in tris:
                if _hit(origin, direction, length, a, b, c):
                    return True
        return False


def _slab(o: Vec, d: Vec, t_max: float, lo: Vec, hi: Vec) -> bool:
    t0, t1 = 0.0, t_max
    for k in range(3):
        if abs(d[k]) < 1e-12:
            if o[k] < lo[k] - 1e-6 or o[k] > hi[k] + 1e-6:
                return False
            continue
        a, b = (lo[k] - o[k]) / d[k], (hi[k] - o[k]) / d[k]
        t0, t1 = max(t0, min(a, b)), min(t1, max(a, b))
        if t0 > t1:
            return False
    return True


def _hit(o: Vec, d: Vec, t_max: float, a: Vec, b: Vec, c: Vec) -> bool:
    """Moller-Trumbore."""
    e1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    e2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    p = (d[1] * e2[2] - d[2] * e2[1], d[2] * e2[0] - d[0] * e2[2], d[0] * e2[1] - d[1] * e2[0])
    det = e1[0] * p[0] + e1[1] * p[1] + e1[2] * p[2]
    if abs(det) < 1e-12:
        return False
    inv = 1.0 / det
    s = (o[0] - a[0], o[1] - a[1], o[2] - a[2])
    u = (s[0] * p[0] + s[1] * p[1] + s[2] * p[2]) * inv
    if u < 0.0 or u > 1.0:
        return False
    q = (s[1] * e1[2] - s[2] * e1[1], s[2] * e1[0] - s[0] * e1[2], s[0] * e1[1] - s[1] * e1[0])
    v = (d[0] * q[0] + d[1] * q[1] + d[2] * q[2]) * inv
    if v < 0.0 or u + v > 1.0:
        return False
    t = (e2[0] * q[0] + e2[1] * q[1] + e2[2] * q[2]) * inv
    return 1e-4 < t < t_max


JITTER = ((0.0, 0.0), (0.12, 0.0), (-0.12, 0.0), (0.0, 0.12), (0.0, -0.12))  # m: a spot is unambiguous if all agree


def _cpu_sun(tris: Triangles, p: Vec, sun: Vec) -> bool | None:
    """True: in the sun; False: shaded; None: near a shadow's edge (shifts disagree)."""
    seen = {not tris.blocked((p[0] + dx, p[1] + dy, p[2] + 0.05), sun, 80.0) for dx, dy in JITTER}
    return seen.pop() if len(seen) == 1 else None


def _cpu_lamp(tris: Triangles, p: Vec, lamp: Vec) -> bool | None:
    seen = set()
    for dx, dy in JITTER:
        o = (p[0] + dx, p[1] + dy, p[2] + 0.05)
        d = (lamp[0] - o[0], lamp[1] - o[1], lamp[2] - o[2])
        n = math.sqrt(sum(c * c for c in d))
        seen.add(not tris.blocked(o, (d[0] / n, d[1] / n, d[2] / n), n - 0.05))
    return seen.pop() if len(seen) == 1 else None


def _lum(c: tuple[float, float, float]) -> float:
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


# ---------------------------------------------------------------------- check
def check(project: Path, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    game = HiddenGame(project)
    keys = game.arcade.key
    report: dict[str, Any] = {}
    try:
        game.load(f"{SCENES}/start.json")
        game.step(60)
        hd, world = game.window.hd2d_renderer, game.window.hd2d_world
        light = hd.lighting
        report["lights"] = {"lamps": len(light.lamps), "shadow_lamps": sum(1 for s in light.lamp_slots if s >= 0),
                            "softness": hd.settings.shadow_softness, "pcf_radius": light.pcf,
                            "sun": [round(v, 3) for v in light.sun], "shadow_resolution": hd.settings.shadow_resolution}
        game.draw()  # shadow maps drawn
        light.render_shadows(hd.static, None, [])  # the sun's map without characters: structures only (CPU twin)
        tris = Triangles(hd)
        # -- every standable spot on a 0.5 m grid over the crossing
        spots: list[tuple[float, float, float, str]] = []
        x = 6.25
        while x < 26.0:
            y = 2.25
            while y < 19.0:
                for h, surface in world.heights_at(x, y):
                    if world.stand(x, y, h, 0.05, 0.05) is not None:
                        spots.append((x, y, h, surface.floor))
                y += 0.5
            x += 0.5
        points = [(sx, sy, sz, 0.0, 0.0, 1.0, False) for sx, sy, sz, _ in spots]
        on_sun = light.probe(points, (0.0, 1.0, 0.0))
        on_lamps = light.probe(points, (0.0, 0.0, 1.0))
        light.enabled = False
        off_sun = light.probe(points, (0.0, 1.0, 0.0))
        off_lamps = light.probe(points, (0.0, 0.0, 1.0))
        light.enabled = True
        t = time.perf_counter()
        sun_stats: dict[str, Any] = {"agree": 0, "disagree": 0, "edge_skipped": 0, "shaded": 0, "lit": 0, "by_floor": {}}
        mismatches = []
        for i, (sx, sy, sz, floor) in enumerate(spots):
            cpu = _cpu_sun(tris, (sx, sy, sz), light.sun)
            lit_off = _lum(off_sun[i])
            if cpu is None or lit_off < 0.05:  # an edge, or a surface turned from the sun (no sunlight to shade)
                sun_stats["edge_skipped"] += 1
                continue
            ratio = _lum(on_sun[i]) / lit_off
            gpu = True if ratio > 0.7 else False if ratio < 0.3 else None
            key = "lit" if cpu else "shaded"
            sun_stats[key] += 1
            per = sun_stats["by_floor"].setdefault(floor.split("/")[-1], {"lit": 0, "shaded": 0})
            per[key] += 1
            if gpu == cpu:
                sun_stats["agree"] += 1
            else:
                sun_stats["disagree"] += 1
                mismatches.append([round(sx, 2), round(sy, 2), round(sz, 2), round(ratio, 3), cpu])
        lamp_stats: dict[str, Any] = {}
        for li, lamp in enumerate(light.lamps):
            if light.lamp_slots[li] < 0:
                continue
            lp = light._lamp_pos(lamp)
            r = lamp.radius / PX
            st: dict[str, Any] = {"agree": 0, "disagree": 0, "edge_skipped": 0, "blocked": 0, "reached": 0, "mismatches": []}
            for i, (sx, sy, sz, _floor) in enumerate(spots):
                d = math.dist((sx, sy, sz), lp)
                lit_off = _lum(off_lamps[i])
                if d > r * 0.9 or lit_off < 0.02 or lp[2] <= sz + 0.05:
                    continue  # out of reach, too faint to judge, or the lamp below the surface
                cpu = _cpu_lamp(tris, (sx, sy, sz), lp)
                if cpu is None:
                    st["edge_skipped"] += 1
                    continue
                ratio = _lum(on_lamps[i]) / lit_off
                gpu = True if ratio > 0.7 else False if ratio < 0.3 else None
                st["reached" if cpu else "blocked"] += 1
                if gpu == cpu:
                    st["agree"] += 1
                else:
                    st["disagree"] += 1
                    st["mismatches"].append([round(sx, 2), round(sy, 2), round(sz, 2), round(ratio, 3), cpu])
            st["mismatches"] = st["mismatches"][:10]
            lamp_stats[f"lamp{li}"] = st
        report["geometric_agreement"] = {"spots": len(spots), "sun": sun_stats, "sun_mismatches": mismatches[:10],
                                         "lamps": lamp_stats, "cpu_seconds": round(time.perf_counter() - t, 1)}

        # -- named cases (probe: total light, shadows on and off)
        def probe_both(pts: list[tuple]) -> list[list[float]]:
            on = light.probe(pts)
            light.enabled = False
            off = light.probe(pts)
            light.enabled = True
            return [[round(_lum(a), 4), round(_lum(b), 4)] for a, b in zip(on, off)]

        hut_lamp = light._lamp_pos(light.lamps[1])
        report["cases"] = {
            # [on, off] luminance of the light arriving (ground and floors face up)
            "underpass_ground_in_the_deck_shadow (16, 10.8)": probe_both([(16.0, 10.8, 0.0, 0, 0, 1, False)])[0],
            "east_platform_in_the_hut_shadow (20, 11.5)": probe_both([(20.0, 11.5, 2.0, 0, 0, 1, False)])[0],
            "open_ground (16, 5)": probe_both([(16.0, 5.0, 0.0, 0, 0, 1, False)])[0],
            "ground_in_west_platform_shadow (6.2, 11)": probe_both([(6.2, 11.0, 0.0, 0, 0, 1, False)])[0],
            "east_platform_open (20, 9.5)": probe_both([(20.0, 9.5, 2.0, 0, 0, 1, False)])[0],
            "east_platform_behind_hut_from_lamp (24.5, 13.5)": probe_both([(24.5, 13.5, 2.0, 0, 0, 1, False)])[0],
            "hut_lamp_term_behind_hut (on, off)": [round(_lum(c), 4) for c in (
                light.probe([(24.5, 13.5, 2.0, 0, 0, 1, False)], (0.0, 0.0, 1.0))[0],)] + [
                round(_lum(_off_probe(light, (24.5, 13.5, 2.0), (0.0, 0.0, 1.0))), 4)],
            "hut_lamp_term_in_front (on, off)": [round(_lum(c), 4) for c in (
                light.probe([(19.5, 11.0, 2.0, 0, 0, 1, False)], (0.0, 0.0, 1.0))[0],)] + [
                round(_lum(_off_probe(light, (19.5, 11.0, 2.0), (0.0, 0.0, 1.0))), 4)],
            "hut_lamp_position_m": [round(v, 2) for v in hut_lamp],
        }
        game.draw()  # back to the sun map with characters

        # -- the player under the bridge and in the open: the light on it, and its drawn pixels
        player = game.player()

        def on_player(tag: str) -> dict[str, Any]:
            fx, fy = _feet(player)
            z = player.mesh_entity_data.get("elevation", 0.0) / PX
            heights = (0.2, 0.75, 1.3)  # feet, middle, head (m above its floor)
            pts = [(player.center_x / PX, player.bottom / PX, z + h, 0.0, -1.0, 0.0, True) for h in heights]
            game.draw()
            on = [round(_lum(c), 4) for c in light.probe(pts)]
            pixels_on = _sprite_brightness(hd, player)
            light.enabled = False
            game.draw()
            off = [round(_lum(c), 4) for c in light.probe(pts)]
            pixels_off = _sprite_brightness(hd, player)
            light.enabled = True
            game.draw().convert("RGB").save(out / f"player_{tag}.png")
            return {"feet_m": [round(fx, 2), round(fy, 2)], "elevation_m": round(z, 2), "light_on": on,
                    "light_off": off, "pixels_mean_on": pixels_on, "pixels_mean_off": pixels_off}

        hold_key(game, player, keys.UP, 1, 5.0)
        report["player_open"] = on_player("open")
        hold_key(game, player, keys.UP, 1, 12.0)
        report["player_under_bridge"] = on_player("under_bridge")
        hold_key(game, player, keys.DOWN, 1, 3.0)
        hold_key(game, player, keys.LEFT, 0, 10.0)
        hold_key(game, player, keys.UP, 1, 11.5)
        hold_key(game, player, keys.RIGHT, 0, 16.0)
        report["player_on_bridge"] = on_player("on_bridge")

        # -- a shadow stays where it is when the camera moves (world-space maps)
        report["camera_moves"] = _camera_invariance(game, hd)

        # -- the warden: walks between sun, lamp light and the underpass's shade
        warden = game.sprite("Warden")
        seen = []
        for frame in range(60 * 40):
            game.step(1)
            if frame % 15 == 0:
                game.draw()
                z = warden.mesh_entity_data.get("elevation", 0.0) / PX
                c = light.probe([(warden.center_x / PX, warden.bottom / PX, z + 0.75, 0.0, -1.0, 0.0, True)])[0]
                seen.append([round(warden.center_x / PX, 1), round(warden.bottom / PX, 1), round(z, 2), round(_lum(c), 4)])
        lums = [s[3] for s in seen]
        report["warden"] = {"samples": len(seen), "light_min": min(lums), "light_max": max(lums),
                            "track": seen[::4]}

        # -- comparable pictures, shadows on / off
        views = {"overview": ((16.0, 10.0, 1.0), 26.0), "underpass": ((16.0, 11.0, 1.0), 13.0),
                 "hut_lamp": ((22.0, 12.0, 2.5), 13.0), "stairs_lamp": ((10.0, 6.0, 1.0), 12.0)}
        saved: dict[str, list[str]] = {}
        for name, (target, distance) in views.items():
            for enabled in (True, False):
                light.enabled = enabled
                hd.camera.target, hd.camera.distance = target, distance
                image = _draw_fixed(game, hd)
                path = f"{name}_{'shadows' if enabled else 'no_shadows'}.png"
                image.convert("RGB").save(out / path)
                saved.setdefault(name, []).append(path)
        light.enabled = True
        hd.camera.distance = hd.settings.camera.distance
        report["pictures"] = saved
        report["stats"] = hd.stats()
    finally:
        game.close()
    _write(out / "check.json", report)
    return report


def _off_probe(light: Any, p: Vec, terms: tuple[float, float, float]) -> tuple[float, float, float]:
    light.enabled = False
    try:
        r, g, b = light.probe([(p[0], p[1], p[2], 0.0, 0.0, 1.0, False)], terms)[0]
        return (float(r), float(g), float(b))
    finally:
        light.enabled = True


def _draw_fixed(game: Any, hd: Any) -> Any:
    """Draw with the camera where it was put (no following for this frame)."""
    follow = hd.update
    hd.update = lambda dt: None
    try:
        return game.draw()
    finally:
        hd.update = follow


def _sprite_brightness(hd: Any, sprite: Any) -> float:
    """Mean luminance (0..255) of the sprite's visible drawn pixels: its mask from a flat draw, its colours from
    the real one."""
    mask = hd.draw(solid=sprite, read=True)
    real = hd.draw(read=True)
    total, n = 0.0, 0
    for i in range(0, len(mask), 3):
        if mask[i] > 200 and mask[i + 1] < 60:
            total += 0.2126 * real[i] + 0.7152 * real[i + 1] + 0.0722 * real[i + 2]
            n += 1
    return round(total / n, 2) if n else 0.0


def _camera_invariance(game: Any, hd: Any) -> dict[str, Any]:
    """Two world spots (one in the bridge's shadow, one in the sun), drawn from two camera positions: each spot's
    drawn colour must not change (shadow maps are in the world, not on the screen)."""
    spots = {"shaded (16, 11.4, 0)": (16.0, 11.4, 0.0), "sunny (16, 7, 0)": (16.0, 7.0, 0.0)}
    out: dict[str, Any] = {}
    for target in ((16.0, 9.0, 1.0), (13.0, 7.0, 1.0)):
        hd.camera.target = target
        follow = hd.update
        hd.update = lambda dt: None
        try:
            game.draw()
            pixels = hd.draw(read=True)
        finally:
            hd.update = follow
        w, h = hd._fbo.size
        vp = hd.camera.view_projection(w / h)
        for name, p in spots.items():
            c = [sum(vp[r][k] * (p[k] if k < 3 else 1.0) for k in range(4)) for r in range(4)]
            sx, sy = int((c[0] / c[3] * 0.5 + 0.5) * w), int((c[1] / c[3] * 0.5 + 0.5) * h)
            i = (sy * w + sx) * 3
            out.setdefault(name, []).append({"camera_target": list(target), "screen": [sx, sy],
                                             "rgb": list(pixels[i:i + 3])})
    return out


# ---------------------------------------------------------------------- Studio's play-test
def studio_play(project: Path, out: Path) -> dict[str, Any]:
    """Open the lit room in Mesh Studio (hidden), play-test it (Studio's own Play), draw, stop: the HD-2D renderer
    and its shadows run inside Studio's play-test, and editing afterwards still works."""
    from engine.studio import open_studio

    out.mkdir(parents=True, exist_ok=True)
    game = HiddenGame(project, size=(1280, 720))
    report: dict[str, Any] = {}
    try:
        game.load(f"{SCENES}/start.json")
        studio = open_studio(game.window, project, "packs/core_regions/worlds/main.json", f"{SCENES}/start.json")
        assert studio is not None
        game.step(5)
        game.draw().convert("RGB").save(out / "studio_edit.png")
        studio.play()
        game.step(60)
        image = game.draw()
        image.convert("RGB").save(out / "studio_play.png")
        hd = game.window.hd2d_renderer
        report["play"] = {"mode": studio.mode, "hd2d": hd is not None, "shadows": bool(hd and hd.lighting.enabled),
                          "shadow_draws": hd.lighting.shadow_draws if hd else 0, "lamps": len(hd.lighting.lamps) if hd else 0}
        studio.stop()
        game.step(5)
        game.draw().convert("RGB").save(out / "studio_after_stop.png")
        report["after_stop"] = {"mode": studio.mode}
    finally:
        game.close()
    _write(out / "studio.json", report)
    return report


# ---------------------------------------------------------------------- bench
def bench(project: Path, out: Path, frames: int = 120) -> dict[str, Any]:
    from engine.hd2d.renderer import Hd2dRenderer
    from engine.hd2d.settings import PointLight, parse_hd2d
    from engine.paths import resolve_path

    out.mkdir(parents=True, exist_ok=True)
    game = HiddenGame(project, size=(1280, 720))
    ctx = game.window.ctx
    result: dict[str, Any] = {"runs": []}
    try:
        game.load(f"{SCENES}/village.json")
        game.step(60)
        base = parse_hd2d(game.window.scene_controller.scene_settings["hd2d"], map_size_px=(1536, 1024))
        base = dataclasses.replace(base, sun=(0.35, 0.5, 0.79), ambient=0.35, shadow_softness="soft")
        game.window.hd2d_renderer.release()
        lamps_all = [PointLight(160.0 + 320.0 * (i % 4) + 96, 128.0 + 256.0 * (i // 4) - 80, 56.0, 224.0,
                                (1.0, 0.7, 0.4) if i % 2 else (0.4, 0.6, 1.0), 1.5, i < 2) for i in range(8)]
        configs = [("shadows off, 0 lamps", False, 0, 2048), ("shadows on, 0 lamps", True, 0, 2048),
                   ("shadows on, 1 lamp", True, 1, 2048), ("shadows on, 2 lamps", True, 2, 2048),
                   ("shadows on, 4 lamps", True, 4, 2048), ("shadows on, 8 lamps", True, 8, 2048),
                   ("shadows off, 8 lamps", False, 8, 2048), ("shadows on, 2 lamps, 1024", True, 2, 1024),
                   ("shadows on, 2 lamps, 4096", True, 2, 4096)]
        query = ctx.query(time=True, samples=False, primitives=False)
        for name, shadows, n_lamps, res in configs:
            settings = dataclasses.replace(base, shadows=shadows, lights=tuple(lamps_all[:n_lamps]), shadow_resolution=res)
            renderer = Hd2dRenderer(game.window, settings, resolve_path)
            game.window.hd2d_renderer = renderer
            renderer.camera.distance = 40.0  # the whole village in view
            t = time.perf_counter()
            renderer.draw()  # the first frame draws the lamps' shadow maps (once)
            ctx.finish()
            first_ms = (time.perf_counter() - t) * 1000
            for _ in range(10):
                renderer.draw()
            ctx.finish()
            before = {k: getattr(ctx.stats, k)[0] for k in ("buffer", "texture", "framebuffer", "geometry")}
            cpu, gpu = [], []
            for _ in range(frames):
                t = time.perf_counter()
                with query:
                    renderer.draw()
                cpu.append((time.perf_counter() - t) * 1000)
                gpu.append(query.time_elapsed / 1e6)
            created = {k: getattr(ctx.stats, k)[0] - before[k] for k in before}
            stats = renderer.stats()
            result["runs"].append({
                "config": name, "cpu_ms_median": round(statistics.median(cpu), 3),
                "cpu_ms_p95": round(sorted(cpu)[int(frames * 0.95)], 3), "gpu_ms_median": round(statistics.median(gpu), 3),
                "first_frame_ms": round(first_ms, 2), "draw_calls": stats["draw_calls"], "shadow_draws": stats["shadow_draws"],
                "shadow_map_mib": round(stats["shadow_map_bytes"] / 2 ** 20, 2), "lamps": stats["lamps"],
                "shadow_lamps": stats["shadow_lamps"], "gpu_objects_created_during_frames": created})
            if name == "shadows on, 8 lamps":
                renderer.draw()
                game.arcade.get_image(0, 0, 1280, 720).convert("RGB").save(out / "village_lit.png")
            renderer.release()
            game.window.hd2d_renderer = None
            ctx.gc()
        result["structures"] = len(base.structures)
        result["frames"] = frames
        result["gl"] = {"renderer": ctx.info.RENDERER, "version": ctx.gl_version}
    finally:
        game.close()
    _write(out / "bench.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["check", "bench", "studio"])
    parser.add_argument("project", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    run = {"check": check, "bench": bench, "studio": studio_play}[args.command]
    print(json.dumps(run(args.project.resolve(), args.out.resolve()), indent=1, default=str))
