"""The Stage 5B demonstration cottage, built and exported by Blender (original; textures from pixel_textures.py).

Run headless (no window), from the repo root:
    blender --factory-startup -noaudio --background --python tooling/hd2d_assets/build_cottage.py -- OUT.glb [--v2]

A 5 x 4 m timber-and-plaster cottage with a slate gable roof, a wooden floor (0.1 m up) and an open doorway in the
middle of its south wall. Collision:

- ``solid``: the floor slab (walkable, a 0.1 m step up from the ground);
- ``wall``: the four walls, the south one in two parts either side of the 1.2 m doorway, and the lintel over it.

``--v2`` is the same cottage after an edit in Blender (Stage 5B's reimport): a cobbled porch in front of the door
(``solid``, 0.15 m up), a stone hearth against the east wall (``wall``) and a chimney on the roof.

``build_kit()`` is the starter kit's cottage (``build_starter_kit.py``, Milestone 17): the same floor, walls, doorway
and collision, refined with the same starter textures (docs/reviews/milestone17_cottage_integration.md):

- a cobbled plinth to PLINTH instead of timber to 1.3 m, and no faces hidden inside the model (the wall boxes' tops
  and bottoms, the lintel's ends and top), so no two materials are coplanar where the cutaway opens a wall;
- timber framing wholly outside the walls: a sill ring on the plinth and an L-shaped post at each corner, the grain
  running up the posts;
- a window either side of the door: a timber frame and cross mullion over a dark pane 2 cm out of the wall;
- the roof's shingles run up the slope at 32 px per metre (``gable_roof`` maps them flat: 27.9 px per metre along
  the slope).
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bmesh  # noqa: E402
import bpy  # noqa: E402
from blender_kit import _finish, box, export, gable_roof, material, reset  # noqa: E402

X0, X1, Y0, Y1, T, FLOOR_TOP, EAVES = -2.5, 2.5, -2.0, 2.0, 0.2, 0.1, 2.5
DOOR = 0.6  # half the doorway's width


def build(v2: bool = False) -> None:
    """The cottage (``v2``: after the edit) in the current Blender scene."""
    TIMBER, PLASTER, SHINGLES = material("timber"), material("plaster"), material("shingles")
    FLOOR, COBBLES = material("floorboards"), material("cobbles")
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
    if v2:
        box("porch", -1.5, Y0 - 1.2, 0.0, 1.5, Y0, 0.15, (COBBLES, COBBLES))
        box("col_porch", -1.5, Y0 - 1.2, 0.0, 1.5, Y0, 0.15, collision="solid")
        box("hearth", X1 - T - 0.7, -0.6, FLOOR_TOP, X1 - T, 0.6, 1.0, (COBBLES, COBBLES))
        box("col_hearth", X1 - T - 0.7, -0.6, FLOOR_TOP, X1 - T, 0.6, 1.0, collision="wall")
        box("chimney", X1 - T - 0.6, -0.35, 2.9, X1 - T - 0.1, 0.35, 4.4, (COBBLES, COBBLES))


# build_kit(): the refinements, in metres unless noted.
SPLIT, RIDGE = 1.3, 3.8  # build()'s timber/plaster split (moved to PLINTH) and ridge
PLINTH = 0.85  # the cobbles' top; the sill (PLINTH..SILL_TOP) hides the plaster texture's baked band at 0.84-1.0 m
SILL_TOP = PLINTH + 0.15
PLINTH_V = 0.15  # the plinth's texture offset: its top edge falls on a gap between cobbles
GAP = 0.01  # the framing stands this far clear of the wall faces
SILL_DEPTH, POST_DEPTH, POST_WIDTH = 0.04, 0.06, 0.16
EPS = 0.002  # between abutting framing pieces, so no two faces are coplanar
EAVE_PHASE = 2 / 32  # roof: the shingles' darkest gap row ends at the eave
BOARD = 8 / 32  # the timber texture's boards (m at one tile per metre)
PX_PER_M = 32  # the window is laid out on the art's grid: px from its top left
OPENING = (6, 6, 22, 25)  # x0, y0, x1, y1
FRAME = {"stile_l": (6, 6, 8, 25, True), "stile_r": (20, 6, 22, 25, True), "rail_top": (8, 6, 20, 8, False),
         "rail_bottom": (8, 23, 20, 25, False), "mullion": (13, 8, 15, 23, True),
         "transom_l": (8, 13, 13, 15, False), "transom_r": (15, 13, 20, 15, False)}  # name: x0, y0, x1, y1, vertical
WINDOW_SIZE = (26, 29)
WINDOW_Z0 = SILL_TOP + 0.125  # centred between the sill and the plaster's baked band at 1.84 m
PANE_OUT, FRAME_OUT = (0.02, 0.025), 0.06  # the pane 2 cm out of the wall; the frame from 2.5 to 6 cm out
GLASS_SRGB = (40, 46, 64)  # the shingles' darkest blue, as a flat colour


def _flat_material(name: str, srgb):
    """A colour without an image: exported as baseColorFactor, which Mesh's reader draws as one texel."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    lin = [((c / 255 + 0.055) / 1.055) ** 2.4 if c / 255 > 0.04045 else c / 255 / 12.92 for c in srgb]
    shader.inputs["Base Color"].default_value = (*lin, 1.0)
    shader.inputs["Roughness"].default_value = 1.0
    return mat


def _drop_faces(obj, keep) -> None:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not keep(f)], context="FACES")
    bm.to_mesh(obj.data)
    bm.free()


def _extrude(name, outline, z0, z1, mat):
    """``outline`` (x, y) extruded from z0 to z1, with the kit's planar UVs."""
    bm = bmesh.new()
    low = [bm.verts.new((x, y, z0)) for x, y in outline]
    high = [bm.verts.new((x, y, z1)) for x, y in outline]
    bm.faces.new(low)
    bm.faces.new(high)
    for i in range(len(outline)):
        j = (i + 1) % len(outline)
        bm.faces.new((low[i], low[j], high[j], high[i]))
    return _finish(name, bm, mat, None)


def _vertical_grain(obj) -> None:
    """Swap u and v on the side faces: the timber's horizontal boards run up the piece."""
    uv = obj.data.uv_layers["UVMap"].data
    for poly in obj.data.polygons:
        if abs(poly.normal.z) < 0.5:
            for li in poly.loop_indices:
                u, v = uv[li].uv
                uv[li].uv = (v, u)


def _window(side: str, cx: float, timber, pane_mat) -> None:
    """The window centred on x = cx in the south wall: a pane and the timber frame."""
    w, h = WINDOW_SIZE
    ox, oy, ox1, oy1 = OPENING
    left, top = cx - (ox1 - ox) / 2 / PX_PER_M, WINDOW_Z0 + (oy1 - oy) / PX_PER_M

    def at(px, py):  # px -> world (x, z)
        return left + (px - ox) / PX_PER_M, top - (py - oy) / PX_PER_M

    (xa, za), (xb, zb) = at(ox, oy1), at(ox1, oy)
    y = Y0 - PANE_OUT[0]
    bm = bmesh.new()
    face = bm.faces.new([bm.verts.new(c) for c in ((xa, y, za), (xb, y, za), (xb, y, zb), (xa, y, zb))])
    uvl = bm.loops.layers.uv.new("UVMap")
    for loop, (px, py) in zip(face.loops, ((ox, oy1), (ox1, oy1), (ox1, oy), (ox, oy))):
        loop[uvl].uv = (px / w, 1 - py / h)
    mesh = bpy.data.meshes.new(f"window_{side}_pane")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(pane_mat)
    bpy.context.collection.objects.link(bpy.data.objects.new(mesh.name, mesh))
    for name, (x0, y0, x1, y1, vertical) in FRAME.items():
        (a, b), (c, d) = at(x0, y1), at(x1, y0)
        # The pieces abut (no gap for the pane to show through), so the frame covers the pane's edges; where two
        # touch, both faces are timber and enclosed by the pieces themselves.
        obj = box(f"window_{side}_{name}", a, Y0 - FRAME_OUT, b, c, Y0 - PANE_OUT[1], d, timber)
        if vertical:
            _vertical_grain(obj)
        _mid_board(obj)


def _mid_board(obj) -> None:
    """Shift V so the piece's front face sits in the middle of a board: the timber texture's 8 px boards each end in
    a dark line, which would otherwise run along a 2 px frame piece's edge."""
    uv = obj.data.uv_layers["UVMap"].data
    front = [uv[li].uv[1] for poly in obj.data.polygons if poly.normal.y < -0.5 for li in poly.loop_indices]
    shift = BOARD / 2 - ((min(front) + max(front)) / 2) % BOARD
    for loop in uv:
        loop.uv = (loop.uv[0], loop.uv[1] + shift)


def build_kit() -> None:
    """The starter kit's cottage in the current Blender scene: ``build()``, refined (see the module's notes)."""
    build()
    timber, plaster, shingles = material("timber"), material("plaster"), material("shingles")
    plinth, pane = material("cobbles"), _flat_material("glass", GLASS_SRGB)
    objs = bpy.data.objects

    objs["floor"].data.materials[1] = plinth  # the slab's 0.1 m edge continues the plinth to the ground
    for obj in [o for o in objs if o.name.startswith("wall_")]:
        low, mesh = obj.name.endswith("_low"), obj.data
        mesh.materials[0] = mesh.materials[1] = plinth if low else plaster
        moved = {v.index for v in mesh.vertices if abs(v.co.z - SPLIT) < 1e-6}
        uv = mesh.uv_layers["UVMap"].data
        for poly in mesh.polygons:
            if abs(poly.normal.z) < 0.5:
                for li in poly.loop_indices:
                    if mesh.loops[li].vertex_index in moved:
                        uv[li].uv[1] = PLINTH
        for i in moved:
            mesh.vertices[i].co.z = PLINTH
        # Hidden faces: a box's top and bottom (against the floor slab, the other box, the roof's underside).
        _drop_faces(obj, lambda f: abs(f.normal.z) < 0.5)
    # The lintel's ends (against the walls) and top (against the roof's underside) are hidden too.
    _drop_faces(objs["lintel"], lambda f: abs(f.normal.x) < 0.5 and f.normal.z < 0.5)

    roof = objs["roof"].data
    roof.materials[0], roof.materials[1] = shingles, plaster
    ym, slope = (Y0 + Y1) / 2, math.hypot((Y1 - Y0) / 2 + 0.3, RIDGE - EAVES)
    uv = roof.uv_layers["UVMap"].data
    for poly in roof.polygons:
        if poly.material_index == 0:  # the two slopes: image up = up the slope, read from outside
            for li in poly.loop_indices:
                co = roof.vertices[roof.loops[li].vertex_index].co
                along = slope - math.hypot(co.y - ym, co.z - RIDGE)
                uv[li].uv = (co.x if poly.normal.y < 0 else -co.x, along + EAVE_PHASE)

    # Framing, wholly outside the walls. The sill: one ring on the plinth, open at the doorway.
    g, s = GAP, GAP + SILL_DEPTH
    ring = [(DOOR, Y0 - g), (X1 + g, Y0 - g), (X1 + g, Y1 + g), (X0 - g, Y1 + g), (X0 - g, Y0 - g), (-DOOR, Y0 - g),
            (-DOOR, Y0 - s), (X0 - s, Y0 - s), (X0 - s, Y1 + s), (X1 + s, Y1 + s), (X1 + s, Y0 - s), (DOOR, Y0 - s)]
    _extrude("frame_sill", ring, PLINTH, SILL_TOP, timber)
    p, w = GAP + POST_DEPTH, POST_WIDTH
    for name, sx, sy in (("sw", -1, -1), ("se", 1, -1), ("nw", -1, 1), ("ne", 1, 1)):
        cx, cy = (X0 if sx < 0 else X1), (Y0 if sy < 0 else Y1)
        outline = [(cx + sx * p, cy + sy * p), (cx - sx * w, cy + sy * p), (cx - sx * w, cy + sy * g),
                   (cx + sx * g, cy + sy * g), (cx + sx * g, cy - sy * w), (cx + sx * p, cy - sy * w)]
        _vertical_grain(_extrude(f"frame_post_{name}", outline, SILL_TOP + EPS, EAVES - 0.01, timber))

    # The plinth's texture offset (every kit texture is 32 px, so one tile per metre is already 32 px per metre).
    for obj in objs:
        if obj.type != "MESH" or "mesh_collision" in obj:
            continue
        uv = obj.data.uv_layers["UVMap"].data
        for poly in obj.data.polygons:
            if obj.data.materials[poly.material_index] == plinth and abs(poly.normal.z) < 0.5:
                for li in poly.loop_indices:
                    uv[li].uv = (uv[li].uv[0], uv[li].uv[1] + PLINTH_V)

    for side, cx in (("w", (X0 - DOOR) / 2), ("e", (X1 + DOOR) / 2)):
        _window(side, cx, timber, pane)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    reset()
    build("--v2" in args)
    export(Path(args[0]).resolve())
