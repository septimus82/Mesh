"""M17-W1: a waterfall in real frames and in Mesh Studio (hidden windows; the glen of tooling/w1_waterfall_study.py,
measured by tooling/w1_waterfall_checks.py). GL-gated: MESH_GL_SMOKE=1.

- The curtain is drawn between its lip and its foot, its streaks move down it (the same time: the same frame), the
  cliff top hides it from behind (and only the depth test does), a character in front of it hides it.
- Foam at its foot (none with foam 0), none far out in the pond; spray made only when asked for, about its foot.
- It adds two draws (the curtain, the spray), nothing is allocated a frame, nothing drawn out of the picture, all of it
  freed when it's gone; with the room's haze and bloom the water writes no emission (the lamps do).
- The player walking down the stream stops at its lip (never drops down the fall), and across the pool stops short of
  its foot.
- Studio: a waterfall made, joined to the pond, carved, tuned, refused (the river as it was), undone and redone, the
  view the game's own, saved, reopened, played, stopped; removing it refused while the pond needs it, then removed
  and freed; the exported game draws it.
"""

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
    pytest.mark.filterwarnings("ignore:.*style dict.*:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


def _keep(name: str, found: dict) -> None:
    keep = REPO / "artifacts" / "river_falls"
    keep.mkdir(parents=True, exist_ok=True)
    (keep / f"{name}_{sys.platform}.json.log").write_text(json.dumps(found, indent=1, default=str), encoding="utf-8")


@pytest.fixture(scope="module")
def frames(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import w1_waterfall_checks

    found: dict = w1_waterfall_checks.frames(tmp_path_factory.mktemp("falls"))
    _keep("frames", found)
    return found


@pytest.fixture(scope="module")
def studio(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import w1_waterfall_checks

    out = tmp_path_factory.mktemp("falls_studio")
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    try:
        found: dict = w1_waterfall_checks.studio(out)
    finally:
        os.environ.pop("MESH_RUNTIME_SETTINGS_PATH", None)
        os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)
    _keep("studio", found)
    return found


def test_the_curtain_is_drawn_from_lip_to_foot_and_its_streaks_move_down(frames: dict) -> None:
    assert frames["errors"] == {"hd2d": None, "water": None, "rivers": None}, frames["errors"]
    c = frames["curtain"]
    assert c["foot_px"][1] - c["lip_px"][1] > 100, c
    assert c["between_lip_and_foot"] > 0.9, ("the curtain covers the drop", c)
    m = frames["motion"]
    assert m["still_same"], "the same time: the same frame"
    assert all(s > 0 for s in m["shifts_down_px"]), ("each frame's streaks lower than the last's", m)
    a = frames["above_the_lip"]
    assert a["changed_by_the_join"] == 0 and a["near_the_shore_changed"] == 0 and a["near_joined"], (
        "the stream above it isn't eased to the pond's", a)


def test_the_cliff_hides_it_from_behind_and_a_character_in_front_hides_it(frames: dict) -> None:
    b = frames["behind"]
    assert b["changed_depth_tested"] < 0.6 * b["changed_no_depth_test"], ("the cliff top hides most of it", b)
    f = frames["in_front"]
    assert f["body_pixels"] > 500 and f["curtain_behind_it"] > 0.9 * f["body_pixels"], f
    assert f["changed_by_the_fall"] == 0, ("nothing of the curtain over the character", f)


def test_foam_at_its_foot_none_far_out_and_spray_only_when_asked(frames: dict) -> None:
    f = frames["foam"]
    assert f["lighter_near"] > 0.25 * f["near_pixels"] and f["lighter_near_foam0"] < 0.02 * f["near_pixels"], f
    assert f["lighter_in_pond"] > 0.15 * f["pond_pixels"] and f["lighter_in_pond_foam0"] < 0.02 * f["pond_pixels"], (
        "the pond it lands in foams too", f)
    assert f["far_changed"] == 0, ("none far out in the pond", f)
    s = frames["spray"]
    assert not s["made_when_none"] and s["made_when_asked"] and s["pixels"] > 100, s
    x0, y0, x1, y1 = s["box"]
    fx, fy = s["foot_px"]
    assert x0 < fx < x1 and y0 - 80 < fy < y1 + 40, ("about its foot", s)


def test_two_draws_nothing_allocated_a_frame_none_out_of_the_picture_all_freed(frames: dict) -> None:
    d = frames["draws"]
    assert d["falls"] == d["plain"] + 2, d
    assert d["made_in_20_frames"] == {"buffer": 0, "texture": 0, "framebuffer": 0, "program": 0}, d
    assert d["fall_buffers_made_in_20_frames"] == 0, d
    a = frames["away"]
    assert a["water_draws"] == 0 and a["spray_draws"] == 0, a
    g = frames["gone"]
    assert not g["fall_program"] and not g["fall_buffers"] and not g["spray"], g
    assert g["objects"] == g["objects_plain"], g


def test_with_haze_and_bloom_the_water_writes_no_emission(frames: dict) -> None:
    hb = frames["haze_bloom"]
    assert hb["stage"] == "composite" and hb["haze"] == "evening" and hb["bloom"] is not None, hb
    assert hb["room_emission_max"] > 0.5 and hb["curtain_emission_max"] == 0.0, hb
    assert hb["fall_count"] > 0, hb


def test_the_player_neither_walks_into_the_fall_nor_drops_down_it(frames: dict) -> None:
    w = frames["walks"]
    above, below = w["from_above"], w["from_below"]
    assert above["y"] >= w["lip_y"] - 1.0, ("stopped at its lip", above)
    assert above["lowest"] >= above["start"][2] - 0.1, ("never dropped down it", above)
    assert below["y"] <= w["foot_y"] + 1.0 and below["y"] > below["start"][1] + 32, ("across the pool to its foot",
                                                                                     below)
    assert not w["falling_at_end"]


def test_studio_makes_joins_carves_and_tunes_a_waterfall(studio: dict) -> None:
    assert studio["selected"] == {"point": 2, "button": True}, studio["selected"]
    m = studio["made"]
    assert m["stored"] == [{"from": 2}] and m["steps"] == 1 and m["curtain_drawn"], m
    assert m["renderer_falls"] == [{"start": 2, "foam": 0.6, "spray": 0.4}], m
    assert m["fields"] == ["river_fall_below", "river_fall_foam", "river_fall_spray"], m
    assert studio["joined"]["mouth"] == "auto" and studio["joined"]["steps"] == 2, studio["joined"]
    c = studio["carved"]
    assert c["lowered"] > 50 and c["falls"] == [{"from": 2}] and c["mouth"] == "auto" and c["curtain_drawn"], c
    t = studio["tuned"]
    assert t["stored"] == [{"from": 2, "foam": 0.3, "spray": 0.0}] and t["steps"] == 5 and not t["spray_made"], t


def test_studio_refuses_impossible_changes_keeping_the_last_valid_river(studio: dict) -> None:
    r = studio["refused"]
    assert r["points_same"] and not r["ok"] and r["held"] and r["steps"] == 5, r
    assert "drops 0.25 m: a waterfall drops at least 0.5 m" in r["message"], r
    assert studio["insert_refused"]["points"] == 5 and "top and foot" in studio["insert_refused"]["message"]
    rn = studio["renumbered"]
    assert rn["inserted"] == [{"from": 3, "foam": 0.3, "spray": 0.0}] and rn["points"] == 5, rn
    assert rn["removed"] == [{"from": 2, "foam": 0.3, "spray": 0.0}], rn
    assert studio["reverse_refused"]["first"] and "fall upwards" in studio["reverse_refused"]["message"]
    rr = studio["remove_refused"]
    assert rr["falls"] and "meets the pond" in rr["message"], ("the pond needs it", rr)


def test_studio_undo_redo_parity_save_reopen_play_stop_remove_export(studio: dict) -> None:
    assert studio["undone"] == [{"from": 3, "foam": 0.3, "spray": 0.0}], ("the point removed, put back",
                                                                         studio["undone"])
    assert studio["redone"] == [{"from": 2, "foam": 0.3, "spray": 0.0}], studio["redone"]
    assert studio["parity"]["same"], ("Studio's view is the game's own picture", studio["parity"])
    assert studio["reopened_same"]
    p = studio["play"]
    assert p["mode"] == "play" and p["curtain_drawn"] and p["feet"] == 1 and p["water_time"] > 0.3, p
    assert p["falls"] == [{"start": 2, "foam": 0.3, "spray": 0.6}], p
    assert studio["stopped"] == {"mode": "edit", "same": True}
    assert studio["removed"] == {"falls": None, "fall_program": False, "spray": False}, studio["removed"]
    e = studio["export"]
    assert e["code"] == 0 and e["same_rivers"], e
    assert e["bundle_run"].get("falls") == [1] and e["bundle_run"].get("fall_count", 0) > 0, e
    assert "export" in e["bundle_run"]["engine_from"], ("the bundle's own engine", e)
