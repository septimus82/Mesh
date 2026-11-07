"""M17-L1: what differs between the shipped lakeside.json and the candidate, by category (exact).
Usage: l1_diff.py BEFORE.json AFTER.json OUT.json"""
import base64
import json
import sys

b, a = (json.loads(open(p, encoding="utf-8").read()) for p in sys.argv[1:3])
res = {}
sb, sa = b["settings"]["hd2d"]["scatter"], a["settings"]["hd2d"]["scatter"]
res["scatter"] = {k: {"before": len(sb.get(k, [])), "after": len(sa.get(k, [])),
                      "kept": len({tuple(r) for r in sb.get(k, [])} & {tuple(r) for r in sa.get(k, [])}),
                      "identical": sb.get(k) == sa.get(k)} for k in sorted(set(sb) | set(sa))}
mb, ma = b["settings"]["hd2d"]["ground"]["terrain"]["materials"], a["settings"]["hd2d"]["ground"]["terrain"]["materials"]
changed = sorted(k for k in set(mb) | set(ma) if mb.get(k) != ma.get(k))
corners = 0
for k in changed:
    x, y = base64.b64decode(mb.get(k, "")), base64.b64decode(ma.get(k, ""))
    corners += sum(1 for i in range(0, max(len(x), len(y)), 4) if x[i:i + 4] != y[i:i + 4])
res["terrain_paint"] = {"chunks_changed": changed, "corners_changed": corners,
                        "heights_identical": b["settings"]["hd2d"]["ground"]["terrain"]["chunks"] == a["settings"]["hd2d"]["ground"]["terrain"]["chunks"]}
res["lights"] = [{"index": i, "before": lb, "after": la} for i, (lb, la) in enumerate(zip(b["lights"], a["lights"])) if lb != la]
res["structures_identical"] = b["settings"]["hd2d"]["structures"] == a["settings"]["hd2d"]["structures"]
res["entities_identical"] = b["entities"] == a["entities"]
other = {k: v for k, v in b["settings"].items() if k != "hd2d"} == {k: v for k, v in a["settings"].items() if k != "hd2d"}
res["other_settings_identical"] = other
res["hd2d_keys_other_than_scatter_ground_identical"] = all(b["settings"]["hd2d"].get(k) == a["settings"]["hd2d"].get(k)
    for k in set(b["settings"]["hd2d"]) | set(a["settings"]["hd2d"]) if k not in ("scatter", "ground"))
gb, ga = dict(b["settings"]["hd2d"]["ground"]), dict(a["settings"]["hd2d"]["ground"])
gb["terrain"] = {k: v for k, v in gb["terrain"].items() if k != "materials"}
ga["terrain"] = {k: v for k, v in ga["terrain"].items() if k != "materials"}
res["ground_apart_from_paint_identical"] = gb == ga
res["top_level_apart_from_settings_lights_entities_identical"] = {k: v for k, v in b.items() if k not in ("settings", "lights", "entities")} == {k: v for k, v in a.items() if k not in ("settings", "lights", "entities")}
open(sys.argv[3], "w", encoding="utf-8").write(json.dumps(res, indent=1))
print(json.dumps(res, indent=1))
