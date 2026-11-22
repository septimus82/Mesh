"""M2-1's Blender building: a small stone house, built and exported by Blender to show a safe reimport (original;
textures from pixel_textures.py, the roof a flat colour).

Run headless (no window), from the repo root:
    blender --factory-startup -noaudio --background --python tooling/hd2d_assets/build_house.py -- OUT.glb [--v2]

A 4 x 3 m stone house with a wooden floor (0.1 m up), a 1 m doorway in the middle of its south wall under a timber
lintel, and a slate-grey gable roof (ridge 3.2 m). Collision:

- ``solid``: ``col_floor``, the floor slab;
- ``wall``: ``col_wall_north``, ``col_wall_west``, ``col_wall_east``, ``col_wall_south_w``, ``col_wall_south_e``
  (either side of the doorway) and ``col_lintel``.

``--v2`` is the same house after an edit in Blender: the north wall moved 1 m north (the house is 4 m deep, so the
floor and the side walls grow with it), the ridge raised to 3.9 m and the roof terracotta. The collider names are
unchanged, so a reimport reports them as changed shape, not as new.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_kit import box, export, gable_roof, material, reset  # noqa: E402
from build_cottage import _flat_material  # noqa: E402

X0, X1, Y0, T, FLOOR_TOP, EAVES = -2.0, 2.0, -1.5, 0.25, 0.1, 2.2
DOOR = 0.5  # half the doorway's width
ROOF_SRGB = {False: (84, 92, 108), True: (178, 84, 52)}  # slate grey; terracotta after the edit


def build(v2: bool = False) -> None:
    """The house (``v2``: after the edit) in the current Blender scene."""
    y1, ridge = (2.5, 3.9) if v2 else (1.5, 3.2)
    stone, timber, floor = material("stone"), material("timber"), material("floorboards")
    roof = _flat_material("roof_terracotta" if v2 else "roof_slate", ROOF_SRGB[v2])
    box("floor", X0, Y0, 0.0, X1, y1, FLOOR_TOP, (floor, stone))
    box("col_floor", X0, Y0, 0.0, X1, y1, FLOOR_TOP, collision="solid")
    walls = {
        "north": (X0, y1 - T, X1, y1),
        "west": (X0, Y0, X0 + T, y1),
        "east": (X1 - T, Y0, X1, y1),
        "south_w": (X0, Y0, -DOOR, Y0 + T),
        "south_e": (DOOR, Y0, X1, Y0 + T),
    }
    for name, (x0, y0, x1, y1w) in walls.items():
        box(f"wall_{name}", x0, y0, FLOOR_TOP, x1, y1w, EAVES, stone)
        box(f"col_wall_{name}", x0, y0, 0.0, x1, y1w, EAVES, collision="wall")
    box("lintel", -DOOR, Y0, 2.0, DOOR, Y0 + T, EAVES, timber)
    box("col_lintel", -DOOR, Y0, 2.0, DOOR, Y0 + T, EAVES, collision="wall")
    gable_roof("roof", X0 - 0.25, Y0 - 0.25, X1 + 0.25, y1 + 0.25, EAVES, ridge, roof, stone)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    reset()
    build("--v2" in args)
    export(Path(args[0]).resolve())
