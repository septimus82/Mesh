"""Reading static structures from glTF 2.0 binary (GLB) files, as Blender exports them. Pure Python (no NumPy).

The supported subset, proven in Milestone 16 Stage 1: nodes with translation / rotation / scale or a matrix (and
children), triangle primitives with POSITION, NORMAL, TEXCOORD_0 and indices, materials with a base-colour texture
embedded in the GLB (PNG), and samplers (NEAREST for pixel art, REPEAT / CLAMP_TO_EDGE). glTF's Y-up becomes Mesh's
Z-up: (x, y, z) -> (x, -z, y), so x is east, y north and z height, in metres.

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


@dataclass
class Model:
    path: Path
    parts: list[Part] = field(default_factory=list)

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
            ref = mat.get("pbrMetallicRoughness", {}).get("baseColorTexture")
            image, nearest, repeat = None, True, True
            if ref is not None:
                tex = doc["textures"][ref["index"]]
                image = images[tex["source"]] if "source" in tex else None
                sampler = doc.get("samplers", [{}])[tex["sampler"]] if "sampler" in tex else {}
                nearest = sampler.get("magFilter", GL_NEAREST) == GL_NEAREST
                repeat = GL_CLAMP_TO_EDGE not in (sampler.get("wrapS"), sampler.get("wrapT"))
            out.append(Material(str(mat.get("name", f"material{len(out)}")), image, nearest, repeat))
        return out or [Material("default", None)]


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
        if "mesh" in node:
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
