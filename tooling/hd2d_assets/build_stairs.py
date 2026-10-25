"""The Stage 5B demonstration staircase: a modular section built and exported by Blender (original; textures from
pixel_textures.py).

Run headless (no window), from the repo root:
    blender --factory-startup -noaudio --background --python tooling/hd2d_assets/build_stairs.py -- OUT.glb

Eight wooden steps (0.25 m high, 0.5 m deep, 2 m wide) climb from the south edge (y -2) to a 2 x 2 m cobbled landing
2 m up, between timber side walls. Collision:

- ``solid``: the steps as one ramp through their front edges (feet stay on the treads), and the landing;
- ``wall``: the side walls.

Its textures are left at Blender's default "Linear" interpolation, as a creator often exports them: Mesh Studio's
import reports them and "Keep pixels sharp" makes the copy crisp.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_kit import box, export, material, ramp, reset  # noqa: E402

OUT = Path(sys.argv[sys.argv.index("--") + 1]).resolve()

reset()
TREAD, SIDE, LANDING = (material(t, interpolation="Linear") for t in ("floorboards", "timber", "cobbles"))
W, H, STEPS = 1.0, 2.0, 8

for k in range(STEPS):
    y0 = -2.0 + 0.5 * k
    box(f"step_{k}", -W, y0, 0.0, W, 2.0, 0.25 * (k + 1), (TREAD, SIDE))
box("landing", -W, 2.0, 0.0, W, 4.0, H, (LANDING, SIDE))
ramp("col_stairs", -W, W, -2.5, 1.5, H)  # through the steps' front edges
box("col_landing", -W, 1.5, 0.0, W, 4.0, H, collision="solid")
for side, (x0, x1) in (("west", (-W - 0.12, -W)), ("east", (W, W + 0.12))):
    box(f"side_{side}", x0, -2.0, 0.0, x1, 4.0, H + 0.8, (SIDE, SIDE))
    box(f"col_side_{side}", x0, -2.0, 0.0, x1, 4.0, H + 0.8, collision="wall")

export(OUT)
