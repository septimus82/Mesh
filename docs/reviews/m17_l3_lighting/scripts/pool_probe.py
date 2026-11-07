"""M17-L3 scratch: each lamp's light pool on the open ground, shadows on vs off, against CPU rays (hidden window).

For every lamp of the scene: the ground inside its radius on a 0.25 m grid, open ground only (no structure overhead:
a CPU ray straight up). The light of THAT lamp alone (the others' intensity zeroed in-process, terms = lamps only)
is read with Lighting.probe, the scene's own shader functions and shadow maps, twice: shadows on and off
(lighting.enabled). On a 0.5 m sub-grid, CPU rays through the room's real triangles (tooling/hd2d_lighting_demo
_cpu_lamp, the lamp's own fixture skipped as the engine does) say whether the light SHOULD arrive:
  visible & on < 0.9 x off  -> false shadow (self-shadowing / acne / bias)
  blocked & on > 0.1 x off  -> leak
Also: pool energy (sum of light) and coverage (area lit > 0.02) on vs off, and a ratio picture per lamp.
Usage: pool_probe.py PROJECT SCENE OUT [--patch NAME]  (--patch: a scratch shader/bias prototype from protos.py)
"""
import dataclasses
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Games\Mesh-l3")
sys.path.insert(0, r"D:\Games\Mesh-l3\tooling")
sys.path.insert(0, str(Path(__file__).parent))
project, scene, out = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
patch = sys.argv[sys.argv.index("--patch") + 1] if "--patch" in sys.argv else None
out.mkdir(parents=True, exist_ok=True)
for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR"):
    os.environ[name] = str(out.parent / "env" / name.lower())
    Path(os.environ[name]).mkdir(parents=True, exist_ok=True)

import engine.hd2d.lighting as L  # noqa: E402

assert L.__file__.startswith(r"D:\Games\Mesh-l3"), L.__file__
if patch:
    import protos  # noqa: E402

    protos.apply(patch)

import numpy as np  # noqa: E402
from hd2d_demo import HiddenGame  # noqa: E402
from hd2d_lighting_demo import Triangles, _cpu_lamp, _hit  # noqa: E402
from PIL import Image  # noqa: E402

PX = 32.0
game = HiddenGame(project, size=(1280, 720))
game.window.audio.set_muted(True)
game.load(scene)
game.step(5)
game.draw()  # (the lamps' shadow maps are drawn with the first frame)
hd = game.window.hd2d_renderer
lt = hd.lighting
tris = Triangles(hd)
lamps = list(lt.lamps)


def surface(x, y, z_from, ground):
    """The first surface straight down from (x, y, z_from) (m), above the ground: (z, its normal facing up)."""
    best = None
    o, d = (x, y, z_from), (0.0, 0.0, -1.0)
    for lo, hi, ts, _sid in tris.parts:
        if not (lo[0] - 1e-6 <= x <= hi[0] + 1e-6 and lo[1] - 1e-6 <= y <= hi[1] + 1e-6) or lo[2] > z_from:
            continue
        for a, b, c in ts:
            if _hit(o, d, z_from - ground, a, b, c):
                e1 = [b[k] - a[k] for k in range(3)]
                e2 = [c[k] - a[k] for k in range(3)]
                nx, ny, nz = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
                ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                if abs(nz / ln) < 0.5:
                    continue  # a wall's edge: not a surface to stand light on
                # the plane's height under (x, y)
                zz = a[2] - (nx * (x - a[0]) + ny * (y - a[1])) / nz
                if best is None or zz > best[0]:
                    best = (zz, (math.copysign(1, nz) * nx / ln, math.copysign(1, nz) * ny / ln, abs(nz) / ln))
    return best if best is not None and best[0] > ground else (ground, (0.0, 0.0, 1.0))


def lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


res = {"scene": scene, "patch": patch, "softness": hd.settings.shadow_softness, "pcf": lt.pcf,
       "strength": hd.settings.shadow_strength, "room_shadows": lt.enabled, "lamps": []}
for i, lamp in enumerate(lamps):
    lp = lt._lamp_pos(lamp)
    r = lamp.radius / PX
    pts, keys = [], []
    n = int(r / 0.25)
    for gx in range(-n, n + 1):
        for gy in range(-n, n + 1):
            x, y = lp[0] + gx * 0.25, lp[1] + gy * 0.25
            if math.hypot(x - lp[0], y - lp[1]) >= r:
                continue
            ground = hd.ground_height(x * PX, y * PX) / PX
            top = surface(x, y, lp[2] - 0.15, ground)  # the surface there (a floor, a table, the ground)
            z, nrm = top
            if tris.blocked((x, y, z + 0.02), (0.0, 0.0, 1.0), 30.0):  # under a roof / inside a structure
                continue
            pts.append((x, y, z, *nrm, False))
            keys.append((gx, gy))
    lt.lamps = [lamp if j == i else dataclasses.replace(other, intensity=0.0) for j, other in enumerate(lamps)]
    lt.enabled = True
    on = [lum(c) for c in lt.probe(pts, terms=(0.0, 0.0, 1.0))]
    lt.enabled = False
    off = [lum(c) for c in lt.probe(pts, terms=(0.0, 0.0, 1.0))]
    lt.enabled = res["room_shadows"]
    lt.lamps = lamps
    slot = lt.lamp_slots[i]
    entry = {"index": i, "pos_m": [round(v, 3) for v in lp], "radius_m": r, "shadow_slot": slot,
             "fixtures": sorted(lt.fixtures[i]), "open_points": len(pts),
             "energy_on": round(sum(on), 3), "energy_off": round(sum(off), 3),
             "energy_ratio": round(sum(on) / sum(off), 4) if sum(off) else None,
             "coverage_on_m2": len([v for v in on if v > 0.02]) * 0.0625,
             "coverage_off_m2": len([v for v in off if v > 0.02]) * 0.0625}
    skip = lt.fixtures[i] if slot >= 0 else L.lamp_fixtures(lp, hd.settings.structures, hd.models)
    entry["cpu_fixtures"] = sorted(skip)
    if True:  # (a lamp without a shadow map too: its light should still stop at walls)
        vis = blk = false_sh = leak = amb = 0
        deficit_vis = []
        bands = {}
        for k, (p, a, b) in enumerate(zip(pts, on, off)):
            gx, gy = keys[k]
            if gx % 2 or gy % 2 or b < 0.01:
                continue
            truth = _cpu_lamp(tris, p[:3], lp, skip)
            d = math.hypot(p[0] - lp[0], p[1] - lp[1])
            band = bands.setdefault(int(d), {"vis": 0, "false": 0, "ratio_sum": 0.0})
            if truth is None:
                amb += 1
            elif truth:
                vis += 1
                band["vis"] += 1
                band["ratio_sum"] += a / b
                deficit_vis.append(a / b)
                if a < 0.9 * b:
                    false_sh += 1
                    band["false"] += 1
            else:
                blk += 1
                if a > 0.1 * b:
                    leak += 1
        entry.update({"cpu_visible": vis, "cpu_blocked": blk, "cpu_ambiguous": amb,
                      "false_shadow": false_sh, "false_shadow_frac": round(false_sh / vis, 4) if vis else None,
                      "leak": leak, "leak_frac": round(leak / blk, 4) if blk else None,
                      "visible_mean_on_over_off": round(sum(deficit_vis) / len(deficit_vis), 4) if deficit_vis else None,
                      "by_distance_m": {str(k): {"visible": v["vis"], "false_frac": round(v["false"] / v["vis"], 3)
                                                 if v["vis"] else None,
                                                 "mean_ratio": round(v["ratio_sum"] / v["vis"], 3) if v["vis"] else None}
                                        for k, v in sorted(bands.items())}})
    # the ratio picture: grey = not open ground, brightness = light off, red = darker with shadows, blue = brighter
    size = 2 * n + 1
    img = np.full((size, size, 3), 40, np.uint8)
    for (gx, gy), a, b in zip(keys, on, off):
        x, y = gx + n, n - gy
        if b <= 0.002:
            img[y, x] = (0, 0, 0)
            continue
        q = min(1.0, a / b)
        v = int(255 * min(1.0, b / max(off)))
        img[y, x] = (v, int(v * q), int(v * q))
    Image.fromarray(img).resize((size * 4, size * 4), Image.NEAREST).save(
        out / f"{Path(scene).stem}__lamp{i}_ratio{'_' + patch if patch else ''}.png")
    res["lamps"].append(entry)
(out / f"{Path(scene).stem}{'_' + patch if patch else ''}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
game.close()
print(json.dumps([{k: e.get(k) for k in ("index", "shadow_slot", "energy_ratio", "coverage_on_m2", "coverage_off_m2",
                                          "false_shadow_frac", "leak_frac", "visible_mean_on_over_off")}
                  for e in res["lamps"]], indent=0))
