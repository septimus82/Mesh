"""M17-L2 scratch: per shot, 1:1 crops round the player: cut OFF (what is in the way) | cutaway NOW | PROPOSED
(prototype); and a full-frame now | proposed sheet. Usage: l2_sheets.py L2_DIR"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

D = Path(sys.argv[1])
O = D / "sheets"
O.mkdir(exist_ok=True)
rep = json.loads((D / "base" / "report.json").read_text(encoding="utf-8"))


def label(d, x, y, t):
    d.rectangle([x, y, x + 10 + 7 * len(t), y + 18], fill="black")
    d.text((x + 5, y + 3), t, fill="white")


for k, v in rep.items():
    box = v["player_box_grown_16px"]
    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    w, h = 420, 300
    x0, y0 = max(0, min(1280 - w, cx - w // 2)), max(0, min(720 - h, cy - h // 2))
    crop = (x0, y0, x0 + w, y0 + h)
    ims = [Image.open(D / "base" / f"{k}__nocut.png").crop(crop), Image.open(D / "base" / f"{k}__cut.png").crop(crop),
           Image.open(D / "proto" / f"{k}__proto.png").crop(crop)]
    out = Image.new("RGB", (3 * w + 16, h + 22), "white")
    d = ImageDraw.Draw(out)
    d.text((4, 5), f"{k}: {v['note']}", fill="black")
    for i, (im, t) in enumerate(zip(ims, ("cutaway OFF (what hides the player)", "cutaway NOW", "PROPOSED (prototype)"))):
        out.paste(im, (i * (w + 8), 22))
        label(d, i * (w + 8), 22, t)
    out.save(O / f"{k}.png")
print("ok", len(rep))
