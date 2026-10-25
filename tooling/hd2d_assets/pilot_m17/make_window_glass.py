"""textures/window_a_glass.png: window_a.png with its cream panes recoloured to dark glass from its own palette.

    py -3.13 tooling/hd2d_assets/pilot_m17/make_window_glass.py

The only edit: inside the glazed area (x 7..20, y 8..23, px from the top left) every pixel of the pane cream
(172, 158, 128) becomes the window's dark blue-grey (74, 76, 86). Nothing else changes; window_a.png is untouched.
"""

from pathlib import Path

from PIL import Image

TEXTURES = Path(__file__).resolve().parent / "textures"
CREAM, GLASS = (172, 158, 128, 255), (74, 76, 86, 255)

if __name__ == "__main__":
    image = Image.open(TEXTURES / "window_a.png").convert("RGBA")
    changed = 0
    for y in range(8, 24):
        for x in range(7, 21):
            if image.getpixel((x, y)) == CREAM:
                image.putpixel((x, y), GLASS)
                changed += 1
    image.save(TEXTURES / "window_a_glass.png")
    print(f"window_a_glass.png: {changed} pixels recoloured")
