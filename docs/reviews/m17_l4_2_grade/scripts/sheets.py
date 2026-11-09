"""Sheets from matched.py frames: py -3.13 sheets.py MATCHED_DIR OUT
  game_<shot>__<time>.png    Original / Natural / Golden hour / Moonlight / Interior warm (the game's frames)
  studio_<shot>__<time>.png  the same in Mesh Studio's real editing view (its canvas, its lines)
  closeup_<shot>__<time>.png 2x crops per preset: the player (game frames), vegetation, a lamp head (night), the
                             darkest detail region
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

M, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
rep = json.loads((M / "report.json").read_text())
PRESETS = [("off", "Original"), ("natural", "Natural"), ("golden_hour", "Golden hour"), ("moonlight", "Moonlight"),
           ("interior_warm", "Interior warm")]
try:
    FONT = ImageFont.truetype("arial.ttf", 15)
except OSError:
    FONT = ImageFont.load_default()


def sheet(name, tiles, cols, scale):
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


jobs = sorted({tuple(k.split("__")[:2]) for k in rep["frames"]})
for shot, time in jobs:
    game = [(lab, Image.open(M / "game" / f"{shot}__{time}__{p}.png").convert("RGB")) for p, lab in PRESETS]
    sheet(f"game_{shot}__{time}.png", game, 3, 0.5)
    studio = [(f"Studio: {lab}", Image.open(M / "studio_canvas" / f"{shot}__{time}__{p}.png").convert("RGB"))
              for p, lab in PRESETS]
    sheet(f"studio_{shot}__{time}.png", studio, 5, 0.5)
    # close-up regions, chosen on the original
    o = np.asarray(game[0][1]).astype(np.float64)
    y = 0.2126 * o[..., 0] + 0.7152 * o[..., 1] + 0.0722 * o[..., 2]
    regions = {"player": (560, 290, 720, 380) if shot != "interior" else (700, 170, 860, 260)}
    g = o[..., 1] - (o[..., 0] + o[..., 2]) / 2  # greenest 160x90 block: vegetation
    best, at = -1e9, (0, 0)
    dark, dat = 1e9, (0, 0)
    for by in range(0, 720 - 90, 45):
        for bx in range(0, 1280 - 160, 80):
            v = g[by:by + 90, bx:bx + 160].mean()
            if v > best:
                best, at = v, (bx, by)
            m = y[by:by + 90, bx:bx + 160]
            score = m.mean() - m.std() * 2  # dark but with detail
            if m.mean() > 6 and score < dark and shot != "interior":
                dark, dat = score, (bx, by)
    regions["vegetation"] = (at[0], at[1], at[0] + 160, at[1] + 90)
    if shot != "interior":
        regions["dark detail"] = (dat[0], dat[1], dat[0] + 160, dat[1] + 90)
    cams = rep["cameras"].get(f"{shot}__{time}")
    if "lamps" in time:  # the brightest small block: a lamp's glass
        sat = o.max(axis=2) - o.min(axis=2)
        score = np.where((o.max(axis=2) > 200) & (sat > 80), 1, 0)
        ys, xs = np.nonzero(score)
        if len(xs):
            cx, cy = int(np.median(xs)), int(np.median(ys))
            regions["lantern glass"] = (max(0, cx - 80), max(0, cy - 45), max(0, cx - 80) + 160, max(0, cy - 45) + 90)
    tiles = []
    for p, lab in PRESETS:
        im = Image.open(M / "game" / f"{shot}__{time}__{p}.png").convert("RGB")
        for rname, box in regions.items():
            tiles.append((f"{lab}: {rname}", im.crop(box)))
    sheet(f"closeup_{shot}__{time}.png", tiles, len(regions), 2.0)
print("sheets", len(list(OUT.glob("*.png"))))
