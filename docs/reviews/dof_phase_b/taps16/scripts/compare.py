"""Scratch: 24 vs 16 samples, matched 1080p captures (q24_<set>, q16_<set>): numbers + picture sheets.

Per view: the study's own facts per cap (player, sharp band, same row, HUD, walking, stills); 24-vs-16 pixel
difference; the 24 run's same-row patches measured in the 16 picture; residual fine detail (mean |Laplacian|) in the
blurred region off / 24 / 16 (a sparser sample disk leaves more grain); crops off | 24 | 16 | |24-16| x8.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, r"D:\Games\Mesh-dof\tooling")
from dof_study import _detail  # noqa: E402

T = Path(sys.argv[1])
sheets = T / "sheets"
sheets.mkdir(exist_ok=True)


def img(p):
    return np.asarray(Image.open(p).convert("RGB")).astype(np.int16)


def lap(a):
    g = a.mean(axis=2)
    out = np.zeros_like(g)
    out[1:-1, 1:-1] = np.abs(4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:])
    return out


def crop_sheet(name, imgs, box, zoom=2):
    y0, y1, x0, x1 = box
    a, b, c = (i[y0:y1, x0:x1] for i in imgs)
    d = np.repeat(np.clip(np.abs(b - c).max(axis=2) * 8, 0, 255)[..., None], 3, axis=2)
    gap = np.full((a.shape[0], 6, 3), 255, np.int16)
    strip = np.concatenate([a, gap, b, gap, c, gap, d], axis=1).astype(np.uint8)
    Image.fromarray(strip).resize((strip.shape[1] * zoom, strip.shape[0] * zoom), Image.NEAREST).save(sheets / name)


res = {}
for st in ("template", "lakeside"):
    r24 = json.loads((T / f"q24_{st}" / "report.json").read_text(encoding="utf-8"))
    r16 = json.loads((T / f"q16_{st}" / "report.json").read_text(encoding="utf-8"))
    res[st] = {"checks_24": {k: r24.get("checks", {}).get(k) for k in ("hud", "walking", "still_frames_identical",
                                                                         "zero_strength_identical_to_off",
                                                                         "disabled_identical_to_off")},
               "checks_16": {k: r16.get("checks", {}).get(k) for k in ("hud", "walking", "still_frames_identical",
                                                                         "zero_strength_identical_to_off",
                                                                         "disabled_identical_to_off")},
               "views": {}}
    for v, f24 in r24["views"].items():
        f16 = r16["views"][v]
        off = img(T / f"q24_{st}" / f"{v}_off.png")
        off16 = img(T / f"q16_{st}" / f"{v}_off.png")
        a, b = img(T / f"q24_{st}" / f"{v}_subtle.png"), img(T / f"q16_{st}" / f"{v}_subtle.png")
        d = np.abs(a - b).max(axis=2)
        blurred = np.abs(a - off).max(axis=2) > 2
        row = {"off_frames_identical": bool(np.array_equal(off, off16)),
               "taps": [f24.get("focus", {}).get("taps"), f16.get("focus", {}).get("taps")],
               "player_changed_share": [f24["player"]["changed_share"], f16["player"]["changed_share"]],
               "sharp_band_changed_share": [(f24.get("sharp_band") or {}).get("changed_share"),
                                            (f16.get("sharp_band") or {}).get("changed_share")],
               "d24_16": {"share_gt2": round(float((d > 2).mean()), 4), "share_gt8": round(float((d > 8).mean()), 4),
                          "share_gt16": round(float((d > 16).mean()), 5), "max": int(d.max()),
                          "mean_in_blurred": round(float(d[blurred].mean()), 3) if blurred.any() else None},
               "residual_detail_in_blurred": ({k: round(float(lap(x)[blurred].mean()), 3)
                                               for k, x in (("off", off), ("24", a), ("16", b))}
                                              if blurred.any() else None)}
        ex = (f24.get("same_row") or {}).get("examples") or []
        row["same_row"] = [{"row": e["row"], "far_coc_px": e["far_coc_px"],
                            "sharp_kept_24_16": [e["sharp_kept"], round(_detail(b, e["row"], e["sharp_col"])
                                                                         / _detail(off, e["row"], e["sharp_col"]), 3)],
                            "far_kept_24_16": [e["far_kept"], round(_detail(b, e["row"], e["far_col"])
                                                                     / _detail(off, e["row"], e["far_col"]), 3)]}
                           for e in ex[:3]]
        res[st]["views"][v] = row
        h, w = d.shape
        crop_sheet(f"{st}_{v}_player.png", (off, a, b), (h // 2 - 170, h // 2 + 110, w // 2 - 140, w // 2 + 140))
        # the most detailed blurred window (high-frequency background): 200x300 where off has the most fine detail
        L = lap(off) * blurred
        best, by, bx = -1.0, 0, 0
        for y in range(0, h - 200, 50):
            for x in range(0, w - 300, 50):
                s = float(L[y:y + 200, x:x + 300].mean())
                if s > best:
                    best, by, bx = s, y, x
        crop_sheet(f"{st}_{v}_background.png", (off, a, b), (by, by + 200, bx, bx + 300))
        row["background_crop_at"] = [by, bx]
        # where 24 and 16 differ most (any silhouette/halo difference shows here)
        D = d.astype(float)
        best, by, bx = -1.0, 0, 0
        for y in range(0, h - 200, 50):
            for x in range(0, w - 300, 50):
                s = float(D[y:y + 200, x:x + 300].mean())
                if s > best:
                    best, by, bx = s, y, x
        crop_sheet(f"{st}_{v}_most_different.png", (off, a, b), (by, by + 200, bx, bx + 300))
        row["most_different_crop_at"] = [by, bx]
(T / "compare.json").write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
print(json.dumps(res, indent=1))
