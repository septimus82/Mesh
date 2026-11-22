"""M2-2's Blender character: one small rigged villager rendered from eight facings into sprite-sheet frames (original;
flat colours, no textures).

Run headless (no window), from the repo root; ``character_sheet.py`` runs this and assembles the sheet:
    blender --factory-startup -noaudio --background --python tooling/hd2d_assets/build_character.py -- FRAMES_DIR [--blend OUT.blend]

- **Rig.** An armature (``hips`` the root, ``torso``, ``head``, ``arm.L``/``arm.R``, ``leg.L``/``leg.R``) and one
  low-poly mesh of boxes skinned to it (each box wholly in its bone's vertex group, an Armature modifier). Blender:
  X east, Y north, Z up, metres; the character stands on the origin facing south (-Y), 1.4 m tall.
- **Animation.** One action on the armature: ``idle`` (IDLE frames, a 1 px breath) then ``walk`` (WALK frames, legs
  and arms swinging, the hips bobbing), keyed on scene frames 1.. in that order.
- **Camera.** Orthographic, looking north and down at the HD-2D pitch (``settings.camera.pitch``, 32 degrees below
  the horizon), 32 px per metre across the screen like the HD-2D renderer, the feet's origin at PIVOT in every frame.
  The camera stays put; the character turns: facing i of FACINGS is a turn of -45 * i degrees about Z.
- **Colours.** PALETTE's sRGB values were picked from one PixelLab reference image (``create-image-pixflux``, 1
  generation, 2026-11-22: a villager in a moss-green tunic). Only these colour values are used; no PixelLab pixels
  are in the sheet or the repository (docs/asset_licensing.md).
- **Render.** Workbench (deterministic, no sampling): no anti-aliasing or dither, the bundled ``paint.sl`` studio
  light fixed in world space (so every facing is lit from the same side), transparent background, Standard view
  transform: one FRAME_W x FRAME_H PNG per (facing, animation, frame), named ``{facing}_{animation}_{frame}.png``.
  ``character_sheet.py`` adds the 1 px outline when it assembles the sheet.
"""

import math
import sys
from pathlib import Path

import bmesh
import bpy

FACINGS = ("down", "down_left", "left", "up_left", "up", "up_right", "right", "down_right")  # S SW W NW N NE E SE
ANIMATIONS = (("idle", 2), ("walk", 8))
FRAME_W, FRAME_H, PIVOT, PITCH, PX_PER_M = 32, 52, (16, 45), 32.0, 32.0

PALETTE = {  # sRGB, from the PixelLab reference (see above)
    "skin": (249, 206, 174), "hair": (129, 76, 44), "eyes": (27, 37, 62), "tunic": (87, 105, 48),
    "belt": (87, 51, 30), "trousers": (98, 97, 109), "boots": (72, 41, 23), "satchel": (142, 90, 60),
}

# Bones: name -> (head, tail, parent).
BONES = {
    "hips": ((0, 0, 0.50), (0, 0, 0.66), None),
    "torso": ((0, 0, 0.66), (0, 0, 0.92), "hips"),
    "head": ((0, 0, 0.92), (0, 0, 1.30), "torso"),
    "arm.L": ((0.21, 0, 0.90), (0.21, 0, 0.56), "torso"),
    "arm.R": ((-0.21, 0, 0.90), (-0.21, 0, 0.56), "torso"),
    "leg.L": ((0.08, 0, 0.50), (0.08, 0, 0.06), "hips"),
    "leg.R": ((-0.08, 0, 0.50), (-0.08, 0, 0.06), "hips"),
}
# Boxes: (bone, colour, x0, y0, z0, x1, y1, z1). The character's left is +X (it faces -Y).
BOXES = [
    ("leg.L", "trousers", 0.025, -0.06, 0.10, 0.135, 0.06, 0.52),
    ("leg.L", "boots", 0.02, -0.11, 0.0, 0.14, 0.07, 0.12),
    ("leg.R", "trousers", -0.135, -0.06, 0.10, -0.025, 0.06, 0.52),
    ("leg.R", "boots", -0.14, -0.11, 0.0, -0.02, 0.07, 0.12),
    ("hips", "tunic", -0.17, -0.10, 0.46, 0.17, 0.10, 0.66),
    ("hips", "belt", -0.175, -0.105, 0.58, 0.175, 0.105, 0.63),
    ("hips", "satchel", -0.24, -0.07, 0.48, -0.175, 0.07, 0.62),  # on the right hip: tells left from right
    ("torso", "tunic", -0.16, -0.09, 0.66, 0.16, 0.09, 0.92),
    ("head", "skin", -0.15, -0.14, 0.92, 0.15, 0.14, 1.22),
    ("head", "hair", -0.16, -0.15, 1.18, 0.16, 0.16, 1.32),  # cap of hair
    ("head", "hair", -0.16, 0.06, 0.96, 0.16, 0.16, 1.18),  # the back of the head
    ("head", "eyes", 0.035, -0.145, 1.06, 0.085, -0.13, 1.12),
    ("head", "eyes", -0.085, -0.145, 1.06, -0.035, -0.13, 1.12),
    ("arm.L", "tunic", 0.165, -0.05, 0.66, 0.255, 0.05, 0.92),
    ("arm.L", "skin", 0.17, -0.045, 0.56, 0.25, 0.045, 0.66),
    ("arm.R", "tunic", -0.255, -0.05, 0.66, -0.165, 0.05, 0.92),
    ("arm.R", "skin", -0.25, -0.045, 0.56, -0.17, 0.045, 0.66),
]


def _linear(srgb):
    return [((c / 255 + 0.055) / 1.055) ** 2.4 if c / 255 > 0.04045 else c / 255 / 12.92 for c in srgb]


def _reset() -> None:
    for collection in (bpy.data.objects, bpy.data.meshes, bpy.data.armatures, bpy.data.materials, bpy.data.cameras,
                       bpy.data.lights, bpy.data.actions):
        for block in list(collection):
            collection.remove(block)


def _armature():
    data = bpy.data.armatures.new("rig")
    rig = bpy.data.objects.new("rig", data)
    bpy.context.collection.objects.link(rig)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for name, (head, tail, parent) in BONES.items():
        bone = data.edit_bones.new(name)
        bone.head, bone.tail, bone.roll = head, tail, 0.0
        if parent:
            bone.parent = data.edit_bones[parent]
            bone.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")
    return rig


def _body(rig):
    names = list(PALETTE)
    bm = bmesh.new()
    groups: dict[str, list[int]] = {}
    for bone, colour, x0, y0, z0, x1, y1, z1 in BOXES:
        v = [bm.verts.new((x, y, z)) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
        bm.verts.index_update()
        groups.setdefault(bone, []).extend(vert.index for vert in v)
        for a, b, c, d in ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)):
            bm.faces.new((v[a], v[b], v[c], v[d])).material_index = names.index(colour)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    mesh = bpy.data.meshes.new("body")
    bm.to_mesh(mesh)
    bm.free()
    for name in names:
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = (*_linear(PALETTE[name]), 1.0)  # what Workbench's Material colour draws
        mesh.materials.append(mat)
    body = bpy.data.objects.new("body", mesh)
    bpy.context.collection.objects.link(body)
    for bone, verts in groups.items():
        body.vertex_groups.new(name=bone).add(verts, 1.0, "REPLACE")
    body.parent = rig
    body.modifiers.new("rig", "ARMATURE").object = rig
    return body


def _pose(rig, animation: str, i: int, count: int) -> None:
    """The pose for frame ``i`` of ``count`` of ``animation``."""
    pb = rig.pose.bones
    for bone in pb:
        bone.rotation_mode = "XYZ"
        bone.rotation_euler = (0.0, 0.0, 0.0)
        bone.location = (0.0, 0.0, 0.0)
    if animation == "idle":
        breath = i % 2  # down one pixel, arms a little out
        pb["hips"].location = (0.0, -0.035 * breath, 0.0)  # the bone's Y runs up the body: this is down
        pb["arm.L"].rotation_euler.z = math.radians(5 * breath)
        pb["arm.R"].rotation_euler.z = math.radians(-5 * breath)
        return
    phase = 2 * math.pi * i / count
    swing = math.sin(phase)
    pb["hips"].location = (0.0, 0.035 * (abs(math.cos(phase)) - 1.0), 0.0)  # lowest at full stride
    pb["leg.L"].rotation_euler.x = math.radians(32) * swing
    pb["leg.R"].rotation_euler.x = -math.radians(32) * swing
    pb["arm.L"].rotation_euler.x = -math.radians(28) * swing
    pb["arm.R"].rotation_euler.x = math.radians(28) * swing


def _animate(rig) -> dict[str, tuple[int, int]]:
    """Key every frame of every animation on one action; returns animation -> (first scene frame, count)."""
    spans, frame = {}, 1
    for animation, count in ANIMATIONS:
        spans[animation] = (frame, count)
        for i in range(count):
            _pose(rig, animation, i, count)
            for bone in rig.pose.bones:
                bone.keyframe_insert("rotation_euler", frame=frame + i)
                bone.keyframe_insert("location", frame=frame + i)
        frame += count
    rig.animation_data.action.name = "idle_walk"
    return spans


def _camera_and_render(scene) -> None:
    cam = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = max(FRAME_W, FRAME_H) / PX_PER_M
    cam.data.sensor_fit = "AUTO"
    # the origin sits (FRAME_H / 2 - PIVOT y) px below the frame's centre and (PIVOT x - FRAME_W / 2) px right of it
    cam.data.shift_x = -(PIVOT[0] - FRAME_W / 2) / max(FRAME_W, FRAME_H)
    cam.data.shift_y = (PIVOT[1] - FRAME_H / 2) / max(FRAME_W, FRAME_H)
    pitch = math.radians(PITCH)
    cam.location = (0.0, -20.0 * math.cos(pitch), 20.0 * math.sin(pitch))
    cam.rotation_euler = (math.pi / 2 - pitch, 0.0, 0.0)
    cam.data.clip_end = 100.0

    render = scene.render
    render.engine = "BLENDER_WORKBENCH"
    render.resolution_x, render.resolution_y, render.resolution_percentage = FRAME_W, FRAME_H, 100
    render.film_transparent = True
    render.image_settings.file_format = "PNG"
    render.image_settings.color_mode = "RGBA"
    render.image_settings.color_depth = "8"
    render.use_stamp = False
    render.dither_intensity = 0.0  # Blender's default dither adds noise when it writes 8 bits
    scene.display.render_aa = "OFF"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.studio_light = "paint.sl"
    shading.use_world_space_lighting = True
    shading.color_type = "MATERIAL"
    shading.show_specular_highlight = False
    shading.show_cavity = False
    shading.show_shadows = False
    shading.show_object_outline = False  # Workbench draws it part-transparent over a transparent film


def main(frames_dir: Path, blend: Path | None) -> None:
    scene = bpy.context.scene
    _reset()
    rig = _armature()
    _body(rig)
    spans = _animate(rig)
    _camera_and_render(scene)
    if blend is not None:
        bpy.ops.wm.save_as_mainfile(filepath=str(blend.resolve()), compress=False)
    frames_dir.mkdir(parents=True, exist_ok=True)
    for f, facing in enumerate(FACINGS):
        rig.rotation_euler = (0.0, 0.0, math.radians(-45.0 * f))
        for animation, (first, count) in spans.items():
            for i in range(count):
                scene.frame_set(first + i)
                scene.render.filepath = str((frames_dir / f"{facing}_{animation}_{i}.png").resolve())
                bpy.ops.render.render(write_still=True)
    print(f"rendered {len(FACINGS) * sum(c for _, c in ANIMATIONS)} frames into {frames_dir}")


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    main(Path(args[0]), Path(args[args.index("--blend") + 1]) if "--blend" in args else None)
