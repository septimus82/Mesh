"""Milestone 23B: campfires on the GPU, in hidden windows (tooling/m23b_fire_study.py): the light a fire adds to the
ground, a tree and the cottage's wall (none once it is put out), its flames leaning in gusts, a fire behind the
cottage hidden by it until the camera turns, and Mesh Studio placing, editing, saving, reopening and playing one with
its own events, silently. GL-gated: MESH_GL_SMOKE=1."""

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
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


@pytest.fixture(autouse=True)
def _settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESH_RUNTIME_SETTINGS_PATH", str(tmp_path / "user_settings.json"))
    monkeypatch.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")


def test_a_fire_lights_the_ground_a_tree_and_a_wall_and_none_once_put_out(tmp_path: Path) -> None:
    import m23b_fire_study as study

    report = study.light(tmp_path)
    assert report["lamps_lit"] == 1 and report["lamps_out"] == 0
    for spot, (r, _g, b) in report["added"].items():  # (the tree is 3 m off, the wall 2 m, the ground 1.5 m)
        assert r >= (3 if spot == "tree" else 12) and r > 2 * b, (spot, report["added"])  # (warm: red, little blue)
    flicker = report["flicker_terrain"]
    assert flicker["max"] - flicker["min"] > 1.0 and flicker["max"] / flicker["min"] < 1.35  # (moves, subtly)


def test_the_flames_lean_downwind_in_gusts_and_stand_in_still_air(tmp_path: Path) -> None:
    import m23b_fire_study as study

    report = study.states(tmp_path, clips=False)
    for when in ("day", "night"):
        calm, gusty = report[f"{when}_calm"]["lean"], report[f"{when}_gusty"]["lean"]
        assert abs(calm["mean_px"]) < 3.0, calm
        assert gusty["mean_px"] > calm["mean_px"] + 5.0 and gusty["spread_px"] > calm["spread_px"], (calm, gusty)  # (east)


def test_a_fire_behind_the_cottage_is_hidden_until_the_camera_turns(tmp_path: Path) -> None:
    import m23b_fire_study as study

    report = study.occlusion(tmp_path)
    assert report["yaw_0"] == 0 and report["yaw_30"] == 0, report  # (behind the cottage: its embers and smoke too)
    assert report["yaw_180"] > 300, report  # (from the north: in the open)


def test_studio_places_edits_saves_reopens_and_plays_a_campfire_silently(tmp_path: Path) -> None:
    import m23b_fire_study as study

    report = study.studio(tmp_path)
    assert report["objects_list_has_campfire"] and report["placed"]["enabled"]
    assert report["editing_preview"]["lamps"] == 1 and report["editing_preview"]["particle_draws"] == 2
    assert report["edited"] == {"enabled": True, "size": 1.3, "smoke": True, "light": 1.4, "light_radius": 224.0,
                                "sound": "assets/ambience/forest_loop.wav"}
    put_out = report["put_out"]
    assert put_out["lamps"] == 0 and put_out["particle_draws"] == 0 and put_out["crackle_enabled"] is False
    assert put_out["fire_draws"] == 1  # (its cold logs)
    assert report["saved_message"].startswith("Saved") and report["reopened"]["same"]
    assert report["reopened"]["unsaved"] == [] and report["reopened"]["lamps"] == 1
    for cycle in report["play_stop"]:
        assert cycle["mode"] == "play" and cycle["stopped"] == "edit" and cycle["campfires"] == 1
        assert cycle["lamps"] == 1 and cycle["fire_draws"] == 1 and cycle["master_volume"] == 0.0


def test_review_edges_a_bridge_fire_seventeen_fires_a_refused_gpu_and_eight_room_lamps(tmp_path: Path) -> None:
    import m23b_fire_study as study

    report = study.edges(tmp_path)
    bridge = report["bridge"]  # (on the deck, 2 m over the valley: not on the ground under it)
    assert bridge["logs_z_m"] == [bridge["deck_m"]] and bridge["anchors_z_m"] == [bridge["deck_m"]]
    assert bridge["lamps_z_m"] == [round(bridge["deck_m"] + 0.6, 3)] and bridge["ground_under_m"] < 0
    seventeen = report["seventeen"]  # (the sixteen put out don't crowd out the one lit)
    assert seventeen["registered"] == seventeen["logs"] == 17 and seventeen["flames"] == 1
    assert seventeen["lamps"] == 1 and len(seventeen["anchors_z_m"]) == 1
    refused = report["refused"]  # (no light without its fire)
    assert refused["refusals"] == 1 and all(f["lamps"] == 0 and f["logs"] == 0 and f["fire_error"]
                                            for f in refused["frames"])
    eight = report["eight_lamps"]  # (a documented limit: Studio says why the fire lights nothing)
    assert eight["room_lamps"] == 8 and "lights it can show" in eight["note"]
