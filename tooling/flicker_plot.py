"""Plot how Mesh's flicker presets move over time (brightness and reach), next to the old flicker.

    py -3.13 tooling/flicker_plot.py OUT.png [--seconds 6] [--reduced]

Each row is one light over the same seconds: brightness (white line) and reach (orange line), both as a
factor of the light's set value (1.0 = as authored). The last two rows are two torches with different
seeds: they must not move together. A picture over time, because a still frame can't show flicker.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.lighting.flicker import FLICKER_PRESETS, FlickerNoise, apply_light_flicker, flicker_sample  # noqa: E402


def series(name: str, seconds: float, reduced: bool, steps: int = 600) -> tuple[list[float], list[float]]:
    times = [seconds * i / steps for i in range(steps + 1)]
    if name == "old (amount 0.2, speed 5)":
        noise = FlickerNoise(3)
        out = [apply_light_flicker(base_radius=100.0, base_color=(200, 200, 200, 255), noise=noise, time_s=t, speed=5.0,
                                   amount=0.2, radius_px=None, intensity=None) for t in times]
        return [1.0] * len(times), [r / 100.0 for r, _c in out]  # the old flicker reached only the radius
    preset, seed = (name.split()[0], int(name.split()[-1])) if name.startswith("torch seed") else (name, 7)
    profile = FLICKER_PRESETS["torch" if preset == "torch" else preset]
    pairs = [flicker_sample(profile, seed, t, 1.0, reduced) for t in times]
    return [b for b, _r in pairs], [r for _b, r in pairs]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--reduced", action="store_true")
    args = parser.parse_args()
    rows = ["old (amount 0.2, speed 5)", "candle", "torch", "fire", "faulty", "torch seed 11", "torch seed 12"]
    w, row_h, pad = 900, 90, 120
    image = Image.new("RGB", (w + pad, row_h * len(rows)), (24, 24, 30))
    draw = ImageDraw.Draw(image)
    for k, name in enumerate(rows):
        brightness, reach = series(name, args.seconds, args.reduced)
        top = k * row_h
        draw.line([(pad, top + row_h // 2), (pad + w, top + row_h // 2)], fill=(60, 60, 70))  # 1.0
        draw.text((6, top + row_h // 2 - 6), name, fill=(220, 220, 220))
        for values, colour in ((reach, (240, 150, 60)), (brightness, (235, 235, 235))):
            points = [(pad + w * i / (len(values) - 1), top + row_h / 2 - (v - 1.0) * row_h * 0.9) for i, v in enumerate(values)]
            draw.line(points, fill=colour, width=2)
        draw.line([(pad, top + row_h - 1), (pad + w, top + row_h - 1)], fill=(40, 40, 48))
    for s in range(int(args.seconds) + 1):
        x = pad + w * s / args.seconds
        draw.line([(x, 0), (x, row_h * len(rows))], fill=(48, 48, 58))
    image.save(args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
