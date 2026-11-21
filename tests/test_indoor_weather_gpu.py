"""Milestone 21C2: the weather outside heard from indoors, in real (hidden) windows on the real audio backend.

``tooling/indoor_weather_demo.py`` takes the HD-2D starter game as its template makes it (a village, and its
cottage's inside: an indoor room) and, by Mesh Studio's own controls, gives the village rain and wind, turns on the
cottage's "Hear outside weather indoors" (told why nothing is heard while it has no weather set), sets its rain and
wind, undoes, redoes, saves and reopens. The game is then played from Studio and alone: the player walks in through
the cottage's door and out again; a save is made indoors and loaded; a game is started in the cottage.
Silent: the project's master volume is 0 (the backend plays every loop; nothing reaches a speaker).
GL-gated: MESH_GL_SMOKE=1."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from engine import optional_arcade
from engine.sound_emitters import INDOORS

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
RAIN, WIND = "assets/ambience/rain_loop.wav", "assets/ambience/wind_loop.wav"
RAIN_OUT = 0.6  # steady rain at the rain sound's own volume


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import indoor_weather_demo

    out = tmp_path_factory.mktemp("indoor_weather")
    # (for its run only, then as they were: absent stays absent, a value comes back, whatever the run did)
    with pytest.MonkeyPatch.context() as env:
        env.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")
        env.setenv("MESH_RUNTIME_SETTINGS_PATH", str(out / "user_settings.json"))  # never the checkout's own file
        made = indoor_weather_demo.setup(out)
        return {"made": made, "studio": indoor_weather_demo.studio(out), "walk": indoor_weather_demo.walk(out)}


def test_the_sound_panel_says_what_each_room_hears(run: dict) -> None:
    studio = run["studio"]
    assert run["made"]["rooms"] == ["Village", "Cottage"]
    village = studio["village"]
    assert village["rain"] == "steady" and village["sounds"]["rain"] == RAIN and village["sounds"]["wind"] == WIND
    assert village["says"].startswith("Outdoors") and village["says_it_on_screen"]
    assert village["outdoors_switch"] and not village["indoor_switch_shown"]  # an outdoor room is not offered it
    cottage = studio["cottage_as_made"]
    assert cottage["indoor"] and cottage["rain_label"] and cottage["outdoors_switch"] and cottage["indoor_switch"]
    assert "Turn on Hear outside weather indoors" in cottage["says"] and cottage["says_it_on_screen"]


def test_turned_on_with_no_weather_set_it_says_why_nothing_is_heard(run: dict) -> None:
    on = run["studio"]["on_with_nothing_set"]
    assert on["setting"] is True and on["message"] == "The weather outside is heard in here, quietly."
    assert on["says"] == ("Nothing will be heard from outside yet: this room has no rain or wind set, so there is no "
                          "weather outside to hear.") and on["says_it_on_screen"]


def test_rain_and_wind_set_in_the_cottage_are_its_weather_outside(run: dict) -> None:
    studio = run["studio"]
    cottage = studio["cottage_set"]
    assert cottage["rain"] == "steady" and cottage["heard"] == {"rain": True, "wind": True}
    assert cottage["sounds"]["indoors"] is True and cottage["copied_into_project"] == [True, True]
    assert cottage["says"] == "Indoors: the rain and wind set here are heard quietly, as the weather outside."
    assert cottage["says_it_on_screen"]
    # on; clicked off (no setting at all); undone; redone; undone
    assert studio["on_clicked_off_undo_redo_undo"] == [True, None, True, None, True]
    assert studio["message_off"] == "Indoors as before: no rain is heard in here."
    assert studio["saved_message"].startswith("Saved")
    assert studio["in_the_saved_file"] == {"weather_exposure": "indoor",
                                           "weather_sounds": {"rain": RAIN, "wind": WIND, "indoors": True}}
    assert studio["reopened"]["setting"] is True and studio["reopened"]["unsaved"] == []
    assert studio["editing_registered_players"] == 0  # the editor is silent


def _checks_of_the_walk(walk: dict) -> None:
    at = walk["at_marks"]
    assert [at[m]["room"] for m in ("outside", "at_the_door", "inside", "inside_later", "outside_again")] == \
        ["start.json", "start.json", "cottage.json", "cottage.json", "start.json"]
    assert at["outside"]["rain_on_screen"] == 1 and at["inside"]["rain_on_screen"] == 0  # no rain falls in the cottage
    assert at["outside"]["rain"] == pytest.approx(RAIN_OUT, abs=0.02) and at["outside"]["wind"] > 0.2
    for mark in ("inside", "inside_later"):
        assert at[mark]["rain"] == pytest.approx(RAIN_OUT * INDOORS, abs=0.01)  # the same rain, quietly
        assert 0.03 < at[mark]["wind"] < at["outside"]["wind"] * 0.6  # the wind too (it gusts: no one number)
    assert at["outside_again"]["rain"] == pytest.approx(RAIN_OUT, abs=0.02) and at["outside_again"]["wind"] > 0.2
    assert max(walk["largest_change_in_one_frame"].values()) < 0.02  # no jump at either door
    assert walk["lowest_after_the_first_three_seconds"]["rain"] > 0.15  # never cut
    assert walk["lowest_after_the_first_three_seconds"]["wind"] > 0.03
    assert walk["loops_heard"] == ["weather:rain", "weather:wind"] and walk["most_players_registered"] == 2


def test_played_from_studio_the_weather_follows_in_through_the_door_and_out(run: dict) -> None:
    first = run["studio"]["play_stop"][0]
    assert first["mode"] == "play" and first["started_in"] == "start.json"
    _checks_of_the_walk(first["walk"])


def test_play_and_stop_leave_no_player_behind_wherever_the_play_test_starts(run: dict) -> None:
    cycles = run["studio"]["play_stop"]
    assert [c["started_in"] for c in cycles] == ["start.json", "start.json", "cottage.json"]
    for cycle in cycles:
        assert cycle["playing"] == {"loops": ["weather:rain", "weather:wind"], "registered": 2}
        assert cycle["after_stop"] == {"mode": "edit", "loops": {}, "registered": 0}
    started_inside = cycles[2]["settled"]
    assert started_inside["rain_on_screen"] == 0 and started_inside["rain"] == pytest.approx(RAIN_OUT * INDOORS, abs=0.01)
    assert run["studio"]["after_close_registered"] == 0


def test_the_switch_off_is_the_cottage_as_it_was(run: dict) -> None:
    off = run["studio"]["switched_off"]
    assert off["setting"] is None and off["played"]["rain"] == 0.0 and off["loops"] == ["weather:wind"]
    assert "no rain falls or is heard in here" in off["says"]


def test_in_the_game_alone_the_walk_a_save_made_indoors_and_a_start_indoors_agree(run: dict) -> None:
    walk = run["walk"]
    _checks_of_the_walk(walk["walk"])
    saved = walk["save_made_indoors"]
    assert saved["outside_before_loading"]["rain"] == pytest.approx(RAIN_OUT, abs=0.02)
    for heard in (saved["inside_before_saving"], saved["after_loading"], walk["started_indoors"]):
        assert heard["rain_on_screen"] == 0 and heard["rain"] == pytest.approx(RAIN_OUT * INDOORS, abs=0.01)
        assert 0.03 < heard["wind"] < 0.25
    assert saved["registered"] == 2 and walk["started_indoors"]["registered"] == 2
    assert walk["registered_after_close"] == 0 and walk["registered_after_second_close"] == 0
