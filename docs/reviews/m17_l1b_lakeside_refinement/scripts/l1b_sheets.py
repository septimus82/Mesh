"""M17-L1b: shipped | L1 (1c23187) | L1b sheets at full size, and 1:1 crop triples, from the matched captures.
Usage: l1b_sheets.py FINAL_DIR OUT_DIR"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

F, O = Path(sys.argv[1]), Path(sys.argv[2])
(O / "sheets").mkdir(parents=True, exist_ok=True)
(O / "crops").mkdir(parents=True, exist_ok=True)


def triple(paths, labels, box=None):
    ims = [Image.open(p).convert("RGB") for p in paths]
    if box:
        ims = [i.crop(box) for i in ims]
    w, h = ims[0].size
    out = Image.new("RGB", (3 * w + 16, h), "white")
    d = ImageDraw.Draw(out)
    for k, (im, lab) in enumerate(zip(ims, labels)):
        out.paste(im, (k * (w + 8), 0))
        d.rectangle([k * (w + 8), 0, k * (w + 8) + 10 + 7 * len(lab), 18], fill="black")
        d.text((k * (w + 8) + 5, 3), lab, fill="white")
    return out


TAGS = ("before", "l1", "l1b")
for v in ("v0_overview_wide", "v1_village", "v3_cottage", "v4_paths", "v4b_north", "v2_shore"):
    triple([F / "720" / f"{v}__{t}.png" for t in TAGS], [f"{v}: SHIPPED", "L1 (1c23187)", "L1b (candidate)"]).save(O / "sheets" / f"{v}.png")
triple([F / "1080" / f"hd_v1_village__{t}.png" for t in TAGS], ["v1 1080p: SHIPPED", "L1", "L1b"]).save(O / "sheets" / "v1_village_1080.png")
CROPS = {"c1_north_wood_edge": ("v4b_north", (0, 0, 700, 460)), "c2_green_cottage_corner": ("v3_cottage", (380, 0, 1000, 380)),
         "c3_green_bridge_approach": ("v1_village", (180, 280, 760, 640)), "c4_green_south_crossroads": ("v4_paths", (420, 200, 1000, 560)),
         "c5_overview_green": ("v0_overview_wide", (0, 200, 760, 720))}
for n, (v, box) in CROPS.items():
    triple([F / "720" / f"{v}__{t}.png" for t in TAGS], ["SHIPPED 1:1", "L1 1:1", "L1b 1:1"], box).save(O / "crops" / f"{n}.png")
print("ok")
