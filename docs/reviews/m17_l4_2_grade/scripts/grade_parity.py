"""Studio vs game: on the pixels where the two ORIGINAL frames agree, do the graded frames agree too (the same grade, the
same vignette by position)? py -3.13 grade_parity.py MATCHED_DIR"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

M = Path(sys.argv[1])
rep = json.loads((M / "report.json").read_text())
out = {}
worst = 1.0
for key in rep["frames"]:
    shot, time, preset = key.split("__")
    if preset == "off":
        continue
    g0 = np.asarray(Image.open(M / "game" / f"{shot}__{time}__off.png")).astype(int)
    s0 = np.asarray(Image.open(M / "studio_1280" / f"{shot}__{time}__off.png")).astype(int)
    g1 = np.asarray(Image.open(M / "game" / f"{key}.png")).astype(int)
    s1 = np.asarray(Image.open(M / "studio_1280" / f"{key}.png")).astype(int)
    agree = (g0 == s0).all(axis=2)
    same = (g1 == s1).all(axis=2)
    share = float(same[agree].mean())
    worst = min(worst, share)
    out[key] = {"originals_agree_share": round(float(agree.mean()), 4), "graded_agree_where_originals_do": round(share, 6),
                "graded_changed_share": round(float((g1 != g0).any(axis=2).mean()), 4)}
(M / "grade_parity.json").write_text(json.dumps(out, indent=1))
print("frames", len(out), "worst graded-agree share where originals agree:", worst)
print("originals agree share range:", min(v["originals_agree_share"] for v in out.values()), max(v["originals_agree_share"] for v in out.values()))
