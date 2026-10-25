"""The Stage 5B demonstration cottage, built and exported by Blender (original; textures from pixel_textures.py).

Run headless (no window), from the repo root:
    blender --factory-startup -noaudio --background --python tooling/hd2d_assets/build_cottage.py -- OUT.glb [--v2]

A 5 x 4 m timber-and-plaster cottage with a slate gable roof, a wooden floor (0.1 m up) and an open doorway in the
middle of its south wall. Collision:

- ``solid``: the floor slab (walkable, a 0.1 m step up from the ground);
- ``wall``: the four walls, the south one in two parts either side of the 1.2 m doorway, and the lintel over it.

``--v2`` is the same cottage after an edit in Blender (Stage 5B's reimport): a cobbled porch in front of the door
(``solid``, 0.15 m up), a stone hearth against the east wall (``wall``) and a chimney on the roof.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_kit import box, export, gable_roof, material, reset  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
OUT, V2 = Path(args[0]).resolve(), "--v2" in args

reset()
TIMBER, PLASTER, SHINGLES = material("timber"), material("plaster"), material("shingles")
FLOOR, COBBLES = material("floorboards"), material("cobbles")
X0, X1, Y0, Y1, T, FLOOR_TOP, EAVES = -2.5, 2.5, -2.0, 2.0, 0.2, 0.1, 2.5
DOOR = 0.6  # half the doorway's width

box("floor", X0, Y0, 0.0, X1, Y1, FLOOR_TOP, (FLOOR, TIMBER))
box("col_floor", X0, Y0, 0.0, X1, Y1, FLOOR_TOP, collision="solid")
walls = {
    "north": (X0, Y1 - T, X1, Y1),
    "west": (X0, Y0, X0 + T, Y1),
    "east": (X1 - T, Y0, X1, Y1),
    "south_w": (X0, Y0, -DOOR, Y0 + T),
    "south_e": (DOOR, Y0, X1, Y0 + T),
}
for name, (x0, y0, x1, y1) in walls.items():
    box(f"wall_{name}_low", x0, y0, FLOOR_TOP, x1, y1, 1.3, TIMBER)
    box(f"wall_{name}_high", x0, y0, 1.3, x1, y1, EAVES, PLASTER)
    box(f"col_wall_{name}", x0, y0, 0.0, x1, y1, EAVES, collision="wall")
box("lintel", -DOOR, Y0, 2.0, DOOR, Y0 + T, EAVES, TIMBER)
box("col_lintel", -DOOR, Y0, 2.0, DOOR, Y0 + T, EAVES, collision="wall")
gable_roof("roof", X0 - 0.3, Y0 - 0.3, X1 + 0.3, Y1 + 0.3, EAVES, 3.8, SHINGLES, PLASTER)

if V2:
    box("porch", -1.5, Y0 - 1.2, 0.0, 1.5, Y0, 0.15, (COBBLES, COBBLES))
    box("col_porch", -1.5, Y0 - 1.2, 0.0, 1.5, Y0, 0.15, collision="solid")
    box("hearth", X1 - T - 0.7, -0.6, FLOOR_TOP, X1 - T, 0.6, 1.0, (COBBLES, COBBLES))
    box("col_hearth", X1 - T - 0.7, -0.6, FLOOR_TOP, X1 - T, 0.6, 1.0, collision="wall")
    box("chimney", X1 - T - 0.6, -0.35, 2.9, X1 - T - 0.1, 0.35, 4.4, (COBBLES, COBBLES))

export(OUT)
