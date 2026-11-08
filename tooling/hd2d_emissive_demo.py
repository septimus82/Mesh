"""M17-L3 E1: glTF emission in HD-2D rooms, checked in real frames of the game (a hidden window).

``swatches_glb`` writes a small deterministic GLB: a row of upright panels facing south, one material each (SWATCHES):
emission from a factor, from a texture, from both, zero emission, an ordinary material and a lit material that also
glows. ``check`` imports it into a scratch project (as Mesh Studio does), places it in front of the camera, and reads
each panel's pixels at noon and at night, with a lamp beside it switched on and off, after saving and reopening, and
after a reimport that changes the emission.

    py tooling/hd2d_emissive_demo.py <new folder>
"""

from __future__ import annotations

import io
import json
import struct
import sys
from pathlib import Path
from typing import Any

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

WIDTH, HEIGHT, GAP = 1.2, 1.2, 0.3  # m: each panel, and between panels
TEXELS = ((200, 40, 40, 255), (40, 200, 40, 255), (40, 40, 200, 255), (128, 128, 128, 255))  # 2x2, row by row
BLACK, GREY = [0.0, 0.0, 0.0, 1.0], [0.2, 0.2, 0.2, 1.0]  # base colours (linear)
# (material name, base colour, emissiveFactor or None, emissive texture?, KHR_materials_emissive_strength or None)
SWATCHES = (
    ("factor_only", BLACK, [1.0, 0.5, 0.25], False, None),
    ("texture_only", BLACK, [1.0, 1.0, 1.0], True, None),  # (white factor: the texture alone, as Blender exports it)
    ("factor_and_texture", BLACK, [0.5, 1.0, 0.25], True, None),
    ("zero_emission", GREY, [0.0, 0.0, 0.0], False, None),
    ("ordinary", GREY, None, False, None),
    ("lit_and_glowing", GREY, [0.25, 0.1, 0.0], False, None),
)
# Texture sampling (wrap modes per axis, Linear filtering of an sRGB emission texture): each panel's emission texture
# (index into SAMPLING_TEXTURES) on uv 0..2 (wrap panels: the texture twice across and down) or 0..1, white factor.
REPEAT, CLAMP, MIRROR, NEAREST, LINEAR = 10497, 33071, 33648, 9728, 9729
BLACK_WHITE = ((0, 0, 0, 255), (255, 255, 255, 255))  # 2 x 1
BLACK_GREY = ((0, 0, 0, 255), (128, 128, 128, 255))  # 2 x 1: a mid-tone, where linear and sRGB values differ
SAMPLING_SAMPLERS = ({"magFilter": NEAREST, "minFilter": NEAREST},
                     {"magFilter": NEAREST, "minFilter": NEAREST, "wrapS": REPEAT, "wrapT": CLAMP},
                     {"magFilter": NEAREST, "minFilter": NEAREST, "wrapS": MIRROR, "wrapT": CLAMP},
                     {"magFilter": NEAREST, "minFilter": NEAREST, "wrapS": CLAMP, "wrapT": REPEAT},
                     {"magFilter": LINEAR, "minFilter": LINEAR, "wrapS": CLAMP, "wrapT": CLAMP})
SAMPLING_TEXTURES = ({"source": 0, "sampler": 1}, {"source": 0, "sampler": 2}, {"source": 0, "sampler": 3},
                     {"source": 1, "sampler": 4}, {"source": 2, "sampler": 4})
SAMPLING = (  # (name, base, factor, texture index, strength), uv span
    (("repeat_u_clamp_v", BLACK, [1.0, 1.0, 1.0], 0, None), 2.0),
    (("mirror_u_clamp_v", BLACK, [1.0, 1.0, 1.0], 1, None), 2.0),
    (("clamp_u_repeat_v", BLACK, [1.0, 1.0, 1.0], 2, None), 2.0),
    (("linear_black_white", BLACK, [1.0, 1.0, 1.0], 3, None), 1.0),
    (("linear_black_grey", BLACK, [1.0, 1.0, 1.0], 4, None), 1.0),
)
GRID = (0.125, 0.375, 0.625, 0.875)  # sample points across and down a wrap panel: the middles of its 4 x 4 texels
LINEAR_AT = (0.1, 0.375, 0.5, 0.625, 0.9)  # across a Linear panel (its two texels' middles at 0.25 and 0.75)
STRUCTURE_PX = (384.0, 256.0)  # where the panels stand (the row's middle)
SCENE = "packs/core_regions/scenes/start.json"


def srgb(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def expected_glow(factor: list[float], texel: tuple[int, ...] | None = None, lit: tuple[int, ...] = (0, 0, 0)) -> tuple[int, ...]:
    """What a panel's pixel should be (bytes): its lit colour and its emission (factor x the texel's linear colour)
    added in linear light, back to sRGB, as glTF means it."""
    out = []
    for k in range(3):
        e = factor[k] * (linear(texel[k] / 255) if texel else 1.0)
        out.append(round(255 * srgb(min(1.0, linear(lit[k] / 255) + e))))
    return tuple(out)


def _png(texels: tuple[tuple[int, ...], ...], size: tuple[int, int] = (2, 2)) -> bytes:
    image = Image.new("RGBA", size)
    image.putdata(list(texels))
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def swatches_glb(path: Path, swatches: tuple = SWATCHES, texels: tuple = TEXELS, *, spans: tuple = (),
                 images: tuple = (), samplers: tuple = ({"magFilter": 9728, "minFilter": 9728},),
                 textures: tuple = ({"source": 0, "sampler": 0},)) -> Path:
    """The panels as a GLB (glTF Y-up: each panel in the XY plane facing +Z, which is south in Mesh), uv (0, 0) at
    each panel's top left, as glTF's texture coordinates are, running to ``spans[i]`` (default 1) at the far corner.
    A panel's texture: True is texture 0, an int that texture. ``images``: (texels, size) pairs (default TEXELS)."""
    binary = bytearray()
    views: list[dict] = []
    accessors: list[dict] = []

    def add(data: bytes, **accessor: Any) -> int:
        views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(data)})
        binary.extend(data + b"\0" * (-len(data) % 4))
        if accessor:
            accessors.append({"bufferView": len(views) - 1, **accessor})
            return len(accessors) - 1
        return len(views) - 1

    image_views = [add(_png(t, size)) for t, size in (images or ((texels, (2, 2)),))]
    total = len(swatches) * WIDTH + (len(swatches) - 1) * GAP
    nodes, meshes, materials = [], [], []
    for i, (name, base, factor, textured, strength) in enumerate(swatches):
        x0 = -total / 2 + i * (WIDTH + GAP)
        corners = ((x0, 0.0), (x0 + WIDTH, 0.0), (x0 + WIDTH, HEIGHT), (x0, HEIGHT))
        pos = add(b"".join(struct.pack("<3f", x, y, 0.0) for x, y in corners), componentType=5126, count=4, type="VEC3",
                  min=[x0, 0.0, 0.0], max=[x0 + WIDTH, HEIGHT, 0.0])
        nrm = add(struct.pack("<12f", *(0.0, 0.0, 1.0) * 4), componentType=5126, count=4, type="VEC3")
        k = spans[i] if i < len(spans) else 1.0
        uv = add(struct.pack("<8f", 0.0, k, k, k, k, 0.0, 0.0, 0.0), componentType=5126, count=4, type="VEC2")
        idx = add(struct.pack("<6H", 0, 1, 2, 0, 2, 3), componentType=5123, count=6, type="SCALAR")
        meshes.append({"primitives": [{"attributes": {"POSITION": pos, "NORMAL": nrm, "TEXCOORD_0": uv},
                                       "indices": idx, "material": i}]})
        nodes.append({"name": name, "mesh": i})
        mat: dict[str, Any] = {"name": name, "pbrMetallicRoughness": {"baseColorFactor": base}}
        if factor is not None:
            mat["emissiveFactor"] = factor
        if textured is not False:
            mat["emissiveTexture"] = {"index": 0 if textured is True else textured}
        if strength is not None:
            mat["extensions"] = {"KHR_materials_emissive_strength": {"emissiveStrength": strength}}
        materials.append(mat)
    doc = {"asset": {"version": "2.0", "generator": "Mesh hd2d_emissive_demo"}, "scene": 0,
           "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes, "materials": materials,
           "images": [{"bufferView": v, "mimeType": "image/png"} for v in image_views],
           "samplers": list(samplers), "textures": list(textures),
           "buffers": [{"byteLength": len(binary)}], "bufferViews": views, "accessors": accessors}
    if any(s[4] is not None for s in swatches):
        doc["extensionsUsed"] = ["KHR_materials_emissive_strength"]
    from engine.hd2d.glb import join_glb

    path.write_bytes(join_glb(doc, bytes(binary)))
    return path


def sampling_glb(path: Path) -> Path:
    """The sampling panels (SAMPLING) as a GLB: wrap modes per axis on a Nearest texture, and a Linear black/white
    emission texture."""
    return swatches_glb(path, tuple(p for p, _span in SAMPLING), spans=tuple(span for _p, span in SAMPLING),
                        images=((TEXELS, (2, 2)), (BLACK_WHITE, (2, 1)), (BLACK_GREY, (2, 1))), samplers=SAMPLING_SAMPLERS,
                        textures=SAMPLING_TEXTURES)


def panel_at(index: int, count: int, fx: float, fy: float) -> tuple[float, float, float]:
    """The world point (m) ``fx`` across and ``fy`` down panel ``index`` of ``count``, placed at STRUCTURE_PX."""
    from engine.hd2d.settings import PIXELS_PER_METRE

    total = count * WIDTH + (count - 1) * GAP
    x0 = -total / 2 + index * (WIDTH + GAP)
    return (STRUCTURE_PX[0] / PIXELS_PER_METRE + x0 + fx * WIDTH, STRUCTURE_PX[1] / PIXELS_PER_METRE,
            (1.0 - fy) * HEIGHT)


def panel_points(index: int, count: int = len(SWATCHES)) -> dict[str, tuple[float, float, float]]:
    """World points (m) on panel ``index``: its middle, and the middles of its texture's four quarters (texel
    row-major: "t0" top left ... "t3" bottom right), placed at STRUCTURE_PX on the ground."""
    from engine.hd2d.settings import PIXELS_PER_METRE

    total = count * WIDTH + (count - 1) * GAP
    x0 = -total / 2 + index * (WIDTH + GAP)
    cx, cy = STRUCTURE_PX[0] / PIXELS_PER_METRE, STRUCTURE_PX[1] / PIXELS_PER_METRE

    def at(u: float, v: float) -> tuple[float, float, float]:  # glTF (x, y, 0) -> Mesh (x, 0, y), then placed
        return (cx + x0 + u * WIDTH, cy, (1.0 - v) * HEIGHT)

    return {"middle": at(0.5, 0.5), "t0": at(0.25, 0.25), "t1": at(0.75, 0.25), "t2": at(0.25, 0.75),
            "t3": at(0.75, 0.75)}


def pixel_at(image: Image.Image, vp: list[list[float]], point: tuple[float, float, float]) -> tuple[int, int, int]:
    """The frame's pixel where ``point`` (m) is drawn (``vp``: the renderer's view-projection, row-major)."""
    x, y, z = point
    clip = [vp[r][0] * x + vp[r][1] * y + vp[r][2] * z + vp[r][3] for r in range(4)]
    w, h = image.size
    px = int((clip[0] / clip[3] * 0.5 + 0.5) * w)
    py = int((1.0 - (clip[1] / clip[3] * 0.5 + 0.5)) * h)
    pixels: Any = image.convert("RGB").load()
    r, g, b = pixels[px, py][:3]
    return r, g, b


def place(project: Path, model: str, *, sun: str = "noon", lamp: dict | None = None) -> None:
    """The start room: the panels at STRUCTURE_PX, the player behind them, the camera looking at their faces."""
    from engine import project_ops as ops

    path = project / SCENE
    scene = json.loads(path.read_text(encoding="utf-8"))
    hd = scene["settings"]["hd2d"]
    hd["structures"] = [{"id": "swatches", "model": model, "x": STRUCTURE_PX[0], "y": STRUCTURE_PX[1]}]
    hd["camera"] = {"pitch": 15, "fov": 30, "distance": 18, "follow": "player"}
    player = next(e for e in scene["entities"] if e.get("prefab_id") == "player")
    player["x"], player["y"] = STRUCTURE_PX[0], STRUCTURE_PX[1] + 96.0  # 3 m north: behind the panels
    scene["entities"] = [player]
    scene["lights"] = [lamp] if lamp else []
    scene = ops.set_hd2d_sun(scene, preset=sun)
    path.write_text(json.dumps(scene, indent=2), encoding="utf-8")


def read_panels(game: Any) -> dict[str, dict[str, tuple[int, int, int]]]:
    """Every panel's pixels (its middle and texture quarters) in a frame of the game, as drawn."""
    image = game.draw()
    vp = game.window.hd2d_renderer.last_vp
    return {name: {k: pixel_at(image, vp, p) for k, p in panel_points(i).items()}
            for i, (name, *_rest) in enumerate(SWATCHES)}


def check(folder: Path) -> dict[str, Any]:
    import hd2d_demo

    from engine.hd2d import catalog, glb

    folder.mkdir(parents=True, exist_ok=False)
    source = swatches_glb(folder / "swatches.glb")
    project = hd2d_demo.build(folder / "game")
    asset = catalog.import_model(project, source, name="swatches")
    report: dict[str, Any] = {"model": asset.model, "report": glb.inspect_glb(project / asset.model)[1].lines()}
    lamp = {"type": "point", "x": STRUCTURE_PX[0], "y": STRUCTURE_PX[1] - 48.0, "radius": 160, "color": [255, 200, 120],
            "elevation": 32, "enabled": True}
    game = hd2d_demo.HiddenGame(project, size=(960, 540))
    try:
        for label, sun, light in (("noon", "noon", None), ("night", "night", None), ("night_lamp_on", "night", lamp),
                                  ("night_lamp_off", "night", {**lamp, "enabled": False})):
            place(project, asset.model, sun=sun, lamp=light)
            game.load(SCENE)
            game.step(30)
            report[label] = read_panels(game)
        # reimport: the same file with factor_only's emission changed (blue), every copy updated
        changed = tuple((n, b, [0.0, 0.25, 1.0] if n == "factor_only" else f, t, s) for n, b, f, t, s in SWATCHES)
        swatches_glb(folder / "swatches_v2.glb", changed)
        catalog.reimport_model(project, asset.id, folder / "swatches_v2.glb")
        place(project, asset.model, sun="night")
        game.load(SCENE)
        game.step(30)
        report["reimported"] = read_panels(game)
        # texture sampling: wrap modes per axis, and a Linear emission texture (imported as exported: not sharpened)
        sampling = catalog.import_model(project, sampling_glb(folder / "sampling.glb"), name="sampling",
                                        pixels="as exported")
        report["sampling_report"] = glb.inspect_glb(project / sampling.model)[1].lines()
        place(project, sampling.model, sun="night")
        game.load(SCENE)
        game.step(30)
        image, vp = game.draw(), game.window.hd2d_renderer.last_vp
        count = len(SAMPLING)
        report["sampling"] = {
            name: {f"{fx},{fy}": pixel_at(image, vp, panel_at(i, count, fx, fy))
                   for fx in (LINEAR_AT if span == 1.0 else GRID) for fy in ((0.5,) if span == 1.0 else GRID)}
            for i, ((name, *_r), span) in enumerate(SAMPLING)}
        place(project, asset.model, sun="night")  # (the panels again, for Studio)
    finally:
        game.close()
    # Mesh Studio's edit view draws it too; an edit saved with Ctrl+S, the project reopened: still glowing.
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops

    d = StudioDriver(project)
    try:
        report["studio"] = studio_panels(d)
        d.studio._edit(lambda s: ops.set_hd2d_sun(s, preset="evening"), "Evening.")
        d.key(d.arcade.key.S, d.arcade.key.MOD_CTRL)
        saved = json.loads((project / SCENE).read_text(encoding="utf-8"))
        report["studio_saved_evening"] = saved["settings"]["hd2d"]["sun"] == ops.set_hd2d_sun(
            saved, preset="evening")["settings"]["hd2d"]["sun"] and not d.studio.project.is_dirty
    finally:
        d.close()
    d = StudioDriver(project)
    try:
        report["studio_reopened"] = studio_panels(d)
    finally:
        d.close()
    return report


def studio_panels(d: Any) -> dict[str, dict[str, tuple[int, int, int]]]:
    """Every panel's pixels in Mesh Studio's 3D view (its edit camera)."""
    image = d.frame().convert("RGB")
    pixels: Any = image.load()
    out: dict[str, dict[str, tuple[int, int, int]]] = {}
    for i, (name, *_rest) in enumerate(SWATCHES):
        out[name] = {}
        for k, p in panel_points(i).items():
            sx, sy = d.screen(p)
            r, g, b = pixels[int(sx), int(image.height - sy)][:3]
            out[name][k] = (r, g, b)
    return out


if __name__ == "__main__":
    print(json.dumps(check(Path(sys.argv[1])), indent=1))
