"""M17-L3 E2 investigation (CPU only): which geometry each lamp would make glow.

- Stage 1 prototype rule ("box"): every fragment of any drawn geometry inside the world box (+2 cm) of the nearest
  drawn node of the lamp's own fixture glows. Measured here as the other geometry whose triangles reach into that box
  (sampled on a 12x12 barycentric grid per triangle).
- Proposed rule ("part"): only the lamp's own fixture (C1 lamp_fixtures: <= 1 m across, a node box within 0.15 m),
  only its node that holds the light (nearest node box within the reach), and of that node only the materials no other
  node of the fixture uses (the kit lamp post: "lantern", not the "iron" shared by its post, cap and lantern frame);
  if that node has no material of its own, all of its parts.

py -3.13 assoc.py <worktree> <out.json> <project> <scene rel>...
"""
import json
import math
import sys
from pathlib import Path

WT = Path(sys.argv[1])
sys.path.insert(0, str(WT))
from engine.hd2d import lighting as L  # noqa: E402
from engine.hd2d.glb import load_glb  # noqa: E402
from engine.hd2d.settings import PIXELS_PER_METRE as PPM, _read_scene_lights, parse_hd2d  # noqa: E402

out_path, project, scenes = Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4:]
EPS = 0.02


def world(st, p):
    c, s = math.cos(math.radians(st.rotation)), math.sin(math.radians(st.rotation))
    x, y, z = (q * st.scale for q in p)
    return (st.x / PPM + c * x - s * y, st.y / PPM + s * x + c * y, st.elevation / PPM + z)


def local(st, p):
    dx, dy, dz = p[0] - st.x / PPM, p[1] - st.y / PPM, p[2] - st.elevation / PPM
    c, s = math.cos(math.radians(st.rotation)), math.sin(math.radians(st.rotation))
    return ((c * dx + s * dy) / st.scale, (-s * dx + c * dy) / st.scale, dz / st.scale)


def node_boxes(model):
    boxes = {}
    for part in model.parts:
        lo, hi = boxes.setdefault(part.node, ([math.inf] * 3, [-math.inf] * 3))
        v = part.vertices
        for i in range(0, len(v), 8):
            for k in range(3):
                lo[k], hi[k] = min(lo[k], v[i + k]), max(hi[k], v[i + k])
    return boxes


report = {"worktree": str(WT), "scenes": {}}
models: dict[str, object] = {}
for rel in scenes:
    scene = json.loads((project / rel).read_text(encoding="utf-8"))
    settings = parse_hd2d(scene["settings"]["hd2d"], lenient=True)
    for st in settings.structures:
        if st.model not in models:
            models[st.model] = load_glb(project / st.model)
    raw = [dict(li, enabled=True) for li in scene.get("lights") or [] if isinstance(li, dict)]
    lamps, _ambient, _status = _read_scene_lights(raw)
    rows = []
    for n, lamp in enumerate(lamps):
        lp = (lamp.x / PPM, lamp.y / PPM, lamp.elevation / PPM)
        fixtures = L.lamp_fixtures(lp, settings.structures, models)
        row = {"lamp": n, "at_m": [round(c, 2) for c in lp], "fixture": sorted(fixtures)}
        # the head: nearest node (within the reach) of the lamp's own fixture
        best = None
        for st in settings.structures:
            if st.id not in fixtures:
                continue
            for node, (lo, hi) in node_boxes(models[st.model]).items():
                d = L._box_distance(local(st, lp), tuple(lo), tuple(hi)) * st.scale
                if d <= L.FIXTURE_REACH_M and (best is None or d < best[0]):
                    best = (d, st, node, lo, hi)
        if best is None:
            row["head"] = None
            rows.append(row)
            continue
        _d, head_st, head_node, lo, hi = best
        model = models[head_st.model]
        mats_by_node: dict[str, set] = {}
        for part in model.parts:
            mats_by_node.setdefault(part.node, set()).add(part.material.name)
        own = mats_by_node[head_node] - set().union(*(m for k, m in mats_by_node.items() if k != head_node))
        part_rule = [(p.node, p.material.name, len(p.indices) // 3) for p in model.parts
                     if p.node == head_node and (p.material.name in own or not own)]
        row["head"] = {"structure": head_st.id, "model": head_st.model, "node": head_node,
                       "part_rule_glows": part_rule}
        # the Stage 1 world box (of the head node), and what else reaches into it
        corners = [world(head_st, (x, y, z)) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
        wlo = [min(c[k] for c in corners) - EPS for k in range(3)]
        whi = [max(c[k] for c in corners) + EPS for k in range(3)]
        collateral = {}
        for st in settings.structures:
            m = models[st.model]
            for part in m.parts:
                if st.id == head_st.id and part.node == head_node:
                    continue
                v, idx = part.vertices, part.indices
                hits = 0
                for t in range(0, len(idx) - 2, 3):
                    tri = [world(st, (v[i * 8], v[i * 8 + 1], v[i * 8 + 2])) for i in idx[t:t + 3]]
                    if any(max(c[k] for c in tri) < wlo[k] or min(c[k] for c in tri) > whi[k] for k in range(3)):
                        continue
                    inside = False
                    for a in range(13):
                        for b in range(13 - a):
                            w = (a / 12, b / 12, 1 - a / 12 - b / 12)
                            p = [sum(w[j] * tri[j][k] for j in range(3)) for k in range(3)]
                            if all(wlo[k] <= p[k] <= whi[k] for k in range(3)):
                                inside = True
                                break
                        if inside:
                            break
                    hits += inside
                if hits:
                    key = f"{st.id}/{part.node}/{part.material.name}"
                    collateral[key] = collateral.get(key, 0) + hits
        row["box_rule_also_glows"] = collateral
        rows.append(row)
    report["scenes"][rel] = rows
out_path.write_text(json.dumps(report, indent=1), encoding="utf-8")
for rel, rows in report["scenes"].items():
    print("==", rel)
    for r in rows:
        h = r["head"]
        print(f"  lamp {r['lamp']} at {r['at_m']} fixture={r['fixture']} head={h and (h['structure'], h['node'])}"
              f" part_rule={h and h['part_rule_glows']} box_rule_extra={r.get('box_rule_also_glows')}")
