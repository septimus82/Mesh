"""Zoomed before/after crops (lamp heads; the test panels) into one sheet. py -3.13 crops.py <ev dir>"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ev = Path(sys.argv[1])
rows = []
for name, box in (("start__noon_glow", (450, 215, 830, 275)), ("start__evening_glow", (450, 215, 830, 275)),
                  ("start__night_glow", (450, 215, 830, 275)), ("swatches__noon", (330, 480, 950, 580)),
                  ("swatches__night", (330, 480, 950, 580))):
    pair = [Image.open(ev / f"frames-{t}" / f"{name}.png").convert("RGB").crop(box) for t in ("base", "e1")]
    w, h = pair[0].size
    scale = 2 if w < 500 else 1
    row = Image.new("RGB", (2 * w * scale + 8, h * scale + 16), (24, 24, 24))
    for i, (img, label) in enumerate(zip(pair, ("base bc547f9", "E1"))):
        row.paste(img.resize((w * scale, h * scale), Image.NEAREST), (i * (w * scale + 8), 16))
        ImageDraw.Draw(row).text((i * (w * scale + 8) + 4, 2), f"{name}: {label}", fill=(230, 230, 230))
    rows.append(row)
sheet = Image.new("RGB", (max(r.width for r in rows), sum(r.height for r in rows)), (24, 24, 24))
y = 0
for r in rows:
    sheet.paste(r, (0, y))
    y += r.height
sheet.save(ev / "sheet_e1_crops.png")
print(sheet.size)
