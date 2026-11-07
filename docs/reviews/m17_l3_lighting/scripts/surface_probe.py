"""M17-L3 scratch: self-shadowing and leakage on EVERY structure surface a lamp lights (hidden window).

Rays from each shadow-casting lamp in 6,000 directions (a Fibonacci sphere); the first structure triangle each meets
within the lamp's radius (its own fixture skipped, as the engine skips it) is, by construction, lit by that lamp.
Its drawn normal (the part's vertex normals, as MESH_FS uses them) must face the lamp. The GPU light of that lamp
alone there (Lighting.probe, shadows on vs off) must then be equal: on < 0.9 x off = FALSE SHADOW. The surface the
same ray meets NEXT (behind the first) is in that lamp's shadow: on > 0.1 x off there = LEAK. Reported by material,
distance and incidence angle (degrees between the normal and the light), which is where bias and near-plane
problems show.
Usage: surface_probe.py PROJECT SCENE OUT [--patch NAME]
"""
import collections
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

from engine.hd2d.renderer import _placement  # noqa: E402

PX = 32.0
game = HiddenGame(project, size=(640, 360))
game.window.audio.set_muted(True)
game.load(scene)
game.step(5)
game.draw()
hd = game.window.hd2d_renderer
lt = hd.lighting
lamps = list(lt.lamps)

# every structure triangle, world metres, with its three drawn normals; numpy for speed
A, B, C, N, TAG = [], [], [], [], []
tags = []
for st in hd.settings.structures:
    m = np.asarray(_placement(st.x / PX, st.y / PX, st.elevation / PX, st.rotation, st.scale), dtype=np.float64)
    for part in hd.models[st.model].parts:
        v = np.frombuffer(part.vertices, dtype=np.float32).reshape(-1, 8).astype(np.float64)
        pos = v[:, :3] @ m[:3, :3].T + m[:3, 3]
        nrm = v[:, 3:6] @ m[:3, :3].T
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
        idx = np.frombuffer(part.indices, dtype=np.uint32).reshape(-1, 3)
        tags.append((st.id, part.node, part.material.name))
        A.append(pos[idx[:, 0]])
        B.append(pos[idx[:, 1]])
        C.append(pos[idx[:, 2]])
        N.append((nrm[idx[:, 0]] + nrm[idx[:, 1]] + nrm[idx[:, 2]]) / 3)
        TAG.append(np.full(len(idx), len(tags) - 1))
A, B, C, N, TAG = (np.concatenate(x) for x in (A, B, C, N, TAG))
E1, E2 = B - A, C - A


def hits(o, d, t_max, skip_ids):
    """All triangles the ray crosses within t_max, sorted by distance: (t, triangle index)."""
    p = np.cross(d, E2)
    det = np.einsum("ij,ij->i", E1, p)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = o - A
    u = np.einsum("ij,ij->i", s, p) * inv
    q = np.cross(s, E1)
    v = (q @ d) * inv
    t = np.einsum("ij,ij->i", E2, q) * inv
    mask = ok & (u >= 0) & (u <= 1) & (v >= 0) & (u + v <= 1) & (t > 1e-4) & (t < t_max)
    if skip_ids:
        mask &= ~np.isin(TAG, skip_ids)
    idx = np.nonzero(mask)[0]
    return sorted(zip(t[idx], idx))


def lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


k = np.arange(6000) + 0.5
phi = np.arccos(1 - 2 * k / 6000)
theta = math.pi * (1 + 5 ** 0.5) * k
DIRS = np.stack([np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)], axis=1)
res = {"scene": scene, "patch": patch, "pcf": lt.pcf, "lamps": []}
for i, lamp in enumerate(lamps):
    if lt.lamp_slots[i] < 0:
        continue
    lp = np.array(lt._lamp_pos(lamp))
    r = lamp.radius / PX
    skip = [j for j, tg in enumerate(tags) if tg[0] in lt.fixtures[i]]
    lit_pts, lit_meta, dark_pts, dark_meta = [], [], [], []
    for d in DIRS:
        hs = hits(lp, d, r, skip)
        if not hs:
            continue
        t0, j0 = hs[0]
        n0 = N[j0] / (np.linalg.norm(N[j0]) + 1e-12)
        cos_in = float(-n0 @ d)
        if cos_in > 0.05:  # its drawn side faces the lamp (else the shader gives it no light anyway)
            p = lp + d * t0
            lit_pts.append((*p, *n0, False))
            lit_meta.append((tags[TAG[j0]][2], float(t0), math.degrees(math.acos(min(1.0, cos_in)))))
        # the next surface along the ray that faces the lamp, at least 5 cm behind: in this lamp's shadow
        for t1, j1 in hs[1:]:
            n1 = N[j1] / (np.linalg.norm(N[j1]) + 1e-12)
            if t1 - t0 > 0.05 and float(-n1 @ d) > 0.05:
                dark_pts.append((*(lp + d * t1), *n1, False))
                dark_meta.append((tags[TAG[j1]][2], float(t1), float(t1 - t0)))
                break
    lt.lamps = [lamp if j == i else dataclasses.replace(o, intensity=0.0) for j, o in enumerate(lamps)]
    out_rows = {}
    for label, pts in (("lit", lit_pts), ("dark", dark_pts)):
        if not pts:
            out_rows[label] = ([], [])
            continue
        lt.enabled = True
        on = [lum(c) for c in lt.probe(pts, terms=(0.0, 0.0, 1.0))]
        lt.enabled = False
        off = [lum(c) for c in lt.probe(pts, terms=(0.0, 0.0, 1.0))]
        out_rows[label] = (on, off)
    lt.enabled = True
    lt.lamps = lamps
    on, off = out_rows["lit"]
    by_mat = collections.defaultdict(lambda: [0, 0])
    by_angle = collections.defaultdict(lambda: [0, 0])
    by_dist = collections.defaultdict(lambda: [0, 0])
    worst = []
    for (mat, dist, ang), a, b in zip(lit_meta, on, off):
        if b < 0.005:
            continue
        bad = a < 0.9 * b
        for table, key in ((by_mat, mat), (by_angle, f"{int(ang // 15) * 15}-{int(ang // 15) * 15 + 15}"),
                           (by_dist, f"{int(dist)}")):
            table[key][0] += 1
            table[key][1] += bad
        if bad:
            worst.append((round(a / b, 3), mat, round(dist, 2), round(ang, 1)))
    don, doff = out_rows["dark"]
    leaks = [(round(a / b, 3), mat, round(dist, 2), round(gap, 3)) for (mat, dist, gap), a, b in zip(dark_meta, don, doff)
             if b >= 0.005 and a > 0.1 * b]
    dark_n = len([b for b in doff if b >= 0.005])
    entry = {"lamp": i, "pos_m": [round(float(c), 3) for c in lp], "radius_m": r, "fixtures": sorted(lt.fixtures[i]),
             "lit_surface_points": int(sum(v[0] for v in by_mat.values())),
             "false_shadow": int(sum(v[1] for v in by_mat.values())),
             "by_material": {m: {"points": v[0], "false": v[1]} for m, v in sorted(by_mat.items())},
             "by_incidence_deg": {m: {"points": v[0], "false": v[1]} for m, v in sorted(by_angle.items(), key=lambda kv: int(kv[0].split('-')[0]))},
             "by_distance_m": {m: {"points": v[0], "false": v[1]} for m, v in sorted(by_dist.items(), key=lambda kv: int(kv[0]))},
             "worst_false": sorted(worst)[:15],
             "shadowed_points": dark_n, "leak": len(leaks),
             "leaks_by_gap_m": dict(collections.Counter(f"{min(int(g / 0.05) * 5, 50)}cm+" for _r, _m, _d, g in leaks)),
             "worst_leaks": sorted(leaks, reverse=True)[:15]}
    res["lamps"].append(entry)
    print(json.dumps({k2: entry[k2] for k2 in ("lamp", "lit_surface_points", "false_shadow", "shadowed_points", "leak")}))
(out / f"surfaces_{Path(scene).stem}{'_' + patch if patch else ''}.json").write_text(json.dumps(res, indent=1),
                                                                                 encoding="utf-8")
game.close()
