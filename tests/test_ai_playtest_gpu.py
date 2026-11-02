"""D2 (#422): an AI plays a Mesh Studio play-test through MCP with the player's own controls, in a real hidden window
(tooling/d2_ai_playtest_scenario.py).

Checked:
- the permissions (none; play-tests only, which doesn't let it play; both) and the refusals for invalid requests
  and for what doesn't fit the screen;
- walking to the Guide by what the snapshots say, talking and choosing "I'll light it.": the flag, and the quest
  moving from agree to cellar with its events in order;
- lining up under the door and walking through it into the Cellar;
- a move cancelled, its key let go, when the person takes the permission back, and the next action refused;
- with no play-test, an action refused even when allowed;
- Studio back to editing with the person's unsaved work, no file changed and nothing proposed; no session once
  Studio closes.

Silent. GL-gated: MESH_GL_SMOKE=1.
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
    import d2_ai_playtest_scenario

    out = tmp_path_factory.mktemp("d2")
    os.environ.setdefault("MESH_RUNTIME_SETTINGS_PATH", str(out / "user_settings.json"))
    return d2_ai_playtest_scenario.run(out)


def _reason(answer: dict) -> str:
    return str(answer.get("reason"))


def test_playing_needs_its_own_permission(run: dict) -> None:
    assert _reason(run["1_editing_refused"]) == "gameplay_control_off"
    assert run["2_started"]["status"] == "playing"  # (play-tests allowed ...)
    assert _reason(run["2_move_refused"]) == "gameplay_control_off"  # (... which doesn't let it play)
    assert run["2_stopped"]["status"] == "stopped"
    assert run["3_allowed"] == {"playtest": True, "gameplay": True} and run["3_started"]["status"] == "playing"


def test_invalid_and_unfitting_actions_are_refused(run: dict) -> None:
    assert {k: _reason(v) for k, v in run["3_invalid"].items()} == {
        "unknown action": "invalid_action", "unknown direction": "invalid_action",
        "too many frames": "invalid_action", "advance with nothing said": "no_dialogue",
        "choose with no choices": "no_choices"}
    assert {k: _reason(v) for k, v in run["4_refused_in_dialogue"].items()} == {
        "move": "dialogue_open", "advance past the choice": "choice_needed",
        "a choice that isn't there": "choice_not_available", "interact again": "dialogue_open"}


def test_the_ai_walks_to_the_guide_talks_and_agrees(run: dict) -> None:
    walk = run["4_walk"]
    assert walk and walk[-1]["after"]["player"][0] > walk[0]["before"]["player"][0]  # (it walked right, to her)
    talk = run["4_interact"]["action"]
    assert talk["status"] == "done" and talk["dialogue"]["open"] and talk["dialogue"]["speaker"] == "Guide"
    assert [c["text"] for c in talk["dialogue"]["choices"]] == ["I'll light it.", "Not now."]
    chose = run["4_choose"]["action"]
    assert chose["status"] == "done" and chose["action"] == {"action": "choose", "choice": 0, "text": "I'll light it."}
    assert chose["dialogue"]["text"].startswith("Thank you!")
    assert run["4_advanced"] and run["4_advanced"][-1]["action"]["dialogue"] == {"available": True, "open": False}
    snap = run["4_snapshot"]
    assert snap["game_state"]["flags"].get("agreed_to_help") is True
    quest = next(q for q in snap["quests"]["quests"] if q["id"] == "light_the_lantern")
    assert (quest["status"], quest["current_stage"], quest["completed_stages"]) == ("active", "cellar", ["agree"])
    stages = [(e["type"], e["payload"].get("stage_id")) for e in snap["events"]["items"] if e["type"].startswith("quest_")]
    assert stages[-2:] == [("quest_stage_completed", "agree"), ("quest_stage_started", "cellar")]
    choice = next(e for e in snap["events"]["items"] if e["type"] == "dialogue_choice")
    assert choice["payload"]["choice_id"] == "help"


def test_the_ai_walks_through_the_door_into_the_cellar(run: dict) -> None:
    assert run["5_through"][-1]["scene"].endswith("cellar.json")
    assert all(step["scene"].endswith("start.json") for step in run["5_through"][:-1])
    snap = run["5_snapshot"]
    assert snap["scene"]["room"]["key"] == "cellar" and snap["player"]["available"]
    assert snap["events"]["items"][-1]["type"] == "scene_transition"


def test_taking_the_permission_back_cancels_the_move_and_lets_go(run: dict) -> None:
    interrupted = run["6_interrupted"]
    action = interrupted["answer"]["action"]
    assert action["status"] == "cancelled" and "took back the permission" in action["message"]
    assert action["frames"] < 120 and interrupted["down_while_moving"] and interrupted["down_after"] == []
    assert interrupted["gameplay_control"] is False and _reason(run["6_after"]) == "gameplay_control_off"


def test_stopping_leaves_the_persons_work_and_nothing_plays_without_a_play_test(run: dict) -> None:
    assert run["7_stopped"]["status"] == "stopped" and _reason(run["7_not_playing"]) == "not_playing"
    assert run["7_editing"] == {"mode": "edit", "same_room": True, "unsaved": True, "sign_kept": True,
                                "files_unchanged": True, "proposals": 0}
    assert _reason(run["7_closed"]) == "studio_not_open"
