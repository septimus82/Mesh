"""Build the lab's structure in Blender and export it as GLB with Blender's own glTF exporter.

Run headless (no window), from the repo root:
    blender --factory-startup -noaudio --background --python tooling/hd2d_lab/blender_build.py -- OUT.glb

Modular pieces, one object each: a raised stone platform, steps up to it, a small hut on it and a pyramid roof.
Units are metres (one 32 px texture tile per metre). Faces get planar UVs in world metres; upward faces use the
stone_top texture, the others stone_wall, the roof its slates. Textures use 'Closest' (pixel art) sampling, which the
exporter writes as a NEAREST glTF sampler.
"""

import sys
from pathlib import Path

import bmesh
import bpy

ASSETS = Path(__file__).resolve().parent / "assets"
OUT = Path(sys.argv[sys.argv.index("--") + 1]).resolve()


def material(name: str, texture: str):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(ASSETS / f"{texture}.png"))
    tex.interpolation = "Closest"
    links.new(tex.outputs["Color"], shader.inputs["Base Color"])
    shader.inputs["Roughness"].default_value = 1.0
    return mat


WALL, TOP, ROOF = material("stone_wall", "stone_wall"), material("stone_top", "stone_top"), material("roof", "roof")


def _uv_and_material(bm, roof: bool) -> None:
    uv = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        n = face.normal
        axis = max(range(3), key=lambda i: abs(n[i]))
        face.material_index = 2 if roof else (1 if axis == 2 and n.z > 0 else 0)
        for loop in face.loops:
            co = loop.vert.co
            loop[uv].uv = {0: (co.y, co.z), 1: (co.x, co.z), 2: (co.x, co.y)}[axis]


def add_object(name: str, build, roof: bool = False):
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    build(bm)
    bm.normal_update()
    _uv_and_material(bm, roof)
    bm.to_mesh(mesh)
    bm.free()
    for mat in (WALL, TOP, ROOF):
        mesh.materials.append(mat)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def box(x0, y0, z0, x1, y1, z1):
    def build(bm):
        v = [bm.verts.new((x, y, z)) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
        for a, b, c, d in ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)):
            bm.faces.new((v[a], v[b], v[c], v[d]))
    return build


def pyramid(x0, y0, x1, y1, z0, apex):
    def build(bm):
        base = [bm.verts.new(p) for p in ((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0))]
        top = bm.verts.new(((x0 + x1) / 2, (y0 + y1) / 2, apex))
        for i in range(4):
            bm.faces.new((base[i], base[(i + 1) % 4], top))
        bm.faces.new(tuple(reversed(base)))
    return build


bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()
# Blender: X east, Y north, Z up. The platform's front (steps) faces south (-Y), towards the camera.
add_object("platform", box(-2.0, -1.0, 0.0, 2.0, 2.0, 1.0))
for i in range(3):  # three steps, 1/3 m each, up the front
    add_object(f"step_{i}", box(-0.6, -1.0 - 0.4 * (3 - i), 0.0, 0.6, -1.0 - 0.4 * (2 - i), (i + 1) / 3))
add_object("hut", box(-1.2, 0.3, 1.0, 1.2, 1.8, 3.0))
add_object("roof", pyramid(-1.5, 0.0, 1.5, 2.1, 3.0, 4.2), roof=True)
for obj in bpy.data.objects:  # flat-faced, pixel-art look
    for poly in obj.data.polygons:
        poly.use_smooth = False

OUT.parent.mkdir(parents=True, exist_ok=True)
bpy.ops.export_scene.gltf(filepath=str(OUT), export_format="GLB", export_yup=True, export_apply=True,
                          export_texcoords=True, export_normals=True, export_materials="EXPORT")
print(f"exported {OUT} ({OUT.stat().st_size} bytes)")
