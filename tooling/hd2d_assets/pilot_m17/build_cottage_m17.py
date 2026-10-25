"""M17 pilot cottage: the starter cottage's geometry and collision, improved, in one of two texture sets.

Run headless (no window), from the repo root:
    blender --factory-startup -noaudio --background --python tooling/hd2d_assets/pilot_m17/build_cottage_m17.py -- OUT.glb --set starter|pixellab

``--set starter`` (models/cottage_m17_geo.glb) uses starter textures only; ``--set pixellab``
(models/cottage_m17.glb) is the same geometry with stone_b_seamfix on the plinth and window_a_glass in the windows.

Geometry and collision come from ``build_cottage.build()`` unchanged; then:

- the timber/plaster split drops from 1.3 m to PLINTH, and the faces hidden inside the model (the wall boxes' tops
  and bottoms against the floor slab, each other and the roof; the lintel's ends and top) are removed, so nothing of two
  materials is coplanar (the cutaway shows the inside of the walls);
- framing in starter timber, wholly outside the walls (GAP clear of every wall face): a sill ring on the plinth and
  an L-shaped post at each corner, vertical grain on vertical timber;
- a modelled window either side of the door: timber frame and cross mullion over a pane 2 cm out of the wall, its
  layout that of window_a.png's opening (32 px per metre);
- every UV at 32 px per metre; the roof's image runs up the slope (the kit maps it flat).
"""

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import blender_kit as kit  # noqa: E402
import bmesh  # noqa: E402
import bpy  # noqa: E402
from build_cottage import DOOR, EAVES, X0, X1, Y0, Y1, build  # noqa: E402

PX_PER_M = 32
SPLIT = 1.3  # build_cottage's timber/plaster split, moved to PLINTH
PLINTH = 0.85  # stone top; the sill (PLINTH..SILL_TOP) hides the starter plaster's baked band at 0.84-1.0 m
SILL_TOP = PLINTH + 0.15
RIDGE = 3.8  # build_cottage's gable_roof ridge height
GAP = 0.01  # framing stands this far clear of the wall faces
SILL_DEPTH, POST_DEPTH, POST_WIDTH = 0.04, 0.06, 0.16
EPS = 0.002  # between abutting framing pieces, so no two faces are coplanar
EAVE_PHASE = 2 / 32  # roof: the shingles' darkest gap row ends at the eave
# The plinth's V offset (m), per texture: the plinth's top edge falls on a mortar line (stone_b_seamfix row 11,
# keeping the stray highlight rows 41-43 off the wall) or on a gap row (cobbles row 0).
PLINTH_V = {"starter": 0.15, "pixellab": 0.80625}
# The window: window_a.png's opening, px (x0, y0, x1, y1) from its top left; frame pieces in the same px.
OPENING = (6, 6, 22, 25)
FRAME = {"stile_l": (6, 6, 8, 25, True), "stile_r": (20, 6, 22, 25, True), "rail_top": (8, 6, 20, 8, False),
         "rail_bottom": (8, 23, 20, 25, False), "mullion": (13, 8, 15, 23, True),
         "transom_l": (8, 13, 13, 15, False), "transom_r": (15, 13, 20, 15, False)}  # name: x0, y0, x1, y1, vertical
WINDOW_SIZE = (26, 29)
WINDOW_Z0 = SILL_TOP + 0.125  # centred between the sill and the plaster's baked band at 1.84 m
PANE_OUT, FRAME_OUT = (0.02, 0.025), 0.06  # the pane 2 cm out; the frame from 2.5 to 6 cm out
GLASS_SRGB = (40, 46, 64)  # set "starter": the starter shingles' darkest blue as a flat colour (no image)


def pilot_material(name: str, extension: str = "REPEAT"):
    """``blender_kit.material`` for a texture in pilot_m17/textures (Closest, like the kit)."""
    saved, kit.TEXTURES = kit.TEXTURES, HERE / "textures"
    try:
        mat = kit.material(name)
    finally:
        kit.TEXTURES = saved
    _image_node(mat).extension = extension
    return mat


def flat_material(name: str, srgb):
    """A colour without an image: exported as baseColorFactor, which Mesh's reader draws as one texel."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    lin = [((c / 255 + 0.055) / 1.055) ** 2.4 if c / 255 > 0.04045 else c / 255 / 12.92 for c in srgb]
    shader.inputs["Base Color"].default_value = (*lin, 1.0)
    shader.inputs["Roughness"].default_value = 1.0
    return mat


def _image_node(mat):
    return next((n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE"), None)


def drop_faces(obj, keep) -> None:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not keep(f)], context="FACES")
    bm.to_mesh(obj.data)
    bm.free()


def prism(name, outline, z0, z1, mat):
    """``outline`` (x, y) extruded from z0 to z1, with the kit's planar UVs."""
    bm = bmesh.new()
    low = [bm.verts.new((x, y, z0)) for x, y in outline]
    high = [bm.verts.new((x, y, z1)) for x, y in outline]
    bm.faces.new(low)
    bm.faces.new(high)
    for i in range(len(outline)):
        j = (i + 1) % len(outline)
        bm.faces.new((low[i], low[j], high[j], high[i]))
    return kit._finish(name, bm, mat, None)


def vertical_grain(obj) -> None:
    """Swap u and v on the side faces: the timber's horizontal boards run up the piece."""
    uv = obj.data.uv_layers["UVMap"].data
    for poly in obj.data.polygons:
        if abs(poly.normal.z) < 0.5:
            for li in poly.loop_indices:
                u, v = uv[li].uv
                uv[li].uv = (v, u)


def window(side: str, cx: float, timber, pane_mat) -> None:
    """The window centred on x = cx in the south wall: a pane (UV = window_a's opening) and the timber frame."""
    w, h = WINDOW_SIZE
    ox, oy, ox1, oy1 = OPENING
    left, top = cx - (ox1 - ox) / 2 / PX_PER_M, WINDOW_Z0 + (oy1 - oy) / PX_PER_M

    def at(px, py):  # window_a px -> world (x, z)
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
        # Each piece EPS short of its neighbours all round, so no two pieces share a face.
        obj = kit.box(f"window_{side}_{name}", a + EPS, Y0 - FRAME_OUT, b + EPS, c - EPS, Y0 - PANE_OUT[1], d - EPS,
                      timber)
        if vertical:
            vertical_grain(obj)


def redress(texture_set: str) -> None:
    timber, plaster, shingles = kit.material("timber"), kit.material("plaster"), kit.material("shingles")
    if texture_set == "pixellab":
        plinth, pane = pilot_material("stone_b_seamfix"), pilot_material("window_a_glass", "EXTEND")
    else:
        plinth, pane = kit.material("cobbles"), flat_material("glass", GLASS_SRGB)
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
        drop_faces(obj, lambda f: abs(f.normal.z) < 0.5)
    # The lintel's ends (against the walls) and top (against the roof's underside) are hidden too.
    drop_faces(objs["lintel"], lambda f: abs(f.normal.x) < 0.5 and f.normal.z < 0.5)

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
    prism("frame_sill", ring, PLINTH, SILL_TOP, timber)
    p, w = GAP + POST_DEPTH, POST_WIDTH
    for name, sx, sy in (("sw", -1, -1), ("se", 1, -1), ("nw", -1, 1), ("ne", 1, 1)):
        cx, cy = (X0 if sx < 0 else X1), (Y0 if sy < 0 else Y1)
        outline = [(cx + sx * p, cy + sy * p), (cx - sx * w, cy + sy * p), (cx - sx * w, cy + sy * g),
                   (cx + sx * g, cy + sy * g), (cx + sx * g, cy - sy * w), (cx + sx * p, cy - sy * w)]
        vertical_grain(prism(f"frame_post_{name}", outline, SILL_TOP + EPS, EAVES - 0.01, timber))

    # 32 px per metre on every kit-mapped face (the kit maps 1 tile per metre); the plinth's V offset.
    for obj in objs:
        if obj.type != "MESH" or "mesh_collision" in obj:
            continue
        uv = obj.data.uv_layers["UVMap"].data
        for poly in obj.data.polygons:
            mat = obj.data.materials[poly.material_index]
            node = _image_node(mat)
            if node is None:
                continue
            offset = PLINTH_V[texture_set] if mat == plinth and abs(poly.normal.z) < 0.5 else 0.0
            scale = PX_PER_M / node.image.size[0]
            for li in poly.loop_indices:
                uv[li].uv = (uv[li].uv[0] * scale, (uv[li].uv[1] + offset) * scale)

    for side, cx in (("w", (X0 - DOOR) / 2), ("e", (X1 + DOOR) / 2)):
        window(side, cx, timber, pane)


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    texture_set = args[args.index("--set") + 1]
    if texture_set not in PLINTH_V:
        raise SystemExit(f"--set must be one of {', '.join(PLINTH_V)}")
    kit.reset()
    build()
    redress(texture_set)
    kit.export(Path(args[0]).resolve())
