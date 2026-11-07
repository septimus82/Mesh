"""M17-L1b metrics: shipped / L1 (1c23187) / L1b from the matched captures and the three scene files.
Usage: l1b_metrics.py FINAL_DIR SHIPPED.json L1.json L1B.json OUT.json"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

F, ship, l1, l1b, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5])
TAGS = ("before", "l1", "l1b")


def load(n, size="720"):
    return np.asarray(Image.open(F / size / f"{n}.png").convert("RGB")).astype(np.float64)


lumw = np.array([0.2126, 0.7152, 0.0722])


def lap(a):
    g = a @ lumw
    o = np.zeros_like(g)
    o[1:-1, 1:-1] = np.abs(4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:])
    return float(o.mean())


res = {"determinism_v1_shipped_repeat_max_diff": int(np.abs(load("v1_village__before") - load("v1_village__before_again")).max())}
views = {}
for v in ("v0_overview_wide", "v1_village", "v3_cottage", "v4_paths", "v4b_north", "v2_shore"):
    fd = {t: lap(load(f"{v}__{t}")) for t in TAGS}
    lu = {t: float((load(f"{v}__{t}") @ lumw).mean()) for t in TAGS}
    views[v] = {"fine_detail": {t: round(x, 2) for t, x in fd.items()},
                "l1b_vs_shipped_pct": round(100 * (fd["l1b"] - fd["before"]) / fd["before"], 1),
                "l1_vs_shipped_pct": round(100 * (fd["l1"] - fd["before"]) / fd["before"], 1),
                "mean_luma": {t: round(x, 1) for t, x in lu.items()}}
fd = {t: lap(load(f"hd_v1_village__{t}", "1080")) for t in TAGS}
views["v1_village_1080"] = {"fine_detail": {t: round(x, 2) for t, x in fd.items()},
                            "l1b_vs_shipped_pct": round(100 * (fd["l1b"] - fd["before"]) / fd["before"], 1)}
res["views"] = views
BOXES = {"v4_paths": {"lamp_left_foot": (slice(350, 400), slice(290, 370)), "lamp_mid_foot": (slice(245, 290), slice(570, 650))},
         "v1_village": {"lamp_left_foot": (slice(590, 640), slice(250, 330)), "lamp_bridge_foot": (slice(262, 300), slice(495, 575))}}
lamps = {}
for v, boxes in BOXES.items():
    on, off = load(f"{v}__l1b"), load(f"{v}__l1b_lights_removed")
    for k, r in boxes.items():
        x, y = float((on[r] @ lumw).mean()), float((off[r] @ lumw).mean())
        lamps[f"{v}/{k}"] = {"l1b": round(x, 1), "l1b_lights_removed": round(y, 1), "diff_pct": round(100 * (x - y) / y, 2)}
    lamps[f"{v}/whole_frame_identical_to_lights_removed"] = bool(np.array_equal(on, off))
res["noon_lamp_ground"] = lamps


def facts(path):
    s = json.loads(path.read_text(encoding="utf-8"))["settings"]["hd2d"]["scatter"]
    fl = np.array([[r[0], r[1]] for k in ("flowers_pink", "flowers_yellow") for r in s.get(k, [])], float)
    d = np.sqrt(((fl[:, None, :] - fl[None, :, :]) ** 2).sum(-1))
    n = (d < 48).sum(1) - 1
    return {"total": sum(len(v) for v in s.values()), "by_asset": {k: len(v) for k, v in sorted(s.items())},
            "flowers": len(fl), "flowers_clumped_share": round(float((n >= 5).mean()), 3),
            "flower_median_neighbours_1p5m": float(np.median(n)), "bytes": path.stat().st_size}


res["scatter"] = {"shipped": facts(ship), "l1": facts(l1), "l1b": facts(l1b)}
meta = json.loads((F / "720" / "shots.json").read_text(encoding="utf-8"))
meta.update(json.loads((F / "1080" / "shots.json").read_text(encoding="utf-8")))
res["draw_calls"] = {k: v.get("draw_calls") for k, v in meta.items()}
out.write_text(json.dumps(res, indent=1), encoding="utf-8")
print(json.dumps(res, indent=1))
