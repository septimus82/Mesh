"""Milestone 16 Stage 2: the engine's GLB reader (engine.hd2d.glb, pure Python: no NumPy) reads Blender's static
structures and refuses what it can't use with an error naming the file and the problem."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from engine.hd2d.glb import GlbError, load_glb

pytestmark = pytest.mark.fast

REPO = Path(__file__).resolve().parents[1]
GLB = REPO / "tooling" / "hd2d_lab" / "assets" / "stone_outpost.glb"


def _glb(doc: dict, binary: bytes = b"", version: int = 2) -> bytes:
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    binary += b"\0" * (-len(binary) % 4)
    chunks = struct.pack("<I4s", len(js), b"JSON") + js + (struct.pack("<I4s", len(binary), b"BIN\0") + binary if binary else b"")
    return b"glTF" + struct.pack("<II", version, 12 + len(chunks)) + chunks


def _triangle(**prim_extra: object) -> tuple[dict, bytes]:
    """One triangle (positions + indices) in a GLB document."""
    pos = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    idx = struct.pack("<3H", 0, 1, 2) + b"\0\0"
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
           "nodes": [{"name": "tri", "mesh": 0}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, **prim_extra}]}],
           "buffers": [{"byteLength": len(pos) + len(idx)}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(pos)},
                           {"buffer": 0, "byteOffset": len(pos), "byteLength": 6}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
                         {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"}]}
    return doc, pos + idx


def test_the_blender_outpost_loads_z_up_with_its_pixel_textures() -> None:
    model = load_glb(GLB)
    assert {p.node for p in model.parts} == {"platform", "step_0", "step_1", "step_2", "hut", "roof"}
    lo, hi = model.bounds()
    # As built in Blender (Z up): x -2..2, the steps reach y -2.2, the roof's overhang y 2.1, height 0..4.2 m.
    assert lo == pytest.approx((-2.0, -2.2, 0.0), abs=1e-4) and hi == pytest.approx((2.0, 2.1, 4.2), abs=1e-4)
    for part in model.parts:
        assert len(part.vertices) % 8 == 0 and len(part.indices) % 3 == 0
        assert max(part.indices) < part.vertex_count
        assert part.material.image is not None and part.material.nearest, "pixel art: an embedded NEAREST texture"
        v = part.vertices
        for i in range(0, len(v), 8):
            assert abs(v[i + 3] ** 2 + v[i + 4] ** 2 + v[i + 5] ** 2 - 1.0) < 1e-4, "unit normals"


def test_a_minimal_glb_triangle_converts_y_up_to_z_up(tmp_path: Path) -> None:
    doc, binary = _triangle()
    path = tmp_path / "tri.glb"
    path.write_bytes(_glb(doc, binary))
    part = load_glb(path).parts[0]
    assert part.node == "tri" and list(part.indices) == [0, 1, 2]
    # glTF (x, y, z) -> Mesh (x, -z, y): glTF's up (0, 1, 0) is Mesh's height (z)
    assert tuple(part.vertices[16:19]) == (0.0, 0.0, 1.0)


@pytest.mark.parametrize(("change", "message"), [
    (lambda d, b: (d | {"skins": [{"joints": [0]}]}, b), "has skins"),
    (lambda d, b: (d | {"animations": [{"channels": []}]}, b), "has animations"),
    (lambda d, b: ({**d, "buffers": [{"byteLength": 1, "uri": "outpost.bin"}]}, b), "external .bin"),
    (lambda d, b: (_with_prim(d, mode=1), b), "isn't triangles"),
    (lambda d, b: (_with_prim(d, targets=[{"POSITION": 0}]), b), "morph targets"),
    (lambda d, b: (_with_prim(d, attributes={}), b), "no POSITION"),
    (lambda d, b: (d, b[:36] + struct.pack("<3H", 0, 1, 7) + b"\0\0"), "index past"),
    (lambda d, b: (d, b[:20]), "runs past the end"),
    (lambda d, b: ({**d, "images": [{"uri": "stone.png"}]}, b), "external file"),
    (lambda d, b: ({**d, "nodes": [{"name": "empty"}]}, b), "contains no meshes"),
])
def test_unusable_glbs_are_refused_naming_the_problem(tmp_path: Path, change, message: str) -> None:
    doc, binary = change(*_triangle())
    path = tmp_path / "bad.glb"
    path.write_bytes(_glb(doc, binary))
    with pytest.raises(GlbError, match=message) as caught:
        load_glb(path)
    assert "bad.glb" in str(caught.value), "the error names the file"


def _with_prim(doc: dict, **changes: object) -> dict:
    doc = json.loads(json.dumps(doc))
    doc["meshes"][0]["primitives"][0].update(changes)
    return doc


def test_not_a_glb_wrong_version_and_missing_files_are_refused(tmp_path: Path) -> None:
    (tmp_path / "a.glb").write_bytes(b"PNG not a model")
    with pytest.raises(GlbError, match="not a GLB file"):
        load_glb(tmp_path / "a.glb")
    (tmp_path / "v1.glb").write_bytes(_glb(_triangle()[0], version=1))
    with pytest.raises(GlbError, match="version 1"):
        load_glb(tmp_path / "v1.glb")
    with pytest.raises(GlbError, match="can't be read"):
        load_glb(tmp_path / "missing.glb")


def test_the_engine_reader_needs_no_numpy() -> None:
    source = (REPO / "engine" / "hd2d" / "glb.py").read_text(encoding="utf-8")
    assert "numpy" not in source.replace("no NumPy", "").replace("(no NumPy)", "")
