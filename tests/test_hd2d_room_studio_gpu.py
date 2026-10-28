"""Milestone 22A: an HD-2D room made with Mesh Studio's own controls (hidden window, window input events like a
person) in a 2D starter project: + New room > HD-2D, 40 x 30 m, outdoors (the starter kit comes in); Camera and
sun...: Wide, pitch 38, See it; Evening, the sun from 260, undo and redo; saved, reopened; in play the game's camera
and sun are what was set. GL-gated: MESH_GL_SMOKE=1."""

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
    import hd2d_room_studio

    out = tmp_path_factory.mktemp("m22a")
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    try:
        return hd2d_room_studio.studio(out, full=False)
    finally:
        os.environ.pop("MESH_RUNTIME_SETTINGS_PATH", None)
        os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)


def test_an_hd2d_room_is_made_in_studio_with_its_size_and_the_kit(run: dict) -> None:
    created = run["created"]
    assert not run["kit_before"] and created["kit_now"] and created["hd2d_view"]
    assert created["room"] == "meadow" and created["ground_to"] == [1280.0, 960.0]
    assert "starter kit" in created["message"]


def test_the_game_camera_and_sun_are_set_and_seen_in_studio(run: dict) -> None:
    assert run["panel"] == "environment"
    assert run["camera"]["view"] == pytest.approx(18.0) and run["camera"]["pitch"] == 38.0
    assert run["see_it_editor_camera"] == {"pitch": 38.0, "fov": 12.0, "distance": run["camera"]["distance"]}
    assert run["sun"]["azimuth"] == 260.0 and run["sun"]["color"] == "#ffb070"
    assert run["sun_set_undo_redo"] == [260.0, 250.0, 260.0]
    assert run["view_renderer"]["camera"]["pitch"] == 38.0 and run["view_renderer"]["sun_intensity"] == 0.85


def test_it_saves_reopens_and_plays_as_set(run: dict) -> None:
    assert run["saved"].startswith("Saved") and run["reopened"] == {"same": True, "unsaved": []}
    play = run["in_play"]
    assert play["mode"] == "play" and play["camera"] == run["view_renderer"]["camera"]
    assert play["sun"] == run["view_renderer"]["sun"] and play["ambient"] == run["view_renderer"]["ambient"]
