"""Compare variant frames against the 'off' frame and against the baseline. Usage: compare.py DIR [variants]"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
D = Path(sys.argv[1])
VARIANTS = (sys.argv[2] if len(sys.argv) > 2 else "daytime,evening").split(",")
for off in sorted(D.glob("*__off.png")):
    key = off.name[:-len("__off.png")]
    a = np.asarray(Image.open(off)).astype(int)
    base = HERE / "baseline" / off.name
    same = (np.asarray(Image.open(base)).astype(int) == a).all() if base.exists() else None
    line = f"{key:24s} off==baseline {same}"
    for v in VARIANTS:
        f = D / f"{key}__{v}.png"
        if not f.exists():
            continue
        c = np.asarray(Image.open(f)).astype(int)
        d = np.abs(c - a).max(axis=2)
        rows = d.mean(axis=1)
        line += f" | {v}: changed {100 * (d > 0).mean():.1f}% rows top/mid/bot " + "/".join(
            f"{rows[i:i + 40].mean():.1f}" for i in (0, 340, 680))
    print(line)
