"""Reading static structures from glTF 2.0 binary (GLB) files, as Blender exports them. Pure Python (no NumPy).

The supported subset, proven in Milestone 16 Stage 1: nodes with translation / rotation / scale or a matrix (and
children), triangle primitives with POSITION, NORMAL, TEXCOORD_0 and indices, materials with a base-colour texture
embedded in the GLB (PNG), and samplers (NEAREST for pixel art, REPEAT / CLAMP_TO_EDGE). glTF's Y-up becomes Mesh's
Z-up: (x, y, z) -> (x, -z, y), so x is east, y north and z height, in metres.

Collision is authored in Blender, never guessed from the picture: an object with the custom property
``mesh_collision`` (exported as the node's ``extras``) is collision only and never drawn. Its kind:

- ``"solid"``: walkable on its upward faces and solid underneath (a platform, terrain, stairs as one ramp);
- ``"floor"``: walkable on its upward faces and open underneath (a bridge deck: you can walk under it);
- ``"wall"``: blocks a body within its box (a hut, a railing, a pillar).

Anything else is refused with a ``GlbError`` that says what and where (skins, animation, morph targets, external
.bin or image files, non-triangle primitives, missing positions, unknown accessors), never silently skipped.
"""

from __future__ import annotations

import io
import json
import math
import struct
from array import array
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

GL_NEAREST, GL_CLAMP_TO_EDGE = 9728, 33071
_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
_FORMATS = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}
_SIZES = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
Matrix = list[list[float]]


class GlbError(ValueError):
    """A GLB file that can't be used as an HD-2D structure; the message names the file and the problem."""


@dataclass
class Material:
    name: str
    image: Image.Image | None
    nearest: bool = True
    repeat: bool = True


@dataclass
class Part:
    """One material's triangles of one node, in the model's own space (Z-up metres): interleaved position (3),
    normal (3) and uv (2) floats, and indices."""

    node: str
    material: Material
    vertices: array  # 'f', 8 per vertex
    indices: array  # 'I'

    @property
    def vertex_count(self) -> int:
        return len(self.vertices) // 8


COLLISION_KINDS = ("solid", "floor", "wall")
Triangle = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]


@dataclass
class Collider:
    """A collision-only node, in the model's own space (Z-up metres): its triangles (for solid and floor, the
    upward-facing ones: the walkable surface) and its box (lo, hi)."""

    node: str
    kind: str
    triangles: list[Triangle]
    lo: tuple[float, float, float]
    hi: tuple[float, float, float]


@dataclass
class Model:
    path: Path
    parts: list[Part] = field(default_factory=list)
    colliders: list[Collider] = field(default_factory=list)

    def bounds(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        lo, hi = [math.inf] * 3, [-math.inf] * 3
        for part in self.parts:
            v = part.vertices
            for i in range(0, len(v), 8):
                for k in range(3):
                    lo[k], hi[k] = min(lo[k], v[i + k]), max(hi[k], v[i + k])
        return (lo[0], lo[1], lo[2]), (hi[0], hi[1], hi[2])


def _mul(a: Matrix, b: Matrix) -> Matrix:
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _node_matrix(node: dict) -> Matrix:
    if "matrix" in node:
        m = node["matrix"]  # column-major
        return [[float(m[c * 4 + r]) for c in range(4)] for r in range(4)]
    tx, ty, tz = node.get("translation", [0, 0, 0])
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    sx, sy, sz = node.get("scale", [1, 1, 1])
    r = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [[r[0][0] * sx, r[0][1] * sy, r[0][2] * sz, tx], [r[1][0] * sx, r[1][1] * sy, r[1][2] * sz, ty],
            [r[2][0] * sx, r[2][1] * sy, r[2][2] * sz, tz], [0.0, 0.0, 0.0, 1.0]]


Y_UP_TO_Z_UP: Matrix = [[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, -1.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]]


def _normal_matrix(m: Matrix) -> Matrix:
    """The inverse transpose of the upper 3 x 3 (normals under non-uniform scale)."""
    a = [row[:3] for row in m[:3]]
    det = (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
           + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    if abs(det) < 1e-12:
        return a
    cof = [[(a[(i + 1) % 3][(j + 1) % 3] * a[(i + 2) % 3][(j + 2) % 3]
             - a[(i + 1) % 3][(j + 2) % 3] * a[(i + 2) % 3][(j + 1) % 3]) / det for j in range(3)] for i in range(3)]
    return cof  # (inverse)^T == cofactor / det


class _Reader:
    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise GlbError(f"{path}: can't be read ({exc.strerror or exc})") from exc
        if len(data) < 12 or data[:4] != b"glTF":
            raise GlbError(f"{path}: not a GLB file (export from Blender as glTF Binary, .glb)")
        version, length = struct.unpack_from("<II", data, 4)
        if version != 2:
            raise GlbError(f"{path}: glTF version {version}; Mesh reads glTF 2.0")
        self.doc: dict | None = None
        self.bin = b""
        offset = 12
        while offset + 8 <= min(length, len(data)):
            size, kind = struct.unpack_from("<I4s", data, offset)
            chunk = data[offset + 8: offset + 8 + size]
            if kind == b"JSON":
                self.doc = json.loads(chunk)
            elif kind == b"BIN\x00":
                self.bin = chunk
            offset += 8 + size
        if self.doc is None:
            raise GlbError(f"{path}: no JSON chunk")
        for unsupported in ("skins", "animations"):
            if self.doc.get(unsupported):
                raise GlbError(f"{path}: has {unsupported}; HD-2D structures are static meshes (export without "
                               f"armatures/animation)")

    def fail(self, what: str) -> GlbError:
        return GlbError(f"{self.path}: {what}")

    def accessor(self, index: int, want: str | None = None) -> list[Any]:
        doc = self.doc or {}
        try:
            acc = doc["accessors"][index]
            view = doc["bufferViews"][acc["bufferView"]]
        except (KeyError, IndexError, TypeError) as exc:
            raise self.fail(f"accessor {index} is missing or has no bufferView") from exc
        if view.get("buffer", 0) != 0 or doc.get("buffers", [{}])[0].get("uri"):
            raise self.fail("uses an external .bin buffer; export as GLB so everything is in one file")
        if want and acc["type"] != want:
            raise self.fail(f"accessor {index} is {acc['type']}, expected {want}")
        fmt, size, comps = _FORMATS[acc["componentType"]], _SIZES[acc["componentType"]], _COMPONENTS[acc["type"]]
        start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = view.get("byteStride") or size * comps
        count = acc["count"]
        if start + stride * (count - 1) + size * comps > len(self.bin):
            raise self.fail(f"accessor {index} runs past the end of the binary chunk")
        values: list[Any] = []
        for i in range(count):
            row = struct.unpack_from(f"<{comps}{fmt}", self.bin, start + i * stride)
            values.append(row if comps > 1 else row[0])
        if acc.get("normalized"):
            top = float((1 << (8 * size - (0 if fmt.isupper() else 1))) - 1)
            values = [tuple(v / top for v in row) if comps > 1 else row / top for row in values]
        return values

    def materials(self) -> list[Material]:
        doc = self.doc or {}
        images: list[Image.Image] = []
        for i, img in enumerate(doc.get("images", [])):
            if "bufferView" not in img:
                raise self.fail(f"image {i} ({img.get('uri', '?')}) is an external file; export with images "
                                f"embedded (glTF Binary)")
            view = doc["bufferViews"][img["bufferView"]]
            raw = self.bin[view.get("byteOffset", 0): view.get("byteOffset", 0) + view["byteLength"]]
            try:
                with Image.open(io.BytesIO(raw)) as decoded:
                    images.append(decoded.convert("RGBA"))
            except OSError as exc:
                raise self.fail(f"image {i} can't be decoded ({exc})") from exc
        out: list[Material] = []
        for mat in doc.get("materials", []):
            pbr = mat.get("pbrMetallicRoughness", {})
            ref = pbr.get("baseColorTexture")
            image, nearest, repeat = None, True, True
            if ref is not None:
                tex = doc["textures"][ref["index"]]
                image = images[tex["source"]] if "source" in tex else None
                sampler = doc.get("samplers", [{}])[tex["sampler"]] if "sampler" in tex else {}
                nearest = sampler.get("magFilter", GL_NEAREST) == GL_NEAREST
                repeat = GL_CLAMP_TO_EDGE not in (sampler.get("wrapS"), sampler.get("wrapT"))
            elif isinstance(pbr.get("baseColorFactor"), list) and len(pbr["baseColorFactor"]) == 4:
                # A flat Blender colour (no texture): one texel of it, so it isn't drawn grey.
                r, g, b, a = (min(max(float(c), 0.0), 1.0) for c in pbr["baseColorFactor"])
                image = Image.new("RGBA", (1, 1), _srgb_byte(r, g, b, a))
            out.append(Material(str(mat.get("name", f"material{len(out)}")), image, nearest, repeat))
        return out or [Material("default", None)]


def _srgb_byte(r: float, g: float, b: float, a: float) -> tuple[int, int, int, int]:
    """glTF's linear base colour as the sRGB bytes a texture would hold (alpha stays linear)."""
    def enc(c: float) -> int:
        return round(255 * (12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055))

    return enc(r), enc(g), enc(b), round(255 * a)


def _transform(m: Matrix, p: tuple[float, ...]) -> tuple[float, float, float]:
    x, y, z = p
    return (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3], m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
            m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3])


def _collider(reader: _Reader, doc: dict, node: dict, index: int, world: Matrix, kind: Any) -> Collider:
    name = str(node.get("name", index))
    if kind not in COLLISION_KINDS:
        raise reader.fail(f"node '{name}': mesh_collision must be one of {', '.join(COLLISION_KINDS)} (got {kind!r})")
    points: list[tuple[float, float, float]] = []
    triangles: list[Triangle] = []
    for prim in doc["meshes"][node["mesh"]]["primitives"]:
        if prim.get("mode", 4) != 4 or "POSITION" not in prim.get("attributes", {}):
            raise reader.fail(f"collider '{name}' must be triangles with positions")
        pos = [_transform(world, p) for p in reader.accessor(prim["attributes"]["POSITION"], "VEC3")]
        idx = reader.accessor(prim["indices"], "SCALAR") if "indices" in prim else list(range(len(pos)))
        if idx and max(idx) >= len(pos):
            raise reader.fail(f"collider '{name}' has an index past its {len(pos)} vertices")
        points.extend(pos)
        for i in range(0, len(idx) - 2, 3):
            a, b, c = pos[idx[i]], pos[idx[i + 1]], pos[idx[i + 2]]
            u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            if kind != "wall" and n[2] >= 0.5 * (math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0):
                triangles.append((a, b, c))  # walkable: faces up (slopes to 60 degrees)
    if not points:
        raise reader.fail(f"collider '{name}' has no geometry")
    if kind != "wall" and not triangles:
        raise reader.fail(f"collider '{name}' ({kind}) has no upward-facing faces to walk on")
    lo = (min(p[0] for p in points), min(p[1] for p in points), min(p[2] for p in points))
    hi = (max(p[0] for p in points), max(p[1] for p in points), max(p[2] for p in points))
    return Collider(name, kind, triangles, lo, hi)


def model_problem(root: str | Path, model: str) -> str | None:
    """Why ``model`` can't be placed as a structure, or None: it must be a project-relative path inside the project
    (``engine.hd2d.settings.asset_path``; and, symlinks followed, still inside it), an existing .glb, and usable."""
    from engine.hd2d.settings import Hd2dSettingsError, asset_path  # noqa: PLC0415

    try:
        rel = asset_path(model, "The model")
    except Hd2dSettingsError as err:
        return str(err)
    if not contained(root, rel):
        return f"The model '{model}' lies outside the project (a link out of it); copy the file into the project."
    path = Path(root) / rel
    if not rel.lower().endswith(".glb") or not path.is_file():
        return f"There is no model '{model}' in the project (a .glb file, as Blender exports it)."
    try:
        load_glb(path)
    except GlbError as err:
        return str(err)
    return None


def contained(root: str | Path, rel: str) -> bool:
    """Whether ``root / rel``, every link followed, is still inside ``root``."""
    base = Path(root).resolve()
    target = (base / rel).resolve()
    return target == base or base in target.parents


def load_glb(path: str | Path) -> Model:
    """A GLB file as a Model (Z-up metres). Raises GlbError, naming the file and the problem."""
    reader = _Reader(Path(path))
    doc = reader.doc or {}
    materials = reader.materials()
    model = Model(Path(path))

    def visit(index: int, parent: Matrix, depth: int) -> None:
        if depth > 64:
            raise reader.fail("node hierarchy too deep (a cycle?)")
        node = doc["nodes"][index]
        world = _mul(parent, _node_matrix(node))
        kind = (node.get("extras") or {}).get("mesh_collision") if isinstance(node.get("extras"), dict) else None
        if kind is not None and "mesh" in node:
            model.colliders.append(_collider(reader, doc, node, index, world, kind))
        elif "mesh" in node:
            nmat = _normal_matrix(world)
            for p, prim in enumerate(doc["meshes"][node["mesh"]]["primitives"]):
                where = f"node '{node.get('name', index)}' primitive {p}"
                if prim.get("mode", 4) != 4:
                    raise reader.fail(f"{where} isn't triangles (mode {prim.get('mode')})")
                if prim.get("targets"):
                    raise reader.fail(f"{where} has morph targets (shape keys); apply them before exporting")
                attrs = prim.get("attributes", {})
                if "POSITION" not in attrs:
                    raise reader.fail(f"{where} has no POSITION")
                pos = reader.accessor(attrs["POSITION"], "VEC3")
                nrm = reader.accessor(attrs["NORMAL"], "VEC3") if "NORMAL" in attrs else [(0.0, 1.0, 0.0)] * len(pos)
                uvs = reader.accessor(attrs["TEXCOORD_0"], "VEC2") if "TEXCOORD_0" in attrs else [(0.0, 0.0)] * len(pos)
                idx = reader.accessor(prim["indices"], "SCALAR") if "indices" in prim else list(range(len(pos)))
                if idx and max(idx) >= len(pos):
                    raise reader.fail(f"{where} has an index past its {len(pos)} vertices")
                verts = array("f")
                for (px, py, pz), (nx, ny, nz), (u, v) in zip(pos, nrm, uvs):
                    w = [sum(world[r][c] * q for c, q in enumerate((px, py, pz, 1.0))) for r in range(3)]
                    n = [sum(nmat[r][c] * q for c, q in enumerate((nx, ny, nz))) for r in range(3)]
                    length = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
                    verts.extend((w[0], w[1], w[2], n[0] / length, n[1] / length, n[2] / length, u, v))
                material = materials[prim.get("material", 0)] if materials else Material("default", None)
                model.parts.append(Part(str(node.get("name", index)), material, verts, array("I", idx)))
        for child in node.get("children", []):
            visit(child, world, depth + 1)

    roots = doc["scenes"][doc.get("scene", 0)]["nodes"] if doc.get("scenes") else range(len(doc.get("nodes", [])))
    for root in roots:
        visit(root, Y_UP_TO_Z_UP, 0)
    if not model.parts:
        raise reader.fail("contains no meshes")
    return model


# ---------------------------------------------------------------------------------------------- importing (Stage 5B)
GL_LINEAR = 9729
_HARMLESS_EXTENSIONS = ("KHR_materials_",)  # PBR extras Blender writes; Mesh's lighting doesn't use them


def split_glb(data: bytes) -> tuple[dict, bytes]:
    """A GLB's JSON document and binary chunk. Raises GlbError if it isn't a GLB."""
    if len(data) < 20 or data[:4] != b"glTF":
        raise GlbError("not a GLB file (export from Blender as glTF Binary, .glb)")
    doc, binary, offset = None, b"", 12
    while offset + 8 <= len(data):
        size, kind = struct.unpack_from("<I4s", data, offset)
        chunk = data[offset + 8: offset + 8 + size]
        if kind == b"JSON":
            doc = json.loads(chunk)
        elif kind == b"BIN\x00":
            binary = chunk
        offset += 8 + size
    if not isinstance(doc, dict):
        raise GlbError("the GLB has no JSON chunk")
    return doc, binary


def join_glb(doc: dict, binary: bytes) -> bytes:
    """A GLB from its JSON document and binary chunk (each padded to 4 bytes, as glTF requires)."""
    text = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    chunks = struct.pack("<I4s", len(text), b"JSON") + text
    if binary:
        binary += b"\0" * (-len(binary) % 4)
        chunks += struct.pack("<I4s", len(binary), b"BIN\x00") + binary
    return struct.pack("<4sII", b"glTF", 2, 12 + len(chunks)) + chunks


def sharpen_textures(data: bytes) -> tuple[bytes, list[str]]:
    """``data`` with every material texture sampled NEAREST (pixel art stays sharp), and the names of the materials
    whose texture was smooth (Blender's default "Linear" interpolation). Only the JSON chunk changes."""
    doc, binary = split_glb(data)
    samplers = doc.setdefault("samplers", [])
    textures = doc.get("textures", [])
    changed: list[str] = []
    for mat in doc.get("materials", []):
        ref = (mat.get("pbrMetallicRoughness") or {}).get("baseColorTexture")
        if not isinstance(ref, dict) or not 0 <= ref.get("index", -1) < len(textures):
            continue
        tex = textures[ref["index"]]
        sampler = samplers[tex["sampler"]] if isinstance(tex.get("sampler"), int) and tex["sampler"] < len(samplers) else {}
        if sampler.get("magFilter", GL_NEAREST) == GL_NEAREST:  # what the renderer goes by (it has no mipmaps)
            continue
        sharp = {**sampler, "magFilter": GL_NEAREST, "minFilter": GL_NEAREST}
        if sharp not in samplers:
            samplers.append(sharp)
        tex["sampler"] = samplers.index(sharp)
        changed.append(str(mat.get("name", "material")))
    return (join_glb(doc, binary) if changed else data), changed


@dataclass
class Report:
    """What a GLB holds, for a person deciding whether to import it: facts, plus warnings (it works, but...)."""

    triangles: int
    parts: int
    size_m: tuple[float, float, float]
    materials: list[tuple[str, tuple[int, int] | None, bool]]  # (name, texture size or None, sharp)
    colliders: list[tuple[str, str]]  # (node, kind)
    warnings: list[str] = field(default_factory=list)

    @property
    def collision(self) -> dict[str, int]:
        return {kind: sum(1 for _n, k in self.colliders if k == kind) for kind in COLLISION_KINDS}

    @property
    def floors(self) -> list[str]:
        """The walkable colliders' node names: each placed copy's floors are ``<structure id>/<name>``."""
        return [name for name, kind in self.colliders if kind != "wall"]

    def lines(self) -> list[str]:
        x, y, z = self.size_m
        out = [f"{x:.1f} x {y:.1f} m, {z:.1f} m high; {self.triangles} triangles in {self.parts} part(s)."]
        textured = [f"{name} ({s[0]}x{s[1]}{'' if sharp else ', smooth'})" for name, s, sharp in self.materials if s]
        flat = [name for name, s, _sharp in self.materials if s is None]
        if textured:
            out.append("Textures: " + ", ".join(textured) + ".")
        if flat:
            out.append("Flat colour: " + ", ".join(flat) + ".")
        counts = self.collision
        if self.colliders:
            out.append("Collision: " + ", ".join(f"{n} {kind}" for kind, n in counts.items() if n) + ".")
        else:
            out.append("No collision: characters walk through it (add mesh_collision objects in Blender).")
        return out + self.warnings


def inspect_glb(path: str | Path) -> tuple[Model, Report]:
    """Read ``path`` as the game will (``load_glb``; raises GlbError) and report on it."""
    model = load_glb(path)
    doc, _binary = split_glb(Path(path).read_bytes())
    lo, hi = model.bounds()
    seen: dict[str, Material] = {}
    for part in model.parts:
        seen.setdefault(part.material.name, part.material)
    materials = [(m.name, None if m.image is None or m.image.size == (1, 1) else m.image.size, m.nearest)
                 for m in seen.values()]
    warnings: list[str] = []
    smooth = [name for name, size, sharp in materials if size and not sharp]
    if smooth:
        warnings.append(f"Smooth (Linear) texture filtering on {', '.join(smooth)}: pixel art will blur. Keep pixels "
                        f"sharp fixes the copy; in Blender, set the Image Texture node to Closest.")
    big = [name for name, size, _s in materials if size and max(size) > 1024]
    if big:
        warnings.append(f"Large textures ({', '.join(big)}): HD-2D pixel art is usually 16-256 px per surface.")
    required = [e for e in doc.get("extensionsRequired", []) if not e.startswith(_HARMLESS_EXTENSIONS)]
    if required:
        raise GlbError(f"{path}: needs glTF extension(s) Mesh doesn't read: {', '.join(required)} (turn off "
                       f"compression such as Draco when exporting)")
    if "KHR_texture_transform" in doc.get("extensionsUsed", []):
        warnings.append("Uses texture transforms (UV offset/scale in the material): Mesh ignores them; apply them "
                        "to the UVs instead.")
    ignored = [(key, len(doc.get(key, []))) for key in ("cameras",) if doc.get(key)]
    lights = len(((doc.get("extensions") or {}).get("KHR_lights_punctual") or {}).get("lights", []))
    if lights:
        ignored.append(("lights", lights))
    if ignored:
        warnings.append("Ignored: " + ", ".join(f"{n} {key}" for key, n in ignored) + " (Mesh lights and frames "
                        "rooms itself; add lamps in Mesh Studio).")
    if any("COLOR_0" in prim.get("attributes", {}) for mesh in doc.get("meshes", []) for prim in mesh.get("primitives", [])):
        warnings.append("Vertex colours are ignored: paint them into a texture.")
    size = (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
    if max(size) > 200:
        warnings.append(f"It is {max(size):.0f} m across: check Blender's unit scale (Mesh reads metres).")
    report = Report(sum(len(p.indices) // 3 for p in model.parts), len(model.parts), size, materials,
                    [(c.node, c.kind) for c in model.colliders], warnings)
    return model, report
