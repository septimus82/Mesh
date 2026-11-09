"""Sheets from lab.py frames: py -3.13 make_sheets.py FRAMES OUT
  baseline_<shot>.png        the shot at every time of day (original renderer)
  effects_<shot>__<time>.png every candidate, labelled, for one shot and time
  closeup_<shot>__<time>.png 2x crops of the frame centre (the followed character) and, with lamps, a lamp head
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FR, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
M = json.loads((FR / "metrics.json").read_text(encoding="utf-8"))
try:
    FONT = ImageFont.truetype("arial.ttf", 15)
except OSError:
    FONT = ImageFont.load_default()
SHOTS = ["village", "shore", "bridge", "cottage", "cottage2", "interior"]
TIMES = ["authored", "morning", "noon", "evening", "night", "night_lamps"]
CANDS = ["original", "grade", "vignette", "vignette_strong", "haze", "haze_overlay", "dof_subtle", "dof_miniature",
         "combo", "combo_dof", "debug_depth", "debug_haze"]


def sheet(name: str, tiles: list[tuple[str, Image.Image]], cols: int, scale: float) -> None:
    if not tiles:
        return
    w, h = int(tiles[0][1].width * scale), int(tiles[0][1].height * scale)
    pad = 22
    rows = (len(tiles) + cols - 1) // cols
    s = Image.new("RGB", (cols * w, rows * (h + pad)), (24, 24, 24))
    d = ImageDraw.Draw(s)
    for i, (lab, im) in enumerate(tiles):
        x, y = (i % cols) * w, (i // cols) * (h + pad)
        s.paste(im.resize((w, h), Image.NEAREST if scale >= 1 else Image.LANCZOS), (x, y + pad))
        d.text((x + 6, y + 3), lab, fill=(235, 235, 235), font=FONT)
    s.save(OUT / name)


def frame(shot: str, time: str, cand: str) -> Image.Image | None:
    p = FR / f"{shot}__{time}__{cand}.png"
    return Image.open(p).convert("RGB") if p.exists() else None


for shot in SHOTS:
    sheet(f"baseline_{shot}.png", [(t, im) for t in TIMES if (im := frame(shot, t, "original"))], 3, 0.5)
    for time in TIMES:
        tiles = []
        for c in CANDS:
            im = frame(shot, time, c)
            if im is None:
                continue
            e = M.get(f"{shot}__{time}__{c}", {})
            tiles.append((e.get("label") or c, im))
        if len(tiles) > 1:
            sheet(f"effects_{shot}__{time}.png", tiles, 3, 0.5)
        crops = []
        for c in ("original", "grade", "vignette", "haze", "dof_subtle", "dof_miniature", "combo", "combo_dof"):
            im = frame(shot, time, c)
            if im is None:
                continue
            crops.append((f"{c}: centre", im.crop((480, 270, 800, 450))))
            lamps = M.get(f"{shot}__{time}__{c}", {}).get("lamp_heads") or []
            if lamps:
                x, y = lamps[0]["at"]
                x0, y0 = max(0, min(1280 - 160, x - 80)), max(0, min(720 - 90, y - 45))
                crops.append((f"{c}: lamp head", im.crop((x0, y0, x0 + 160, y0 + 90)).resize((320, 180), Image.NEAREST)))
        if len(crops) > 1:
            sheet(f"closeup_{shot}__{time}.png", crops, 4 if any("lamp" in c[0] for c in crops) else 4, 2.0
                  if not any("lamp" in c[0] for c in crops) else 1.0)
print("sheets:", len(list(OUT.glob("*.png"))))
