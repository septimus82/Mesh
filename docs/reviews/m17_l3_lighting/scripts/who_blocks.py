"""M17-L3 scratch: which drawn part (structure, glTF node, material) first blocks the ray from floor spots to a lamp.
Usage: who_blocks.py PROJECT SCENE LAMP_INDEX OUT"""
import collections
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Games\Mesh-l3")
sys.path.insert(0, r"D:\Games\Mesh-l3\tooling")
project, scene, li, out = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), Path(sys.argv[4])
out.mkdir(parents=True, exist_ok=True)
for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR"):
    os.environ[name] = str(out.parent / "env" / name.lower())
    Path(os.environ[name]).mkdir(parents=True, exist_ok=True)
from hd2d_demo import HiddenGame  # noqa: E402
from hd2d_lighting_demo import _hit  # noqa: E402

from engine.hd2d.renderer import _placement  # noqa: E402

PX = 32.0
game = HiddenGame(project, size=(640, 360))
game.load(scene)
game.step(3)
game.draw()
hd = game.window.hd2d_renderer
lt = hd.lighting
lamp = lt.lamps[li]
lp = lt._lamp_pos(lamp)
parts = []
for st in hd.settings.structures:
    m = _placement(st.x / PX, st.y / PX, st.elevation / PX, st.rotation, st.scale)
    for part in hd.models[st.model].parts:
        v = part.vertices
        pts = [(m[0][0] * v[i] + m[0][1] * v[i + 1] + m[0][2] * v[i + 2] + m[0][3],
                m[1][0] * v[i] + m[1][1] * v[i + 1] + m[1][2] * v[i + 2] + m[1][3],
                m[2][0] * v[i] + m[2][1] * v[i + 1] + m[2][2] * v[i + 2] + m[2][3]) for i in range(0, len(v), 8)]
        tris = [(pts[part.indices[i]], pts[part.indices[i + 1]], pts[part.indices[i + 2]]) for i in range(0, len(part.indices), 3)]
        lo = [min(p[k] for p in pts) for k in range(3)]
        hi = [max(p[k] for p in pts) for k in range(3)]
        parts.append((st.id, part.node, part.material.name, tris, lo, hi))
inside = [(sid, node, mat, [round(c, 3) for c in lo], [round(c, 3) for c in hi]) for sid, node, mat, _t, lo, hi in parts
          if all(lo[k] - 0.01 <= lp[k] <= hi[k] + 0.01 for k in range(3))]
counts = collections.Counter()
r = lamp.radius / PX
for gx in range(-12, 13):
    for gy in range(-12, 13):
        x, y = lp[0] + gx * 0.5, lp[1] + gy * 0.5
        if math.hypot(x - lp[0], y - lp[1]) >= r:
            continue
        z = hd.ground_height(x * PX, y * PX) / PX + 0.05
        d = (lp[0] - x, lp[1] - y, lp[2] - z)
        n = math.sqrt(sum(c * c for c in d))
        d = (d[0] / n, d[1] / n, d[2] / n)
        hits = []
        for sid, node, mat, tris, _lo, _hi in parts:
            for a, b, c in tris:
                if _hit((x, y, z), d, n - 0.01, a, b, c):
                    hits.append(f"{sid}/{node}/{mat}")
                    break
        counts[tuple(sorted(set(hits)))] += 1
res = {"scene": scene, "lamp": li, "lamp_m": lp, "parts_whose_box_holds_the_lamp": inside,
       "fixtures_found": sorted(lt.fixtures[li]), "ray_blockers": {" + ".join(k) or "(clear)": v for k, v in counts.most_common()}}
(out / f"who_blocks_{Path(scene).stem}_{li}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
print(json.dumps(res, indent=1))
game.close()
