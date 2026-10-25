"""Helpers for the Stage 5B demonstration models, run inside Blender (``bpy``): pixel-art materials, boxes, ramps and
gable roofs with planar UVs (one texture tile per metre), collision objects, and the glTF export Mesh reads.

Blender: X east, Y north, Z up, metres. A collision object is an ordinary mesh with the custom property
``mesh_collision`` = "solid" | "floor" | "wall"; the exporter writes it to the node's ``extras`` (Include > Custom
Properties) and Mesh never draws it.
"""

from pathlib import Path

import bmesh
import bpy

TEXTURES = Path(__file__).resolve().parent / "textures"
_MATERIALS: dict = {}


def reset() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    _MATERIALS.clear()


def material(texture: str, *, interpolation: str = "Closest"):
    """A material showing ``textures/<texture>.png``. "Closest" keeps pixel art sharp; Blender's default is
    "Linear" (smooth), which Mesh Studio's "Keep pixels sharp" corrects on import."""
    key = (texture, interpolation)
    if key not in _MATERIALS:
        mat = bpy.data.materials.new(f"{texture}")
        mat.use_nodes = True
        nodes, links = mat.node_tree.nodes, mat.node_tree.links
        shader = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(str(TEXTURES / f"{texture}.png"))
        tex.interpolation = interpolation
        links.new(tex.outputs["Color"], shader.inputs["Base Color"])
        shader.inputs["Roughness"].default_value = 1.0
        _MATERIALS[key] = mat
    return _MATERIALS[key]


def _finish(name: str, bm, mats, collision: str | None):
    """``mats``: (top, sides) materials, or one for every face."""
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    mesh = bpy.data.meshes.new(name)
    if collision is None:
        top, sides = mats if isinstance(mats, tuple) else (mats, mats)
        uv = bm.loops.layers.uv.new("UVMap")
        for face in bm.faces:
            n = face.normal
            axis = max(range(3), key=lambda i: abs(n[i]))
            face.material_index = 0 if axis == 2 and n.z > 0 else 1
            for loop in face.loops:
                co = loop.vert.co
                loop[uv].uv = {0: (co.y, co.z), 1: (co.x, co.z), 2: (co.x, co.y)}[axis]
    bm.to_mesh(mesh)
    bm.free()
    if collision is None:
        mesh.materials.append(top)
        mesh.materials.append(sides)
        for poly in mesh.polygons:
            poly.use_smooth = False
    obj = bpy.data.objects.new(name, mesh)
    if collision is not None:
        obj["mesh_collision"] = collision
    bpy.context.collection.objects.link(obj)
    return obj


def box(name, x0, y0, z0, x1, y1, z1, mats=None, collision=None):
    bm = bmesh.new()
    v = [bm.verts.new((x, y, z)) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    for a, b, c, d in ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)):
        bm.faces.new((v[a], v[b], v[c], v[d]))
    return _finish(name, bm, mats, collision)


def ramp(name, x0, x1, y0, y1, z_top, collision="solid"):
    """A collision ramp rising from (y0, z 0) to (y1, z_top): stairs as one walkable slope."""
    bm = bmesh.new()
    a0, a1 = bm.verts.new((x0, y0, 0)), bm.verts.new((x1, y0, 0))
    b0, b1 = bm.verts.new((x0, y1, 0)), bm.verts.new((x1, y1, 0))
    t0, t1 = bm.verts.new((x0, y1, z_top)), bm.verts.new((x1, y1, z_top))
    for face in ((a0, a1, t1, t0), (a0, b0, b1, a1), (b0, t0, t1, b1), (a0, t0, b0), (a1, b1, t1)):
        bm.faces.new(face)
    return _finish(name, bm, None, collision)


def gable_roof(name, x0, y0, x1, y1, z0, ridge, roof_mat, gable_mat):
    """A roof whose ridge runs east-west at height ``ridge`` over the rectangle, gable ends on the east and west."""
    bm = bmesh.new()
    ym = (y0 + y1) / 2
    s0, s1 = bm.verts.new((x0, y0, z0)), bm.verts.new((x1, y0, z0))
    n0, n1 = bm.verts.new((x0, y1, z0)), bm.verts.new((x1, y1, z0))
    r0, r1 = bm.verts.new((x0, ym, ridge)), bm.verts.new((x1, ym, ridge))
    slopes = [bm.faces.new((s0, s1, r1, r0)), bm.faces.new((n1, n0, r0, r1))]
    gables = [bm.faces.new((s0, r0, n0)), bm.faces.new((s1, n1, r1))]
    bm.faces.new((s0, n0, n1, s1))  # the underside
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    uv = bm.loops.layers.uv.new("UVMap")
    for face in bm.faces:
        face.material_index = 0 if face in slopes else 1
        for loop in face.loops:
            co = loop.vert.co
            loop[uv].uv = (co.x, co.y) if face in slopes or face not in gables else (co.y, co.z)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(roof_mat)
    mesh.materials.append(gable_mat)
    for poly in mesh.polygons:
        poly.use_smooth = False
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def export(out: Path) -> None:
    """glTF Binary, Y-up, transforms applied, custom properties (the collision tags) included."""
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(out), export_format="GLB", export_yup=True, export_apply=True,
                              export_texcoords=True, export_normals=True, export_materials="EXPORT",
                              export_extras=True)
    print(f"exported {out} ({out.stat().st_size} bytes)")
