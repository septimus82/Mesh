"""Milestone 21C1: a sound behind a wall, in real (hidden) windows on the real audio backend.

``tooling/occlusion_demo.py`` makes two throwaway projects with Mesh's own authoring operations: the HD-2D starter
village with flowing water north of its cottage, and a 2D room with a hum behind a wall of tiles. Mesh Studio's own
"Quieter behind walls" switch is clicked, undone, redone, saved and reopened; the game is played from Studio and alone,
the player walking (arrow keys) from a clear line to behind the wall and back, and stepping in and out at its corner.
Silent: both projects' master volume is 0 (the backend plays every loop; nothing reaches a speaker).
GL-gated: MESH_GL_SMOKE=1."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from engine import optional_arcade
from engine.sound_emitters import OCCLUDED

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
    import occlusion_demo

    out = tmp_path_factory.mktemp("occlusion")
    # (for its run only, then as they were: absent stays absent, a value comes back, whatever the run did)
    with pytest.MonkeyPatch.context() as env:
        env.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")
        env.setenv("MESH_RUNTIME_SETTINGS_PATH", str(out / "user_settings.json"))  # never the checkout's own file
        made = occlusion_demo.setup(out)
        return {"made": made, "studio": occlusion_demo.studio(out), "walk": occlusion_demo.walk(out)}


def test_the_switch_is_in_the_sound_inspector_and_undoes_redoes_saves_and_reopens(run: dict) -> None:
    studio = run["studio"]
    assert run["made"]["hd2d"]["settings"]["occlusion"] is True  # set by the authoring operation (as an AI tool does)
    assert studio["inspector_shows_the_switch"]
    # as made (on); clicked off (no setting at all); on; undone; undone; redone; redone
    assert studio["clicked_off_on_undo_undo_redo_redo"] == [True, None, True, None, True, None, True]
    assert studio["message_off"] == "Heard the same through walls."
    assert studio["message_on"] == "Quieter while a wall is between it and the player."
    assert studio["saved_message"].startswith("Saved") and studio["in_the_saved_file"]["occlusion"] is True
    assert studio["reopened"] == {"setting": True, "unsaved": []}
    assert studio["editing_registered_players"] == 0  # the editor is silent


def _checks_of_the_cottage_walk(walk: dict) -> None:
    level, behind = walk["levels_at_marks"], walk["behind_walls_at_marks"]
    assert [behind[m] for m in ("clear", "behind", "deep", "behind_again", "clear_again", "end")] == \
        [False, True, True, True, False, False]
    assert level["clear"] > 0.5 and level["behind"] < level["clear"] * 0.5  # plainly quieter behind the cottage
    assert level["behind_again"] == pytest.approx(level["behind"], abs=0.02)  # the same place: the same loudness
    assert level["deep"] > level["behind"]  # nearer to it behind the cottage: louder (distance still counts)
    assert level["clear_again"] == pytest.approx(level["clear"], abs=0.02) and level["end"] == pytest.approx(level["clear"], abs=0.02)
    for i in range(3):  # three quick steps behind the corner and out
        assert behind[f"edge_in_{i}"] and not behind[f"edge_out_{i}"]
        assert level[f"edge_in_{i}"] < level[f"edge_out_{i}"] * 0.6
    pan = walk["pans_at_marks"]
    assert pan["clear"] < -0.5 and pan["clear"] < pan["behind"] < 0  # from the west throughout; less so behind it
    assert walk["largest_change_in_one_frame"] < 0.03  # no jump: a frame changes it by under 3 % of full
    assert walk["silent_frames_after_the_first_second"] == 0 and len(walk["loops_heard"]) == 1  # one loop, never cut
    assert 0 < walk["wall_questions_asked"] < walk["frames"] / 4  # asked as the player moves, not every frame


def test_played_from_studio_it_is_quieter_behind_the_cottage_and_returns(run: dict) -> None:
    first = run["studio"]["play_stop"][0]
    assert first["mode"] == "play"
    _checks_of_the_cottage_walk(first["walk"])


def test_play_and_stop_leave_no_player_behind(run: dict) -> None:
    for cycle in run["studio"]["play_stop"]:
        assert cycle["playing"]["registered"] == 1 and len(cycle["playing"]["loops"]) == 1  # one loop, one player
        assert cycle["after_stop"] == {"mode": "edit", "loops": {}, "registered": 0}
    assert run["studio"]["after_close_registered"] == 0


def test_in_the_game_alone_the_hd2d_walk_is_the_same(run: dict) -> None:
    walk = run["walk"]["hd2d"]
    assert walk["hd2d"] and walk["hd2d_error"] is None
    _checks_of_the_cottage_walk(walk)
    assert walk["levels_at_marks"] == run["studio"]["play_stop"][0]["walk"]["levels_at_marks"]  # as from Studio
    assert walk["players_registered_while_playing"] == 1 and walk["players_registered_after_close"] == 0


def test_in_a_2d_room_a_wall_of_tiles_does_the_same(run: dict) -> None:
    walk = run["walk"]["2d"]
    assert not walk["hd2d"]
    level, behind = walk["levels_at_marks"], walk["behind_walls_at_marks"]
    assert (behind["clear"], behind["behind"], behind["clear_again"]) == (False, True, False)
    volume = run["made"]["2d"]["settings"]["volume"]  # (both places are within its full-strength radius)
    assert level["clear"] == pytest.approx(volume, abs=0.02) and level["clear_again"] == pytest.approx(volume, abs=0.02)
    assert level["behind"] == pytest.approx(volume * OCCLUDED, abs=0.02)
    assert walk["largest_change_in_one_frame"] < 0.03 and walk["silent_frames_after_the_first_second"] == 0
    assert walk["players_registered_while_playing"] == 1 and walk["players_registered_after_close"] == 0
