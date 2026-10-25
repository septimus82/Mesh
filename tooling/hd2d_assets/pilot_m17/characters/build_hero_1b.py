"""M17 Stage 1B: derive hero_m17_h2/h3/h4.png from hero_m17.png by exact pixel edits (no resampling, no API calls).

    py -3.13 tooling/hd2d_assets/pilot_m17/characters/build_hero_1b.py

Sheet: 4x4 frames of 32x48; rows down, left, right, up; columns stand, step, stand, step (idle = column 0).
Deterministic: same input, same output bytes. Every edit is listed in EDITS (copied into provenance.json by hand).

- h2 "repaired": front/back rows rebuilt as [stand, step A, stand, step B] around one canonical upper body
  (both feet planted in the stand, built by mirroring the planted leg; steps keep their original order);
  red removed from legs and side-view faces; the satchel (only in 2 of 16 frames) removed.
- h3 "moss tunic": h2 with the tunic ramp recoloured to moss green.
- h4 "legible": h3 with a darker moss tunic (value-separated from grass and dirt), a darker outline colour and a
  continuous 1 px outline ring around the silhouette (sides and top; feet stay on row 47).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SRC = HERE / "hero_m17.png"
FW, FH = 32, 48
DOWN, LEFT, RIGHT, UP = 0, 1, 2, 3
CLEAR = (0, 0, 0, 0)


def rgb(h: str) -> tuple[int, int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), 255


# Stage 1 colours by role (from hero_m17.png).
OUTLINE = rgb("#392a23")
TROUSER_DARK = rgb("#443639")
BOOT = rgb("#6f493a")
SKIN_SHADOW = rgb("#c49a7e")
SKIN_DARK = rgb("#b07255")
RED_DEEP = rgb("#562e2f")   # scarf shadow that bled onto the side-view back legs
RED = rgb("#a84840")         # scarf red
RED_2 = rgb("#9c433d")
TUNIC = {"shadow": rgb("#645c53"), "base": rgb("#786d61"), "light": rgb("#8c7f6b")}

EDITS: list[str] = []


def frames_of(sheet: Image.Image) -> dict[tuple[int, int], Image.Image]:
    return {(r, c): sheet.crop((c * FW, r * FH, (c + 1) * FW, (r + 1) * FH)) for r in range(4) for c in range(4)}


def sheet_of(frames: dict[tuple[int, int], Image.Image]) -> Image.Image:
    out = Image.new("RGBA", (FW * 4, FH * 4), CLEAR)
    for (r, c), f in frames.items():
        out.paste(f, (c * FW, r * FH))
    return out


def recolour(f: Image.Image, mapping: dict, rows: range, cols: range = range(FW)) -> int:
    px, n = f.load(), 0
    for y in rows:
        for x in cols:
            if px[x, y] in mapping:
                px[x, y] = mapping[px[x, y]]
                n += 1
    return n


def splice(upper: Image.Image, lower: Image.Image, cut: int, cols: range) -> Image.Image:
    """Rows < cut from upper; rows >= cut from lower (only within cols, the rest cleared)."""
    out = upper.copy()
    px, lo = out.load(), lower.load()
    for y in range(cut, FH):
        for x in range(FW):
            px[x, y] = lo[x, y] if x in cols else CLEAR
    return out


def mirror_legs(f: Image.Image, top: int, axis2: int, keep_left: bool) -> Image.Image:
    """Rows >= top: copy the kept leg onto the other side, mirrored about x = axis2 / 2."""
    out = f.copy()
    px = out.load()
    centre = axis2 / 2
    for y in range(top, FH):
        for x in range(FW):
            if (x > centre) if keep_left else (x < centre):
                px[x, y] = CLEAR
        for x in range(FW):
            if ((x < centre) if keep_left else (x > centre)) and 0 <= axis2 - x < FW:
                px[axis2 - x, y] = px[x, y]
    return out


def clear_box(f: Image.Image, x0: int, y0: int, x1: int, y1: int) -> None:
    px = f.load()
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            px[x, y] = CLEAR


def close_outline(f: Image.Image, colour: tuple, rows: range, cols: range) -> int:
    """Give opaque non-outline pixels inside the box an outline pixel wherever they touch transparency (4-way)."""
    px, add = f.load(), []
    for y in rows:
        for x in cols:
            if px[x, y][3] and px[x, y] != colour:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < FW and 0 <= ny < FH and px[nx, ny][3] == 0:
                        add.append((nx, ny))
    for p in set(add):
        px[p] = colour
    return len(set(add))


def build_h2(src: Image.Image) -> Image.Image:
    F = frames_of(src)
    out = dict(F)

    # 1. Front (down): canonical upper body = down_0 rows 0-34, red mouth -> skin shadow.
    upper_d = F[DOWN, 0].copy()
    n = recolour(upper_d, {RED: SKIN_SHADOW}, range(15, 18), range(13, 19))
    EDITS.append(f"down: canonical upper body = Stage-1 down_0 rows 0-34; red mouth -> skin shadow ({n} px)")
    step_a = upper_d                                   # down_0: right foot lifted
    step_b = splice(upper_d, F[DOWN, 1], 35, range(9, 24))  # down_1 legs: left foot lifted
    stand = mirror_legs(upper_d, 35, 32, keep_left=True)  # left (planted) leg mirrored about x=16
    out[DOWN, 0], out[DOWN, 1], out[DOWN, 2], out[DOWN, 3] = stand, step_a, stand.copy(), step_b
    EDITS.append("down: [stand, down_0, stand, down_1 legs]; stand = down_0 with its planted left leg (rows 35-47) "
                 "mirrored about x=16; down_2 (different face, wide arms) and down_3 (irregular) dropped")

    # 2. Back (up): canonical upper body = up_0 rows 0-35.
    upper_u = F[UP, 0].copy()
    step_a = upper_u                                   # up_0: left foot lifted
    step_b = splice(upper_u, F[UP, 3], 36, range(10, 21))  # up_3 legs: right foot lifted
    stand = mirror_legs(upper_u, 36, 30, keep_left=False)  # right (planted) leg mirrored about x=15
    out[UP, 0], out[UP, 1], out[UP, 2], out[UP, 3] = stand, step_a, stand.copy(), step_b
    EDITS.append("up: [stand, up_0, stand, up_3 legs]; stand = up_0 with its planted right leg (rows 36-47) "
                 "mirrored about x=15; up_1/up_2 dropped")

    # 3. Side rows: red off the legs, red off the face, satchel out.
    for r in (LEFT, RIGHT):
        for c in range(4):
            f = out[r, c] = out[r, c].copy()
            n = recolour(f, {RED_DEEP: TROUSER_DARK, RED: BOOT, RED_2: BOOT}, range(36, FH))
            if r == LEFT:
                n2 = recolour(f, {RED: SKIN_SHADOW, RED_2: SKIN_SHADOW}, range(10, 18), range(0, 14))
            else:
                n2 = recolour(f, {RED: SKIN_DARK, RED_2: SKIN_DARK}, range(10, 17), range(12, 24))
            EDITS.append(f"{'left' if r == LEFT else 'right'}_{c}: legs red->trouser/boot ({n} px), face red->skin ({n2} px)")
    # Satchel: east frames 1 and 2 only (absent from 14 of 16 frames) -> removed.
    f = out[RIGHT, 2]
    clear_box(f, 8, 30, 12, 36)
    n = close_outline(f, OUTLINE, range(28, 38), range(11, 16))
    EDITS.append(f"right_2: satchel cleared (x 8-12, y 30-36), silhouette re-outlined ({n} px)")
    f = out[RIGHT, 1]
    n = recolour(f, {rgb("#583c2a"): OUTLINE, rgb("#64322b"): OUTLINE, rgb("#b07255"): OUTLINE},
                 range(30, 33), range(10, 14))
    EDITS.append(f"right_1: satchel pixels (x 10-13, y 30-32) -> outline, merging into the back arm ({n} px)")
    return sheet_of(out)


def build_h3(h2: Image.Image, ramp: dict[str, str]) -> tuple[Image.Image, int]:
    out = h2.copy()
    mapping = {TUNIC[k]: rgb(v) for k, v in ramp.items()}
    n = 0
    F = frames_of(out)
    for key, f in F.items():
        n += recolour(f, mapping, range(17, 38))  # tunic band only (keeps any trouser/boot use below)
    return sheet_of(F), n


def build_h4(h3: Image.Image, outline: tuple) -> tuple[Image.Image, int, int]:
    F = frames_of(h3)
    total_ring = total_dark = 0
    for key, f in F.items():
        total_dark += recolour(f, {OUTLINE: outline}, range(FH))
        px = f.load()
        ring = [(x, y) for y in range(FH) for x in range(FW) if px[x, y][3] == 0 and any(
            0 <= x + dx < FW and 0 <= y + dy < FH and px[x + dx, y + dy][3]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
        for p in ring:
            px[p] = outline
        total_ring += len(ring)
    return sheet_of(F), total_dark, total_ring


MOSS_H3 = {"shadow": "#4f5a34", "base": "#66733f", "light": "#7d8a4f"}   # moss, about the old tunic's values
MOSS_H4 = {"shadow": "#38422a", "base": "#4b5733", "light": "#61703f"}   # deeper moss: well below grass/dirt
# Outline darkness was the lever at gameplay scale (tested #241a17, #1c1412, #120c0b): every spot's background is
# lighter than the outline, so darker = more edge contrast. #1c1412 (L ~0.09, the baseline's darkness) clears H0
# at all three spots; #120c0b clears it further but is near-black.
OUTLINE_H4 = rgb("#1c1412")


def main() -> None:
    src = Image.open(SRC).convert("RGBA")
    h2 = build_h2(src)
    h2.save(HERE / "hero_m17_h2.png")
    h3, n3 = build_h3(h2, MOSS_H3)
    EDITS.append(f"h3: tunic ramp {[k + '->' + v for k, v in MOSS_H3.items()]} ({n3} px, rows 17-37)")
    h3.save(HERE / "hero_m17_h3.png")
    h4, _ = build_h3(h2, MOSS_H4)
    h4, nd, nr = build_h4(h4, OUTLINE_H4)
    EDITS.append(f"h4: deeper tunic ramp {MOSS_H4}; outline #392a23 -> #1c1412 ({nd} px); "
                 f"1 px outer outline ring added ({nr} px)")
    h4.save(HERE / "hero_m17_h4.png")
    for line in EDITS:
        print(line)


if __name__ == "__main__":
    main()
