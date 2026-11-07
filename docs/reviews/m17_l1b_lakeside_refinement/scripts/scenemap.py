"""Scratch (M17-L1): a plan map of a Lakeside scene file from its data (not a render): painted ground, height
shading, water, structures, lamps, doors, and the scatter by kind. North up, 1 image px = 2 world px, grid every 4 m.
Usage: scenemap.py SCENE.json OUT.png"""
import json
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, r"D:\Games\Mesh-lva")
from engine import project_ops as ops  # noqa: E402
from engine.hd2d.terrain import Terrain  # noqa: E402

scene = json.loads(open(sys.argv[1], encoding="utf-8").read())
W, H, S = 2048, 1536, 2
img = Image.new("RGB", (W // S, H // S), (70, 120, 60))
d = ImageDraw.Draw(img)
ground = ops._parsed_ground(scene)
t = Terrain.from_ground(ground)
MAT = {"grass": None, "earth": (150, 105, 60), "stone": (140, 140, 140), "mud": (90, 70, 50), "sand": (210, 190, 140)}
for y in range(0, H, 8):
    for x in range(0, W, 8):
        h = (t.height(x, y) or 0.0) / 32.0
        m = MAT[t.material_at(x, y)]
        c = m or (int(70 + 18 * h), int(120 + 18 * h), int(60 + 10 * h))
        d.rectangle([x // S, (H - y - 8) // S, (x + 8) // S, (H - y) // S], fill=c)
for gx in range(0, W, 128):
    d.line([(gx // S, 0), (gx // S, H // S)], fill=(60, 100, 50))
for gy in range(0, H, 128):
    d.line([(0, (H - gy) // S), (W // S, (H - gy) // S)], fill=(60, 100, 50))
for e in scene["entities"]:
    cfg = (e.get("behaviour_config") or {}).get("WaterSurface")
    if cfg:
        w, h = cfg["width"] / 2 / S, cfg["height"] / 2 / S
        cx, cy = e["x"] / S, (H - e["y"]) / S
        d.ellipse([cx - w, cy - h, cx + w, cy + h], outline=(40, 80, 200), width=2)
COL = {"tree_small": (20, 60, 20), "bush": (40, 90, 40), "bush_berries": (120, 40, 80), "flowers_pink": (240, 120, 200),
       "flowers_yellow": (250, 230, 60), "reeds": (160, 150, 90), "reeds_cattail": (120, 80, 40),
       "rock_small": (150, 150, 150), "rock_medium": (200, 200, 200), "grass_dry": (190, 170, 90)}
for k, pts in scene["settings"]["hd2d"]["scatter"].items():
    if k in ("grass_tuft", "grass_tall"):
        continue
    r = 4 if k == "tree_small" else 1
    for p in pts:
        x, y = p[0] / S, (H - p[1]) / S
        d.ellipse([x - r, y - r, x + r, y + r], fill=COL.get(k, (255, 255, 255)))
for s in scene["settings"]["hd2d"]["structures"]:
    x, y = s["x"] / S, (H - s["y"]) / S
    d.rectangle([x - 6, y - 6, x + 6, y + 6], outline=(255, 255, 255), width=2)
    d.text((x + 8, y - 6), s["id"], fill=(255, 255, 255))
for lt in scene["lights"]:
    if "x" in lt:
        x, y = lt["x"] / S, (H - lt["y"]) / S
        d.ellipse([x - 4, y - 4, x + 4, y + 4], outline=(255, 200, 0), width=2)
for e in scene["entities"]:
    if not (e.get("behaviour_config") or {}).get("WaterSurface"):
        x, y = e["x"] / S, (H - e["y"]) / S
        d.rectangle([x - 3, y - 3, x + 3, y + 3], fill=(255, 0, 0))
img.save(sys.argv[2])
print("ok")
