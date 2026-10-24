"""Draw Mesh's starter art: the hero, a villager and a signpost (original, generated here; no third-party art).

    py -3.13 tooling/make_starter_art.py

Writes assets/sprites/starter_hero.png, starter_villager.png (4 x 4 sheets of 32 x 48 frames: rows down, left,
right, up; columns stand, step, stand, other step) and starter_sign.png (32 x 32). Deterministic: rerunning
rewrites the same pixels. Provenance: docs/starter_art.md.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
FW, FH = 32, 48
DIRECTIONS = ("down", "left", "right", "up")
OUTLINE = (34, 28, 40, 255)
SKIN = (241, 200, 160, 255)
EYE = (40, 32, 48, 255)

HERO = {"hair": (122, 74, 38, 255), "body": (58, 110, 204, 255), "shade": (40, 80, 160, 255),
        "accent": (210, 64, 64, 255), "legs": (56, 54, 78, 255), "boots": (92, 56, 32, 255), "hat": None}
VILLAGER = {"hair": (150, 150, 150, 255), "body": (92, 150, 72, 255), "shade": (66, 112, 52, 255),
            "accent": (232, 222, 190, 255), "legs": (110, 80, 52, 255), "boots": (70, 50, 34, 255),
            "hat": (226, 190, 96, 255)}


def _rect(d: ImageDraw.ImageDraw, x0: int, y0: int, x1: int, y1: int, colour) -> None:
    d.rectangle((x0, y0, x1, y1), fill=colour)


def _outline(img: Image.Image) -> Image.Image:
    """A one-pixel dark outline around everything drawn: reads clearly on any ground."""
    out = img.copy()
    w, h = img.size
    alpha = list(img.getchannel("A").getdata())
    for y in range(h):
        for x in range(w):
            if alpha[y * w + x]:
                continue
            if any(0 <= x + dx < w and 0 <= y + dy < h and alpha[(y + dy) * w + x + dx]
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                out.putpixel((x, y), OUTLINE)
    return out


def _character_frame(p: dict, direction: str, step: int) -> Image.Image:
    """One frame; ``step`` is 0 (standing), 1 or -1 (which leg is forward)."""
    img = Image.new("RGBA", (FW, FH), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bob = 1 if step else 0  # the body dips on a step
    top = 7 + bob
    side = direction in ("left", "right")
    # legs and boots
    if side:
        front, back = (14, 17) if step >= 0 else (16, 19), (16, 19) if step >= 0 else (13, 16)
        for (x0, x1), lift in ((back, 0), (front, 0)):
            _rect(d, x0, 35 + bob, x1, 43 - lift, p["legs"])
            _rect(d, x0, 43, x1, 45, p["boots"])
        if step:
            _rect(d, front[0] + 1, 43, front[1] + 1, 45, p["boots"])
    else:
        left_lift, right_lift = (2, 0) if step == 1 else (0, 2) if step == -1 else (0, 0)
        _rect(d, 11, 35 + bob, 14, 43 - left_lift, p["legs"])
        _rect(d, 11, 43 - left_lift, 14, 45 - left_lift, p["boots"])
        _rect(d, 17, 35 + bob, 20, 43 - right_lift, p["legs"])
        _rect(d, 17, 43 - right_lift, 20, 45 - right_lift, p["boots"])
    # body
    x0, x1 = (12, 20) if side else (10, 21)
    _rect(d, x0, top + 13, x1, top + 27, p["body"])
    _rect(d, x1 - 1, top + 13, x1, top + 27, p["shade"])
    _rect(d, x0, top + 24, x1, top + 25, p["boots"])  # belt
    if direction == "down":
        if p["hat"]:
            _rect(d, 13, top + 16, 18, top + 27, p["accent"])  # apron
        else:
            _rect(d, 11, top + 13, 20, top + 14, p["accent"])  # scarf
    elif p["hat"] is None and side:
        _rect(d, x0, top + 13, x1, top + 14, p["accent"])
    # arms (swinging opposite to the legs)
    swing = step
    if side:
        ax = 15 + (2 if direction == "right" else -2) * swing
        _rect(d, ax, top + 14, ax + 2, top + 22, p["body"])
        _rect(d, ax, top + 23, ax + 2, top + 24, SKIN)
    else:
        for ax, s in ((8, swing), (22, -swing)):
            _rect(d, ax, top + 14 + s, ax + 1, top + 22 + s, p["body"])
            _rect(d, ax, top + 23 + s, ax + 1, top + 24 + s, SKIN)
    # head
    hx0, hx1 = (11, 20) if side else (10, 21)
    _rect(d, hx0, top, hx1, top + 12, SKIN)
    if direction == "up":
        _rect(d, hx0, top - 1, hx1, top + 10, p["hair"])
    elif side:
        back_x = hx0 if direction == "right" else hx1 - 3
        _rect(d, hx0, top - 1, hx1, top + 2, p["hair"])
        _rect(d, back_x, top - 1, back_x + 3, top + 8, p["hair"])
        eye = hx1 - 3 if direction == "right" else hx0 + 2
        _rect(d, eye, top + 5, eye, top + 7, EYE)
    else:
        _rect(d, hx0, top - 1, hx1, top + 3, p["hair"])
        _rect(d, hx0, top + 3, hx0 + 1, top + 7, p["hair"])
        _rect(d, hx1 - 1, top + 3, hx1, top + 7, p["hair"])
        _rect(d, 13, top + 5, 13, top + 7, EYE)
        _rect(d, 18, top + 5, 18, top + 7, EYE)
    if p["hat"]:
        _rect(d, hx0 - 2, top + 1, hx1 + 2, top + 2, p["hat"])  # brim
        _rect(d, hx0 + 1, top - 3, hx1 - 1, top + 1, p["hat"])
        _rect(d, hx0 + 1, top, hx1 - 1, top, p["accent"])  # band
    return _outline(img)


def character_sheet(palette: dict) -> Image.Image:
    sheet = Image.new("RGBA", (FW * 4, FH * 4), (0, 0, 0, 0))
    for row, direction in enumerate(DIRECTIONS):
        for col, step in enumerate((0, 1, 0, -1)):
            if direction == "left":
                frame = _character_frame(palette, "right", step).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            else:
                frame = _character_frame(palette, direction, step)
            sheet.paste(frame, (col * FW, row * FH))
    return sheet


def sign() -> Image.Image:
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    wood, dark, light = (170, 116, 62, 255), (122, 80, 42, 255), (204, 150, 92, 255)
    _rect(d, 14, 18, 17, 30, dark)  # post
    _rect(d, 4, 5, 27, 19, wood)  # board
    _rect(d, 4, 5, 27, 6, light)
    _rect(d, 4, 12, 27, 12, dark)  # plank seam
    for y, x1 in ((8, 22), (10, 18), (15, 24), (17, 15)):  # writing
        _rect(d, 8, y, x1, y, (70, 46, 26, 255))
    return _outline(img)


def main() -> None:
    out = ROOT / "assets/sprites"
    character_sheet(HERO).save(out / "starter_hero.png")
    character_sheet(VILLAGER).save(out / "starter_villager.png")
    sign().save(out / "starter_sign.png")
    print("wrote starter_hero.png, starter_villager.png, starter_sign.png")


if __name__ == "__main__":
    main()
