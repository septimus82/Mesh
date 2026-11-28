"""Milestone 16 Stage 1: the HD-2D lab reads a Blender-exported GLB (tooling/hd2d_lab/assets/stone_outpost.glb,
built by tooling/hd2d_lab/blender_build.py) into Z-up geometry with its pixel-art textures and samplers. The lab is
isolated: nothing in the engine imports it."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast
np = pytest.importorskip("numpy")  # the lab needs numpy; Mesh itself doesn't declare it

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
GLB = REPO / "tooling" / "hd2d_lab" / "assets" / "stone_outpost.glb"


def test_the_blender_glb_loads_as_z_up_modular_geometry() -> None:
    from hd2d_lab.gltf import load_glb

    scene = load_glb(GLB)
    assert {p.node for p in scene.primitives} == {"platform", "step_0", "step_1", "step_2", "hut", "roof"}
    lo, hi = scene.bounds()
    # As built in Blender (Z up): x -2..2, the steps reach y -2.2, the roof's overhang y 2.1, height 0..4.2 m.
    assert lo == pytest.approx([-2.0, -2.2, 0.0], abs=1e-4) and hi == pytest.approx([2.0, 2.1, 4.2], abs=1e-4)
    for prim in scene.primitives:
        assert len(prim.indices) % 3 == 0 and prim.indices.max() < len(prim.positions)
        assert np.allclose(np.linalg.norm(prim.normals, axis=1), 1.0, atol=1e-4)
        assert prim.material.image is not None and prim.material.image.size == (32, 32)
        assert prim.material.nearest and prim.material.repeat, "Blender's 'Closest' became a NEAREST, repeating sampler"
    tops = [p for p in scene.primitives if p.material.name == "stone_top"]
    assert tops and all(np.allclose(p.normals, [0, 0, 1], atol=1e-4) for p in tops), "upward faces point up (+z)"


def test_a_file_that_isnt_a_glb_is_refused(tmp_path: Path) -> None:
    from hd2d_lab.gltf import load_glb

    bad = tmp_path / "x.glb"
    bad.write_bytes(b"not a glb at all")
    with pytest.raises(ValueError):
        load_glb(bad)


def test_the_engine_never_imports_the_lab() -> None:
    offenders = [p.relative_to(REPO).as_posix() for p in (REPO / "engine").rglob("*.py")
                 if "hd2d_lab" in p.read_text(encoding="utf-8", errors="ignore")]
    assert offenders == []
