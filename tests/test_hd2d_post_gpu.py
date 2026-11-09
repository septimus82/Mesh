"""M17-L4-2: an HD-2D room's colour grade and vignette in real frames (hidden windows): off and strength 0 are the
original picture; each preset keeps characters readable, lamp glass and emission their hue, adds no clipping and
doesn't crush the night; the vignette leaves the centre; the HUD is untouched; and in Mesh Studio the controls,
undo/redo, an AI proposal (accepted, undone, refused on a conflict), play, save, reopen and export all agree.
(tooling/hd2d_post_study.py, tooling/hd2d_post_studio.py.) GL-gated: MESH_GL_SMOKE=1."""

from __future__ import annotations

import json
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
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
ROOMS = ("village", "lakeside", "fixtures", "cottage", "emissive")
PRESETS = ("natural", "golden_hour", "moonlight", "interior_warm")


def _keep(name: str, found: dict) -> None:
    keep = REPO / "artifacts" / "hd2d_post"
    keep.mkdir(parents=True, exist_ok=True)
    (keep / f"{name}_{sys.platform}.json.log").write_text(json.dumps(found, indent=1, default=str), encoding="utf-8")


@pytest.fixture(scope="module")
def frames(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import hd2d_post_study

    found: dict = hd2d_post_study.study(tmp_path_factory.mktemp("post"))
    _keep("frames", found)
    return found


@pytest.fixture(scope="module")
def studio(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import hd2d_post_studio

    out = tmp_path_factory.mktemp("post_studio")
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    try:
        found: dict = hd2d_post_studio.studio(out, export=True)
    finally:
        os.environ.pop("MESH_RUNTIME_SETTINGS_PATH", None)
        os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)
    _keep("studio", found)
    return found


@pytest.mark.parametrize("name", ROOMS)
def test_off_and_strength_zero_are_the_original_picture(frames: dict, name: str) -> None:
    r = frames["rooms"][name]
    assert r["off"]["stage"] == "blit" and not r["off"]["made"], r["off"]
    assert r["strength_zero"] == {"same": True, "stage": "blit", "made": False}, r["strength_zero"]
    assert r["off_again_same"], r


@pytest.mark.parametrize("name", ROOMS)
def test_each_preset_grades_once_keeping_the_picture_readable(frames: dict, name: str) -> None:
    r = frames["rooms"][name]
    for preset, p in r["presets"].items():
        where = (name, preset, p)
        assert p["stage"] == "composite" and p["changed_share"] > 0.5 and p["repeat_same"], where
        assert p["uniform_updates_on_repeat"] == 0 and p["draw_calls"] == r["off"]["draw_calls"], where
        assert p["world_read_unchanged"], where  # draw(read=True): the world before the composite, as ever
        if p["weber_change_min"] is not None:  # (characters: as distinct from what is round them, edges kept)
            assert p["weber_change_min"] >= -0.02 and p["edge_ratio_min"] >= 0.9, where
        if p["glass_hue_shift_max"] is not None:  # (E2's lamp glass keeps its warm hue)
            assert p["glass_hue_shift_max"] <= 2.0, where
        assert p["clipped_increase"] <= 0.0 and p["crushed_increase"] <= 0.1, where


def test_the_night_grade_doesn_t_crush_the_night(frames: dict) -> None:
    for name in ("village", "lakeside", "cottage"):
        moon = frames["rooms"][name]["presets"]["moonlight"]
        assert moon["crushed_increase"] <= 0.05 and moon["dark_mean_ratio"] >= 0.95, (name, moon)


def test_e1_emission_keeps_its_hue(frames: dict) -> None:
    em = frames["emission"]
    assert em["coloured_swatches"] >= 2 and max(em["hue_shift_max"].values()) <= 5.0, em


@pytest.mark.parametrize("name", ROOMS)
def test_the_vignette_leaves_the_centre_and_darkens_the_corners(frames: dict, name: str) -> None:
    v = frames["rooms"][name]["vignette"]
    assert v["centre_same"] and 0.5 < v["corner_ratio"] < 0.9, v


@pytest.mark.parametrize("name", ROOMS)
def test_with_the_depth_of_field_it_takes_the_dof_s_picture(frames: dict, name: str) -> None:
    dof = frames["rooms"][name]["with_dof"]
    assert dof == {"stage": "dof+composite", "chain_allocations": 1, "world_read_unchanged": True}, dof


def test_the_grade_works_in_linear_light_and_keeps_alpha(frames: dict) -> None:
    tx = frames["texels"]
    r, g, b, _a = tx["exposure_grey"]  # sRGB 100 -> linear 0.1274 x 1.5 = 0.1911 -> sRGB 121 (in sRGB values: 150)
    assert r == g == b and abs(r - 121) <= 1, tx
    assert tx["exposure_grey"][3] == 77, tx  # (alpha kept)
    r, g, b, a = tx["saturation_zero"]  # sRGB (200, 60, 30): linear luminance 0.1556 -> sRGB 110 grey
    assert r == g == b and abs(r - 110) <= 1 and a == 255, tx
    assert tuple(tx["neutral"]) == (37, 180, 222, 9), tx  # (neutral values: decode/encode round-trips exactly)
    # highlight protection: the bright warm texel keeps its colour (each channel within 4 levels), unprotected it cools;
    # a dark one is graded whatever the protection
    kept = max(abs(a - b) for a, b in zip(tx["bright_protected"][:3], (250, 180, 80)))
    cooled = max(abs(a - b) for a, b in zip(tx["bright_unprotected"][:3], (250, 180, 80)))
    assert kept <= 4 and cooled >= 12, tx
    r, _g, b, _a = tx["dark_protected"]  # (60, 50, 40) graded as computed: red 60 -> 55, blue 40 -> 44
    assert r <= 56 and b >= 43, tx


def test_the_hud_is_never_graded(frames: dict) -> None:
    hud = frames["hud"]
    assert hud["hud_pixels"] > 500 and hud["hud_same"] and hud["hud_alone_same"] and hud["world_changed"], hud


def test_studio_grades_its_view_at_once_and_not_its_lines(studio: dict) -> None:
    assert studio["before"]["preset"] is None and studio["still"], studio["before"]
    nat = studio["natural"]
    assert nat["stored"] == {"preset": "natural"} and nat["stage"] == "composite" and nat["changed_share"] > 0.5, nat
    lines = studio["lines"]
    assert lines["after_calls"] and set(lines["after_calls"]) == {"composite"}, lines
    assert lines["pixels"][0] > 1000 and lines["same_share"] >= 0.99, lines
    assert studio["parity"] == {"same": True, "stage": "composite"}, studio["parity"]
    assert studio["canvas_equals_origin"], "the grade and vignette by the picture's pixels, right in the offset canvas"


def test_studio_s_fields_undo_redo_and_off(studio: dict) -> None:
    assert studio["typed"] == {"preset": "natural", "strength": 0.5, "vignette": 0.3}
    assert studio["undone"] == {"preset": "natural", "strength": 0.5}
    assert studio["redone"] == studio["typed"] and studio["redone_renderer"] == {"strength": 0.5, "vignette": 0.3}
    assert studio["op_parity"], "Studio's edits and the project operation store the same"
    assert studio["off"] == {"stored": None, "stage": "blit", "view_same_as_before": True}, studio["off"]


def test_an_ai_proposal_is_accepted_undone_and_refused_on_a_conflict(studio: dict) -> None:
    assert studio["ai_staged"]["summary"] == ["Village: picture treatment moonlight"], studio["ai_staged"]
    acc = studio["ai_accepted"]
    assert acc["status"] == "accepted" and acc["stored"] == {"preset": "moonlight"}, acc
    assert acc["renderer_preset"] == "moonlight" and acc["stage"] == "composite", acc
    assert studio["ai_undone"] == {"stored": None, "renderer_post": None}, studio["ai_undone"]
    clash = studio["ai_conflict"]
    assert clash["status"] == "conflict" and clash["conflicts"] >= 1, clash
    assert clash["stored"] == {"preset": "interior_warm"}, clash  # (the person's change kept, the AI's not applied)


def test_it_plays_saves_reopens_and_exports(studio: dict) -> None:
    assert studio["in_play"] == {"mode": "play", "preset": "natural", "stage": "composite"}, studio["in_play"]
    assert studio["saved"].startswith("Saved") and studio["in_the_saved_file"] == {"preset": "natural"}
    assert studio["rest_of_the_room_unchanged"], "only the post key differs from the template's room"
    reopened = studio["reopened"]
    assert reopened["post"]["preset"] == "natural" and reopened["unsaved"] == [] and reopened["renderer_preset"] == "natural"
    ex = studio["export"]
    assert ex["code"] == 0 and ex["scene_setting"] == {"preset": "natural"}, ex
    assert ex["bundle_run"].get("preset") == "natural" and ex["bundle_run"].get("stage") == "composite", ex
