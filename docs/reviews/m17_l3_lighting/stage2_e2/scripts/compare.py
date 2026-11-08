"""Base vs E1 frames: identical or not, how many pixels differ, where (box), mean luminance change there, and a
before / after / difference sheet per pair. py -3.13 compare.py <ev dir>"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageStat

ev = Path(sys.argv[1])
out = {}
sheets = ev / "sheets"
sheets.mkdir(exist_ok=True)
for a in sorted((ev / "frames-base").glob("*.png")):
    b = ev / "frames-e1" / a.name
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    diff = ImageChops.difference(ia, ib)
    mask = diff.convert("L").point(lambda v: 255 if v else 0)
    count = sum(1 for v in mask.getdata() if v)
    box = mask.getbbox()
    rec = {"identical": count == 0, "pixels_changed": count, "box": box}
    if box:
        rec["luma_before"] = round(ImageStat.Stat(ia.convert("L"), mask).mean[0], 2)
        rec["luma_after"] = round(ImageStat.Stat(ib.convert("L"), mask).mean[0], 2)
    out[a.stem] = rec
    w, h = ia.size
    sheet = Image.new("RGB", (w * 3 // 2, h // 2 + 18), (24, 24, 24))
    for i, (img, label) in enumerate(((ia, "base bc547f9"), (ib, "E1"), (mask.convert("RGB"), "changed pixels"))):
        sheet.paste(img.resize((w // 2, h // 2)), (i * w // 2, 18))
        ImageDraw.Draw(sheet).text((i * w // 2 + 4, 3), f"{a.stem}: {label}", fill=(230, 230, 230))
    sheet.save(sheets / f"{a.stem}.png")
(ev / "compare.json").write_text(json.dumps(out, indent=1))
for k, v in out.items():
    print(f"{k:24} {v}")
