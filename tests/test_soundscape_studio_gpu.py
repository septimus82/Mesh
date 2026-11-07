"""Milestone 21B: a sound placed with Mesh Studio's own controls (hidden window, window input events like a person) is
heard in the game: the Sound panel, + Add sound, a click on the map, its sound chosen from Mesh's library (copied into
the project), its settings typed, dragged, undone and redone, rain and wind, saved, reopened; then Play: walking to it
it rises, walking away it falls; five Play/Stop cycles leave no player behind, and the editor is silent throughout.
Silent: the project's master volume is 0 (the backend plays; nothing reaches a speaker). GL-gated: MESH_GL_SMOKE=1."""

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


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import soundscape_studio

    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    out = tmp_path_factory.mktemp("soundscape")
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")  # never the checkout's own file
    try:
        soundscape_studio.setup2d(out)
        return soundscape_studio.studio2d(out)
    finally:
        os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)
        os.environ.pop("MESH_RUNTIME_SETTINGS_PATH", None)


def test_a_sound_is_placed_chosen_and_set_with_studios_controls(run: dict) -> None:
    assert run["panel"] == "sound" and run["selected_after_placing"] and run["picker"] == "pick_sound"
    assert run["copied_into_project"] and run["picked_by_clicking_its_marker"]
    assert run["create_undo_redo"] == [1, 0, 1]  # placing it: undone, redone
    assert run["property_undo_redo"] == [384.0, None, 384.0]  # its reach typed (12 m): undone to the default, redone
    assert run["set"] == {"sound": "assets/ambience/stream_loop.wav", "volume": 0.7, "distance": 256.0}
    assert [list(p) for p in run["move_undo_redo"]] == [[640.0, 192.0], [608.0, 128.0], [640.0, 192.0]]


def test_rain_and_wind_come_with_their_sounds(run: dict) -> None:
    weather = run["weather"]
    assert weather["rain"] == "steady" and weather["wind"]["speed"] == 3.0
    assert weather["sounds"]["rain"] == "assets/ambience/rain_loop.wav"
    assert weather["sounds"]["wind"] == "assets/ambience/wind_loop.wav"


def test_it_saves_and_reopens_as_it_was(run: dict) -> None:
    assert run["saved_message"].startswith("Saved")
    assert list(run["in_the_saved_file"]["emitters"][0][:2]) == [640.0, 192.0]
    assert run["reopened"]["same_emitters"] and run["reopened"]["unsaved"] == []


def test_the_editor_is_silent(run: dict) -> None:
    assert run["editing_registered_players"] == 0
    assert run["editing_after_authoring"] == {"registered_players": 0, "loops": {}}
    assert run["reopened"]["registered_players"] == 0


def test_walking_to_the_sound_it_rises_and_away_it_falls(run: dict) -> None:
    walk = run["play_stop"][0]["walk"]
    heard = [next((v for k, v in step["loops"].items() if k.startswith("emitter:")), 0.0) for step in walk]
    near = heard.index(max(heard))
    assert heard[0] == 0.0 and max(heard) > 0.2 and heard[-1] == 0.0
    assert walk[near]["x"] > walk[0]["x"] + 250  # loudest near it (it is at x 640)
    assert all(step["loops"].get("weather:rain", 0) > 0 for step in walk[4:])  # the rain heard (fading in at first)


def test_play_and_stop_leave_no_player_behind(run: dict) -> None:
    for cycle in run["play_stop"]:
        assert cycle["mode"] == "play" and cycle["registered"] >= 2  # rain and wind (and the stream, if near)
        assert cycle["after_stop"] == {"mode": "edit", "loops": {}, "registered": 0}
    assert run["after_close_registered"] == 0
