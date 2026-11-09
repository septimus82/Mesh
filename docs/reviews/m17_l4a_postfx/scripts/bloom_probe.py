"""Would bloom have anything to work with? Per original frame: % of pixels over common LDR bloom thresholds (max
channel >= 250; luma >= 200), and at night with lamps the size of the brightest blobs (the lamp glass).
py -3.13 bloom_probe.py FRAMES OUT.json"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

FR = Path(sys.argv[1])
out = {}
for p in sorted(FR.glob("*__original.png")):
    a = np.asarray(Image.open(p).convert("RGB")).astype(np.float64)
    y = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    hot = a.max(axis=2) >= 250
    out[p.stem.replace("__original", "")] = {
        "maxch_ge_250_pct": round(float(hot.mean() * 100), 3), "luma_ge_200_pct": round(float((y >= 200).mean() * 100), 3),
        "luma_ge_160_pct": round(float((y >= 160).mean() * 100), 3), "hot_pixels": int(hot.sum())}
Path(sys.argv[2]).write_text(json.dumps(out, indent=1))
for k, v in out.items():
    print(f"{k:28} {v}")
