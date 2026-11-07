"""Scratch: labelled comparison sheets from matched captures (each panel half size), plus a pixel check that a
matched pair differs only where the setting acts."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

C = Path(sys.argv[1]); O = Path(sys.argv[2]); O.mkdir(exist_ok=True)


def sheet(name, panels, cols=2, scale=0.5):
    ims = [(lab, Image.open(C / f"{f}.png").convert("RGB")) for lab, f in panels]
    w, h = int(ims[0][1].width * scale), int(ims[0][1].height * scale)
    rows = (len(ims) + cols - 1) // cols
    out = Image.new("RGB", (cols * w + (cols - 1) * 4, rows * h + (rows - 1) * 4), "white")
    d = ImageDraw.Draw(out)
    for i, (lab, im) in enumerate(ims):
        x, y = (i % cols) * (w + 4), (i // cols) * (h + 4)
        out.paste(im.resize((w, h), Image.LANCZOS), (x, y))
        d.rectangle([x, y, x + 8 + 7 * len(lab), y + 18], fill="black")
        d.text((x + 4, y + 3), lab, fill="white")
    out.save(O / f"{name}.png")


for v in ("v1_village", "v2_shore", "v3_cottage", "v5_npcs"):
    sheet(f"sun_{v}", [("default (noon)", f"{v}__default"), ("morning preset", f"{v}__morning"),
                       ("evening preset", f"{v}__evening"), ("overcast preset", f"{v}__overcast")])
sheet("night", [("v1 default", "v1_village__default"), ("v1 night preset", "v1_village__night"),
                ("v4 default", "v4_paths__default"), ("v4 night preset", "v4_paths__night"),
                ("v5 default", "v5_npcs__default"), ("v5 night preset", "v5_npcs__night")])
sheet("grade", [("v1 default", "v1_village__default"), ("v1 + grade/vignette", "v1_village__grade"),
                ("v2 default", "v2_shore__default"), ("v2 + grade/vignette", "v2_shore__grade"),
                ("v5 default", "v5_npcs__default"), ("v5 + grade/vignette", "v5_npcs__grade"),
                ("v1 evening", "v1_village__evening"), ("v1 evening + grade/vignette", "v1_village__evening_grade")])
sheet("dof", [("v1 DoF off", "v1_village__default"), ("v1 DoF Subtle", "v1_village__dof"),
              ("v2 DoF off", "v2_shore__default"), ("v2 DoF Subtle", "v2_shore__dof"),
              ("v1 evening, DoF off", "v1_village__evening"), ("v1 evening, DoF Subtle", "v1_village__evening_dof")])
