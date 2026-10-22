"""Generate the starter tileset (assets/tilesets/starter.png + starter.json).

Functional placeholder art: each tile only needs to read clearly as what it is.
Row 0 is ground (walkable), row 1 is walls and obstacles (blocking). Each tile's
``layer`` property tells Mesh Studio which map layer it paints. Deterministic.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from PIL import Image, ImageDraw

T = 32
OUT = Path(__file__).resolve().parents[1] / "assets" / "tilesets"

GROUND = ["Grass", "Flowers", "Path", "Stone floor", "Wood floor", "Sand", "Carpet", "Cobbles"]
WALLS = ["Stone wall", "Brick wall", "Wood wall", "Fence", "Rock", "Bush", "Tree", "Water"]


def _speckle(d: ImageDraw.ImageDraw, x0: int, y0: int, rnd: random.Random, base, var, n=70) -> None:
    d.rectangle([x0, y0, x0 + T - 1, y0 + T - 1], fill=base)
    for _ in range(n):
        x, y = x0 + rnd.randrange(T), y0 + rnd.randrange(T)
        c = tuple(max(0, min(255, v + rnd.randint(-var, var))) for v in base)
        d.point((x, y), fill=c)


def _bricks(d, x0, y0, base, mortar, rows=4, cols=2):
    d.rectangle([x0, y0, x0 + T - 1, y0 + T - 1], fill=mortar)
    h = T // rows
    w = T // cols
    for r in range(rows):
        shift = (w // 2) if r % 2 else 0
        for c in range(-1, cols + 1):
            bx = x0 + c * w + shift
            left, right = max(x0, bx + 1), min(x0 + T - 1, bx + w - 2)
            if right >= left:  # bricks overhanging the tile edge are clipped away
                d.rectangle([left, y0 + r * h + 1, right, y0 + r * h + h - 2], fill=base)


def make() -> None:
    rnd = random.Random(7)
    img = Image.new("RGBA", (T * 8, T * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    g = lambda i: (i * T, 0)  # noqa: E731
    w = lambda i: (i * T, T)  # noqa: E731

    _speckle(d, *g(0), rnd, (86, 160, 72), 18)                       # grass
    _speckle(d, *g(1), rnd, (86, 160, 72), 18)                       # flowers
    for _ in range(7):
        x, y = g(1)[0] + rnd.randrange(3, T - 3), rnd.randrange(3, T - 3)
        d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=rnd.choice([(240, 220, 90), (235, 110, 150), (250, 250, 250)]))
    _speckle(d, *g(2), rnd, (176, 140, 92), 14)                      # path
    _bricks(d, *g(3), (150, 150, 158), (110, 110, 118), rows=2, cols=2)  # stone floor
    x0 = g(4)[0]
    d.rectangle([x0, 0, x0 + T - 1, T - 1], fill=(160, 112, 66))     # wood floor
    for yy in (7, 15, 23):
        d.line([x0, yy, x0 + T - 1, yy], fill=(122, 82, 46))
    _speckle(d, *g(5), rnd, (226, 206, 150), 12)                     # sand
    x0 = g(6)[0]
    d.rectangle([x0, 0, x0 + T - 1, T - 1], fill=(150, 40, 52))      # carpet
    d.rectangle([x0 + 3, 3, x0 + T - 4, T - 4], outline=(214, 170, 70))
    _bricks(d, *g(7), (128, 124, 116), (96, 92, 86), rows=4, cols=3)  # cobbles

    _bricks(d, *w(0), (112, 112, 122), (70, 70, 78))                 # stone wall
    _bricks(d, *w(1), (166, 72, 54), (120, 104, 92))                 # brick wall
    x0 = w(2)[0]
    d.rectangle([x0, T, x0 + T - 1, 2 * T - 1], fill=(112, 74, 42))  # wood wall
    for xx in (7, 15, 23):
        d.line([x0 + xx, T, x0 + xx, 2 * T - 1], fill=(78, 50, 28), width=2)
    x0 = w(3)[0]                                                     # fence
    for xx in (4, 14, 24):
        d.rectangle([x0 + xx, T + 6, x0 + xx + 4, 2 * T - 3], fill=(150, 106, 60))
    d.rectangle([x0, T + 11, x0 + T - 1, T + 14], fill=(170, 124, 72))
    d.rectangle([x0, T + 21, x0 + T - 1, T + 24], fill=(170, 124, 72))
    x0 = w(4)[0]                                                     # rock
    d.ellipse([x0 + 3, T + 7, x0 + T - 4, 2 * T - 3], fill=(128, 126, 122), outline=(84, 82, 80), width=2)
    x0 = w(5)[0]                                                     # bush
    d.ellipse([x0 + 2, T + 4, x0 + T - 3, 2 * T - 3], fill=(46, 112, 46), outline=(28, 76, 28), width=2)
    x0 = w(6)[0]                                                     # tree
    d.rectangle([x0 + 13, T + 20, x0 + 18, 2 * T - 2], fill=(110, 72, 40))
    d.ellipse([x0 + 3, T + 1, x0 + T - 4, T + 23], fill=(38, 120, 52), outline=(24, 80, 34), width=2)
    _speckle(d, *w(7), rnd, (58, 110, 196), 10)                      # water
    x0 = w(7)[0]
    for yy in (9, 21):
        d.arc([x0 + 4, T + yy - 4, x0 + 16, T + yy + 4], 200, 340, fill=(170, 200, 240), width=2)

    OUT.mkdir(parents=True, exist_ok=True)
    img.save(OUT / "starter.png")
    tiles = [
        {"id": i, "properties": [{"name": "layer", "type": "string", "value": "ground"},
                                 {"name": "label", "type": "string", "value": name}]}
        for i, name in enumerate(GROUND)
    ] + [
        {"id": 8 + i, "properties": [{"name": "layer", "type": "string", "value": "walls"},
                                     {"name": "label", "type": "string", "value": name}]}
        for i, name in enumerate(WALLS)
    ]
    tileset = {"type": "tileset", "name": "Starter", "tilewidth": T, "tileheight": T, "columns": 8, "tilecount": 16,
               "image": "starter.png", "imagewidth": T * 8, "imageheight": T * 2, "margin": 0, "spacing": 0, "tiles": tiles}
    (OUT / "starter.json").write_text(json.dumps(tileset, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    make()
