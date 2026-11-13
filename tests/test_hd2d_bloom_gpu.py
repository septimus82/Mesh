"""M17-L4-4: an HD-2D room's bloom in real frames (hidden windows): off and strength 0 are the original picture with
nothing made; the world's emission is the emitters' alone (lamp heads; a campfire's flames and embers, a torch), hidden
behind what stands in front; the prefilter is the CPU's threshold, knee and cap of it; the glow holds the light that
passed, near the emitters, never far from them; what is merely bright never glows; the camera moving and the picture's
size keep it the same; with the haze, the depth of field and the grade it runs in the one composite in their order;
known texels match the maths; the HUD is untouched; a refused driver keeps the rest of the picture; nothing of it is
left allocated when it's off; and in Mesh Studio the controls, undo/redo, the game's path, play, save, reopen, export
and a malformed block all agree. (tooling/hd2d_bloom_study.py, tooling/hd2d_bloom_studio.py.) GL-gated:
MESH_GL_SMOKE=1."""

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
ROOMS = ("village", "campfire")
LOOKS = ("subtle", "warm", "strong")


def _keep(name: str, found: dict) -> None:
    keep = REPO / "artifacts" / "hd2d_bloom"
    keep.mkdir(parents=True, exist_ok=True)
    (keep / f"{name}_{sys.platform}.json.log").write_text(json.dumps(found, indent=1, default=str), encoding="utf-8")


@pytest.fixture(scope="module")
def frames(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import hd2d_bloom_study

    found: dict = hd2d_bloom_study.study(tmp_path_factory.mktemp("bloom"))
    _keep("frames", found)
    return found


@pytest.fixture(scope="module")
def studio(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import hd2d_bloom_studio

    out = tmp_path_factory.mktemp("bloom_studio")
    # (for its run only, then as they were: absent stays absent, a value comes back, whatever the run did)
    with pytest.MonkeyPatch.context() as env:
        env.setenv("MESH_RUNTIME_SETTINGS_PATH", str(out / "user_settings.json"))
        env.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")
        found: dict = hd2d_bloom_studio.studio(out, export=True)
    _keep("studio", found)
    return found


@pytest.mark.parametrize("name", ROOMS)
def test_off_and_strength_zero_are_the_original_picture_with_nothing_made(frames: dict, name: str) -> None:
    r = frames[name]
    assert r["off"] == {"stage": "blit", "made": False}, r["off"]
    assert r["zero"] == {"same": True, "stage": "blit", "made": False}, r["zero"]
    assert r["off_again"] == {"same": True, "made": False, "objects_more": 0}, r["off_again"]


@pytest.mark.parametrize("name", ROOMS)
def test_the_glow_comes_from_the_emission_and_holds_its_light(frames: dict, name: str) -> None:
    for look in LOOKS:
        p, where = frames[name][look], (name, look, frames[name][look])
        assert p["stage"] == "composite" and p["passes"] == 11 and p["repeat_same"], where
        assert p["emitting_px"] > 300, where
        if name == "village":  # (its only emitters: the two lamp heads; ground, walls, characters, grass emit nothing)
            assert p["emitting_outside_heads"] == 0, where
        # the prefilter: the CPU's threshold, knee and cap, area-averaged (the emission target's float precision)
        assert p["prefilter_error"] <= 0.02 * max(1.0, p["prefilter_max"]), where
        assert 0.95 <= p["energy_glow"] / p["energy_passed"] <= 1.0001, where  # (no gain, no loss but rounding)
        assert p["changed"] > 1000 and p["changed_far"] == 0 and p["far_px"] > 50000, where  # far away: the bytes
        assert p["added_near_share"] >= (0.8 if look == "strong" else 0.95), where  # (most of it close by)


def test_the_presets_are_restrained_and_the_strong_look_shows_it_all(frames: dict) -> None:
    for name in ROOMS:
        r = frames[name]
        assert r["subtle"]["changed"] < r["warm"]["changed"] < r["strong"]["changed"], name
        assert r["subtle"]["energy_passed"] < r["warm"]["energy_passed"] <= r["strong"]["energy_passed"], name


def test_what_is_merely_bright_never_glows(frames: dict) -> None:
    m = frames["merely_bright"]
    assert m["emission_sum"] == 0.0 and m["same"] and m["stage"] == "composite", m


def test_the_backdrop_never_glows(frames: dict) -> None:
    """Where nothing is drawn (an interior's surroundings) the emission is zero, not the sky's colour the framebuffer
    is cleared to."""
    b = frames["backdrop"]
    assert b["backdrop_px"] > 10000 and b["emission_sum"] == 0.0 and b["same"], b


def test_an_emitter_behind_a_character_is_hidden(frames: dict) -> None:
    o = frames["occluded"]
    assert o["player_px"] > 500 and o["emitting_under_player_aside"] > 20, o  # (the player covers the lamp head)
    assert o["emitting_under_player"] == 0, o


def test_the_camera_moving_keeps_the_glow_s_light(frames: dict) -> None:
    m = frames["moving"]
    assert 0.95 <= m["glow_over_passed_min"] and m["glow_over_passed_max"] <= 1.0001, m
    assert m["glow_over_passed_max"] - m["glow_over_passed_min"] <= 0.01, m  # (no flicker from the chain)


def test_the_glow_is_the_same_share_of_any_picture(frames: dict) -> None:
    s = frames["sizes"]
    assert s["960x540"]["base"] == s["1920x1080"]["base"] == [640, 360], s
    assert s["correlation"] >= 0.97 and 0.9 <= s["energy_ratio"] <= 1.1, s


def test_an_emitter_in_the_haze_glows_as_dimly_as_it_shows(frames: dict) -> None:
    h = frames["haze"]
    assert h["error"] <= 0.02 * max(1.0, h["max"]) and h["dimmed_by"] > 0.05, h


def test_with_the_depth_of_field_bloom_follows_it(frames: dict) -> None:
    d = frames["dof"]
    assert d["dof_stage"] == "dof" and d["stage"] == "dof+composite" and d["changed"] > 1000, d
    assert d["changed_far"] == 0, d  # (far from emitters: the depth of field's own picture, byte for byte)


def test_known_texels_match_the_maths_in_order(frames: dict) -> None:
    t = frames["texels"]
    for case in ("none", "added", "clipped", "after_haze"):
        got, model = t[case]["got"], t[case]["model"]
        assert all(abs(a - b) <= 1 for a, b in zip(got, model)) and got[3] == model[3], (case, t[case])
    assert t["none"]["got"] == t["none"]["model"], t["none"]  # (no glow: the texel exactly)
    order = t["before_grade"]
    assert all(abs(a - b) <= 1 for a, b in zip(order["got"], order["grade_of_sum"])), order
    assert any(abs(a - b) > 1 for a, b in zip(order["got"], order["sum_of_grade"])), order  # (and not after it)


def test_the_hud_never_glows(frames: dict) -> None:
    hud = frames["hud"]
    assert hud["hud_pixels"] > 500 and hud["world_changed"] and hud["opaque_same"], hud


def test_a_refused_driver_keeps_the_rest_of_the_picture(frames: dict) -> None:
    for name, r in frames["refused"].items():
        assert r["alone_same"] and r["with_haze_same"] and not r["made"], (name, r)
        assert r["stage"] == "composite" and "bloom is off on this computer" in str(r["reason"]), (name, r)


def test_it_is_made_when_needed_remade_on_resize_and_freed_when_off(frames: dict) -> None:
    lc = frames["lifecycle"]
    assert lc["objects_on"] > lc["objects_off"] and lc["objects_after_off"] == lc["objects_off"], lc
    assert lc["allocations_first"] == 2 and not lc["made_after_off"], lc  # (the emission target and the chain)
    assert lc["resized"]["objects"] == lc["objects_on"] and lc["resized"]["allocations"] == 4, lc  # (none leaked)
    assert lc["resized"]["emission"] == [800, 600], lc
    from engine.hd2d.bloom import level_sizes

    sizes = level_sizes((960, 540))  # the emission target, every level down and all but the last up: 4 bytes a texel
    assert lc["memory_bytes"] == 4 * (960 * 540 + sum(w * h for w, h in sizes) + sum(w * h for w, h in sizes[:-1])), lc


def test_software_gl_runs_bloom(frames: dict) -> None:
    """CI's llvmpipe runs these tests: bloom runs there (it isn't bypassed), with the same results."""
    assert frames["village"]["warm"]["passes"] == 11, frames["gl"]


def test_studio_glows_its_view_at_once_and_not_its_lines(studio: dict) -> None:
    s = studio["subtle"]
    assert s["stored"] == {"preset": "subtle"} and s["stage"] == "composite" and s["renderer_preset"] == "subtle", s
    assert 0.001 < s["changed_share"] < 0.2 and s["made"], s  # (around the two lamp heads only)
    assert s["fields"] == ["bloom_strength", "bloom_threshold", "bloom_spread"], s
    lines = studio["lines"]
    assert lines["after_calls"] and all(c == "composite" for c in lines["after_calls"]), lines
    assert lines["same_share"] >= 0.98 and lines["unglowing_px"] > 1000, lines
    # where nothing glows, the same line pixels: within 1 level (bloom off draws them into the world before the blit,
    # on lays them over the picture after the composite: two blends, one rounding apart)
    assert lines["unglowing_max_diff"] <= 1, lines


def test_studio_s_view_and_the_game_s_path_are_one_picture(studio: dict) -> None:
    p = studio["parity"]
    assert p["same"] and p["stage"] == "composite" and p["bloom"][0] == p["bloom"][1], p


def test_studio_s_fields_refuse_bad_values_undo_redo_and_off(studio: dict) -> None:
    typed = {"preset": "subtle", "strength": 2.5, "threshold": 0.05, "spread": 0.6}
    assert studio["typed"] == typed and studio["op_parity"], studio
    assert studio["typed_view"]["changed_share"] > studio["subtle"]["changed_share"], studio
    for key in ("too_strong", "not_a_number"):
        assert studio[key]["stored"] == typed and not studio[key]["ok"], (key, studio[key])
    assert studio["undone"] == {"preset": "subtle", "strength": 2.5, "threshold": 0.05}, studio["undone"]
    assert studio["undone_renderer"] == 0.5, studio  # (the view took the undo: the preset's spread again)
    assert studio["redone"] == typed, studio["redone"]
    assert studio["redone_renderer"] == {"strength": 2.5, "threshold": 0.05, "spread": 0.6}, studio
    assert studio["combined"] == {"stage": "composite", "post": "golden_hour", "haze": "evening", "bloom": "subtle"}
    off = studio["off"]
    assert off["stored"] is None and off["stage"] == "blit" and off["view_same_as_before"], off
    assert off["freed"] and off["objects_more"] <= 1, off  # (at most the shared composite's program, kept as ever)


def test_it_plays_saves_reopens_and_exports(studio: dict) -> None:
    play = studio["in_play"]
    assert play["preset"] == "warm" and play["stage"] == "composite" and play["bloom"]["passes"] == 11, play
    assert studio["in_the_saved_file"] == {"preset": "warm"} and studio["rest_of_the_room_unchanged"], studio
    assert studio["reopened"]["bloom"]["preset"] == "warm" and studio["reopened"]["renderer_preset"] == "warm"
    assert studio["reopened"]["unsaved"] == [], studio["reopened"]
    e = studio["export"]
    assert e["code"] == 0 and e["scene_setting"] == {"preset": "warm"}, e
    assert e["bundle_run"].get("preset") == "warm" and e["bundle_run"].get("stage") == "composite", e


def test_studio_shows_and_repairs_a_malformed_block(studio: dict) -> None:
    m = studio["malformed"]
    assert m["bloom_of"]["preset"] is None and "settings.hd2d.bloom.preset" in m["bloom_of"]["error"], m
    assert m["renderer_bloom"] is None and m["renderer_error"] and m["stage"] == "blit" and m["warning"], m
    r = m["repaired"]
    assert r["stored"] == {"preset": "subtle"} and r["renderer_preset"] == "subtle" and r["stage"] == "composite", r
    assert not r["warning"] and m["undone"] == {"preset": ["warm"], "strength": 1}, m


def test_one_strong_light_is_capped(frames: dict) -> None:
    c = frames["capped"]
    assert c["emission_max"] > c["cap"], c  # (lamp heads past the cap: the check means something)
    assert c["prefilter_luma_max"] <= c["cap"] + 1e-6 and c["level_luma_max"] <= c["cap"] * 1.02, c  # (luminance)
    assert c["prefilter_error"] <= 0.02 * max(1.0, c["prefilter_max"]), c


def test_spread_reaches_farther_holding_the_same_light(frames: dict) -> None:
    s = frames["spreads"]
    assert s["0.9"]["far_share"] > s["0.2"]["far_share"] + 0.2, s
    assert all(0.95 <= v["glow_over_passed"] <= 1.0001 for v in s.values()), s
