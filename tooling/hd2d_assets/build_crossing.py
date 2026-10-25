"""Build the Stage 3 test structure in Blender and export it as GLB, with its collision authored beside it.

Run headless (no window), from the repo root:
    blender --factory-startup -noaudio --background --python tooling/hd2d_assets/build_crossing.py -- OUT.glb

Blender: X east, Y north, Z up, metres (one 32 px texture tile per metre). The crossing: two stone platforms 2 m
high (west and east), each with a staircase down its south side, joined by a railed bridge whose deck (top at 2 m)
spans the 6 m gap; the ground under the bridge is an open underpass. A hut with a roof stands on the east platform.

Collision is separate objects, never drawn, each with the custom property ``mesh_collision`` (exported to the
node's glTF ``extras``; see engine/hd2d/glb.py):

- ``solid``: the platforms, and each staircase as one ramp through the steps' front edges (feet stay on the steps);
- ``floor``: the bridge deck (open underneath: the underpass);
- ``wall``: the railings and the hut.
"""

import sys
from pathlib import Path

import bmesh
import bpy

LAB = Path(__file__).resolve().parents[1] / "hd2d_lab" / "assets"  # the Stage 1 pixel textures
OUT = Path(sys.argv[sys.argv.index("--") + 1]).resolve()


def material(name: str, texture: str):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(LAB / f"{texture}.png"))
    tex.interpolation = "Closest"
    links.new(tex.outputs["Color"], shader.inputs["Base Color"])
    shader.inputs["Roughness"].default_value = 1.0
    return mat


WALL, TOP, ROOF = material("stone_wall", "stone_wall"), material("stone_top", "stone_top"), material("roof", "roof")


def _finish(name: str, bm, *, roof: bool = False, collision: str | None = None):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)  # outward: upward faces are the walkable ones
    bm.normal_update()
    mesh = bpy.data.meshes.new(name)
    if collision is None:
        uv = bm.loops.layers.uv.new("UVMap")
        for face in bm.faces:
            n = face.normal
            axis = max(range(3), key=lambda i: abs(n[i]))
            face.material_index = 2 if roof else (1 if axis == 2 and n.z > 0 else 0)
            for loop in face.loops:
                co = loop.vert.co
                loop[uv].uv = {0: (co.y, co.z), 1: (co.x, co.z), 2: (co.x, co.y)}[axis]
    bm.to_mesh(mesh)
    bm.free()
    if collision is None:
        for mat in (WALL, TOP, ROOF):
            mesh.materials.append(mat)
        for poly in mesh.polygons:
            poly.use_smooth = False
    obj = bpy.data.objects.new(name, mesh)
    if collision is not None:
        obj["mesh_collision"] = collision
    bpy.context.collection.objects.link(obj)
    return obj


def box(name, x0, y0, z0, x1, y1, z1, collision=None):
    bm = bmesh.new()
    v = [bm.verts.new((x, y, z)) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    for a, b, c, d in ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)):
        bm.faces.new((v[a], v[b], v[c], v[d]))
    return _finish(name, bm, collision=collision)


def wedge(name, x0, x1, y0, y1, z_top, collision):
    """A ramp rising from (y0, z 0) to (y1, z_top)."""
    bm = bmesh.new()
    a0, a1 = bm.verts.new((x0, y0, 0)), bm.verts.new((x1, y0, 0))
    b0, b1 = bm.verts.new((x0, y1, 0)), bm.verts.new((x1, y1, 0))
    t0, t1 = bm.verts.new((x0, y1, z_top)), bm.verts.new((x1, y1, z_top))
    for face in ((a0, a1, t1, t0), (a0, b0, b1, a1), (b0, t0, t1, b1), (a0, t0, b0), (a1, b1, t1)):
        bm.faces.new(face)
    return _finish(name, bm, collision=collision)


def pyramid(name, x0, y0, x1, y1, z0, apex):
    bm = bmesh.new()
    base = [bm.verts.new(p) for p in ((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0))]
    top = bm.verts.new(((x0 + x1) / 2, (y0 + y1) / 2, apex))
    for i in range(4):
        bm.faces.new((base[i], base[(i + 1) % 4], top))
    bm.faces.new(tuple(reversed(base)))
    return _finish(name, bm, roof=True)


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()
H = 2.0  # platform and deck height
for side, (x0, x1) in (("west", (-9.0, -3.0)), ("east", (3.0, 9.0))):
    box(f"platform_{side}", x0, -3.0, 0.0, x1, 3.0, H)
    box(f"col_platform_{side}", x0, -3.0, 0.0, x1, 3.0, H, collision="solid")
    sx0, sx1 = (x0 + x1) / 2 - 1.0, (x0 + x1) / 2 + 1.0  # stairs 2 m wide, centred on the platform's south side
    for k in range(8):  # eight steps of 0.25 m, 0.5 m deep: y -7 .. -3
        box(f"stairs_{side}_{k}", sx0, -7.0 + 0.5 * k, 0.0, sx1, -3.0, 0.25 * (k + 1))
    wedge(f"col_stairs_{side}", sx0, sx1, -7.5, -3.5, H, collision="solid")  # through the steps' front edges
    box(f"col_landing_{side}", sx0, -3.5, 0.0, sx1, -3.0, H, collision="solid")  # the top step
box("bridge_deck", -3.0, -1.0, 1.85, 3.0, 1.0, H)
box("col_bridge_deck", -3.0, -1.0, 1.85, 3.0, 1.0, H, collision="floor")
for side, (y0, y1) in (("south", (-1.0, -0.85)), ("north", (0.85, 1.0))):
    box(f"railing_{side}", -3.0, y0, H, 3.0, y1, H + 0.6)
    box(f"col_railing_{side}", -3.0, y0, H, 3.0, y1, H + 0.6, collision="wall")
box("hut", 4.5, 0.5, H, 7.5, 2.5, H + 2.0)
pyramid("roof", 4.2, 0.2, 7.8, 2.8, H + 2.0, H + 3.2)
box("col_hut", 4.2, 0.2, H, 7.8, 2.8, H + 2.2, collision="wall")

OUT.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.export_scene.gltf(filepath=str(OUT), export_format="GLB", export_yup=True, export_apply=True,
                          export_texcoords=True, export_normals=True, export_materials="EXPORT", export_extras=True)
print(f"exported {OUT} ({OUT.stat().st_size} bytes)")
