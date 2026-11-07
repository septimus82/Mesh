"""Scratch: nearest-neighbour detail crops of the captures (pairs side by side where a setting is compared)."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

C = Path(sys.argv[1]); O = Path(sys.argv[2]); O.mkdir(exist_ok=True)


def crop(name, items, box, zoom=2):
    x0, y0, x1, y1 = box
    ims = [(lab, Image.open(C / f"{f}.png").convert("RGB").crop(box).resize(((x1 - x0) * zoom, (y1 - y0) * zoom),
                                                                         Image.NEAREST)) for lab, f in items]
    w, h = ims[0][1].size
    out = Image.new("RGB", (len(ims) * w + (len(ims) - 1) * 6, h), "white")
    d = ImageDraw.Draw(out)
    for i, (lab, im) in enumerate(ims):
        out.paste(im, (i * (w + 6), 0))
        if lab:
            d.rectangle([i * (w + 6), 0, i * (w + 6) + 8 + 7 * len(lab), 16], fill="black")
            d.text((i * (w + 6) + 4, 2), lab, fill="white")
    out.save(O / f"{name}.png")


crop("c1_cutaway_overcut", [("v1 default", "v1_village__default")], (560, 260, 960, 440))
crop("c2_lamp_night", [("noon", "v4_paths__default"), ("night preset", "v4_paths__night")], (520, 60, 700, 320))
crop("c3_water_presets", [("noon", "v2_shore__default"), ("evening", "v2_shore__evening")], (300, 90, 760, 330), 1)
crop("c4_meadow_trees", [("v4b default", "v4b_north__default")], (0, 40, 700, 520), 1)
crop("c5_roof_cottage", [("v3 default", "v3_cottage__default")], (470, 70, 980, 420))
crop("c6_character_scale", [("v3 default", "v3_cottage__default")], (560, 280, 720, 420), 3)
crop("c7_dof_far_band", [("DoF off", "v2_shore__default"), ("DoF Subtle", "v2_shore__dof")], (300, 0, 940, 240), 1)
crop("c8_template_paths", [("v5 default", "v5_npcs__default")], (0, 380, 1280, 600), 1)
crop("c9_lamp_noon_pool", [("v5 default (noon)", "v5_npcs__default")], (0, 200, 460, 500), 1)
