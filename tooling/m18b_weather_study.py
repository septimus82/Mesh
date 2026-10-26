"""Milestone 18B evidence: rain and snow meeting the HD-2D starter village (hidden windows only).

    py -3.13 tooling/m18b_weather_study.py proof OUT   # shelter and impacts, judged in world space; pictures
    py -3.13 tooling/m18b_weather_study.py pictures OUT  # top-down shelter maps, 18A beside 18B, a pan, Studio
    py -3.13 tooling/m18b_weather_study.py perf OUT    # the cost against Stage 18A's; maps, lifecycle, failures

The proof doesn't trust pictures for shelter: a drop hidden behind a roof looks the same as a drop stopped by it.
A probe draws the particles (no depth test: the camera's occlusion can't hide anything) top-down into a float target
in the shader's diagnostics mode, which writes each particle's world position and id, and whether it has landed. Every
probed particle is then checked against the village's real triangles (its models as placed, and the ground) by ray
casts along that effect's own fall:

- a falling drop must have nothing above it (it would be under shelter), robustly: 5 rays 12 cm apart all blocked;
- a landed one (a splash, a settling flake) must sit on a surface (within 15 cm below it along the fall) with nothing
  above it, and is told by the structure it landed on (the cottage's roof, the bridge, terraces, stairs, the ground).

Negative controls: the same probes with shelter off (Stage 18A's behaviour). Pictures: 18A and 18B side by side at
the cottage, the bridge and the terraces; 4x close-ups; walking clips; the dry interior.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
import hd2d_visual_study as study  # noqa: E402
import m18_particles_study as m18  # noqa: E402
from hd2d_demo import SCENES, HiddenGame, _gl_counts  # noqa: E402

PROBE_PX = 2048
NOTHING = 1.0e9  # the probe target's clear value: no particle here


# ---------------------------------------------------------------------- the world's triangles (metres)
def triangles(hd: Any) -> tuple[Any, Any, list[str]]:
    """Every triangle of the room (structures as placed, the ground): (T, 3, 3) and, per triangle, its owner's index
    in ``names`` (the structure's model; "ground")."""
    from engine.hd2d.renderer import _placement
    from engine.hd2d.settings import PIXELS_PER_METRE as PXM

    tris, owner, names = [], [], []
    for st in hd.settings.structures:
        m = np.array(_placement(st.x / PXM, st.y / PXM, st.elevation / PXM, st.rotation, st.scale))
        name = Path(st.model).stem
        if name not in names:
            names.append(name)
        for part in hd.models[st.model].parts:
            v = np.array(part.vertices, dtype=np.float64).reshape(-1, 8)[:, :3]
            w = v @ m[:3, :3].T + m[:3, 3]
            idx = np.array(part.indices, dtype=np.int64).reshape(-1, 3)
            tris.append(w[idx])
            owner.append(np.full(len(idx), names.index(name)))
    g = hd.settings.ground
    if g is not None:
        names.append("ground")
        z = g.elevation / PXM
        x0, y0, x1, y1 = g.lo[0] / PXM, g.lo[1] / PXM, g.hi[0] / PXM, g.hi[1] / PXM
        tris.append(np.array([[[x0, y0, z], [x1, y0, z], [x1, y1, z]], [[x0, y0, z], [x1, y1, z], [x0, y1, z]]]))
        owner.append(np.full(2, len(names) - 1))
    return np.concatenate(tris), np.concatenate(owner), names


def ray_hits(origins: Any, direction: Any, tris: Any) -> tuple[Any, Any]:
    """For each origin, the nearest hit (distance along ``direction``, > 1 mm) and which triangle; inf / -1: none."""
    best = np.full(len(origins), np.inf)
    which = np.full(len(origins), -1)
    e1, e2 = tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    pvec = np.cross(direction, e2)
    det = np.einsum("ij,ij->i", e1, pvec)
    ok = np.abs(det) > 1e-12
    e1, e2, pvec, det, v0 = e1[ok], e2[ok], pvec[ok], det[ok], tris[ok, 0]
    index = np.nonzero(ok)[0]
    inv = 1.0 / det
    for start in range(0, len(origins), 64):
        o = origins[start:start + 64, None, :]
        tvec = o - v0[None]
        u = np.einsum("pij,ij->pi", tvec, pvec) * inv
        q = np.cross(tvec, e1[None])
        v = (q @ direction) * inv
        t = np.einsum("pij,ij->pi", q, e2) * inv
        hit = (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-3)
        t = np.where(hit, t, np.inf)
        k = np.argmin(t, axis=1)
        best[start:start + 64] = t[np.arange(len(k)), k]
        which[start:start + 64] = np.where(np.isfinite(best[start:start + 64]), index[k], -1)
    return best, which


def sheltered(points: Any, fall: Any, tris: Any, lift: float = 0.0) -> Any:
    """Robustly under something along the fall: rays up (against it) from the point and 12 cm round it all blocked."""
    up = -fall / np.linalg.norm(fall)
    side = np.cross(up, [0.0, 0.0, 1.0] if abs(up[2]) < 0.99 else [1.0, 0.0, 0.0])
    side /= np.linalg.norm(side)
    other = np.cross(up, side)
    blocked = np.ones(len(points), dtype=bool)
    for offset in (np.zeros(3), side * 0.12, -side * 0.12, other * 0.12, -other * 0.12):
        hit, _ = ray_hits(points + up * lift + offset, up, tris)
        blocked &= np.isfinite(hit)
    return blocked


# ---------------------------------------------------------------------- the probe
def _ortho_vp(box_min: tuple[float, ...], box_size: tuple[float, ...]) -> tuple[float, ...]:
    """Top-down: the box's x and y fill the target; any height is inside the depth range."""
    sx, sy = 2.0 / box_size[0], 2.0 / box_size[1]
    tx, ty = -1.0 - box_min[0] * sx, -1.0 - box_min[1] * sy
    return (sx, 0.0, 0.0, 0.0, 0.0, sy, 0.0, 0.0, 0.0, 0.0, 0.01, 0.0, tx, ty, 0.0, 1.0)


def probe(game: HiddenGame, *, shelter: bool = True) -> dict[str, Any]:
    """Every particle of the room's first effect in the box about the camera's target: world positions (m) of
    those falling and those landed, and their ids."""
    from engine.scene_particles import box_for_3d, impact_reach

    hd = game.window.hd2d_renderer
    layer, ctx = hd.particles, game.window.ctx
    ground = hd.settings.ground.elevation / 32.0 if hd.settings.ground is not None else 0.0
    maps = hd.precipitation_maps()
    effect = layer.effects[0]
    box_min, box_size = box_for_3d(hd.camera.target, hd.camera.pitch, effect.area, ground,
                                   impact_reach(effect) if maps and maps[0] is not None and shelter else 0.0)
    colour = ctx.texture((PROBE_PX, PROBE_PX), components=4, dtype="f4")
    depth = ctx.depth_texture((PROBE_PX, PROBE_PX))
    fbo = ctx.framebuffer(color_attachments=[colour], depth_attachment=depth)
    previous = ctx.active_framebuffer
    keep = (layer.probe, layer.depth_test, layer.shelter)
    try:
        fbo.use()
        fbo.clear(color_normalized=(0.0, 0.0, 0.0, NOTHING), depth=1.0)
        layer.probe, layer.depth_test, layer.shelter = True, False, shelter
        layer.draw_3d(_ortho_vp(box_min, box_size), hd.camera, ground, (1.0, 1.0, 1.0), fbo, maps)
        data = np.frombuffer(fbo.read(components=4, dtype="f4"), dtype=np.float32).reshape(-1, 4)
    finally:
        layer.probe, layer.depth_test, layer.shelter = keep
        previous.use()
        for obj in (fbo, colour, depth):
            obj.delete()
    data = data[data[:, 3] < NOTHING / 2]
    codes, first = np.unique(np.round(data[:, 3]).astype(np.int64), return_index=True)
    rows = data[first, :3].astype(np.float64)
    landed = codes < 0
    return {"falling": rows[~landed], "landed": rows[landed], "falling_ids": codes[~landed],
            "landed_ids": -codes[landed] - 1, "fall": np.array(maps[0].direction if maps and maps[0] else (0, 0, -1.0)),
            "box": (box_min, box_size)}


def judge(sample: dict[str, Any], tris: Any, owner: Any, names: list[str]) -> dict[str, Any]:
    """The probed particles against the world's geometry (see the module's notes)."""
    fall = sample["fall"]
    falling, landed = sample["falling"], sample["landed"]
    out: dict[str, Any] = {"falling": int(len(falling)), "landed": int(len(landed))}
    out["falling_under_shelter"] = int(sheltered(falling, fall, tris).sum()) if len(falling) else 0
    if len(landed):
        down = fall / np.linalg.norm(fall)
        hit, which = ray_hits(landed - down * 0.15, down, tris)  # from just above, along the fall
        on = hit < 0.30
        out["landed_on_a_surface"] = int(on.sum())
        out["landed_off_any_surface"] = int((~on).sum())
        if (~on).any():  # how far off: the nearest surface along the fall from 1 m above
            far, _ = ray_hits(landed[~on] - down * 1.0, down, tris)
            out["off_surface_gap_m"] = [round(float(g), 3) for g in np.sort(np.abs(far - 1.0))[:20]]
        out["landed_under_shelter"] = int(sheltered(landed, fall, tris, lift=0.15).sum())
        out["landed_height_error_m_max"] = round(float(np.max(np.abs(hit[on] - 0.15))), 3) if on.any() else None
        surfaces: dict[str, int] = {}
        heights: dict[str, list[float]] = {}
        for k, z in zip(which[on], landed[on][:, 2]):
            name = names[owner[k]]
            surfaces[name] = surfaces.get(name, 0) + 1
            heights.setdefault(name, []).append(float(z))
        out["landed_on"] = dict(sorted(surfaces.items(), key=lambda kv: -kv[1]))
        out["landed_heights_m"] = {k: [round(min(v), 2), round(max(v), 2)] for k, v in heights.items()}
    return out


# ---------------------------------------------------------------------- the proof
CASES = {  # name: (particles in start.json, camera targets (m) to probe from)
    "rain": [{"preset": "rain", "count": 6000, "seed": 2}],
    "rain_wind": [{"preset": "rain", "count": 6000, "seed": 2, "wind": [4.0, 1.0]}],
    "snow": [{"preset": "snow", "count": 4000, "seed": 2}],
}


def targets(hd: Any) -> list[tuple[float, float, float]]:
    """Camera targets covering the room in 18 m steps (the boxes overlap)."""
    lo, hi = hd.world_box()
    xs = np.arange(lo[0] + 9.0, hi[0], 18.0)
    ys = np.arange(lo[1] + 9.0, hi[1], 18.0)
    return [(float(x), float(y), 1.0) for x in xs for y in ys]


def run_case(out: Path, name: str, effects: list[dict]) -> dict[str, Any]:
    game = HiddenGame(m18.make_project(out, f"proj_{name}", effects), size=study.SIZE)
    report: dict[str, Any] = {"effects": effects}
    try:
        game.load(f"{SCENES}/start.json")
        game.step(30)
        hd = game.window.hd2d_renderer
        tris, owner, names = triangles(hd)
        report["triangles"] = int(len(tris))
        totals: dict[str, dict[str, Any]] = {"18B": {}, "18A_no_shelter": {}}
        for target in targets(hd):
            hd.camera.target = target
            for label, shelter in (("18B", True), ("18A_no_shelter", False)):
                for t in (0.0, 0.37, 0.81):  # three moments
                    hd.particles.time = 5.0 + t
                    j = judge(probe(game, shelter=shelter), tris, owner, names)
                    acc = totals[label]
                    for k, v in j.items():
                        if isinstance(v, int):
                            acc[k] = acc.get(k, 0) + v
                        elif k == "landed_on":
                            for s, n in v.items():
                                acc.setdefault(k, {})[s] = acc.setdefault(k, {}).get(s, 0) + n
                        elif k == "landed_heights_m":
                            for s, (a, b) in v.items():
                                cur = acc.setdefault(k, {}).get(s, [a, b])
                                acc[k][s] = [min(cur[0], a), max(cur[1], b)]
                        elif k == "landed_height_error_m_max" and v is not None:
                            acc[k] = max(acc.get(k, 0.0), v)
        report.update(totals)
        report["maps"] = hd.stats()["precipitation_maps"]
        report["map_build_ms"] = [round(v, 2) for v in hd.precipitation.build_ms]
    finally:
        game.close()
    print(name, json.dumps({k: report[k] for k in ("18B", "18A_no_shelter")}), flush=True)
    return report


def anchored(out: Path, case: str) -> dict[str, Any]:
    """Impacts stay put: the same moment probed from two camera targets gives the same landed positions; and a
    landed particle keeps its place over most of the time it shows (rain 0.15 s, snow 1.5 s)."""
    game = HiddenGame(m18.make_project(out, f"proj_anchor_{case}", CASES[case]), size=study.SIZE)
    try:
        game.load(f"{SCENES}/start.json")
        game.step(30)
        hd = game.window.hd2d_renderer
        hd.camera.target = (10.0, 12.0, 1.0)
        hd.particles.time = 7.0
        a = probe(game)
        hd.camera.target = (11.5, 12.6, 1.0)
        b = probe(game)
        pa = dict(zip(a["landed_ids"].tolist(), a["landed"]))
        pb = dict(zip(b["landed_ids"].tolist(), b["landed"]))
        both = [i for i in pa if i in pb]
        moved_camera = max((float(np.linalg.norm(pa[i] - pb[i])) for i in both), default=0.0)
        drifts: list[float] = []
        big: list[list[float]] = []
        life = 1.5 if case == "snow" else 0.15  # follow them over most of the time they show
        for dt in (life * 0.2, life * 0.4, life * 0.6, life * 0.8):
            hd.particles.time = 7.0 + dt
            c = probe(game)
            pc = dict(zip(c["landed_ids"].tolist(), c["landed"]))
            drifts += [float(np.linalg.norm(pb[i] - pc[i])) for i in pb if i in pc]
            big += [[round(float(c), 2) for c in pb[i]] for i in pb if i in pc and np.linalg.norm(pb[i] - pc[i]) > 0.03]
    finally:
        game.close()
    return {"landed_seen_from_both_targets": len(both), "max_difference_m_camera_moved": round(moved_camera, 4),
            "landed_followed_over_time": len(drifts), "max_drift_m_over_their_life": round(max(drifts, default=0.0), 4),
            "p99_drift_m": round(float(np.percentile(drifts, 99)), 4) if drifts else None,
            "median_drift_m": round(statistics.median(drifts), 4) if drifts else None,
            "drifts_over_3_cm": sum(1 for d in drifts if d > 0.03), "where_over_3_cm": big[:12]}


def interior(out: Path) -> dict[str, Any]:
    """The cottage with rain asked for: indoors (the template's), no particle pixels; told outdoor, they show."""
    project: Path = study.new_project(out, "proj_inside", stage6a=False)
    path = project / SCENES / "cottage.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    report: dict[str, Any] = {"template_exposure": scene.get("settings", {}).get("weather_exposure")}
    for exposure in ("indoor", "outdoor"):
        scene["settings"]["particles"] = [{"preset": "rain", "count": 3000}]
        scene["settings"]["weather_exposure"] = exposure
        path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
        game = HiddenGame(project, size=study.SIZE)
        try:
            game.load(f"{SCENES}/cottage.json")
            game.step(30)
            hd = game.window.hd2d_renderer
            wet = game.draw().convert("RGB")
            if hd.particles is not None:
                hd.particles.set_enabled(0, False)
            dry = game.draw().convert("RGB")
            changed = sum(1 for p, q in zip(wet.getdata(), dry.getdata()) if p != q)
            report[exposure] = {"particle_pixels": changed, "layer": hd.particles is not None,
                                "notice": game.window.scene_particles_notice}
            wet.save(out / f"interior_{exposure}.png")
        finally:
            game.close()
    return report


def proof(out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"method": __doc__.split("\n\n")[1].strip()}
    for name, effects in CASES.items():
        report[name] = run_case(out, name, effects)
    report["anchored"] = {case: anchored(out, case) for case in ("rain", "rain_wind", "snow")}
    print("anchored", report["anchored"], flush=True)
    report["interior"] = interior(out)
    print("interior", report["interior"], flush=True)
    (out / "proof.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


# ---------------------------------------------------------------------- pictures
TOP_PX_PER_M = 16


def _structure_centre(hd: Any, word: str) -> tuple[float, float, float]:
    """Where the first structure whose model's name has ``word`` stands (m): found, not typed in."""
    for st in hd.settings.structures:
        if word in Path(st.model).stem:
            return (st.x / 32.0, st.y / 32.0, st.elevation / 32.0)
    raise KeyError(word)


def topdown(game: HiddenGame, *, shelter: bool, near: float = 0.9) -> Any:
    """The room from straight above (16 px a metre): its triangles shaded by height (paler is higher), every
    falling particle within ``near`` m of the ground (blue) and every landed one (white), from probes over the
    whole room at four moments. Where nothing blue falls, something above shelters the ground."""
    from PIL import Image, ImageDraw

    hd = game.window.hd2d_renderer
    tris, _owner, _names = triangles(hd)
    lo, hi = hd.world_box()
    w, h = int((hi[0] - lo[0]) * TOP_PX_PER_M), int((hi[1] - lo[1]) * TOP_PX_PER_M)
    image = Image.new("RGB", (w, h), (40, 60, 40))
    draw = ImageDraw.Draw(image)

    def px(x: float, y: float) -> tuple[float, float]:
        return ((x - lo[0]) * TOP_PX_PER_M, h - (y - lo[1]) * TOP_PX_PER_M)

    for k in np.argsort(tris[:, :, 2].max(axis=1)):  # low first: higher surfaces drawn over them
        top = float(tris[k, :, 2].max())
        shade = int(max(0.0, min(1.0, top / 4.5)) * 150) + 60
        draw.polygon([px(*tris[k, j, :2]) for j in range(3)], fill=(shade, shade, int(shade * 0.92)))
    for target in targets(hd):
        hd.camera.target = target
        for t in (5.0, 5.3, 5.6, 5.9):
            hd.particles.time = t
            s = probe(game, shelter=shelter)
            for x, y, z in s["falling"]:
                if z < near:
                    cx, cy = px(x, y)
                    draw.rectangle((cx - 1, cy - 1, cx, cy), fill=(70, 140, 255))
            for x, y, _z in s["landed"]:
                cx, cy = px(x, y)
                draw.point((cx, cy), fill=(255, 255, 255))
    return image


def pictures(out: Path) -> dict[str, Any]:
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    made: dict[str, Any] = {}
    for case in ("rain", "rain_wind", "snow"):
        game = HiddenGame(m18.make_project(out, f"pic_{case}", CASES[case]), size=study.SIZE)
        try:
            game.load(f"{SCENES}/start.json")
            game.step(30)
            hd = game.window.hd2d_renderer
            sheet = m18.pair([topdown(game, shelter=False), topdown(game, shelter=True)],
                             [f"18A ({case}): falling within 0.9 m of the ground, blue", "18B: the same, and landed (white)"])
            sheet.save(out / f"topdown_{case}.png")
            made[f"topdown_{case}"] = sheet.size
            if case == "rain_wind":
                continue
            # the game's view at the cottage, the bridge and the terraces, the same moment, 18A beside 18B (2x)
            spots = {"cottage": _structure_centre(hd, "cottage"), "bridge": _structure_centre(hd, "bridge"),
                     "terraces": _structure_centre(hd, "platform")}
            for name, (x, y, z) in spots.items():
                hd.camera.target = (x, y - 1.0, z + 1.0)
                hd._camera_ready = True
                shots = []
                for shelter in (False, True):
                    hd.particles.shelter = shelter
                    hd.particles.time = 6.2
                    picture = Image.frombytes("RGB", study.SIZE, hd.draw(read=True)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                    shots.append(m18.crop_at(picture, study.SIZE[0] / 2, study.SIZE[1] / 2, (480, 270))
                                 .resize((960, 540), Image.Resampling.NEAREST))
                hd.particles.shelter = True
                m18.pair(shots, [f"18A {case}: {name}", f"18B {case}: {name}"]).save(out / f"view_{case}_{name}.png")
            if case == "rain":  # moving the camera across the village: splashes stay where they landed (1:1)
                clip = []
                x, y, z = spots["cottage"]
                for i in range(40):
                    hd.camera.target = (x - 2.0 + i * 0.1, y - 1.0, z + 1.0)
                    hd.particles.time = 8.0 + i / 30
                    picture = Image.frombytes("RGB", study.SIZE, hd.draw(read=True)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                    clip.append(m18.crop_at(picture, study.SIZE[0] / 2, study.SIZE[1] / 2, (640, 360)))
                clip[0].save(out / "rain_camera_pan.webp", save_all=True, append_images=clip[1:], duration=33, loop=0,
                             quality=82, method=6)
                made["pan_frames"] = len(clip)
        finally:
            game.close()
    import os

    import hd2d_studio_demo

    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    driver = hd2d_studio_demo.StudioDriver(m18.make_project(out, "pic_studio", CASES["rain"]))
    try:
        hd = driver.renderer
        hd.particles.time = 4.0
        on = driver.frame().convert("RGB")
        driver.button("Preview weather: on")
        off = driver.frame().convert("RGB")
        m18.pair([on.resize((960, 540)), off.resize((960, 540))],
                 ["Studio, editing: Preview weather on", "Preview weather off"]).save(out / "studio_preview.png")
    finally:
        driver.close()
    inside = [Image.open(out / f"interior_{e}.png") for e in ("indoor", "outdoor")] if (out / "interior_indoor.png").exists() else []
    if inside:
        m18.pair([i.resize((960, 540)) for i in inside],
                 ["the cottage as the template makes it: indoors, dry", "negative control: told outdoor"]).save(out / "interior.png")
    return made


# ---------------------------------------------------------------------- the cost
PERF_CASES = {
    "rain_1000": [{"preset": "rain", "count": 1000}], "rain_5000": [{"preset": "rain", "count": 5000}],
    "rain_10000": [{"preset": "rain", "count": 10000}], "rain_20000": [{"preset": "rain", "count": 20000}],
    "snow_10000": [{"preset": "snow", "count": 10000}],
    "rain_and_snow_15000": [{"preset": "rain", "count": 10000}, {"preset": "snow", "count": 5000}],
}


def _lifecycle(game: HiddenGame) -> dict[str, Any]:
    """GL objects (after ctx.gc()) as maps are made, invalidated, swapped and released."""
    from engine.scene_particles import parse_particles

    ctx, hd = game.window.ctx, game.window.hd2d_renderer

    def counts() -> dict[str, int]:
        ctx.gc()
        return dict(_gl_counts(ctx))

    hd.set_particles(())
    game.window.dispatch_event("on_draw")
    life: dict[str, Any] = {"none": counts()}
    hd.set_particles(parse_particles(PERF_CASES["rain_and_snow_15000"]))
    game.window.dispatch_event("on_draw")
    life["rain_and_snow_two_maps"] = counts()
    for _ in range(50):  # Studio dragging a structure: a new map every frame
        hd.precipitation.invalidate()
        game.window.dispatch_event("on_draw")
    life["after_50_invalidations"] = counts()
    for i in range(20):  # the wind changing: another map each time
        hd.set_particles(parse_particles([{"preset": "rain", "count": 5000, "wind": [0.5 * i, 0.0]}]))
        game.window.dispatch_event("on_draw")
    life["after_20_wind_changes_one_map"] = counts()
    hd.set_particles(())
    game.window.dispatch_event("on_draw")
    life["released"] = counts()
    return life


def _failure(game: HiddenGame) -> dict[str, Any]:
    """A map that can't be made (the driver refuses a framebuffer): rain still falls (18A), what was made is freed,
    the reason is kept; a structure edit doesn't retry it, the room's next load does."""
    from engine.scene_particles import parse_particles

    ctx, hd = game.window.ctx, game.window.hd2d_renderer
    hd.set_particles(parse_particles([{"preset": "rain", "count": 5000}]))
    hd.particles.set_enabled(0, False)
    game.window.dispatch_event("on_draw")
    hd.particles.set_enabled(0, True)
    ctx.gc()
    before = _gl_counts(ctx)
    real = ctx.framebuffer

    def refuse(*_: Any, **__: Any) -> Any:
        raise RuntimeError("out of GPU memory (injected)")

    ctx.framebuffer = refuse
    try:
        game.window.dispatch_event("on_draw")
    finally:
        ctx.framebuffer = real
    ctx.gc()
    out = {"error": hd.stats()["precipitation_error"], "rain_draw_calls": hd.particles.draw_calls,
           "gl_unchanged": _gl_counts(ctx) == before, "maps": len(hd.precipitation.maps)}
    hd.precipitation.invalidate()  # a structure edit doesn't retry it (no retrying every frame of a drag)
    game.window.dispatch_event("on_draw")
    out["after_invalidate_maps"] = len(hd.precipitation.maps)
    game.load(f"{SCENES}/start.json")  # the room's next load does
    hd = game.window.hd2d_renderer
    hd.set_particles(parse_particles([{"preset": "rain", "count": 5000}]))
    game.window.dispatch_event("on_draw")
    out["after_room_reload_maps"] = len(hd.precipitation.maps)
    out["after_room_reload_error"] = hd.stats()["precipitation_error"]
    return out


def _drag(game: HiddenGame, frames: int = 60) -> dict[str, Any]:
    """A structure dragged as in Mesh Studio (moved every frame: the maps made again each frame), the frame's wall
    time (draw and GPU finished) with the weather drawn and switched off, interleaved."""
    hd, ctx = game.window.hd2d_renderer, game.window.ctx
    st = hd.settings.structures[0]
    hd.set_live_ids([st.id])
    times: dict[str, list[float]] = {"on": [], "off": []}
    for i in range(frames):
        for on in (True, False):
            for k in range(len(hd.particles.effects)):
                hd.particles.set_enabled(k, on)
            hd.set_live(st.id, st.x + (i % 20) * 4.0, st.y, st.elevation, st.rotation, st.scale)
            start = time.perf_counter()
            game.window.dispatch_event("on_draw")
            ctx.finish()
            times["on" if on else "off"].append((time.perf_counter() - start) * 1000)
    hd.set_live_ids([])
    out = {k: round(statistics.median(v), 2) for k, v in times.items()}
    out["added_ms"] = round(out["on"] - out["off"], 2)
    return out


def _play_stop(out: Path) -> dict[str, Any]:
    """Mesh Studio, the village with rain: Edit -> Play -> Stop five times; GL objects after each."""
    import os

    import hd2d_studio_demo

    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    driver = hd2d_studio_demo.StudioDriver(m18.make_project(out, "proj_studio", PERF_CASES["rain_and_snow_15000"]))
    try:
        f4 = driver.arcade.key.F4
        rows = [driver.gl_counts()]
        for _ in range(5):
            driver.key(f4)
            driver.frame(10)
            driver.key(f4)
            driver.frame(3)
            rows.append(driver.gl_counts())
    finally:
        driver.close()
    return {"edit_then_after_each_play_stop": rows}


def perf(out: Path) -> dict[str, Any]:
    from engine.scene_particles import parse_particles

    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"method": "one game; per case the renderer's particles set, the first frame (the map "
                                        "made) timed; then Stage 18B (shelter on) and Stage 18A (shelter off) each "
                                        "measured by 18A's harness: 5 interleaved rounds of 60 frames drawn and "
                                        "switched off (medians)", "cases": {}}
    game = HiddenGame(m18.make_project(out, "proj", []), size=study.SIZE)
    try:
        ctx = game.window.ctx
        report["gpu"] = {"renderer": ctx.info.RENDERER, "vendor": ctx.info.VENDOR, "gl_version": list(ctx.gl_version)}
        game.load(f"{SCENES}/start.json")
        game.step(60)
        m18.go(game, m18.PLACES["cottage_front"][2])
        hd = game.window.hd2d_renderer
        for name, effects in PERF_CASES.items():
            hd.set_particles(parse_particles(effects))
            start = time.perf_counter()
            game.window.dispatch_event("on_draw")
            first = (time.perf_counter() - start) * 1000
            layer = hd.particles

            def switch(on: bool, layer: Any = layer) -> None:
                for i in range(len(layer.effects)):
                    layer.set_enabled(i, on)

            stats = hd.stats()
            row: dict[str, Any] = {"particles": stats["particles"], "draw_calls": stats["draw_calls"],
                                   "particle_bytes": stats["particle_bytes"], "maps": stats["precipitation_maps"],
                                   "map_bytes": stats["precipitation_bytes"],
                                   "map_build_ms": [round(v, 2) for v in hd.precipitation.build_ms[-stats["precipitation_maps"]:]],
                                   "first_frame_ms": round(first, 2)}
            row["18B"] = m18._rounds(game, switch)
            layer.shelter = False
            row["18A"] = m18._rounds(game, switch)
            layer.shelter = True
            report["cases"][name] = row
            print(name, {k: row[k] for k in ("draw_calls", "maps", "map_build_ms", "first_frame_ms")},
                  "18B pass", row["18B"]["particle_pass_gpu_ms_on"], "18A pass", row["18A"]["particle_pass_gpu_ms_on"],
                  "18B added", row["18B"]["added_frame_ms"], flush=True)
        hd.set_particles(parse_particles(PERF_CASES["rain_10000"]))
        game.window.dispatch_event("on_draw")
        rebuilds = []
        for _ in range(30):
            hd.precipitation.invalidate()
            game.window.dispatch_event("on_draw")
            rebuilds.append(hd.precipitation.build_ms[-1])
        report["map_rebuild_ms"] = {"median": round(statistics.median(rebuilds), 2), "max": round(max(rebuilds), 2)}
        hd.set_particles(parse_particles(PERF_CASES["rain_and_snow_15000"]))
        report["studio_drag_two_maps"] = _drag(game)
        report["lifecycle"] = _lifecycle(game)
        report["failure_recovery"] = _failure(game)
    finally:
        game.close()
    loads: dict[str, list[float]] = {}
    for label, effects in (("no_weather", []), ("rain_and_snow", PERF_CASES["rain_and_snow_15000"])):
        game = HiddenGame(m18.make_project(out, f"proj_{label}", effects), size=study.SIZE)
        try:
            for _ in range(6):  # a room load and its first frame (the maps made then)
                start = time.perf_counter()
                game.load(f"{SCENES}/start.json")
                game.window.dispatch_event("on_draw")
                game.window.ctx.finish()
                loads.setdefault(label, []).append((time.perf_counter() - start) * 1000)
            report[f"room_changes_{label}"] = m18._room_changes(game)
        finally:
            game.close()
    report["room_load_and_first_frame_ms"] = {k: round(statistics.median(v[1:]), 1) for k, v in loads.items()}
    report["play_stop"] = _play_stop(out)
    (out / "perf.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["proof", "pictures", "perf"])
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    if args.command == "pictures":
        print(pictures(args.out))
        return
    report = proof(args.out) if args.command == "proof" else perf(args.out)
    if args.command == "perf":
        print(json.dumps({k: v for k, v in report.items() if k != "cases"}, indent=1))


if __name__ == "__main__":
    main()
