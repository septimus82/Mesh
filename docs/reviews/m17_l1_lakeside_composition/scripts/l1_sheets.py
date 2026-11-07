"""M17-L1: before | after sheets (full frames, side by side at full size) and 1:1 crop pairs from the matched captures.
Usage: l1_sheets.py FINAL_DIR OUT_DIR"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

F, O = Path(sys.argv[1]), Path(sys.argv[2])
(O / "sheets").mkdir(parents=True, exist_ok=True)
(O / "crops").mkdir(parents=True, exist_ok=True)


def label(d, x, y, text):
    d.rectangle([x, y, x + 10 + 7 * len(text), y + 18], fill="black")
    d.text((x + 5, y + 3), text, fill="white")


def pair(name, a, b, la, lb, box=None, scale=1.0):
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if box:
        ia, ib = ia.crop(box), ib.crop(box)
    if scale != 1.0:
        ia = ia.resize((int(ia.width * scale), int(ia.height * scale)), Image.LANCZOS)
        ib = ib.resize((int(ib.width * scale), int(ib.height * scale)), Image.LANCZOS)
    out = Image.new("RGB", (ia.width * 2 + 8, ia.height), "white")
    out.paste(ia, (0, 0))
    out.paste(ib, (ia.width + 8, 0))
    d = ImageDraw.Draw(out)
    label(d, 0, 0, la)
    label(d, ia.width + 8, 0, lb)
    return out


VIEWS = ["v0_overview_wide", "v1_village", "v3_cottage", "v4_paths", "v4b_north", "v2_shore"]
for v in VIEWS:
    pair(v, F / "720" / f"{v}__before.png", F / "720" / f"{v}__after.png", f"{v}: BEFORE (shipped)",
         f"{v}: AFTER (L1 candidate)").save(O / "sheets" / f"{v}.png")
pair("hd", F / "1080" / "hd_v1_village__before.png", F / "1080" / "hd_v1_village__after.png",
     "v1 1920x1080: BEFORE", "v1 1920x1080: AFTER").save(O / "sheets" / "v1_village_1080.png")
CROPS = {  # 1:1 (no scaling), from the 1280x720 frames unless noted
    "c1_crossroads_lamps": ("v4_paths", (240, 60, 760, 480)),
    "c2_cottage_door_garden": ("v3_cottage", (380, 60, 1000, 480)),
    "c3_shop_front": ("v1_village", (520, 260, 1080, 640)),
    "c4_flower_drift_woods": ("v4b_north", (0, 60, 760, 480)),
    "c5_pond_grove": ("v2_shore", (120, 160, 820, 600)),
    "c6_overview_village_green": ("v0_overview_wide", (0, 220, 700, 700)),
}
for n, (v, box) in CROPS.items():
    pair(n, F / "720" / f"{v}__before.png", F / "720" / f"{v}__after.png", "BEFORE 1:1", "AFTER 1:1",
         box=box).save(O / "crops" / f"{n}.png")
pair("c7_1080", F / "1080" / "hd_v1_village__before.png", F / "1080" / "hd_v1_village__after.png",
     "BEFORE 1:1 (1080p)", "AFTER 1:1 (1080p)", box=(300, 300, 1260, 1000)).save(O / "crops" / "c7_shop_lamps_1080.png")
print("ok")
