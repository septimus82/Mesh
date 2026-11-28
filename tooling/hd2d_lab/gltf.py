"""A minimal glTF 2.0 binary (GLB) reader for static, textured meshes: enough for the HD-2D lab, nothing more.

Reads nodes (translation / rotation / scale or matrix, with children), triangle primitives (POSITION, NORMAL,
TEXCOORD_0, indices), base-colour textures (embedded PNG) and their samplers. Converts glTF's Y-up to Mesh's
Z-up: glTF (x, y, z) -> (x, -z, y), so x is east, y is north (Mesh's map y) and z is height.

Not supported (raises or ignores, documented): skins, animation, morph targets, external .bin/.png files (.gltf
text form), KHR extensions, vertex colours, non-triangle modes.
"""

from __future__ import annotations

import io
import json
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
_DTYPES = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
GL_NEAREST = 9728
GL_CLAMP_TO_EDGE = 33071
Y_UP_TO_Z_UP = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=np.float64)


@dataclass
class Material:
    name: str
    image: Image.Image | None
    nearest: bool = True  # magFilter NEAREST (pixel art); glTF's default sampler is linear
    repeat: bool = True  # wrapS/wrapT: glTF's default is REPEAT (UVs in metres tile the texture)


@dataclass
class Primitive:
    node: str
    positions: np.ndarray  # (n, 3) float32, Z-up world
    normals: np.ndarray  # (n, 3) float32
    uvs: np.ndarray  # (n, 2) float32, glTF convention (v down from the image's top)
    indices: np.ndarray  # (m,) uint32
    material: Material


@dataclass
class Scene:
    primitives: list[Primitive] = field(default_factory=list)

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        allp = np.concatenate([p.positions for p in self.primitives])
        return allp.min(axis=0), allp.max(axis=0)


def _chunks(data: bytes) -> tuple[dict, bytes]:
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2:
        raise ValueError("not a glTF 2.0 binary (GLB) file")
    offset, doc, binary = 12, None, b""
    while offset < length:
        size, kind = struct.unpack_from("<I4s", data, offset)
        chunk = data[offset + 8: offset + 8 + size]
        if kind == b"JSON":
            doc = json.loads(chunk)
        elif kind == b"BIN\x00":
            binary = chunk
        offset += 8 + size
    if doc is None:
        raise ValueError("GLB without a JSON chunk")
    return doc, binary


def _accessor(doc: dict, binary: bytes, index: int) -> np.ndarray:
    acc = doc["accessors"][index]
    view = doc["bufferViews"][acc["bufferView"]]
    if view.get("buffer", 0) != 0:
        raise ValueError("only the GLB's own binary buffer is supported")
    dtype = np.dtype(_DTYPES[acc["componentType"]])
    comps, count = _COMPONENTS[acc["type"]], acc["count"]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = view.get("byteStride", 0) or dtype.itemsize * comps
    rows = [np.frombuffer(binary, dtype=dtype, count=comps, offset=start + i * stride) for i in range(count)] \
        if stride != dtype.itemsize * comps else [np.frombuffer(binary, dtype=dtype, count=comps * count, offset=start)]
    out = np.concatenate(rows).reshape(count, comps) if comps > 1 else np.concatenate(rows)
    if acc.get("normalized"):
        out = out.astype(np.float32) / np.iinfo(np.dtype(dtype).type).max
    return out


def _node_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T  # glTF stores column-major
    t = np.eye(4)
    t[:3, 3] = node.get("translation", [0, 0, 0])
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    r = np.eye(4)
    r[:3, :3] = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                 [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                 [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    s = np.diag([*node.get("scale", [1, 1, 1]), 1.0])
    return t @ r @ s


def _materials(doc: dict, binary: bytes) -> list[Material]:
    images = []
    for img in doc.get("images", []):
        if "bufferView" not in img:
            raise ValueError("only images embedded in the GLB are supported")
        view = doc["bufferViews"][img["bufferView"]]
        raw = binary[view.get("byteOffset", 0): view.get("byteOffset", 0) + view["byteLength"]]
        images.append(Image.open(io.BytesIO(raw)).convert("RGBA"))
    out = []
    for mat in doc.get("materials", []):
        ref = mat.get("pbrMetallicRoughness", {}).get("baseColorTexture")
        image, nearest, repeat = None, True, True
        if ref is not None:
            tex = doc["textures"][ref["index"]]
            image = images[tex["source"]] if "source" in tex else None
            sampler = doc.get("samplers", [{}])[tex["sampler"]] if "sampler" in tex else {}
            nearest = sampler.get("magFilter") == GL_NEAREST
            repeat = GL_CLAMP_TO_EDGE not in (sampler.get("wrapS"), sampler.get("wrapT"))
        out.append(Material(mat.get("name", "material"), image, nearest, repeat))
    return out


def load_glb(path: str | Path) -> Scene:
    doc, binary = _chunks(Path(path).read_bytes())
    materials = _materials(doc, binary) or [Material("default", None)]
    scene = Scene()

    def visit(index: int, parent: np.ndarray) -> None:
        node = doc["nodes"][index]
        world = parent @ _node_matrix(node)
        if "mesh" in node:
            normal_matrix = np.linalg.inv(world[:3, :3]).T
            for prim in doc["meshes"][node["mesh"]]["primitives"]:
                if prim.get("mode", 4) != 4:
                    raise ValueError("only triangle primitives are supported")
                attrs = prim["attributes"]
                pos = _accessor(doc, binary, attrs["POSITION"]).astype(np.float64)
                pos = (np.c_[pos, np.ones(len(pos))] @ world.T)[:, :3]
                nrm = _accessor(doc, binary, attrs["NORMAL"]).astype(np.float64) @ normal_matrix.T \
                    if "NORMAL" in attrs else np.tile([0.0, 0.0, 1.0], (len(pos), 1))
                nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
                uv = _accessor(doc, binary, attrs["TEXCOORD_0"]) if "TEXCOORD_0" in attrs else np.zeros((len(pos), 2))
                idx = _accessor(doc, binary, prim["indices"]).astype(np.uint32) if "indices" in prim \
                    else np.arange(len(pos), dtype=np.uint32)
                scene.primitives.append(Primitive(node.get("name", f"node{index}"), pos.astype(np.float32),
                                                  nrm.astype(np.float32), uv.astype(np.float32), idx,
                                                  materials[prim.get("material", 0)]))
        for child in node.get("children", []):
            visit(child, world)

    roots = doc["scenes"][doc.get("scene", 0)]["nodes"] if doc.get("scenes") else range(len(doc["nodes"]))
    for root in roots:
        visit(root, Y_UP_TO_Z_UP)
    return scene
