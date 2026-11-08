"""E2 close-up sheet: per scene, the lamp head zoomed (glass and frame) and a wider crop with its light pool, E1 base
beside E2. py -3.13 crops.py <ev dir>"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ev = Path(sys.argv[1])
WEST, EAST = (452, 228, 512, 278), (772, 228, 832, 278)  # lamp heads (zoom x5)
WEST_WIDE, EAST_WIDE = (400, 180, 600, 420), (720, 180, 920, 420)  # with the pool (x1.5)
ROWS = [("village_on_noon", "west"), ("village_on_evening", "west"), ("village_on_night", "west"),
        ("village_off_night", "west"), ("village_blue_east_night", "east"), ("village_dim_west_night", "west"),
        ("village_bright_west_night", "west"), ("village_zero_west_night", "west"),
        ("village_zero_west_night", "east")]
rows = []
for name, side in ROWS:
    close, wide = (WEST, WEST_WIDE) if side == "west" else (EAST, EAST_WIDE)
    tiles = []
    for tag in ("base", "e2"):
        img = Image.open(ev / f"frames-{tag}" / f"{name}.png").convert("RGB")
        c = img.crop(close)
        tiles.append(c.resize((c.width * 5, c.height * 5), Image.NEAREST))
    for tag in ("base", "e2"):
        img = Image.open(ev / f"frames-{tag}" / f"{name}.png").convert("RGB")
        c = img.crop(wide)
        tiles.append(c.resize((int(c.width * 1.25), int(c.height * 1.25)), Image.NEAREST))
    h = max(t.height for t in tiles)
    row = Image.new("RGB", (sum(t.width for t in tiles) + 8 * len(tiles), h + 16), (24, 24, 24))
    x = 0
    for t, label in zip(tiles, ("E1 head", "E2 head", "E1 with pool", "E2 with pool")):
        row.paste(t, (x, 16))
        ImageDraw.Draw(row).text((x + 4, 2), f"{name} ({side}): {label}", fill=(230, 230, 230))
        x += t.width + 8
    rows.append(row)
sheet = Image.new("RGB", (max(r.width for r in rows), sum(r.height for r in rows)), (24, 24, 24))
y = 0
for r in rows:
    sheet.paste(r, (0, y))
    y += r.height
sheet.save(ev / "sheet_e2_closeups.png")
print(sheet.size)
