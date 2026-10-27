"""Mesh's starter scatter models (Milestone 20D): rocks, a boulder and a fallen branch, built and exported by Blender
in one headless run (original; textures from pixel_textures.py, sampled "Closest"; fixed seeds, so rebuilding writes
the same shapes).

    blender --factory-startup -noaudio --background --python tooling/hd2d_assets/build_scatter_models.py -- OUT_DIR

Writes OUT_DIR/<name>.glb (``-- OUT_DIR --study``: the comparison models instead, Milestone 20E).
Blender: X east, Y north, Z up, metres; each model's origin is where it stands, its base
a little below the ground so it sits in it on a slope. Faceted lumps (the convex hull of points round a squashed
sphere): low-poly, flat-shaded, one texture tile a metre, as the rest of the kit; the small tree's trunk (its
canopy is sprites). Only the boulder and the tree block (a
``mesh_collision`` wall the size of its middle); the rest are walked through.
"""

import math
import random
import sys
from pathlib import Path

import bmesh

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_kit import _finish, box, export, material, reset  # noqa: E402


def lump(name: str, seed: int, rx: float, ry: float, rz: float, points: int = 22, sink: float = 0.06,
         at: tuple[float, float, float] = (0.0, 0.0, 0.0), texture: str = "boulder") -> None:
    """A stone: the hull of ``points`` points on a sphere squashed to (rx, ry, rz), jittered, the bottom cut flat."""
    rng = random.Random(seed)
    bm = bmesh.new()
    for k in range(points):
        z = 1 - 2 * (k + 0.5) / points  # (spread evenly over the sphere, then jittered)
        r, a = math.sqrt(1 - z * z), k * math.pi * (3 - math.sqrt(5)) + rng.uniform(-0.3, 0.3)
        j = rng.uniform(0.8, 1.1)
        bm.verts.new((at[0] + rx * r * math.cos(a) * j, at[1] + ry * r * math.sin(a) * j,
                      at[2] + max(-sink, rz * (z + 1) / 2 * j - sink)))
    bmesh.ops.convex_hull(bm, input=bm.verts)
    rock = material(texture)
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


def tree(name: str, seed: int, canopy: bool = False) -> None:
    """A small tree's trunk (Milestone 20E): a tapering eight-sided trunk 1.9 m tall, a little bent, with three
    limbs reaching up and out where its canopy (sprites that sway: engine.hd2d.scatter's tree_small) is attached;
    a wall the size of the trunk, so characters walk round it. ``canopy``: lumps of leaves on it too, a whole 3D
    tree (for comparing ways to draw a tree; not in the kit)."""
    rng = random.Random(seed)
    bark = material("bark")
    bm = bmesh.new()
    rings = []
    for i, z in enumerate((-0.05, 0.4, 0.9, 1.4, 1.9)):
        r = 0.15 - 0.022 * i
        cx, cy = 0.04 * math.sin(z * 1.7), 0.02 * math.cos(z * 1.3)
        rings.append([bm.verts.new((cx + r * math.cos(2 * math.pi * s / 8), cy + r * math.sin(2 * math.pi * s / 8), z))
                      for s in range(8)])
    for a, b in zip(rings, rings[1:]):
        for s in range(8):
            bm.faces.new((a[s], a[(s + 1) % 8], b[(s + 1) % 8], b[s]))
    bm.faces.new(tuple(rings[-1]))
    _finish(name, bm, (bark, bark), None)
    for k, (z, ang, up) in enumerate(((1.15, 2.6, 0.55), (1.35, -0.4, 0.6), (1.6, 1.2, 0.5))):
        bm = bmesh.new()
        r0, r1, length = 0.06, 0.03, 0.7 + rng.uniform(-0.1, 0.1)
        tip = (length * math.cos(ang) * (1 - up), length * math.sin(ang) * (1 - up), z + length * up)
        ring0 = [bm.verts.new((r0 * math.cos(2 * math.pi * s / 6), r0 * math.sin(2 * math.pi * s / 6), z))
                 for s in range(6)]
        ring1 = [bm.verts.new((tip[0] + r1 * math.cos(2 * math.pi * s / 6), tip[1] + r1 * math.sin(2 * math.pi * s / 6),
                               tip[2])) for s in range(6)]
        for s in range(6):
            bm.faces.new((ring0[s], ring0[(s + 1) % 6], ring1[(s + 1) % 6], ring1[s]))
        bm.faces.new(tuple(ring1))
        _finish(f"{name}_limb_{k}", bm, (bark, bark), None)
    box(f"col_{name}", -0.17, -0.17, 0.0, 0.17, 0.17, 1.8, collision="wall")
    if canopy:
        for k, (x, y, z, r) in enumerate(((0.0, 0.0, 2.3, 0.85), (-0.55, 0.15, 1.9, 0.6), (0.6, 0.1, 2.0, 0.6),
                                          (0.1, -0.3, 2.7, 0.55))):
            lump(f"{name}_leaves_{k}", seed + 10 + k, r, r * 0.9, r * 1.4, points=20, sink=0.0, at=(x, y, z - r * 0.7),
                 texture="grass")


MODELS = {
    "rock_small": lambda: lump("rock_small", 81, 0.22, 0.18, 0.18, points=14),
    "rock_medium": lambda: lump("rock_medium", 82, 0.45, 0.36, 0.38, points=18),
    "boulder": lambda: (lump("boulder", 83, 0.85, 0.7, 1.1, points=26, sink=0.12),
                        box("col_boulder", -0.6, -0.5, 0.0, 0.6, 0.5, 1.0, collision="wall")),
    "fallen_branch": lambda: branch("fallen_branch", 84),
    "tree_small": lambda: tree("tree_small", 85),
}
STUDY = {"tree_layered": lambda: tree("tree_layered", 85, canopy=True)}  # (--study: comparisons, not in the kit)


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1:]
    out = Path(args[0])
    for name, make in (STUDY if "--study" in args else MODELS).items():
        reset()
        make()
        export(out / f"{name}.glb")


main()
