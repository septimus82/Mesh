"""Same screen height, different depth, from a lab run's saved pictures: the CoC map (miniature, the lab's own depth
and focus: black = inside the sharp band, blue = farther, brighter = more blur) picks, on one screen row, a patch in
the sharp band and a patch at full far blur; the off / subtle / miniature pictures say how much detail each keeps.
A screen-height blur would treat both patches alike. Writes OUT/same_row.json and a crop picture per view."""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

LAB = Path(sys.argv[1])
P = 4  # patch half-size (px)


def detail(img: np.ndarray, y: int, x: int) -> float:
    p = img[y - P:y + P, x - P:x + P].astype(np.float64).mean(axis=2)
    return float((np.abs(np.diff(p, axis=0)).mean() + np.abs(np.diff(p, axis=1)).mean()) / 2)


out = {}
for coc_path in sorted(LAB.glob("*_coc_miniature.png")):
    name = coc_path.name[:-len("_coc_miniature.png")]
    coc = np.asarray(Image.open(coc_path).convert("RGB")).astype(int)
    shots = {k: np.asarray(Image.open(LAB / f"{name}_{k}.png").convert("RGB")) for k in ("off", "subtle", "miniature")}
    h, w = coc.shape[:2]
    sharp = (coc.max(axis=2) == 0)
    far = (coc[..., 2] >= 150) & (coc[..., 0] == 0)  # (at least ~60% of the far maximum)
    found = []
    for y in range(P + 2, h - P - 2, 6):
        xs_sharp = [x for x in range(P + 2, w - P - 2, 3) if sharp[y - P:y + P, x - P:x + P].all()]
        xs_far = [x for x in range(P + 2, w - P - 2, 3) if far[y - P:y + P, x - P:x + P].all()]
        best = None
        for xa in xs_sharp:
            if detail(shots["off"], y, xa) < 6:
                continue
            for xb in xs_far:
                if detail(shots["off"], y, xb) < 6:
                    continue
                score = min(detail(shots["off"], y, xa), detail(shots["off"], y, xb))
                if best is None or score > best[0]:
                    best = (score, xa, xb)
        if best:
            _, xa, xb = best
            found.append({"row": y, "sharp_col": xa, "far_col": xb, **{
                f"{k}_kept": [round(detail(shots[k], y, xa) / detail(shots["off"], y, xa), 3),
                              round(detail(shots[k], y, xb) / detail(shots["off"], y, xb), 3)] for k in ("subtle", "miniature")}})
    out[name] = {"rows_with_a_pair": len(found), "examples": sorted(found, key=lambda f: f["miniature_kept"][1])[:5]}
    if found:
        f = sorted(found, key=lambda f: f["miniature_kept"][1])[0]
        y, xa, xb = f["row"], f["sharp_col"], f["far_col"]
        strips = []
        for k in ("off", "miniature"):
            im = Image.fromarray(shots[k]).copy()
            d = ImageDraw.Draw(im)
            for x, colour in ((xa, (255, 255, 255)), (xb, (80, 160, 255))):
                d.rectangle([x - P - 2, y - P - 2, x + P + 2, y + P + 2], outline=colour, width=2)
            d.line([0, y, w, y], fill=(255, 255, 0), width=1)
            strips.append(im.crop((0, max(0, y - 90), w, min(h, y + 90))))
        sheet = Image.new("RGB", (w, sum(s.height for s in strips)))
        top = 0
        for s in strips:
            sheet.paste(s, (0, top))
            top += s.height
        sheet.save(LAB / f"{name}_same_row.png")
(LAB / "same_row.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
print(json.dumps({k: {"rows": v["rows_with_a_pair"], "best": v["examples"][:2]} for k, v in out.items()}, indent=1))
