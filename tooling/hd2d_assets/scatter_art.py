"""Mesh's starter foliage sprites (Milestone 20D): original pixel art drawn here, deterministic, no third-party art.

    py -3.13 tooling/hd2d_assets/scatter_art.py      writes assets/hd2d_starter/scatter/foliage.png

One sheet of 48 x 48 px cells (1.5 m: 32 px a metre, as the ground and the characters), each a sprite standing on
the cell's bottom row, centred: grass tufts, dry grass, flowers, low bushes, reeds. The HD-2D character style
(``tooling/make_starter_art.py``): colours from the kit's textures, three tones lit from the upper left (the engine's
default sun), outlines a darker shade of what they edge, never near-black. ``engine.hd2d.scatter.SPRITES`` names the
cells in order.
"""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "hd2d_starter" / "scatter" / "foliage.png"
OUT_MOTION = OUT.with_name("foliage_motion.png")  # Milestone 20E's cells (engine.hd2d.scatter.FIRST_MOTION on)
FIRST_MOTION = 17
CELL = 48

# the kit's grass (tooling/hd2d_assets/pixel_textures.py: grass) and its flowers
GRASS = [(62, 104, 48), (74, 124, 54), (84, 136, 60), (96, 150, 66), (132, 178, 86)]  # (the ground's greens, lit tips)
DRY = [(104, 86, 48), (150, 128, 70), (172, 150, 86), (210, 190, 120)]
LEAF = [(50, 88, 46), (68, 118, 56), (84, 138, 64), (110, 160, 80)]
REED = [(92, 120, 60), (110, 140, 70), (128, 156, 82)]
CATTAIL = [(96, 64, 38), (118, 80, 46)]


def _shade(img: Image.Image, outline: bool = True, top: bool = True) -> Image.Image:
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
                sides = ((0, -1), (-1, 0), (1, 0)) if top else ((0, -1),)  # (top=False: under it only)
                near = next(((x + dx, y + dy) for dx, dy in sides if (x + dx, y + dy) in opaque),
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
            c = colours[0] if k < 1 else (colours[-1] if k >= h - 1 else colour)
            if last is not None and abs(x - last) > 1:  # (no gaps where it bends)
                d.point([((x + last) // 2, y)], fill=(*c, 255))
            d.point([(x, y)], fill=(*c, 255))
            last = x


def grass_tuft(seed: int, tall: bool = False, wide: bool = False) -> Image.Image:
    img, d = _cell()
    rng = random.Random(seed)
    n, width, height = (26, 9, (8, 16)) if tall else (28, 16, (4, 9)) if wide else (22, 10, (5, 11))
    _blades(d, rng, n, width, height, GRASS, 2.6 if wide else 2.0)
    return img


def dry_grass(seed: int) -> Image.Image:
    img, d = _cell()
    rng = random.Random(seed)
    _blades(d, rng, 11, 12, (4, 11), DRY, lean=3.2)  # (few, leaning: blades, not a stook)
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
    shape = {(x, y) for y in range(CELL) for x in range(CELL) if px[x, y][3]}
    for x in range(CELL):  # a leafy top edge: 1-2 px notches out of the dome's outline
        column = [y for y in range(CELL) if (x, y) in shape]
        if column and rng.random() < 0.45:
            for y in column[: rng.choice([1, 2])]:
                shape.discard((x, y))
                px[x, y] = (0, 0, 0, 0)
    for x, y in shape:  # the dome's shade: lighter up and to the left, darker low down and to the right
        k = (y - (CELL - height)) / height * 0.9 + (x - cx) / width * 0.5
        px[x, y] = (*LEAF[0 if k > 0.75 else 1 if k > 0.35 else 2], 255)
    for _ in range(18):  # leaf clusters, 3-4 px, lit on top (not a speckle: clumps of leaves read as a bush)
        x, y = cx + rng.randint(-width // 2 + 2, width // 2 - 2), CELL - 1 - rng.randint(3, height - 2)
        if (x, y) in shape:
            lit = (128, 178, 92) if y < CELL - height * 0.55 else LEAF[3]  # (lit clusters stand out on the dome)
            for dx, dy in ((0, 0), (1, 0), (0, 1), (-1, 1), (1, 1)):
                if (x + dx, y + dy) in shape:
                    px[x + dx, y + dy] = (*(lit if dy == 0 else LEAF[1]), 255)
    if berries:
        for _ in range(7):
            x, y = cx + rng.randint(-width // 2 + 3, width // 2 - 3), CELL - 1 - rng.randint(4, height - 3)
            if px[x, y][3]:
                px[x, y] = (*berries, 255)
    return _shade(img, top=False)


def reeds(seed: int, heads: int = 3) -> Image.Image:
    img, d = _cell()
    rng = random.Random(seed)
    _blades(d, rng, 15, 8, (16, 32), [(58, 78, 40), *REED, (156, 178, 100)], lean=1.2)
    cx = CELL // 2
    for _ in range(heads):  # cattails: a brown head on a stalk
        x, top = cx + rng.randint(-4, 4), CELL - 1 - rng.randint(28, 38)
        d.line([(x, CELL - 1), (x, top + 5)], fill=(*REED[1], 255))
        d.rectangle([x - 1, top, x, top + 5], fill=(*CATTAIL[0], 255))
        d.point([(x - 1, top)], fill=(*CATTAIL[1], 255))
        d.point([(x, top - 1), (x, top - 2)], fill=(*REED[2], 255))
    return img


# ---------------------------------------------------------------------- Milestone 20E: animated decoration, a tree
WOOD = [(70, 48, 32), (96, 66, 42), (124, 88, 56), (150, 112, 72)]
IRON = [(48, 46, 54), (72, 70, 80), (98, 96, 104)]
FLAME = [(198, 72, 30), (236, 124, 42), (252, 186, 70), (255, 238, 164)]
FLAME_EDGE = (138, 40, 26)
CLOTH = [(104, 28, 36), (140, 40, 48), (172, 58, 62), (214, 176, 84)]
STONE = [(70, 72, 76), (92, 94, 98), (118, 118, 120), (146, 144, 140)]
MOSS = [(64, 96, 50), (86, 122, 60)]
WATER = [(120, 160, 196), (170, 204, 230), (216, 236, 250)]
GLOW = [(40, 92, 90), (70, 146, 136), (118, 192, 172)]  # (muted toward the kit's greens: they glow in the dark)
BELL = [(78, 76, 128), (104, 100, 160), (140, 136, 188)]


def torch_post() -> Image.Image:
    """A wooden post with an iron cup at the top (0.94 m: the flame, a part of its own, stands in the cup)."""
    img, d = _cell()
    cx = CELL // 2
    d.rectangle([cx - 2, 19, cx + 1, CELL - 1], fill=(*WOOD[2], 255))
    d.line([(cx - 2, 19), (cx - 2, CELL - 1)], fill=(*WOOD[3], 255))
    for y in range(22, CELL - 1, 6):  # the grain
        d.point([(cx, y), (cx - 1, y + 3)], fill=(*WOOD[1], 255))
    d.rectangle([cx - 4, 16, cx + 3, 19], fill=(*IRON[1], 255))  # the cup
    d.line([(cx - 4, 16), (cx + 3, 16)], fill=(*IRON[2], 255))
    d.rectangle([cx - 3, 20, cx + 2, 21], fill=(*IRON[0], 255))  # its band
    return _shade(img, top=False)


def flame(frame: int) -> Image.Image:
    """A torch's flame (one of six): a tongue of fire standing in the cup (the cell's bottom row, no wider than the
    cup), its tip leaning and forking, a dark red edge round it, sparks rising off it."""
    img = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
    cx = CELL // 2
    height = (12, 14, 11, 15, 13, 12)[frame]
    lean = (0.0, 1.0, 1.5, 0.5, -1.0, -1.5)[frame]
    fork = frame in (1, 3)
    shape = set()
    for y in range(height):
        t = y / height
        half = 2.6 * (1 - t) ** 0.7 + (0.4 if y < 3 else 0.0)
        x0 = cx - 0.5 + lean * t * t * 2.0
        for x in range(round(x0 - half), round(x0 + half) + 1):
            if fork and t > 0.7 and abs(x - x0) < 0.6:
                continue  # (a forked tip)
            shape.add((x, CELL - 1 - y))
    for x, y in shape:
        t = (CELL - 1 - y) / height
        inner = sum((x + dx, y + dy) in shape for dx, dy in ((1, 0), (-1, 0), (0, -1), (0, 1))) == 4
        tone = 3 if inner and t < 0.45 else 2 if inner else 1 if t < 0.8 else 0
        img.putpixel((x, y), (*FLAME[tone], 255))
    px: Any = img.load()
    for x, y in shape:  # the dark red edge, beside and over it (its foot is in the cup)
        for dx, dy in ((1, 0), (-1, 0), (0, -1)):
            q = (x + dx, y + dy)
            if q not in shape and 0 <= q[0] < CELL and 0 <= q[1] < CELL and px[q][3] == 0:
                px[q] = (*FLAME_EDGE, 255)
    for k in range(2):  # sparks: each rises a little more each frame
        rise = (frame * 2 + k * 5) % 9
        x = cx + (-2 if k else 2) + round(lean * 0.7) + (rise // 4) * (1 if k else -1)
        img.putpixel((x, CELL - 1 - height - 2 - rise), (*FLAME[2 if rise < 5 else 1], 255))
    return img


def banner_pole() -> Image.Image:
    """A banner's pole: 1.2 m, a gilt knob on top (the cloth is a part of its own)."""
    img, d = _cell()
    cx = CELL // 2
    d.rectangle([cx - 1, 9, cx, CELL - 1], fill=(*WOOD[1], 255))
    d.line([(cx - 1, 9), (cx - 1, CELL - 1)], fill=(*WOOD[2], 255))
    d.rectangle([cx - 2, 6, cx + 1, 8], fill=(*CLOTH[3], 255))
    return _shade(img, top=False)


def banner_cloth(frame: int) -> Image.Image:
    """The cloth (one of four), fixed to the pole along its left edge (the cell's centre), streaming right: a wave
    runs along it, larger toward its free end."""
    img = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
    cx, length, height = CELL // 2, 17, 17
    for i in range(length):
        k = i / length
        dy = round(2.2 * k * math.sin(i * 0.55 - frame * math.pi / 2))
        top = CELL - height + dy
        bottom = CELL - 1 + dy - (1 if i == length - 1 else 0)
        for y in range(max(0, top), min(CELL, bottom + 1)):
            stripe = height * 0.45 <= y - top <= height * 0.58
            shade = 3 if stripe else 2 if math.sin(i * 0.55 - frame * math.pi / 2 + 1.2) > 0.3 else 1
            img.putpixel((cx + i, y), (*CLOTH[shade], 255))
        if i % 2 == 0 and i > 2:  # a ragged lower hem
            img.putpixel((cx + i, min(CELL - 1, bottom + 1)), (*CLOTH[0], 255))
    px: Any = img.load()
    for y in range(CELL - height, CELL):
        if px[cx, y][3]:
            img.putpixel((cx, y), (*CLOTH[0], 255))
    return img


def banner_limp() -> Image.Image:
    """The cloth in still air: hanging down beside the pole from the same top, folds down its length."""
    img = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
    cx, height = CELL // 2, 17
    for y in range(CELL - height, CELL):
        depth = y - (CELL - height)
        width = 4 + (1 if depth > 6 else 0)
        for i in range(width):
            fold = (i + depth // 5) % 3 == 0
            stripe = height * 0.45 <= depth <= height * 0.58
            img.putpixel((cx + i, y), (*CLOTH[3 if stripe and i else 0 if i == 0 else 1 if fold else 2], 255))
    for i in range(1, 5, 2):  # a ragged lower hem
        img.putpixel((cx + i, CELL - 1), (0, 0, 0, 0))
    return img


def dripping_rock(frame: int) -> Image.Image:
    """A mossy rock with an overhanging lip that water drips from (one of four): a drop forms, swells, falls and
    splashes into the little pool at the rock's foot. Shaded and outlined as the kit's other sprites."""
    img, d = _cell()
    rng = random.Random(611)
    d.polygon([(12, 47), (11, 40), (13, 33), (17, 29), (24, 28), (30, 30), (32, 32), (29, 34), (28, 40), (29, 47)],
              fill=(*STONE[1], 255))  # (its lip juts out to the right)
    px: Any = img.load()
    shape = {(x, y) for y in range(CELL) for x in range(CELL) if px[x, y][3]}
    for x, y in shape:  # lit up and to the left, a darker foot
        k = (y - 28) / 19 * 0.8 + (x - 12) / 20 * 0.5
        px[x, y] = (*STONE[3 if k < 0.25 else 2 if k < 0.55 else 1 if k < 0.9 else 0], 255)
    for _ in range(14):  # its grain
        x, y = rng.randint(13, 28), rng.randint(31, 46)
        if (x, y) in shape:
            px[x, y] = (*STONE[0], 255)
    for x, y in ((18, 35), (19, 36), (19, 37), (24, 41), (25, 42)):  # a crack
        if (x, y) in shape:
            px[x, y] = (*STONE[0], 255)
    for x in range(14, 31):  # moss along its top
        col = [y for y in range(CELL) if (x, y) in shape]
        if col and rng.random() < 0.85:
            for y in col[:rng.choice([1, 2])]:
                px[x, y] = (*MOSS[rng.randint(0, 1)], 255)
    out = _shade(img)
    o: Any = out.load()
    for x in range(28, 37):  # the pool: against the rock's foot, under the drip
        o[x, CELL - 1] = (*WATER[0 if x in (28, 36) else 1], 255)
    drop: list[list[tuple[int, int]]] = [[(30, 33)], [(30, 33), (31, 33), (30, 34), (31, 34)],
                                         [(30, 40), (31, 40), (30, 41), (31, 41), (30, 39)], []]
    for x, y in drop[frame]:
        o[x, y] = (*WATER[2], 255)
    if frame == 3:  # the splash
        for x, y in ((29, 45), (32, 45), (28, 44), (33, 44), (30, 46), (31, 46)):
            o[x, y] = (*WATER[2 if y < 46 else 1], 255)
    return out


def glowcaps(frame: int) -> Image.Image:
    """Three small glowing mushrooms (one of two: their spores drifting up), dark-edged caps. They shine in the
    dark (Asset.glow); by day they are muted, as the kit's other plants."""
    img, d = _cell()
    cx = CELL // 2
    for x, h, w in ((cx - 5, 7, 3), (cx + 1, 10, 4), (cx + 6, 5, 3)):
        d.line([(x, CELL - 1), (x, CELL - h)], fill=(176, 182, 160, 255))
        d.ellipse([x - w, CELL - h - 3, x + w, CELL - h + 1], fill=(*GLOW[1], 255))
        d.line([(x - w + 1, CELL - h - 2), (x, CELL - h - 3)], fill=(*GLOW[2], 255))
        d.line([(x - w, CELL - h), (x + w, CELL - h)], fill=(*GLOW[0], 255))
        d.point([(x - w, CELL - h - 1), (x + w, CELL - h - 1)], fill=(*GLOW[0], 255))
    rng = random.Random(620 + frame)
    for _ in range(3):
        img.putpixel((cx + rng.randint(-7, 7), CELL - 14 - rng.randint(0, 8)), (*GLOW[2], 255))
    return img


def bellflowers(frame: int) -> Image.Image:
    """Bellflowers on arching stalks (one of three: the bells nodding)."""
    img, d = _cell()
    rng = random.Random(630)
    _blades(d, rng, 9, 12, (3, 7), LEAF, lean=2.2)
    cx = CELL // 2
    nod = (0, 1, 2)[frame]
    for k in range(5):
        x0, h = cx + (-6, -2, 2, 5, 8)[k] - 1, (12, 15, 11, 14, 10)[k]
        tip = (x0 + 2 + nod * (1 if k % 2 else 0), CELL - h + nod // 2)
        d.line([(x0, CELL - 1), (x0, CELL - h + 2), tip], fill=(*LEAF[1], 255))
        bx, by = tip
        d.polygon([(bx - 1, by + 1), (bx + 1, by + 1), (bx + 2, by + 4), (bx - 2, by + 4)], fill=(*BELL[1], 255))
        d.point([(bx - 1, by + 2)], fill=(*BELL[2], 255))
        d.point([(bx + 1, by + 4), (bx + 2, by + 4)], fill=(*BELL[0], 255))
    return img


def trunk_sprite() -> Image.Image:
    """A small tree's trunk as a flat sprite (for comparing ways to draw a tree: the starter tree's is a model)."""
    img, d = _cell()
    cx = CELL // 2
    for y in range(4, CELL):
        half = 1.5 + 1.8 * (y / CELL) ** 2
        d.line([(round(cx - half), y), (round(cx + half), y)], fill=(*WOOD[1], 255))
    d.line([(cx, 22), (cx + 7, 12)], fill=(*WOOD[1], 255), width=2)
    d.line([(cx - 1, 28), (cx - 8, 18)], fill=(*WOOD[1], 255), width=2)
    return _shade(img, top=False)


def canopy(seed: int, width: int, height: int) -> Image.Image:
    """A cluster of a tree's leaves, attached at its bottom middle (where it sways from): leafy lumps in a rounded
    crown, lit from the upper left, a few dark gaps, a ragged edge."""
    img, d = _cell()
    rng = random.Random(seed)
    cx = CELL // 2
    for _ in range(34):
        rx, ry = rng.randint(3, 7), rng.randint(3, 6)
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(0, 1) ** 0.6
        x = cx + round(math.cos(a) * r * (width / 2 - rx))
        y = CELL - 1 - height // 2 + round(math.sin(a) * r * (height / 2 - ry))
        d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=(*LEAF[1], 255))
    px: Any = img.load()
    shape = {(x, y) for y in range(CELL) for x in range(CELL) if px[x, y][3]}
    for x, y in list(shape):  # a ragged edge
        if any((x + dx, y + dy) not in shape for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))) and rng.random() < 0.3:
            shape.discard((x, y))
            px[x, y] = (0, 0, 0, 0)
    top = CELL - height
    for x, y in shape:  # the crown's shade: lit up and to the left
        k = (y - top) / height * 0.8 + (x - cx) / width * 0.6
        px[x, y] = (*LEAF[0 if k > 0.8 else 1 if k > 0.4 else 2], 255)
    for _ in range(26):  # lit leaf clumps, a few dark gaps
        x, y = cx + rng.randint(-width // 2 + 2, width // 2 - 2), CELL - 1 - rng.randint(3, height - 2)
        lit = (y - top) / height < 0.55
        for dx, dy in ((0, 0), (1, 0), (0, 1)):
            if (x + dx, y + dy) in shape:
                px[x + dx, y + dy] = (*((128, 178, 92) if lit else LEAF[0]), 255)
    return _shade(img, top=False)


SHEET = [  # cells in the order engine.hd2d.scatter.ASSETS uses them (several variants a thing; 17 on: 20E's sheet)
    lambda: grass_tuft(71), lambda: grass_tuft(81), lambda: grass_tuft(91, wide=True),  # 0-2 grass tuft
    lambda: grass_tuft(72, tall=True), lambda: grass_tuft(82, tall=True),  # 3-4 tall grass
    lambda: dry_grass(73), lambda: dry_grass(83),  # 5-6 dry grass
    lambda: flowers(74, [(236, 220, 120), (244, 236, 160)]), lambda: flowers(84, [(236, 220, 120), (250, 246, 220)]),
    lambda: flowers(75, [(230, 150, 170), (238, 232, 226)]), lambda: flowers(85, [(214, 140, 196), (238, 232, 226)]),
    lambda: bush(76, 34, 22), lambda: bush(86, 30, 20),  # 11-12 bush
    lambda: bush(77, 26, 16, berries=(186, 62, 64)),  # 13 berry bush
    lambda: reeds(78, heads=0), lambda: reeds(88, heads=1),  # 14-15 reeds
    lambda: reeds(79),  # 16 cattails
    torch_post, *(lambda f=f: flame(f) for f in range(6)),  # 17 torch, 18-23 its flame
    banner_pole, *(lambda f=f: banner_cloth(f) for f in range(4)), banner_limp,  # 24 banner, 25-28 cloth, 29 limp
    *(lambda f=f: dripping_rock(f) for f in range(4)),  # 30-33 dripping rock
    *(lambda f=f: glowcaps(f) for f in range(2)),  # 34-35 glowcaps
    *(lambda f=f: bellflowers(f) for f in range(3)),  # 36-38 bellflowers
    trunk_sprite,  # 39 a trunk as a sprite (comparisons only)
    lambda: canopy(641, 40, 30), lambda: canopy(642, 32, 24), lambda: canopy(643, 36, 28),  # 40-42 canopy clusters
]


def sheet(cells: list[Any]) -> Image.Image:
    out = Image.new("RGBA", (CELL * len(cells), CELL), (0, 0, 0, 0))
    for k, make in enumerate(cells):
        out.paste(make(), (k * CELL, 0))
    return out


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for path, cells in ((OUT, SHEET[:FIRST_MOTION]), (OUT_MOTION, SHEET[FIRST_MOTION:])):
        sheet(cells).save(path)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
