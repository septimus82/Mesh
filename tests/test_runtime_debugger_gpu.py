"""D1 (#422): an AI debugs a Mesh Studio play-test through MCP, in a real hidden window (tooling/d1_debug_scenario.py).

Mesh Studio opens a disposable project with its live session on; the MCP tools are called on another thread while
the window keeps running, so Studio answers from its main thread. Checked: the refusals (not allowed yet; the person
typing in a box, which is left as typed), Play and Play again, snapshots of the real room, player, flags, quests and
events, a conversation played with the game's own keys changing a flag (and the snapshot showing it with the events
that did it), a door into the second room, reading changing nothing, Stop and Stop again, Studio back to editing with
the person's unsaved work and no file changed, and no session once Studio closes. Silent. GL-gated: MESH_GL_SMOKE=1.
"""

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
    import d1_debug_scenario

    out = tmp_path_factory.mktemp("d1")
    # (for its run only, then as it was: absent stays absent, a value is left as it is and comes back)
    with pytest.MonkeyPatch.context() as env:
        if "MESH_RUNTIME_SETTINGS_PATH" not in os.environ:
            env.setenv("MESH_RUNTIME_SETTINGS_PATH", str(out / "user_settings.json"))
        return d1_debug_scenario.run(out)


def test_editing_is_not_playing_and_play_needs_the_persons_permission(run: dict) -> None:
    assert run["1_editing"]["status"] == "not_playing" and run["1_editing"]["studio"]["mode"] == "editing"
    assert run["2_refused"]["ok"] is False and run["2_refused"]["reason"] == "playtest_control_off"
    assert run["2_allowed"] == {"playtest_control": True, "shown": True}  # (the AI panel's switch, clicked)
    assert run["3_busy"]["ok"] is False and run["3_busy"]["reason"] == "studio_busy"
    assert run["3_box_kept"]["text"].endswith(" the Elder") and run["3_box_kept"]["mode"] == "edit"


def _quest(snap: dict) -> dict:
    return next(q for q in snap["quests"]["quests"] if q["id"] == "light_the_lantern")


def _agrees(reported: dict, runtime_quests: dict) -> bool:
    """The debugger's quest is the running game's own record of it, field for field."""
    runtime = runtime_quests["light_the_lantern"]
    return {k: reported[k] for k in runtime} == runtime and reported["auto_start"] is True


def test_play_starts_once_and_the_snapshot_shows_the_running_room_and_player(run: dict) -> None:
    import d1_debug_scenario as scenario

    started, again, snap = run["4_started"], run["4_again"], run["4_snapshot"]
    assert started["status"] == "playing" and started["playtest"]["started_by"] == "ai"
    assert again["status"] == "already_playing" and again["playtest"]["id"] == started["playtest"]["id"]
    assert snap["status"] == "playing" and snap["playtest"]["id"] == started["playtest"]["id"]
    assert snap["scene"]["room"]["key"] == "start" and snap["scene"]["path"] == "packs/core_regions/scenes/start.json"
    assert snap["player"]["available"] and (snap["player"]["x"], snap["player"]["y"]) == (128.0, 128.0)
    # Not agreed yet; other flags the engine sets itself (the HUD's "hint_shown_quest_log") don't matter here.
    assert not snap["game_state"]["flags"].get(scenario.FLAG)
    assert snap["studio"]["unsaved_changes"] is True  # (the person's Sign: Studio's, not the game's)
    # The auto_start quest started with the play-test (#446), and that is the only event so far.
    reported = _quest(snap)
    assert (reported["status"], reported["current_stage"], reported["completed_stages"]) == ("active", "agree", [])
    assert _agrees(reported, run["4_runtime_quests"])
    assert [(e["type"], e["payload"]["stage_id"]) for e in snap["events"]["items"]] == [("quest_stage_started", "agree")]
    assert snap["events"]["made_this_playtest"] == 1


def test_a_conversation_sets_the_flag_and_the_next_snapshot_shows_it_and_why(run: dict) -> None:
    import d1_debug_scenario as scenario

    assert run["5_talk"]["said"][-1].startswith("Thank you!")
    snap = run["6_snapshot"]
    assert snap["game_state"]["flags"].get(scenario.FLAG) is True  # (other engine flags may be set too)
    assert snap["player"]["x"] > run["4_snapshot"]["player"]["x"]  # (it walked to the Guide)
    events = snap["events"]["items"]
    assert [e["seq"] for e in events] == sorted(e["seq"] for e in events)
    choice = next(e for e in events if e["type"] == "dialogue_choice")
    assert choice["entity"] == "Guide" and choice["payload"]["choice_id"] == "help"
    assert [e["type"] for e in events if e["type"].startswith("dialogue_")][:2] == ["dialogue_started", "dialogue_line"]
    assert snap["sequence"] > run["4_snapshot"]["sequence"] and snap["diagnostics"]["available"]
    # Agreeing completed the quest's "agree" stage and moved it on to "cellar" (#446), right after the choice.
    reported = _quest(snap)
    assert (reported["status"], reported["current_stage"], reported["completed_stages"]) == ("active", "cellar",
                                                                                              ["agree"])
    assert _agrees(reported, run["6_runtime_quests"])
    stages = [(e["type"], e["payload"].get("stage_id")) for e in events if e["type"].startswith("quest_")]
    assert stages == [("quest_stage_started", "agree"), ("quest_stage_completed", "agree"),
                      ("quest_stage_started", "cellar")]
    after_choice = [e["type"] for e in events if e["seq"] > choice["seq"]]
    assert after_choice.index("quest_stage_completed") < after_choice.index("quest_stage_started")


def test_a_door_moves_the_play_test_to_the_other_room(run: dict) -> None:
    assert run["7_moved"]["to"].endswith("cellar.json")
    snap = run["7_snapshot"]
    assert snap["scene"]["room"]["key"] == "cellar" and snap["player"]["available"]
    assert snap["events"]["items"][-1]["type"] == "scene_transition"
    assert snap["game_state"]["flags"] == run["6_snapshot"]["game_state"]["flags"]  # (the game goes on)


def test_reading_changes_nothing(run: dict) -> None:
    assert run["read_changes_nothing"] == {"unchanged": True}


def test_stop_returns_to_editing_with_the_persons_work_as_it_was(run: dict) -> None:
    assert run["8_stopped"]["status"] == "stopped" and run["8_stopped"]["editing"]["unsaved_changes"] is True
    assert run["8_stopped"]["playtest"]["id"] == run["4_started"]["playtest"]["id"] and run["8_stopped"]["playtest"]["stopped_at"]
    assert run["8_again"]["status"] == "not_playing"
    assert run["8_snapshot"]["status"] == "not_playing" and run["8_snapshot"]["last_playtest"]["stopped_at"]
    assert run["9_editing"] == {"mode": "edit", "room": "start", "same_room": True, "unsaved": True, "sign_kept": True,
                                "files_unchanged": True, "flags_after_stop": {}}
    assert run["9_closed"]["reason"] == "studio_not_open"
    assert run["nothing_secret"] == {"token": True, "project_folder": True}
