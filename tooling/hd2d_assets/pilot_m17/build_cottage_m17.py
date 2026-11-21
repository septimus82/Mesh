"""M17 pilot: the starter cottage re-dressed with PixelLab textures (an art-direction experiment, not a rebuild).

Run headless (no window), from the repo root:
    blender --factory-startup -noaudio --background --python tooling/hd2d_assets/pilot_m17/build_cottage_m17.py -- OUT.glb

Geometry and collision come from ``build_cottage.build()`` unchanged; this script only re-dresses the result:

- lower walls and the floor slab's edge: ``stone_b_seamfix`` (a stone plinth), its top lowered from 1.3 m to PLINTH;
- upper walls and gable ends: the starter ``plaster`` (``plaster_b`` was tried and rejected); roof: ``roof_slate``;
- modest starter-timber framing (corner posts, a sill beam on the plinth, door jambs) and two ``window_a`` decals on
  the south wall (the only face the game camera sees), all drawn only (no collision), a few centimetres proud;
- every UV at 32 px per metre: the kit's planar UVs (1 tile per metre) scaled by 32 / texture width, and the roof
  slopes re-mapped along the slope (the kit projects them flat, which stretches them to ~28 px/m).
"""

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import blender_kit as kit  # noqa: E402
import bmesh  # noqa: E402
import bpy  # noqa: E402
from build_cottage import DOOR, EAVES, FLOOR_TOP, X0, X1, Y0, Y1, build  # noqa: E402

PX_PER_M = 32
PLINTH = 0.9  # top of the stone band (the starter's timber band stops at 1.3)
SPLIT = 1.3  # the starter's split, moved to PLINTH
PROUD = 0.03  # how far the framing stands out of the wall faces
RIDGE = 3.8  # build_cottage's gable_roof ridge height


def pilot_material(name: str, extension: str = "REPEAT"):
    """``blender_kit.material`` for a texture in pilot_m17/textures (Closest, like the kit)."""
    saved, kit.TEXTURES = kit.TEXTURES, HERE / "textures"
    try:
        mat = kit.material(name)
    finally:
        kit.TEXTURES = saved
    next(n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE").extension = extension
    return mat


def _image_width(mat) -> int:
    return int(next(n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE").image.size[0])


def decal(name, corners, mat):
    """A one-sided quad (corners counter-clockwise from bottom-left, seen from the front), UV 0..1 over it."""
    bm = bmesh.new()
    face = bm.faces.new([bm.verts.new(c) for c in corners])
    uv = bm.loops.layers.uv.new("UVMap")
    for loop, st in zip(face.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop[uv].uv = st
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def redress() -> None:
    stone, plaster = pilot_material("stone_b_seamfix"), kit.material("plaster")
    slate, window = pilot_material("roof_slate"), pilot_material("window_a", "EXTEND")
    timber = kit.material("timber")
    objs = bpy.data.objects

    # Materials: (top, sides) slots as blender_kit made them.
    objs["floor"].data.materials[1] = stone  # the slab's 0.1 m edge continues the plinth to the ground
    for obj in objs:
        if obj.name.startswith("wall_"):
            low = obj.name.endswith("_low")
            for i in range(2):
                obj.data.materials[i] = stone if low else plaster
            # Lower the stone/plaster split; side-face UVs carry z as v, so they move with it.
            mesh = obj.data
            moved = {v.index for v in mesh.vertices if abs(v.co.z - SPLIT) < 1e-6}
            uv = mesh.uv_layers["UVMap"].data
            for poly in mesh.polygons:
                if abs(poly.normal.z) < 0.5:
                    for li in poly.loop_indices:
                        if mesh.loops[li].vertex_index in moved:
                            uv[li].uv[1] = PLINTH
            for i in moved:
                mesh.vertices[i].co.z = PLINTH
    roof = objs["roof"].data
    roof.materials[0], roof.materials[1] = slate, plaster
    ym = (Y0 + Y1) / 2
    uv = roof.uv_layers["UVMap"].data
    for poly in roof.polygons:
        if poly.material_index == 0:  # the two slopes (gable_roof: slot 0)
            for li in poly.loop_indices:
                co = roof.vertices[roof.loops[li].vertex_index].co
                uv[li].uv = (co.x, math.hypot(co.y - ym, co.z - RIDGE))  # metres along the slope from the ridge

    # Framing (drawn only). Corner posts from the plinth to the eaves, standing PROUD + 0.01 out of both faces.
    p = PROUD + 0.01
    for name, (cx, cy) in {"sw": (X0, Y0), "se": (X1, Y0), "nw": (X0, Y1), "ne": (X1, Y1)}.items():
        x0, x1 = (cx - p, cx + 0.22) if cx == X0 else (cx - 0.22, cx + p)
        y0, y1 = (cy - p, cy + 0.22) if cy == Y0 else (cy - 0.22, cy + p)
        kit.box(f"frame_post_{name}", x0, y0, PLINTH, x1, y1, EAVES, timber)
    sill = {
        "north": (X0 - PROUD, Y1 - 0.05, X1 + PROUD, Y1 + PROUD),
        "west": (X0 - PROUD, Y0 - PROUD, X0 + 0.05, Y1 + PROUD),
        "east": (X1 - 0.05, Y0 - PROUD, X1 + PROUD, Y1 + PROUD),
        "south_w": (X0 - PROUD, Y0 - PROUD, -DOOR - 0.15, Y0 + 0.05),  # stops at the jambs
        "south_e": (DOOR + 0.15, Y0 - PROUD, X1 + PROUD, Y0 + 0.05),
    }
    for name, (x0, y0, x1, y1) in sill.items():
        kit.box(f"frame_sill_{name}", x0, y0, PLINTH, x1, y1, PLINTH + 0.15, timber)
    # Door jambs: in front of the wall face only, so they never meet the doorway's reveal faces (no z-fighting)
    # and never narrow the 1.2 m opening.
    kit.box("frame_jamb_w", -DOOR - 0.15, Y0 - p, FLOOR_TOP, -DOOR, Y0, 2.0, timber)
    kit.box("frame_jamb_e", DOOR, Y0 - p, FLOOR_TOP, DOOR + 0.15, Y0, 2.0, timber)

    # 32 px per metre on every kit-mapped face: the kit maps 1 texture tile per metre.
    for obj in objs:
        if obj.type != "MESH" or "mesh_collision" in obj:
            continue
        uv = obj.data.uv_layers["UVMap"].data
        for poly in obj.data.polygons:
            scale = PX_PER_M / _image_width(obj.data.materials[poly.material_index])
            for li in poly.loop_indices:
                uv[li].uv = (uv[li].uv[0] * scale, uv[li].uv[1] * scale)

    # Windows (26 x 29 px at 32 px/m), 1 cm out of the south wall, centred in each 1.9 m span beside the doorway,
    # sill at 1.1 m so the top (2.006 m) meets the lintel line. The door sprite covers |x| <= 0.75 m.
    w, h = 26 / PX_PER_M, 29 / PX_PER_M
    z0, z1, y = 1.1, 1.1 + h, Y0 - 0.01
    for side, cx in (("w", (X0 - DOOR) / 2), ("e", (X1 + DOOR) / 2)):
        decal(f"window_south_{side}", [(cx - w / 2, y, z0), (cx + w / 2, y, z0), (cx + w / 2, y, z1),
                                       (cx - w / 2, y, z1)], window)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    kit.reset()
    build()
    redress()
    kit.export(Path(args[0]).resolve())
