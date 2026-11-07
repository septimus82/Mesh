"""Scratch: numbers from the matched captures (sRGB 0-255; luminance = Rec.709 weights on the stored values)."""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

C = Path(sys.argv[1])


def load(n):
    return np.asarray(Image.open(C / f"{n}.png").convert("RGB")).astype(np.float64)


def lum(a):
    return a @ np.array([0.2126, 0.7152, 0.0722])


def hsv(a):
    x = a / 255.0
    mx, mn = x.max(2), x.min(2)
    d = mx - mn + 1e-9
    r, g, b = x[..., 0], x[..., 1], x[..., 2]
    h = np.where(mx == r, (g - b) / d % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    s = np.where(mx > 0, (mx - mn) / (mx + 1e-9), 0)
    return h, s, mx


def lap(a):
    g = lum(a)
    o = np.zeros_like(g)
    o[1:-1, 1:-1] = np.abs(4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:])
    return o


res = {"views": {}}
for n in ["v1_village__default", "v2_shore__default", "v3_cottage__default", "v4_paths__default",
          "v4b_north__default", "v5_npcs__default", "v6_interior__default", "v0_overview_wide"]:
    a = load(n)
    h, s, v = hsv(a)
    green = (h > 65) & (h < 170) & (s > 0.25) & (v > 0.12)
    L = lum(a)
    res["views"][n] = {"green_share": round(float(green.mean()), 3), "mean_saturation": round(float(s.mean()), 3),
                       "luma_p5_p50_p95": [round(float(np.percentile(L, q)), 1) for q in (5, 50, 95)],
                       "fine_detail_mean_abs_laplacian": round(float(lap(a).mean()), 2)}
# water vs meadow, per sun preset (v2: a box on open water, a box of lit meadow, both clear of trees and HUD)
WATER, MEADOW = (slice(120, 200), slice(360, 560)), (slice(560, 680), slice(780, 1100))
res["water_v2"] = {}
for k in ("default", "morning", "evening", "overcast"):
    a = load(f"v2_shore__{k}")
    w, m = lum(a[WATER]).mean(), lum(a[MEADOW]).mean()
    res["water_v2"][k] = {"water_luma": round(float(w), 1), "meadow_luma": round(float(m), 1),
                          "water_over_meadow": round(float(w / m), 2),
                          "water_rgb": [round(float(c)) for c in a[WATER].reshape(-1, 3).mean(0)]}
# night lamps (v4): the ground just below each lamp base vs open meadow far from lamps; noon for reference
BASES = {"lamp_left": (slice(350, 400), slice(290, 370)), "lamp_mid": (slice(245, 290), slice(570, 650))}
FAR = (slice(560, 700), slice(900, 1200))
HEADS = {"head_left": (slice(185, 225), slice(308, 340)), "head_mid": (slice(88, 125), slice(590, 620))}
res["lamps_v4"] = {}
for k in ("default", "night"):
    a = load(f"v4_paths__{k}")
    row = {b: round(float(lum(a[r]).mean()), 1) for b, r in {**BASES, **HEADS}.items()}
    row["far_meadow"] = round(float(lum(a[FAR]).mean()), 1)
    res["lamps_v4"][k] = row
# DoF: fine detail by band (top third: far; middle; bottom third: near), and in a box round the player
PLAYER = (slice(310, 410), slice(610, 670))
res["dof"] = {}
for v in ("v1_village", "v2_shore", "v5_npcs"):
    off, on = load(f"{v}__default"), load(f"{v}__dof")
    lo, ln = lap(off), lap(on)
    bands = {b: round(float(ln[r].mean() / lo[r].mean()), 3) for b, r in
             (("top_third", slice(0, 240)), ("middle", slice(240, 480)), ("bottom_third", slice(480, 720)))}
    res["dof"][v] = {"detail_kept_on_over_off": bands,
                     "player_box_max_delta": int(np.abs(off[PLAYER] - on[PLAYER]).max()),
                     "changed_share_gt8": round(float((np.abs(off - on).max(2) > 8).mean()), 3)}
res["grade"] = {}
for v in ("v1_village", "v2_shore", "v5_npcs"):
    a, b = load(f"{v}__default"), load(f"{v}__grade")
    sa, sb = hsv(a)[1], hsv(b)[1]
    La, Lb = lum(a), lum(b)
    res["grade"][v] = {"saturation": [round(float(sa.mean()), 3), round(float(sb.mean()), 3)],
                       "luma_p5_p95": [[round(float(np.percentile(x, q)), 1) for q in (5, 95)] for x in (La, Lb)],
                       "corner_luma": [round(float(La[:90, :160].mean()), 1), round(float(Lb[:90, :160].mean()), 1)]}
print(json.dumps(res, indent=1))
(C.parent.parent / "measurements.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
