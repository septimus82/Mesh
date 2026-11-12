"""M17-L4-4 comparison sheets (labelled tiles) and close crops. Usage: sheets.py OUT STUDIO_PICS"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
F, C, E, OUT, ST = HERE / "final", HERE / "final_combined", HERE / "evidence", Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "crops").mkdir(exist_ok=True)
TW, TH = 640, 360
FULL = "warm~strength=3~threshold=0~spread=0.8"
NAMES = {"off": "off", "subtle": "Subtle", "warm": "Warm", FULL: "full (strength 3, threshold 0, spread 0.8)"}


def tile(path: Path, label: str, size=(TW, TH), box=None) -> Image.Image:
    im = Image.open(path).convert("RGB")
    if box:
        im = im.crop(box)
    im = im.resize(size, Image.NEAREST if box else Image.LANCZOS)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 8 + 6 * len(label), 16), fill=(0, 0, 0))
    d.text((4, 3), label, fill=(255, 255, 255))
    return im


def grid(rows, name: str) -> None:
    w, h = rows[0][0].size
    cols = max(len(r) for r in rows)
    sheet = Image.new("RGB", (w * cols, h * len(rows)), (16, 16, 16))
    for y, r in enumerate(rows):
        for x, im in enumerate(r):
            sheet.paste(im, (x * w, y * h))
    sheet.save(OUT / name, optimize=True)


def looks(prefix: str, label: str, keys=("off", "subtle", "warm", FULL), folder=F):
    return [tile(folder / f"{prefix}__{k}.png", f"{label}: {NAMES[k]}") for k in keys]


grid([looks(f"{s}__day", f"{s} day", ("off", "warm")) for s in ("village", "shore", "bridge", "cottage")],
     "lakeside_day_off_vs_warm.png")
grid([looks(f"{s}__evening_lamps", f"{s} evening, lamps lit", ("off", "subtle", "warm")) for s in ("village", "bridge", "shore")],
     "lakeside_evening_lamps.png")
grid([looks(f"{s}__night_lamps", f"{s} night", ("off", "subtle", "warm", FULL))[:2] for s in ("village", "bridge")]
     + [looks(f"{s}__night_lamps", f"{s} night", ("off", "subtle", "warm", FULL))[2:] for s in ("village", "bridge")],
     "lakeside_night_lamps.png")
grid([looks("interior__night_hearth", "interior, a hearth")[:2], looks("interior__night_hearth", "interior, a hearth")[2:]],
     "interior_hearth.png")
grid([looks("interior__night_lamps", "interior, ceiling lamp (no visible emitter)", ("off", "warm"))],
     "interior_lamp_light_never_glows.png")
grid([[tile(E / "template" / f"template__{t}__{k}.png", f"template {t}: {NAMES.get(k, k)}") for k in ("off", "subtle", "warm", "full")]
      for t in ("day", "night")], "template_village.png")
grid([[tile(E / "campfire" / f"campfire__night__{k}.png", f"campfire night: {NAMES.get(k, k)}") for k in ("off", "subtle")],
      [tile(E / "campfire" / f"campfire__night__{k}.png", f"campfire night: {NAMES.get(k, k)}") for k in ("warm", "full")]],
     "campfire.png")
grid([[tile(E / "emission" / f"{n}.png", f"{n}: frame (Warm) | its emission buffer", (1280, 360))]
      for n in ("village_night", "bridge_night", "hearth_interior")], "emission_maps.png")
grid([[tile(p, f"walking frame {p.stem[-2:]}: off | Warm", (1280, 360))] for p in sorted((E / "moving").glob("walk_*.png"))[::2]],
     "walking.png")
COMB = [("off", "off"), ("warm", "bloom (Warm)"), ("off+haze=evening+post=natural", "haze + grade"),
        ("warm+haze=evening+post=natural", "bloom + haze + grade"), ("off+dof", "depth of field"),
        ("warm+haze=evening+post=natural+dof", "bloom + haze + grade + DoF")]
for t in ("evening_lamps", "night_lamps"):
    tiles = [tile(C / f"bridge__{t}__{k}.png", f"bridge {t.split('_')[0]}: {lab}") for k, lab in COMB]
    grid([tiles[:2], tiles[2:4], tiles[4:]], f"combined_{t.split('_')[0]}.png")
grid([[tile(ST / "studio_off.png", "Studio's view: bloom off", (480, 432)), tile(ST / "studio_subtle.png", "Studio: Subtle bloom", (480, 432)),
       tile(ST / "studio_typed.png", "Studio: strength 2.5, threshold 0.05", (480, 432)),
       tile(ST / "studio_bloom_haze_grade.png", "Studio: bloom + haze + grade", (480, 432))]], "studio.png")


def crops(off: Path, looks_: list[tuple[Path, str]], tag: str, n: int = 2, w: int = 180, h: int = 120) -> None:
    """Around the ``n`` places the full look changed most, and one patch far from them (ordinary materials)."""
    a = np.asarray(Image.open(off).convert("RGB")).astype(int)
    b = np.asarray(Image.open(looks_[-1][0]).convert("RGB")).astype(int)
    diff = np.abs(b - a).max(axis=2).astype(float)
    centres = []
    d = diff.copy()
    for _ in range(n):
        y, x = np.unravel_index(int(d.argmax()), d.shape)
        if d[y, x] <= 0:
            break
        centres.append((x, y))
        d[max(0, y - 2 * h):y + 2 * h, max(0, x - 2 * w):x + 2 * w] = 0
    hgt, wid = diff.shape
    ys, xs = np.mgrid[0:hgt:40, 0:wid:40]
    far = [(int(x), int(y)) for x, y in zip(xs.ravel(), ys.ravel())
           if w // 2 < x < wid - w // 2 and h // 2 < y < hgt - h // 2
           and all(abs(x - cx) > 2.5 * w or abs(y - cy) > 2.5 * h for cx, cy in centres)]
    if far:
        centres.append(far[len(far) // 2])
    rows = []
    for i, (x, y) in enumerate(centres):
        box = (x - w // 2, y - h // 2, x + w // 2, y + h // 2)
        what = "plain materials, far from any emitter" if i == len(centres) - 1 and far else "an emitter"
        rows.append([tile(off, f"{what}: off", (w * 3, h * 3), box)]
                    + [tile(p, f"{lab}", (w * 3, h * 3), box) for p, lab in looks_])
    grid(rows, f"crops/{tag}.png")


for s, t in (("village", "night_lamps"), ("bridge", "night_lamps"), ("village", "evening_lamps")):
    crops(F / f"{s}__{t}__off.png", [(F / f"{s}__{t}__{k}.png", NAMES[k].split(" (")[0]) for k in ("subtle", "warm", FULL)],
          f"{s}_{t}")
crops(F / "interior__night_hearth__off.png",
      [(F / f"interior__night_hearth__{k}.png", NAMES[k].split(" (")[0]) for k in ("subtle", "warm", FULL)], "interior_hearth", n=1)
crops(E / "campfire" / "campfire__night__off.png",
      [(E / "campfire" / f"campfire__night__{k}.png", k) for k in ("subtle", "warm", "full")], "campfire", n=1)
print(sorted(str(p.relative_to(OUT)) for p in OUT.rglob("*.png")))
