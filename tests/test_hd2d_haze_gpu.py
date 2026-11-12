"""M17-L4-3: an HD-2D room's atmospheric depth in real frames (hidden windows): off and strength 0 are the original
picture; with each preset every pixel's haze is the one its own depth calls for (read back from the picture and the
depth buffer), nearer pixels keep their bytes, characters stay readable, the onset stays beyond the player; walking and
a flat camera agree; with the grade and the depth of field it runs in the one composite; known texels match the maths;
the HUD is untouched; a refused driver gives the original picture; and in Mesh Studio the controls, undo/redo, the
game's path, play, save, reopen, export and a malformed block all agree. (tooling/hd2d_haze_study.py,
tooling/hd2d_haze_studio.py.) GL-gated: MESH_GL_SMOKE=1."""

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
ROOMS = ("village", "lakeside", "fixtures", "cottage")
OUTDOOR = ("village", "lakeside", "fixtures")  # (the cottage interior's camera sees ~2.5 m of depth: inside the start)
PRESETS = ("daytime", "evening")


def _keep(name: str, found: dict) -> None:
    keep = REPO / "artifacts" / "hd2d_haze"
    keep.mkdir(parents=True, exist_ok=True)
    (keep / f"{name}_{sys.platform}.json.log").write_text(json.dumps(found, indent=1, default=str), encoding="utf-8")


@pytest.fixture(scope="module")
def frames(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import hd2d_haze_study

    found: dict = hd2d_haze_study.study(tmp_path_factory.mktemp("haze"))
    _keep("frames", found)
    return found


@pytest.fixture(scope="module")
def studio(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import hd2d_haze_studio

    out = tmp_path_factory.mktemp("haze_studio")
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    try:
        found: dict = hd2d_haze_studio.studio(out, export=True)
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
def test_every_pixel_s_haze_is_the_one_its_depth_calls_for(frames: dict, name: str) -> None:
    for preset, p in frames["rooms"][name]["presets"].items():
        m, where = p["match"], (name, preset, p)
        assert p["stage"] == "composite" and p["repeat_same"] and p["uniform_updates_on_repeat"] == 0, where
        assert p["draw_calls"] == frames["rooms"][name]["off"]["draw_calls"] and p["world_read_unchanged"], where
        assert m["pixels"] > 10000 and m["err_p99"] <= 0.01 and m["err_max"] <= 0.04, where  # (8-bit rounding)
        assert m["near_same"], where  # nearer than the onset: the bytes exactly
        assert m["hazed_share"] > 0.1 if name in OUTDOOR else m["hazed_share"] == 0.0, where
        assert p["clipped_increase"] <= 0.0, where
        assert p["lit_as_the_room"], where  # (its colour lit by this room's own sun and ambient light)
        shown = [b for b in m["by_depth"] if b is not None]
        assert all(b >= a - 1e-4 for a, b in zip(shown, shown[1:])), where  # (farther: never less)


def test_the_backdrop_is_never_hazed(frames: dict) -> None:
    cottage = frames["rooms"]["cottage"]["presets"]  # (the interior: its dark surroundings are the room's backdrop)
    for preset, p in cottage.items():
        assert p["match"]["backdrop_share"] > 0.2 and p["match"]["near_same"], (preset, p["match"])


@pytest.mark.parametrize("name", ROOMS)
def test_characters_stay_readable_and_the_haze_starts_beyond_the_player(frames: dict, name: str) -> None:
    for preset, p in frames["rooms"][name]["presets"].items():
        where = (name, preset, p)
        assert p["onset_beyond_character"], where
        if p["weber_ratio_min"] is not None:  # (a villager a few metres behind the player fades only a little)
            assert p["weber_ratio_min"] >= 0.85 and p["edge_ratio_min"] >= 0.85, where


@pytest.mark.parametrize("name", ROOMS)
def test_a_start_of_zero_still_leaves_the_player_alone(frames: dict, name: str) -> None:
    z = frames["rooms"][name]["start_zero"]
    if z["followed"]:  # (moved out to the character's own depth and a metre more)
        assert z["onset"] == pytest.approx(z["band"] + 1.0, abs=1e-3), z
    assert z["match"] <= 0.01, z


def test_walking_keeps_the_haze_on_its_depth(frames: dict) -> None:
    w = frames["walking"]
    assert w["moved"] >= 4 and w["onset_offsets"] == [4.0], w  # (the camera moved; the onset kept its place)
    assert all(f["err_p99"] <= 0.01 and f["near_same"] for f in w["frames"]), w


def test_a_flat_camera_uses_its_own_depth(frames: dict) -> None:
    f = frames["flat_camera"]
    assert f["err_p99"] <= 0.01 and f["near_same"] and f["hazed_share"] > 0.1, f


@pytest.mark.parametrize("name", ROOMS)
def test_with_the_grade_and_the_depth_of_field_it_is_the_one_composite(frames: dict, name: str) -> None:
    r = frames["rooms"][name]
    assert r["with_grade"] == {"stage": "composite", "near_same_as_grade": True, "far_changed": name in OUTDOOR}, r
    assert r["with_dof"] == {"stage": "dof+composite", "chain_allocations": 1, "world_read_unchanged": True}, r


def test_known_texels_match_the_maths(frames: dict) -> None:
    tx = frames["texels"]
    assert tx["near"]["got"] == [37, 180, 222, 9] and tx["at_onset"]["got"] == [37, 180, 222, 9], tx  # (exactly)
    assert tx["backdrop"]["got"] == [18, 14, 11, 255], tx  # nothing drawn there (an interior's darkness): untouched
    for name, case in tx.items():
        if name == "order":
            continue
        assert case["got"][3] == case["model"][3], tx  # (alpha kept)
        assert max(abs(a - b) for a, b in zip(case["got"], case["model"])) <= 1, (name, tx)


def test_the_haze_comes_before_the_grade(frames: dict) -> None:
    order = frames["texels"]["order"]  # one pass: the haze, then the grade on the hazed scene
    assert max(abs(a - b) for a, b in zip(order["both"], order["haze_then_grade"])) <= 1, order
    assert max(abs(a - b) for a, b in zip(order["both"], order["grade_then_haze"])) >= 3, order  # (order matters)


def test_night_haze_is_dim(frames: dict) -> None:
    n = frames["night"]  # the village under Studio's night sun: the same haze, lit by the night
    assert max(n["light"]) < 0.5 and n["lit_as_the_room"] and n["match"]["err_p99"] <= 0.01, n
    assert all(a < b for a, b in zip(n["shown"], n["day_shown"])), n


def test_the_hud_is_never_hazed(frames: dict) -> None:
    hud = frames["hud"]
    assert hud["hud_pixels"] > 500 and hud["hud_same"] and hud["world_changed"], hud


def test_a_refused_driver_gives_the_original_picture(frames: dict) -> None:
    r = frames["refused"]
    assert r["stage"] == "blit" and r["same"] and "graphics driver refused it" in str(r["reason"]), r


def test_studio_hazes_its_view_at_once_and_not_its_lines(studio: dict) -> None:
    assert studio["before"] == {"preset": None, "error": None} and studio["still"], studio
    day = studio["daytime"]
    assert day["stored"] == {"preset": "daytime"} and day["stage"] == "composite" and day["renderer_preset"] == "daytime"
    assert day["changed_share"] > 0.1 and len(day["fields"]) == 4, day
    lines = studio["lines"]
    assert lines["after_calls"] and set(lines["after_calls"]) == {"composite"} and lines["same_share"] == 1.0, lines


def test_studio_s_view_and_the_game_s_path_are_one_picture(studio: dict) -> None:
    p = studio["parity"]
    assert p["same"] and p["stage"] == "composite" and p["onsets"][0] == p["onsets"][1], p


def test_studio_s_fields_refuse_bad_values_undo_redo_and_off(studio: dict) -> None:
    typed = {"preset": "daytime", "strength": 0.4, "start": 2.0, "falloff": 20.0, "color": "#a0b8d0"}
    assert studio["typed"] == typed and studio["redone"] == typed and studio["op_parity"], studio
    for bad in ("bad_colour", "too_strong"):
        assert studio[bad]["stored"] == typed and studio[bad]["ok"] is False, studio[bad]
        assert studio[bad]["put_back"] == "Put back as it was.", studio[bad]
    assert studio["undone"] != typed and "falloff" not in studio["undone"], studio
    assert studio["redone_renderer"]["falloff"] == 20.0, studio
    assert studio["with_grade"] == {"stage": "composite", "post": "golden_hour"}, studio
    assert studio["off"] == {"stored": None, "stage": "blit", "view_same_as_before": True}, studio["off"]


def test_it_plays_saves_reopens_and_exports(studio: dict) -> None:
    assert studio["in_play"]["mode"] == "play" and studio["in_play"]["preset"] == "evening", studio["in_play"]
    assert studio["in_play"]["stage"] == "composite", studio["in_play"]
    assert studio["in_the_saved_file"] == {"preset": "evening"} and studio["rest_of_the_room_unchanged"], studio
    assert studio["reopened"]["haze"]["preset"] == "evening" and not studio["reopened"]["unsaved"], studio["reopened"]
    ex = studio["export"]
    assert ex["code"] == 0 and ex["scene_setting"] == {"preset": "evening"}, ex
    assert ex["bundle_run"].get("preset") == "evening" and ex["bundle_run"].get("stage") == "composite", ex


def test_studio_shows_and_repairs_a_malformed_block(studio: dict) -> None:
    m = studio["malformed"]
    assert m["haze_of"]["preset"] is None and "settings.hd2d.haze.preset" in m["haze_of"]["error"], m
    assert m["renderer_haze"] is None and m["stage"] == "blit" and m["warning"], m
    assert m["repaired"] == {"stored": {"preset": "daytime"}, "renderer_preset": "daytime", "stage": "composite",
                             "warning": False}, m
    assert m["undone"] == {"preset": ["daytime"], "strength": 0.2}, m
