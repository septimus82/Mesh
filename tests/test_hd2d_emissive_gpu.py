"""M17-L3 E1, in real frames of the game and of Mesh Studio (hidden windows; tooling/hd2d_emissive_demo.py): an
imported model's glTF emission is drawn as glTF means it, unlit, the same at noon and at night and with a lamp beside
it on or off; zero emission and ordinary materials are drawn exactly as before; a reimport changes it; Studio's edit
view draws it, and it survives saving and reopening. GL-gated: set MESH_GL_SMOKE=1."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
    pytest.mark.filterwarnings("ignore:.*style dict.*:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
import hd2d_emissive_demo as demo  # noqa: E402

GLOWING = ("factor_only", "texture_only", "factor_and_texture")  # (black base colour: the pixel is the emission)
LIGHTINGS = ("noon", "night", "night_lamp_on", "night_lamp_off")


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    # (the AI bridge off for its Studio session only, then as it was: absent stays absent, a value comes back)
    with pytest.MonkeyPatch.context() as env:
        env.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")
        return demo.check(tmp_path_factory.mktemp("em") / "d")


def _close(got: tuple[int, ...], want: tuple[int, ...], tol: int = 1) -> bool:
    return all(abs(a - b) <= tol for a, b in zip(got, want))


def _want(name: str, quarter: int | None = None, factor: list[float] | None = None) -> tuple[int, ...]:
    _n, _base, f, textured, _s = next(s for s in demo.SWATCHES if s[0] == name)
    return demo.expected_glow(factor or f, demo.TEXELS[quarter] if textured and quarter is not None else None)


def test_the_import_report_names_what_glows(run: dict) -> None:
    assert ("Glows (emission, unlit): factor_only, texture_only (texture 2x2), factor_and_texture (texture 2x2), "
            "lit_and_glowing.") in run["report"]


@pytest.mark.parametrize("lighting", LIGHTINGS)
def test_emission_is_drawn_as_gltf_means_unlit_in_any_light(run: dict, lighting: str) -> None:
    panels = run[lighting]
    assert _close(panels["factor_only"]["middle"], _want("factor_only")), panels["factor_only"]
    for name in ("texture_only", "factor_and_texture"):  # each texel where its uv puts it (uv 0,0: the top left)
        for q in range(4):
            assert _close(panels[name][f"t{q}"], _want(name, q)), (name, q, panels[name])


def test_emission_does_not_change_with_the_sun_or_a_lamp_switched_off(run: dict) -> None:
    for name in GLOWING:
        assert run["noon"][name] == run["night"][name] == run["night_lamp_on"][name] == run["night_lamp_off"][name]
    assert run["noon"]["ordinary"]["middle"] != run["night"]["ordinary"]["middle"]  # (the light did change)
    assert run["night_lamp_on"]["zero_emission"] != run["night_lamp_off"]["zero_emission"]  # (the lamp lights it)


@pytest.mark.parametrize("lighting", LIGHTINGS)
def test_zero_emission_draws_exactly_as_an_ordinary_material(run: dict, lighting: str) -> None:
    if lighting == "night_lamp_on":  # (the lamp stands nearer one than the other: compare without it)
        pytest.skip("lit unevenly by the lamp")
    assert run[lighting]["zero_emission"] == run[lighting]["ordinary"]


@pytest.mark.parametrize("lighting", ("noon", "night", "night_lamp_off"))
def test_a_lit_material_that_glows_is_its_lit_colour_plus_the_emission(run: dict, lighting: str) -> None:
    lit = run[lighting]["ordinary"]["middle"]
    got = run[lighting]["lit_and_glowing"]["middle"]
    assert _close(got, demo.expected_glow([0.25, 0.1, 0.0], lit=lit)), (got, lit)
    assert got[0] > lit[0] and got[1] > lit[1]


def test_a_reimport_changes_the_emission_of_every_copy(run: dict) -> None:
    re_ = run["reimported"]
    assert _close(re_["factor_only"]["middle"], demo.expected_glow([0.0, 0.25, 1.0])), re_["factor_only"]
    assert re_["texture_only"] == run["night"]["texture_only"] and re_["ordinary"] == run["night"]["ordinary"]


def _wrapped(coord: float, mode: int) -> float:
    """glTF's wrap of a texture coordinate into 0..1 (OpenGL's: REPEAT, CLAMP_TO_EDGE, MIRRORED_REPEAT)."""
    if mode == demo.REPEAT:
        return coord % 1.0
    if mode == demo.MIRROR:
        whole = int(coord // 1.0)
        frac = coord - whole
        return 1.0 - frac if whole % 2 else frac
    return min(max(coord, 0.0), 0.999)


@pytest.mark.parametrize("panel", ("repeat_u_clamp_v", "mirror_u_clamp_v", "clamp_u_repeat_v"))
def test_an_emission_texture_wraps_each_axis_as_its_sampler_says(run: dict, panel: str) -> None:
    """uv 0..2 across and down the panel: each axis repeats, clamps or mirrors on its own (Nearest texels)."""
    index = next(i for i, ((name, *_r), _s) in enumerate(demo.SAMPLING) if name == panel)
    sampler = demo.SAMPLING_SAMPLERS[demo.SAMPLING_TEXTURES[index]["sampler"]]
    for fx in demo.GRID:
        for fy in demo.GRID:
            u, v = _wrapped(2 * fx, sampler["wrapS"]), _wrapped(2 * fy, sampler["wrapT"])
            texel = demo.TEXELS[int(v * 2) * 2 + int(u * 2)]
            got = run["sampling"][panel][f"{fx},{fy}"]
            assert _close(got, texel[:3]), (panel, fx, fy, got, texel)


def test_a_linear_emission_texture_blends_in_linear_light(run: dict) -> None:
    """A Linear-filtered black / white emission texture (texel middles at u 0.25 and 0.75) blends as glTF's reference
    does: texels decoded from sRGB, then blended. Halfway is linear 0.5, drawn 188 (blending the stored sRGB bytes would
    draw 128)."""
    got = run["sampling"]["linear_black_white"]
    for fx in demo.LINEAR_AT:
        white = min(max((fx - 0.25) / 0.5, 0.0), 1.0)
        want = round(255 * demo.srgb(white))
        assert all(abs(c - want) <= 3 for c in got[f"{fx},0.5"]), (fx, got[f"{fx},0.5"], want)
    assert abs(got["0.5,0.5"][0] - 188) <= 3 and abs(got["0.375,0.5"][0] - 137) <= 3


def test_a_linear_emission_texture_blends_a_mid_tone_in_linear_light(run: dict) -> None:
    """Black / grey 128: linear light blends 0 and 0.216 (grey decoded), halfway 0.108, drawn 93. (Blending the sRGB
    bytes and decoding after draws 64; reading the bytes as linear draws 137.)"""
    got = run["sampling"]["linear_black_grey"]
    grey = demo.linear(128 / 255)
    for fx in demo.LINEAR_AT:
        want = round(255 * demo.srgb(grey * min(max((fx - 0.25) / 0.5, 0.0), 1.0)))
        assert all(abs(c - want) <= 3 for c in got[f"{fx},0.5"]), (fx, got[f"{fx},0.5"], want)
    assert abs(got["0.5,0.5"][0] - 93) <= 3


def test_studio_draws_it_and_it_survives_saving_and_reopening(run: dict) -> None:
    assert run["studio_saved_evening"]
    for label in ("studio", "studio_reopened"):
        panels = run[label]
        assert _close(panels["factor_only"]["middle"], demo.expected_glow([0.0, 0.25, 1.0])), (label, panels)
        for q in range(4):
            assert _close(panels["texture_only"][f"t{q}"], _want("texture_only", q)), (label, q, panels)
