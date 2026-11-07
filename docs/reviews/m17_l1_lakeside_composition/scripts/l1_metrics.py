"""M17-L1 metrics from the matched captures and the two scene files.
Usage: l1_metrics.py FINAL_DIR BEFORE_lakeside.json AFTER_lakeside.json OUT.json"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

F, before_scene, after_scene, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])


def load(n, size="720"):
    return np.asarray(Image.open(F / size / f"{n}.png").convert("RGB")).astype(np.float64)


def lum(a):
    return a @ np.array([0.2126, 0.7152, 0.0722])


def lap(a):
    g = lum(a)
    o = np.zeros_like(g)
    o[1:-1, 1:-1] = np.abs(4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:])
    return float(o.mean())


def green_share(a):
    x = a / 255
    mx, mn = x.max(2), x.min(2)
    d = mx - mn + 1e-9
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    h = np.where(mx == r, (g - b) / d % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    s = (mx - mn) / (mx + 1e-9)
    return float(((h > 65) & (h < 170) & (s > 0.25) & (mx > 0.12)).mean())


res = {"determinism_v1_before_repeat_max_diff": int(np.abs(load("v1_village__before") - load("v1_village__before_again")).max())}
views = {}
for v in ("v0_overview_wide", "v1_village", "v3_cottage", "v4_paths", "v4b_north", "v2_shore"):
    b, a = load(f"{v}__before"), load(f"{v}__after")
    fb, fa = lap(b), lap(a)
    views[v] = {"fine_detail": [round(fb, 2), round(fa, 2)], "change_pct": round(100 * (fa - fb) / fb, 1),
                "mean_luma": [round(float(lum(b).mean()), 1), round(float(lum(a).mean()), 1)],
                "green_share": [round(green_share(b), 3), round(green_share(a), 3)],
                "pixels_changed_gt8": round(float((np.abs(b - a).max(2) > 8).mean()), 3)}
b, a = load("hd_v1_village__before", "1080"), load("hd_v1_village__after", "1080")
views["v1_village_1080"] = {"fine_detail": [round(lap(b), 2), round(lap(a), 2)],
                            "change_pct": round(100 * (lap(a) - lap(b)) / lap(b), 1)}
res["views"] = views
# noon lamp ground: the candidate (lamp lights switched off) vs the candidate with the point lights removed outright
BOXES = {"v4_paths": {"lamp_left_foot": (slice(350, 400), slice(290, 370)), "lamp_mid_foot": (slice(245, 290), slice(570, 650))},
         "v1_village": {"lamp_left_foot": (slice(590, 640), slice(250, 330)), "lamp_bridge_foot": (slice(262, 300), slice(495, 575))}}
lamps = {}
for v, boxes in BOXES.items():
    on, off = load(f"{v}__after"), load(f"{v}__after_lights_removed")
    be = load(f"{v}__before")
    for k, r in boxes.items():
        x, y = float(lum(on[r]).mean()), float(lum(off[r]).mean())
        lamps[f"{v}/{k}"] = {"before_lamps_lit": round(float(lum(be[r]).mean()), 1), "after": round(x, 1),
                             "after_lights_removed": round(y, 1), "diff_pct": round(100 * (x - y) / y, 2)}
    lamps[f"{v}/whole_frame_identical_to_lights_removed"] = bool(np.array_equal(on, off))
res["noon_lamp_ground"] = lamps


def scatter_facts(path):
    s = json.loads(path.read_text(encoding="utf-8"))["settings"]["hd2d"]["scatter"]
    fl = np.array([[r[0], r[1]] for k in ("flowers_pink", "flowers_yellow") for r in s.get(k, [])], float)
    d = np.sqrt(((fl[:, None, :] - fl[None, :, :]) ** 2).sum(-1))
    n = (d < 48).sum(1) - 1
    return {"total": sum(len(v) for v in s.values()), "by_asset": {k: len(v) for k, v in sorted(s.items())},
            "flowers": len(fl), "flowers_clumped_share": round(float((n >= 5).mean()), 3),
            "flower_median_neighbours_1p5m": float(np.median(n))}


res["scatter"] = {"before": scatter_facts(before_scene), "after": scatter_facts(after_scene)}
meta = json.loads((F / "720" / "shots.json").read_text(encoding="utf-8"))
meta.update(json.loads((F / "1080" / "shots.json").read_text(encoding="utf-8")))
res["draw_calls"] = {k: v.get("draw_calls") for k, v in meta.items()}
out.write_text(json.dumps(res, indent=1), encoding="utf-8")
print(json.dumps(res, indent=1))
