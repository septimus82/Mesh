"""Comparison sheets for the M17-L4-3 review (labelled tiles, half size). Usage: sheets.py OUT"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
F, E, OUT = HERE / "final", HERE / "evidence", Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
TW, TH = 640, 360


def tile(path: Path, label: str, size: tuple[int, int] = (TW, TH)) -> Image.Image:
    im = Image.open(path).convert("RGB").resize(size, Image.LANCZOS)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 8 + 7 * len(label), 18), fill=(0, 0, 0))
    d.text((4, 3), label, fill=(255, 255, 255))
    return im


def grid(rows: list[list[Image.Image]], name: str) -> None:
    w, h = rows[0][0].size
    cols = max(len(r) for r in rows)
    sheet = Image.new("RGB", (w * cols, h * len(rows)), (16, 16, 16))
    for y, r in enumerate(rows):
        for x, im in enumerate(r):
            sheet.paste(im, (x * w, y * h))
    sheet.save(OUT / name, optimize=True)


shots = ("village", "shore", "bridge", "cottage")
grid([[tile(F / f"{s}__day__off.png", f"{s} day: off"), tile(F / f"{s}__day__daytime.png", f"{s} day: Daytime haze")]
      for s in shots], "lakeside_day_off_vs_daytime.png")
grid([[tile(F / f"{s}__evening__off.png", f"{s} evening: off"),
       tile(F / f"{s}__evening__evening.png", f"{s} evening: Evening haze")] for s in shots],
     "lakeside_evening_off_vs_evening.png")
grid([[tile(F / f"{s}__night_lamps__off.png", f"{s} night: off"),
       tile(F / f"{s}__night_lamps__evening.png", f"{s} night: Evening haze (lit by the night)")]
      for s in ("village", "bridge")], "lakeside_night_haze_is_dim.png")
grid([[tile(F / "interior__day__off.png", "interior: off"), tile(F / "interior__day__evening.png", "interior: Evening")]],
     "interior_unchanged.png")
grid([[tile(E / "depth_map" / f"{s}.png", f"{s}: Daytime frame | haze amount from depth (dark: none, blue->red: more)",
            (1280, 360))] for s in ("village", "bridge", "shore")], "depth_maps.png")
grid([[tile(E / "walking" / f"step{i}.png", f"walking step {i}: off | Daytime", (1280, 360))] for i in (0, 2, 5)],
     "walking.png")
for t in ("day", "evening"):
    names = [("off", "off"), ("haze", "haze"), ("grade_vignette", "grade + vignette"), ("dof", "depth of field"),
             ("all", "haze + grade + vignette + DoF")]
    tiles = [tile(E / "combined" / f"bridge__{t}__{n}.png", f"bridge {t}: {lab}") for n, lab in names]
    grid([tiles[:2], tiles[2:4], [tiles[4]]], f"combined_{t}.png")
grid([[tile(E / "template" / f"template__{t}__{n}.png", f"template {t}: {n}") for n in ("off", "daytime", "evening")]
      for t in ("day", "night")], "template_village.png")
grid([[tile(E / "studio" / "studio_window__off.png", "Studio editing view: haze off"),
       tile(E / "studio" / "studio_window__evening.png", "Studio editing view: Evening (Haze section)")],
      [tile(E / "studio" / "studio_path__evening.png", "Studio's renderer path, game camera, Evening"),
       tile(F / "village__day__evening.png", "the game's frame, village day, Evening")]], "studio_vs_game.png")
print(sorted(p.name for p in OUT.glob("*.png")))
