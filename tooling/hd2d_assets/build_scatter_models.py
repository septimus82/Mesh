"""Mesh's starter scatter models (Milestone 20D): rocks, a boulder and a fallen branch, built and exported by Blender
in one headless run (original; textures from pixel_textures.py, sampled "Closest"; fixed seeds, so rebuilding writes
the same shapes).

    blender --factory-startup -noaudio --background --python tooling/hd2d_assets/build_scatter_models.py -- OUT_DIR

Writes OUT_DIR/<name>.glb. Blender: X east, Y north, Z up, metres; each model's origin is where it stands, its base
a little below the ground so it sits in it on a slope. Faceted lumps (the convex hull of points round a squashed
sphere): low-poly, flat-shaded, one texture tile a metre, as the rest of the kit. Only the boulder blocks (a
``mesh_collision`` wall the size of its middle); the rest are walked through.
"""

import math
import random
import sys
from pathlib import Path

import bmesh

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_kit import _finish, box, export, material, reset  # noqa: E402


def lump(name: str, seed: int, rx: float, ry: float, rz: float, points: int = 22, sink: float = 0.06) -> None:
    """A stone: the hull of ``points`` points on a sphere squashed to (rx, ry, rz), jittered, the bottom cut flat."""
    rng = random.Random(seed)
    bm = bmesh.new()
    for k in range(points):
        z = 1 - 2 * (k + 0.5) / points  # (spread evenly over the sphere, then jittered)
        r, a = math.sqrt(1 - z * z), k * math.pi * (3 - math.sqrt(5)) + rng.uniform(-0.3, 0.3)
        j = rng.uniform(0.8, 1.1)
        bm.verts.new((rx * r * math.cos(a) * j, ry * r * math.sin(a) * j, max(-sink, rz * (z + 1) / 2 * j - sink)))
    bmesh.ops.convex_hull(bm, input=bm.verts)
    rock = material("boulder")
    _finish(name, bm, (rock, rock), None)


def branch(name: str, seed: int) -> None:
    """A fallen branch along X: a tapering eight-sided log, two broken stubs, lying half sunk."""
    rng = random.Random(seed)
    bark = material("bark")
    bm = bmesh.new()
    rings = []
    for i, x in enumerate((-0.9, -0.3, 0.3, 0.9)):
        r = 0.11 - 0.025 * i
        y, z = rng.uniform(-0.04, 0.04), r - 0.03
        rings.append([bm.verts.new((x, y + r * math.cos(2 * math.pi * s / 8), z + r * math.sin(2 * math.pi * s / 8)))
                      for s in range(8)])
    for a, b in zip(rings, rings[1:]):
        for s in range(8):
            bm.faces.new((a[s], a[(s + 1) % 8], b[(s + 1) % 8], b[s]))
    bm.faces.new(tuple(reversed(rings[0])))
    bm.faces.new(tuple(rings[-1]))
    _finish(name, bm, (bark, bark), None)
    for x, ang in ((-0.4, 0.9), (0.45, -0.7)):  # broken-off side branches
        bm = bmesh.new()
        ring0 = [bm.verts.new((x + 0.04 * math.cos(2 * math.pi * s / 6), 0.04 * math.sin(2 * math.pi * s / 6), 0.1))
                 for s in range(6)]
        tip = (x + 0.3 * math.cos(ang), 0.3 * math.sin(ang), 0.16)
        ring1 = [bm.verts.new((tip[0] + 0.02 * math.cos(2 * math.pi * s / 6), tip[1] + 0.02 * math.sin(2 * math.pi * s / 6),
                               tip[2])) for s in range(6)]
        for s in range(6):
            bm.faces.new((ring0[s], ring0[(s + 1) % 6], ring1[(s + 1) % 6], ring1[s]))
        bm.faces.new(tuple(ring1))
        _finish(f"{name}_stub_{x:+.1f}", bm, (bark, bark), None)


MODELS = {
    "rock_small": lambda: lump("rock_small", 81, 0.22, 0.18, 0.18, points=14),
    "rock_medium": lambda: lump("rock_medium", 82, 0.45, 0.36, 0.38, points=18),
    "boulder": lambda: (lump("boulder", 83, 0.85, 0.7, 1.1, points=26, sink=0.12),
                        box("col_boulder", -0.6, -0.5, 0.0, 0.6, 0.5, 1.0, collision="wall")),
    "fallen_branch": lambda: branch("fallen_branch", 84),
}


def main() -> None:
    out = Path(sys.argv[sys.argv.index("--") + 1])
    for name, make in MODELS.items():
        reset()
        make()
        export(out / f"{name}.glb")


main()
