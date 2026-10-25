"""Pixel-art textures for the Stage 5B demonstration models, drawn here (original, deterministic; no third-party art).

    py -3.13 tooling/hd2d_assets/pixel_textures.py     writes tooling/hd2d_assets/textures/*.png (32 x 32, one per metre)

The way a creator would make them in PixelLab or Aseprite: a small palette, hard edges, no anti-aliasing, one tile
per metre of surface, seamless when repeated. Blender then samples them with "Closest" interpolation.
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "textures"
SIZE = 32


def _speckle(img: Image.Image, rng: random.Random, colours: list[tuple[int, int, int]], amount: int) -> None:
    px = img.load()
    assert px is not None
    for _ in range(amount):
        px[rng.randrange(img.width), rng.randrange(img.height)] = (*rng.choice(colours), 255)


def timber() -> Image.Image:
    """Horizontal weatherboards: four boards per metre, each with a dark lower lip and a few knots."""
    rng = random.Random(51)
    img = Image.new("RGBA", (SIZE, SIZE), (112, 74, 44, 255))
    d = ImageDraw.Draw(img)
    for top in range(0, SIZE, 8):
        shade = rng.choice([(126, 84, 50), (118, 78, 46), (134, 90, 54)])
        d.rectangle([0, top, SIZE - 1, top + 6], fill=(*shade, 255))
        d.line([0, top + 7, SIZE - 1, top + 7], fill=(70, 44, 26, 255))
        d.line([0, top, SIZE - 1, top], fill=(150, 104, 64, 255))
        knot = rng.randrange(2, SIZE - 3)
        d.rectangle([knot, top + 3, knot + 1, top + 4], fill=(86, 56, 32, 255))
    return img


def plaster() -> Image.Image:
    """Lime plaster with a timber beam across the top: the cottage's upper walls."""
    rng = random.Random(52)
    img = Image.new("RGBA", (SIZE, SIZE), (214, 202, 172, 255))
    _speckle(img, rng, [(200, 188, 158), (226, 216, 190), (190, 176, 146)], 90)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, SIZE - 1, 3], fill=(96, 62, 36, 255))
    d.line([0, 4, SIZE - 1, 4], fill=(70, 44, 26, 255))
    return img


def shingles() -> Image.Image:
    """Slate-blue roof shingles in staggered rows with dark gaps."""
    rng = random.Random(53)
    img = Image.new("RGBA", (SIZE, SIZE), (40, 46, 64, 255))
    d = ImageDraw.Draw(img)
    for row, top in enumerate(range(0, SIZE, 6)):
        offset = 0 if row % 2 == 0 else 4
        for left in range(-8 + offset, SIZE, 8):
            colour = rng.choice([(78, 92, 122), (70, 84, 112), (86, 100, 130)])
            d.rectangle([left + 1, top, left + 7, top + 4], fill=(*colour, 255))
            d.line([left + 1, top + 4, left + 7, top + 4], fill=(56, 64, 86, 255))
    return img


def floorboards() -> Image.Image:
    """Lengthwise floorboards, lighter than the walls: what a character walks on indoors and on the stairs."""
    rng = random.Random(54)
    img = Image.new("RGBA", (SIZE, SIZE), (150, 108, 66, 255))
    d = ImageDraw.Draw(img)
    for left in range(0, SIZE, 8):
        shade = rng.choice([(164, 120, 74), (156, 112, 70), (172, 128, 80)])
        d.rectangle([left, 0, left + 6, SIZE - 1], fill=(*shade, 255))
        d.line([left + 7, 0, left + 7, SIZE - 1], fill=(104, 72, 42, 255))
        joint = rng.randrange(4, SIZE - 4)
        d.line([left, joint, left + 6, joint], fill=(120, 84, 50, 255))
    return img


def cobbles() -> Image.Image:
    """Rounded grey cobbles: the stairs' landing and the cottage's porch."""
    rng = random.Random(55)
    img = Image.new("RGBA", (SIZE, SIZE), (64, 62, 60, 255))
    d = ImageDraw.Draw(img)
    for top in range(0, SIZE, 8):
        offset = 0 if (top // 8) % 2 == 0 else 4
        for left in range(-8 + offset, SIZE, 8):
            colour = rng.choice([(132, 128, 120), (118, 114, 108), (144, 140, 130)])
            d.rectangle([left + 1, top + 1, left + 6, top + 6], fill=(*colour, 255))
            d.point([(left + 1, top + 1), (left + 6, top + 1), (left + 1, top + 6), (left + 6, top + 6)], fill=(64, 62, 60, 255))
            d.line([left + 2, top + 2, left + 4, top + 2], fill=(166, 162, 150, 255))
    return img


TEXTURES = {"timber": timber, "plaster": plaster, "shingles": shingles, "floorboards": floorboards, "cobbles": cobbles}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, make in TEXTURES.items():
        image = make()
        assert image.size == (SIZE, SIZE)
        image.save(OUT / f"{name}.png")
        print(f"wrote {OUT / name}.png")


if __name__ == "__main__":
    main()
