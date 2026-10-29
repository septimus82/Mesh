"""Milestone 23D: the starting room and room music authored in Mesh Studio with its own input events, in hidden
windows (tooling/m23d_start_music_studio.py), and played: Village made the start room (undo, redo, after Save,
reopened); Track A imported into assets/music, a room carrying on and a room silent, kept apart through saving and
reopening; the editor silent and F4 testing the room being edited; a new game starting in Village and the music through
the doors (Track A carries on into Woodland unrestarted, stops in Ruins, plays again in Village); an existing save
loading where it was made; an older project's states kept. Silent. GL-gated: MESH_GL_SMOKE=1."""

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
TRACK_A = "assets/music/forest_theme.wav"


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import m23d_start_music_studio as study

    out = tmp_path_factory.mktemp("m23d")
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    try:
        return {"out": out, **{name: study.PHASES[name](out) for name in ("creator", "game", "saves")}}
    finally:
        os.environ.pop("MESH_RUNTIME_SETTINGS_PATH", None)
        os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)


def test_village_is_made_the_start_room_without_leaving_the_room_being_edited(run: dict) -> None:
    creator = run["creator"]
    assert creator["made"]["start_scene"] == "start" and creator["village_offered"]
    assert creator["set_village"]["start"] == creator["set_village"]["editing"] == "village"
    assert creator["set_village"]["dirty"] and "New games start in: Village" in creator["set_village"]["rows"]


def test_the_start_room_undoes_redoes_saves_and_reopens(run: dict) -> None:
    steps = run["creator"]["woodland_start"]
    assert steps["set"] == ("woodland", "woodland") and steps["undo"] == ("village", "woodland")
    assert steps["redo"] == ("woodland", "woodland") and steps["saved"] == "woodland"
    assert steps["undo_after_save"] == ("village", True) and steps["saved_again"] == "woodland"
    assert run["creator"]["reopened_woodland"]["start"] == "woodland"
    assert run["creator"]["final"]["start_scene"] == "village"


def test_the_three_music_states_stay_apart_through_save_and_reopen(run: dict) -> None:
    creator = run["creator"]
    assert creator["picker"] == {"panel": "pick_sound", "has_import": True}
    assert creator["village_music"]["room"] == {"mode": "track", "path": TRACK_A} and creator["village_music"]["imported_file"]
    assert creator["woodland_music"]["after_silence"]["mode"] == "silence"
    assert creator["woodland_music"]["after_continue"]["mode"] == "continue"
    assert creator["saved"] == {"start_scene": "village", "village": TRACK_A, "woodland": "(none)", "ruins": None}
    assert {k: v["mode"] for k, v in creator["reopened"]["rooms"].items()} == \
        {"village": "track", "woodland": "continue", "ruins": "silence"}
    assert creator["reopened"]["unsaved"] is False


def test_the_editor_is_silent_and_f4_tests_the_room_being_edited(run: dict) -> None:
    creator = run["creator"]
    for audio in (creator["before"]["audio"], creator["editing_audio"], creator["after_stop_audio"]):
        assert audio["music"] is None and audio["live_players"] == 0 and audio["scene_music"] is False
    play = creator["play_ruins"]
    assert play["mode"] == "play" and play["room"].endswith("ruins.json") and play["audio"]["music"] is None
    assert play["audio"]["master"] == 0.0
    village = creator["play_village"]  # (Play parity: the play-test plays the room's track, as the game does)
    assert village["mode"] == "play" and village["room"].endswith("village.json")
    assert village["audio"]["music"] == TRACK_A and village["audio"]["live_players"] == 1
    assert village["after_stop"]["music"] is None and village["after_stop"]["live_players"] == 0


def test_a_new_game_starts_in_village_and_the_music_follows_the_rooms(run: dict) -> None:
    game = run["game"]
    assert game["start_key"] == "village" and game["room"].endswith("village.json")
    route = game["route"]
    village, later = route["village"], route["village_1s_later"]
    assert village["music"] == TRACK_A and later["played_s"] > village["played_s"]
    assert route["woodland_arrived"] and route["woodland"]["music"] == TRACK_A
    assert route["woodland"]["track_id"] == village["track_id"] and route["woodland"]["player_id"] == village["player_id"]
    assert route["woodland_1s_later"]["played_s"] > later["played_s"]  # (carried on: never restarted)
    assert route["ruins_arrived"] and route["ruins"]["music"] is None and route["ruins"]["live_players"] == 0
    assert route["village_again_arrived"] and route["village_again"]["music"] == TRACK_A
    assert route["village_again_1s_later"]["played_s"] > 0


def test_an_existing_save_loads_where_it_was_made_after_the_start_room_changes(run: dict) -> None:
    saves = run["saves"]
    assert saves["travelled"] and saves["save_ok"] and saves["saved_in"].endswith("woodland.json")
    assert saves["studio_start"] == "ruins" and saves["slot_untouched_by_studio"]
    assert saves["new_game_starts_in"] == "ruins" and saves["new_game_room"].endswith("ruins.json")
    assert saves["loaded"] and saves["slot_records"].endswith("woodland.json") and saves["loaded_is_hd2d"]
    assert saves["loaded_room_objects"] and all(i.startswith("woodland_") for i in saves["loaded_room_objects"])
    assert saves["save_music"]["music"] == TRACK_A and saves["start_back"] == "village"


def test_an_older_projects_absent_and_null_music_and_missing_start_room_are_kept(
        tmp_path_factory: pytest.TempPathFactory) -> None:
    import m23d_start_music_studio as study

    out = tmp_path_factory.mktemp("m23d_older")
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    try:
        report = study.older(out)
    finally:
        os.environ.pop("MESH_RUNTIME_SETTINGS_PATH", None)
        os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)
    assert report["before"]["start_scene"] == "(none)" and report["dirty_on_open"] is False
    assert any(line.startswith("This world names no starting room") and "Start" in line for line in report["rows"])
    assert report["after"] == {"start_scene": "(none)", "village": TRACK_A, "woodland": "(none)", "ruins": None}
    assert {k: v["mode"] for k, v in report["reopened"].items()} == \
        {"village": "track", "woodland": "continue", "ruins": "silence"}
