"""M17-L3 E1: an imported model's glTF emission is read as glTF means it (``emissiveFactor``, ``emissiveTexture`` on
the first UV map, ``KHR_materials_emissive_strength``, the defaults), malformed emission is refused naming the
material, and what Mesh doesn't draw is said in the import report. Models without emission (every model Mesh ships)
read exactly as before. The pixels: tests/test_hd2d_emissive_gpu.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from engine.hd2d import glb
from engine.hd2d.glb import GlbError, inspect_glb, load_glb

pytestmark = pytest.mark.fast

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
import hd2d_emissive_demo as demo  # noqa: E402


def _materials(path: Path) -> dict[str, glb.Material]:
    return {p.material.name: p.material for p in load_glb(path).parts}


def _edited(tmp_path: Path, change, name: str = "edited.glb") -> Path:
    """The test panels' GLB with its JSON changed by ``change(doc)``."""
    doc, binary = glb.split_glb(demo.swatches_glb(tmp_path / "source.glb").read_bytes())
    change(doc)
    path = tmp_path / name
    path.write_bytes(glb.join_glb(doc, binary))
    return path


def _material(doc: dict, name: str) -> dict:
    return next(m for m in doc["materials"] if m["name"] == name)


def test_each_panels_emission_is_read_as_gltf_means(tmp_path: Path) -> None:
    m = _materials(demo.swatches_glb(tmp_path / "s.glb"))
    assert m["factor_only"].emissive == (1.0, 0.5, 0.25) and m["factor_only"].emissive_image is None
    textured = m["texture_only"]
    assert textured.emissive == (1.0, 1.0, 1.0) and textured.emissive_nearest
    assert textured.emissive_wrap == (glb.GL_REPEAT, glb.GL_REPEAT)
    assert textured.emissive_image is not None and list(textured.emissive_image.getdata()) == list(demo.TEXELS)
    assert m["factor_and_texture"].emissive == (0.5, 1.0, 0.25) and m["factor_and_texture"].emissive_image is not None
    assert m["lit_and_glowing"].emissive == (0.25, 0.1, 0.0)
    for name in ("zero_emission", "ordinary"):
        assert m[name].emissive == (0.0, 0.0, 0.0) and not m[name].glows and m[name].emissive_image is None
    assert m["zero_emission"].image.tobytes() == m["ordinary"].image.tobytes()  # (the base colour is untouched)
    assert all(m[n].glows for n in ("factor_only", "texture_only", "factor_and_texture", "lit_and_glowing"))


def test_a_texture_without_a_factor_gives_no_emission(tmp_path: Path) -> None:
    """glTF's emissiveFactor defaults to black: the texture alone emits nothing (it isn't even read)."""
    path = _edited(tmp_path, lambda doc: _material(doc, "texture_only").pop("emissiveFactor"))
    m = _materials(path)["texture_only"]
    assert not m.glows and m.emissive_image is None
    assert "texture_only" not in next(line for line in inspect_glb(path)[1].lines() if line.startswith("Glows"))


def test_emission_strength_multiplies_and_brighter_than_full_is_said(tmp_path: Path) -> None:
    def stronger(doc: dict) -> None:
        _material(doc, "factor_only")["extensions"] = {glb.EMISSIVE_STRENGTH: {"emissiveStrength": 3.0}}
        _material(doc, "lit_and_glowing")["extensions"] = {glb.EMISSIVE_STRENGTH: {"emissiveStrength": 2.0}}

    path = _edited(tmp_path, stronger)
    m = _materials(path)
    assert m["factor_only"].emissive == (3.0, 1.5, 0.75) and m["lit_and_glowing"].emissive == (0.5, 0.2, 0.0)
    lines = inspect_glb(path)[1].lines()
    assert any(line.startswith("factor_only's emission is brighter than full") and "no bloom" in line for line in lines)
    assert not any(line.startswith("lit_and_glowing's emission is brighter") for line in lines)
    assert not any(glb.EMISSIVE_STRENGTH in line and "doesn't draw" in line for line in lines)  # (it is drawn)


def test_factors_are_clamped_as_the_base_colour_is(tmp_path: Path) -> None:
    path = _edited(tmp_path, lambda doc: _material(doc, "factor_only").update(emissiveFactor=[2.0, -1.0, 0.5]))
    assert _materials(path)["factor_only"].emissive == (1.0, 0.0, 0.5)


@pytest.mark.parametrize("change", [
    {"emissiveFactor": "orange"},
    {"emissiveFactor": [1.0, 0.5]},
    {"emissiveFactor": [1.0, float("nan"), 0.0]},
    {"emissiveFactor": [True, 0.0, 0.0]},
    {"extensions": {glb.EMISSIVE_STRENGTH: {"emissiveStrength": -1.0}}},
    {"extensions": {glb.EMISSIVE_STRENGTH: {"emissiveStrength": "bright"}}},
])
def test_malformed_emission_is_refused_naming_the_material(tmp_path: Path, change: dict) -> None:
    path = _edited(tmp_path, lambda doc: _material(doc, "factor_only").update(change))
    with pytest.raises(GlbError, match="material 'factor_only': its emission"):
        load_glb(path)


def test_emission_on_a_second_uv_map_is_not_drawn_and_said(tmp_path: Path) -> None:
    path = _edited(tmp_path, lambda doc: _material(doc, "texture_only")["emissiveTexture"].update(texCoord=1))
    m = _materials(path)["texture_only"]
    assert not m.glows and m.emissive_image is None
    lines = inspect_glb(path)[1].lines()
    assert any(line.startswith("texture_only's emission texture uses a second UV map") for line in lines)
    assert not any("texture_only" in line for line in lines if line.startswith("Glows"))


def test_the_report_names_what_glows_and_the_material_extensions_mesh_does_not_draw(tmp_path: Path) -> None:
    def extras(doc: dict) -> None:
        _material(doc, "ordinary")["extensions"] = {"KHR_materials_transmission": {"transmissionFactor": 1.0}}
        _material(doc, "zero_emission")["extensions"] = {"KHR_materials_unlit": {},
                                                         "KHR_materials_transmission": {}}
        doc["extensionsUsed"] = ["KHR_materials_transmission", "KHR_materials_unlit"]

    lines = inspect_glb(_edited(tmp_path, extras))[1].lines()
    assert ("Glows (emission, unlit): factor_only, texture_only (texture 2x2), factor_and_texture (texture 2x2), "
            "lit_and_glowing.") in lines
    assert ("Material extensions Mesh doesn't draw: KHR_materials_transmission (zero_emission, ordinary); "
            "KHR_materials_unlit (zero_emission). Mesh draws a material's base colour and its emission.") in lines


def test_keep_pixels_sharp_also_sharpens_an_emission_texture(tmp_path: Path) -> None:
    def smooth_emission(doc: dict) -> None:  # the emission's own texture, sampled Linear (Blender's default)
        doc["samplers"].append({"magFilter": glb.GL_LINEAR, "minFilter": glb.GL_LINEAR})
        doc["textures"].append({"source": 0, "sampler": 1})
        _material(doc, "texture_only")["emissiveTexture"] = {"index": 1}

    path = _edited(tmp_path, smooth_emission)
    assert not _materials(path)["texture_only"].emissive_nearest
    assert any("texture_only (emission)" in line and line.startswith("Smooth") for line in inspect_glb(path)[1].lines())
    sharp, changed = glb.sharpen_textures(path.read_bytes())
    assert changed == ["texture_only"]
    (tmp_path / "sharp.glb").write_bytes(sharp)
    assert _materials(tmp_path / "sharp.glb")["texture_only"].emissive_nearest


def test_an_emission_textures_wrap_modes_are_kept_per_axis(tmp_path: Path) -> None:
    m = _materials(demo.sampling_glb(tmp_path / "sampling.glb"))
    assert m["repeat_u_clamp_v"].emissive_wrap == (glb.GL_REPEAT, glb.GL_CLAMP_TO_EDGE)
    assert m["mirror_u_clamp_v"].emissive_wrap == (glb.GL_MIRRORED_REPEAT, glb.GL_CLAMP_TO_EDGE)
    assert m["clamp_u_repeat_v"].emissive_wrap == (glb.GL_CLAMP_TO_EDGE, glb.GL_REPEAT)
    assert m["linear_black_white"].emissive_wrap == (glb.GL_CLAMP_TO_EDGE, glb.GL_CLAMP_TO_EDGE)
    assert all(m[n].emissive_nearest for n in ("repeat_u_clamp_v", "mirror_u_clamp_v", "clamp_u_repeat_v"))
    assert not m["linear_black_white"].emissive_nearest and not m["linear_black_grey"].emissive_nearest


def test_a_base_colour_textures_wrap_reads_as_before(tmp_path: Path) -> None:
    """Unchanged for base colour textures: one wrap for both axes, clamped if either axis clamps."""
    def mixed_base(doc: dict) -> None:
        doc["samplers"].append({"magFilter": glb.GL_NEAREST, "wrapS": glb.GL_REPEAT, "wrapT": glb.GL_CLAMP_TO_EDGE})
        doc["textures"].append({"source": 0, "sampler": 1})
        _material(doc, "ordinary")["pbrMetallicRoughness"] = {"baseColorTexture": {"index": 1}}

    ordinary = _materials(_edited(tmp_path, mixed_base))["ordinary"]
    assert ordinary.repeat is False and ordinary.nearest and ordinary.emissive_image is None


def test_an_unknown_emission_wrap_mode_is_refused(tmp_path: Path) -> None:
    def bad_wrap(doc: dict) -> None:
        doc["samplers"][0]["wrapT"] = 12345

    with pytest.raises(GlbError, match="material 'texture_only': its emission texture's wrap mode"):
        load_glb(_edited(tmp_path, bad_wrap))


def test_every_model_mesh_ships_has_no_emission_so_draws_as_before() -> None:
    shipped = sorted([*REPO.glob("assets/**/*.glb"), *REPO.glob("tooling/**/*.glb")])
    assert len(shipped) >= 20
    for path in shipped:
        model, report = inspect_glb(path)
        assert not any(p.material.glows or p.material.emissive_image for p in model.parts), path
        assert not report.glowing and not any("Material extensions" in w for w in report.warnings), path
