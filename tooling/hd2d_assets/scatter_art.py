"""Mesh's starter foliage sprites (Milestone 20D): original pixel art drawn here, deterministic, no third-party art.

    py -3.13 tooling/hd2d_assets/scatter_art.py      writes assets/hd2d_starter/scatter/foliage.png

One sheet of 48 x 48 px cells (1.5 m: 32 px a metre, as the ground and the characters), each a sprite standing on
the cell's bottom row, centred: grass tufts, dry grass, flowers, low bushes, reeds. The HD-2D character style
(``tooling/make_starter_art.py``): colours from the kit's textures, three tones lit from the upper left (the engine's
default sun), outlines a darker shade of what they edge, never near-black. ``engine.hd2d.scatter.SPRITES`` names the
cells in order.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "hd2d_starter" / "scatter" / "foliage.png"
CELL = 48

# the kit's grass (tooling/hd2d_assets/pixel_textures.py: grass) and its flowers
GRASS = [(46, 80, 38), (96, 150, 64), (108, 164, 72), (120, 176, 80), (164, 202, 104)]  # (brighter than the ground)
DRY = [(104, 86, 48), (150, 128, 70), (172, 150, 86), (210, 190, 120)]
LEAF = [(52, 92, 46), (70, 122, 58), (86, 142, 66), (104, 160, 78)]
REED = [(92, 120, 60), (110, 140, 70), (128, 156, 82)]
CATTAIL = [(96, 64, 38), (118, 80, 46)]


def _shade(img: Image.Image, outline: bool = True) -> Image.Image:
    """Light from the upper left: right and lowest edges darker, upper-left edges lighter; then (``outline``) a
    one-pixel outline in a darker shade of the colour it edges, below and to the sides only (tops stay soft)."""
    w, h = img.size
    px: Any = img.load()  # (PixelAccess: its items are RGBA tuples here)
    assert px is not None
    opaque = {(x, y) for y in range(h) for x in range(w) if px[x, y][3]}
    out = img.copy()
    po: Any = out.load()
    assert po is not None

    def tone(c: tuple, k: float, toward: tuple, t: float) -> tuple:
        return tuple(round(min(255, c[i] * k * (1 - t) + toward[i] * t)) for i in range(3)) + (255,)

    for x, y in opaque:
        c = px[x, y]
        if (x + 1, y) not in opaque or y >= h - 1:
            po[x, y] = tone(c, 0.78, (40, 44, 72), 0.10)
        elif (x - 1, y) not in opaque or (x, y - 1) not in opaque:
            po[x, y] = tone(c, 1.0, (255, 240, 200), 0.16)
    if outline:
        for y in range(h):
            for x in range(w):
                if (x, y) in opaque:
                    continue
                near = next(((x + dx, y + dy) for dx, dy in ((0, -1), (-1, 0), (1, 0)) if (x + dx, y + dy) in opaque),
                            None)  # (the pixel above, or beside: an outline under and around, not over the tips)
                if near is not None and y < h:
                    po[x, y] = tone(po[near], 0.5, (24, 20, 30), 0.25)
    return out


def _cell() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _blades(d: ImageDraw.ImageDraw, rng: random.Random, n: int, width: int, height: tuple[int, int],
            colours: list[tuple], lean: float = 2.0) -> None:
    """Blades fanning out from a base ``width`` px wide, one pixel thick (no outline: thin things stay light), each
    dark where it meets the ground, its own green along it and lit at its tip."""
    cx = CELL // 2
    for _ in range(n):
        x0 = cx + round(rng.gauss(0, width / 4))
        h = rng.randint(*height)
        spread = (x0 - cx) / max(1.0, width / 2) * lean * 2 + rng.uniform(-lean, lean)
        colour = rng.choice(colours[1:-1] or colours[1:])
        last = None
        for k in range(h + 1):
            t = k / max(1, h)
            x, y = round(x0 + spread * t * t), CELL - 1 - k
            c = colours[0] if k < 2 else (colours[-1] if k >= h - 1 else colour)
            if last is not None and abs(x - last) > 1:  # (no gaps where it bends)
                d.point([((x + last) // 2, y)], fill=(*c, 255))
            d.point([(x, y)], fill=(*c, 255))
            last = x


def grass_tuft(seed: int, tall: bool = False) -> Image.Image:
    img, d = _cell()
    rng = random.Random(seed)
    _blades(d, rng, 24 if not tall else 26, 10 if not tall else 9, (5, 11) if not tall else (8, 16), GRASS, 2.0)
    return img


def dry_grass(seed: int) -> Image.Image:
    img, d = _cell()
    rng = random.Random(seed)
    _blades(d, rng, 20, 10, (4, 10), DRY, lean=2.0)
    return img


def flowers(seed: int, petals: list[tuple]) -> Image.Image:
    img, d = _cell()
    rng = random.Random(seed)
    _blades(d, rng, 10, 14, (3, 7), LEAF, lean=2.5)
    cx = CELL // 2
    for _ in range(9):  # small heads on short stalks
        x, top = cx + rng.randint(-8, 8), CELL - 1 - rng.randint(6, 11)
        d.line([(x, CELL - 1), (x, top + 1)], fill=(*LEAF[1], 255))
        colour = rng.choice(petals)
        d.point([(x, top), (x - 1, top + 1), (x + 1, top + 1), (x, top + 2)], fill=(*colour, 255))
        d.point([(x, top + 1)], fill=(236, 214, 110, 255))
    return img


def bush(seed: int, width: int, height: int, berries: tuple | None = None) -> Image.Image:
    img, d = _cell()
    rng = random.Random(seed)
    cx = CELL // 2
    for _ in range(26):  # leafy lumps, bigger low down, the whole a low dome
        rx, ry = rng.randint(3, 6), rng.randint(3, 5)
        x = cx + rng.randint(-width // 2 + rx, width // 2 - rx)
        lift = height * (1 - (abs(x - cx) / (width / 2)) ** 2)
        y = CELL - 1 - ry - rng.randint(0, max(0, int(lift) - 2 * ry))
        d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=(*LEAF[1], 255))
    px: Any = img.load()  # (PixelAccess: its items are RGBA tuples here)
    assert px is not None
    for y in range(CELL):  # leaf texture: speckle of the four greens, darker towards the bottom
        for x in range(CELL):
            if px[x, y][3]:
                k = rng.random() + (y - (CELL - height)) / height * 0.6
                px[x, y] = (*LEAF[0 if k > 1.1 else 1 if k > 0.7 else 2 if k > 0.25 else 3], 255)
    if berries:
        for _ in range(7):
            x, y = cx + rng.randint(-width // 2 + 3, width // 2 - 3), CELL - 1 - rng.randint(4, height - 3)
            if px[x, y][3]:
                px[x, y] = (*berries, 255)
    return _shade(img)


def reeds(seed: int) -> Image.Image:
    img, d = _cell()
    rng = random.Random(seed)
    _blades(d, rng, 15, 8, (16, 32), [(58, 78, 40), *REED, (156, 178, 100)], lean=1.2)
    cx = CELL // 2
    for _ in range(3):  # cattails: a brown head on a stalk
        x, top = cx + rng.randint(-4, 4), CELL - 1 - rng.randint(28, 38)
        d.line([(x, CELL - 1), (x, top + 5)], fill=(*REED[1], 255))
        d.rectangle([x - 1, top, x, top + 5], fill=(*CATTAIL[0], 255))
        d.point([(x - 1, top)], fill=(*CATTAIL[1], 255))
        d.point([(x, top - 1), (x, top - 2)], fill=(*REED[2], 255))
    return img


SHEET = [  # in engine.hd2d.scatter.SPRITES order
    lambda: grass_tuft(71), lambda: grass_tuft(72, tall=True), lambda: dry_grass(73),
    lambda: flowers(74, [(236, 220, 120), (244, 236, 160)]), lambda: flowers(75, [(230, 150, 170), (238, 232, 226)]),
    lambda: bush(76, 34, 22), lambda: bush(77, 26, 16, berries=(186, 62, 64)), lambda: reeds(78), lambda: reeds(79),
]


def sheet() -> Image.Image:
    out = Image.new("RGBA", (CELL * len(SHEET), CELL), (0, 0, 0, 0))
    for k, make in enumerate(SHEET):
        out.paste(make(), (k * CELL, 0))
    return out


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sheet().save(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
