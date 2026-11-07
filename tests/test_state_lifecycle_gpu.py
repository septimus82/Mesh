"""Studio's Play / Stop, again and again, in a real hidden window (#422 runtime state lifecycle).

D1's disposable project (tooling/d1_debug_scenario.py) with two more objects in the starter room: a Pinger counting
"ping" events (an IncrementCounterOnEvent behaviour) and a Coin within the player's reach. Three play-tests, each one:
the player collects the coin, agrees with the Guide's flag, one "ping" is sent, and one ends in a game over. Checked
each time:
- the play-test starts as a new game: no flags from the last one, the auto_start quest at its first stage (#446),
  one listener for "ping", not in a game over;
- one "ping" counts once, and the flag moves the quest on;
- after Stop, Studio shows the room as written, the Coin included, and the document is unchanged.

Silent. GL-gated: MESH_GL_SMOKE=1.
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
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
START = "packs/core_regions/scenes/start.json"
PICTURE = "assets/sprites/starter_sign.png"


@pytest.fixture(scope="module")
def cycles(tmp_path_factory: pytest.TempPathFactory) -> list[dict]:
    import d1_debug_scenario as d1
    from hd2d_studio_demo import StudioDriver

    project = tmp_path_factory.mktemp("lifecycle") / "project"
    d1.build(project)
    scene = json.loads((project / START).read_text(encoding="utf-8"))
    scene["entities"] += [
        {"id": "pinger", "name": "Pinger", "x": 600.0, "y": 400.0, "sprite": PICTURE,
         "behaviours": ["IncrementCounterOnEvent"],
         "behaviour_config": {"IncrementCounterOnEvent": {"event_type": "ping", "counter": "pings"}}},
        {"id": "coin", "name": "Coin", "x": 160.0, "y": 128.0, "sprite": PICTURE,
         "behaviours": ["Collectible"], "behaviour_config": {"Collectible": {"collect_by_name": "Player"}}}]
    (project / START).write_text(json.dumps(scene, indent=1), encoding="utf-8")
    os.environ.setdefault("MESH_RUNTIME_SETTINGS_PATH", str(project.parent / "user_settings.json"))
    hidden_bridge = os.environ.get("MESH_STUDIO_NO_AI_BRIDGE")
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    d = StudioDriver(project)
    studio, window = d.studio, d.window
    results = []

    def now() -> dict:
        state = window.game_state_controller.state
        return {"flags": dict(state.flags), "counters": dict(state.counters),
                "quest": dict((state.values.get("quests") or {}).get("light_the_lantern") or {}),
                "listeners": len(window.event_bus._subscribers.get("ping", [])),
                "game_over": bool(window.game_over),
                "coin": any(getattr(s, "mesh_name", "") == "Coin" for s in window.scene_controller.all_sprites)}

    try:
        window.audio.set_muted(True)
        document = json.dumps(studio.project.scene(), sort_keys=True)
        for cycle in range(3):
            studio.play()
            d.advance(5)
            started = now()
            player = d.game.player()
            player.center_x, player.center_y = 160.0, 128.0
            d.advance(5)
            window.set_flag(d1.FLAG, True)
            window.emit_signal("ping")
            d.advance(5)
            played = now()
            if cycle == 1:  # (this play-test ends with the player dead)
                window.game_over, window.paused = True, True
                window.game_over_screen.visible = True
            studio.stop()
            d.advance(3)
            results.append({"started": started, "played": played, "stopped": now(),
                            "document_unchanged": json.dumps(studio.project.scene(), sort_keys=True) == document})
    finally:
        d.close()
        if hidden_bridge is None:
            os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)
        else:
            os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = hidden_bridge
    return results


def test_every_play_test_starts_as_a_new_game(cycles: list[dict]) -> None:
    for cycle in cycles:
        started = cycle["started"]
        assert "agreed_to_help" not in started["flags"] and "pings" not in started["counters"]
        assert (started["quest"]["status"], started["quest"]["current_stage"]) == ("active", "agree")  # (#446)
        assert started["listeners"] == 1 and started["game_over"] is False and started["coin"] is True


def test_in_every_play_test_one_event_counts_once_and_the_flag_moves_the_quest(cycles: list[dict]) -> None:
    for cycle in cycles:
        played = cycle["played"]
        assert played["counters"].get("pings") == 1.0 and played["coin"] is False  # (collected)
        assert played["quest"]["current_stage"] == "cellar" and played["quest"]["completed_stages"] == ["agree"]


def test_after_stop_studio_shows_the_room_as_written(cycles: list[dict]) -> None:
    for cycle in cycles:
        stopped = cycle["stopped"]
        assert stopped["coin"] is True and stopped["game_over"] is False and stopped["flags"] == {}
        assert cycle["document_unchanged"] is True
