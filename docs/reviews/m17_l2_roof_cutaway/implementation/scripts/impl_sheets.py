"""M17-L2: per shot, 1:1 crops round the player: cutaway OFF | BEFORE (f9f1f81) | AFTER (feature/m17-l2-cutaway); and
full-frame BEFORE | AFTER pairs for the key shots. Usage: impl_sheets.py L2_DIR"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

D = Path(sys.argv[1])
O = D / "impl_sheets"
(O / "full").mkdir(parents=True, exist_ok=True)
rep = json.loads((D / "base" / "report.json").read_text(encoding="utf-8"))
cmp = json.loads((D / "comparison_impl.json").read_text(encoding="utf-8"))["shots"]


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
           Image.open(D / "impl" / f"{k}__cut.png").crop(crop)]
    c = cmp[k]
    out = Image.new("RGB", (3 * w + 16, h + 22), "white")
    d = ImageDraw.Draw(out)
    d.text((4, 5), f"{k}: {v['note']}  |  cut px {c['cut_px_before']} -> {c['cut_px_after']}; player visible "
                   f"{c['visible_with_cut_before']} -> {c['visible_with_cut_after']}", fill="black")
    for i, (im, t) in enumerate(zip(ims, ("cutaway OFF (what hides the player)", "BEFORE (f9f1f81)", "AFTER (this change)"))):
        out.paste(im, (i * (w + 8), 22))
        label(d, i * (w + 8), 22, t)
    out.save(O / f"{k}.png")
for k in ("a2_beside_shop", "b3_behind_cottage_x608", "c1_partly_hidden", "d3_inside_shop", "e_close_behind_cottage",
          "e_indoor_partly_hidden", "v4_village_beside_shop"):
    a, b = Image.open(D / "base" / f"{k}__cut.png"), Image.open(D / "impl" / f"{k}__cut.png")
    out = Image.new("RGB", (2568, 720), "white")
    out.paste(a, (0, 0)); out.paste(b, (1288, 0))
    d = ImageDraw.Draw(out)
    label(d, 0, 0, f"{k}: BEFORE (f9f1f81)"); label(d, 1288, 0, "AFTER (this change)")
    out.save(O / "full" / f"{k}.png")
print("ok")
