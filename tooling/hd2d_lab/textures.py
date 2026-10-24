"""The lab's pixel-art textures, drawn here (original, deterministic; no third-party art).

    py -3.13 tooling/hd2d_lab/textures.py      writes tooling/hd2d_lab/assets/*.png (32 x 32, one per metre)
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "assets"
SIZE = 32


def _noise(img: Image.Image, rng: random.Random, colours: list[tuple[int, int, int]], amount: int) -> None:
    px = img.load()
    for _ in range(amount):
        x, y = rng.randrange(img.width), rng.randrange(img.height)
        px[x, y] = (*rng.choice(colours), 255)


def stone_wall(seed: int = 16) -> Image.Image:
    """Courses of grey stone blocks with dark mortar."""
    rng = random.Random(seed)
    img = Image.new("RGBA", (SIZE, SIZE), (58, 56, 66, 255))  # mortar
    d = ImageDraw.Draw(img)
    stones = [(122, 118, 128), (108, 104, 116), (132, 128, 136), (98, 96, 108)]
    for row, top in enumerate(range(0, SIZE, 8)):
        offset = 0 if row % 2 == 0 else 8
        for left in range(-16 + offset, SIZE, 16):
            colour = rng.choice(stones)
            d.rectangle([left + 1, top + 1, left + 14, top + 6], fill=(*colour, 255))
            d.line([left + 1, top + 1, left + 14, top + 1], fill=(min(255, colour[0] + 22),) * 3 + (255,))
            d.line([left + 1, top + 6, left + 14, top + 6], fill=(colour[0] - 26, colour[1] - 26, colour[2] - 22, 255))
    _noise(img, rng, [(88, 86, 96), (140, 136, 144)], 40)
    return img


def stone_top(seed: int = 17) -> Image.Image:
    """Flagstones seen from above."""
    rng = random.Random(seed)
    img = Image.new("RGBA", (SIZE, SIZE), (70, 68, 76, 255))
    d = ImageDraw.Draw(img)
    for (x0, y0, x1, y1) in ((1, 1, 14, 14), (17, 1, 30, 10), (17, 13, 30, 30), (1, 17, 14, 30)):
        c = rng.choice([(146, 140, 132), (136, 130, 124), (156, 150, 140)])
        d.rectangle([x0, y0, x1, y1], fill=(*c, 255))
        d.line([x0, y0, x1, y0], fill=(c[0] + 18, c[1] + 18, c[2] + 16, 255))
    _noise(img, rng, [(118, 112, 106), (168, 162, 152)], 36)
    return img


def roof(seed: int = 18) -> Image.Image:
    """Rows of red-brown slates."""
    rng = random.Random(seed)
    img = Image.new("RGBA", (SIZE, SIZE), (70, 30, 28, 255))
    d = ImageDraw.Draw(img)
    for row, top in enumerate(range(0, SIZE, 6)):
        offset = 0 if row % 2 == 0 else 4
        for left in range(-8 + offset, SIZE, 8):
            c = rng.choice([(150, 62, 48), (136, 54, 44), (164, 74, 56)])
            d.rectangle([left + 1, top, left + 6, top + 4], fill=(*c, 255))
            d.line([left + 1, top + 4, left + 6, top + 4], fill=(96, 38, 34, 255))
    return img


def grass(seed: int = 19) -> Image.Image:
    """Short grass with a few tufts and flowers."""
    rng = random.Random(seed)
    img = Image.new("RGBA", (SIZE, SIZE), (74, 128, 64, 255))
    _noise(img, rng, [(64, 116, 56), (86, 142, 72), (58, 104, 50)], 260)
    px = img.load()
    for _ in range(10):
        x, y = rng.randrange(1, SIZE - 1), rng.randrange(2, SIZE)
        px[x, y - 1] = px[x, y - 2] = (98, 160, 80, 255)
    for _ in range(2):
        x, y = rng.randrange(2, SIZE - 2), rng.randrange(2, SIZE - 2)
        px[x, y] = (236, 220, 96, 255)
    return img


TEXTURES = {"stone_wall": stone_wall, "stone_top": stone_top, "roof": roof, "grass": grass}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, draw in TEXTURES.items():
        draw().save(OUT / f"{name}.png")
    print(f"{len(TEXTURES)} textures -> {OUT}")


if __name__ == "__main__":
    main()
