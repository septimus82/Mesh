"""S1 5.6 (E8 contracts 4 and 5; 5.6 (d) smokes): what Studio and the AI write, the game opens and runs.

Contract 4, a Studio/MCP write -> the GameWindow opens it: a cutscene and a quest written through the MCP server's
``apply_ops`` (as the AI writes them), and an item reference (a chest's reward, set through MCP
``set_behaviour_params`` on a chest Studio placed) that the game resolves from the project's ``assets/data/items.json``.
There is no item-database writer in Studio or MCP to test: the item list is the project's data file. The game is
started afterwards, by ``run_game(project_root=)`` from another folder (tests/_real_game.py), and each write is live.

Contract 5, live event delivery for runners on the real SceneController: an ActionListRunner and cutscene steps,
authored the same ways, run from events sent on the game's bus and delivered by its own frame (#622: before, the
runner heard nothing in a game and cutscene steps called a ``find_sprite`` the SceneController doesn't have).
"""
from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

import engine.optional_arcade as optional_arcade
from tests._real_game import RealGame, author, batch, new_project, place, real_game

pytestmark = [pytest.mark.integration,  # (a generated project in a temporary folder; one hidden game window)
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

ROOM = "Wiring"
LANTERN = "lantern"
CUTSCENES = {
    "welcome": [{"type": "set_flag", "flag": "welcomed"}, {"type": "add_counter", "name": "visits", "delta": 1}],
    "stage_walk": [{"type": "move_entity", "entity": "Actor", "x": 400, "y": 300, "duration": 0},
                   {"type": "camera_focus", "entity": "Actor"},
                   {"type": "start_dialogue", "target": "Actor", "dialogue_id": "actor_talk"},
                   {"type": "emit_event", "event": "scene_done"}],
}
QUEST = {"id": "deliver", "title": "Deliver the lantern",
         "stages": [{"id": "carry", "description": "Bring the lantern", "complete_on": "lantern_delivered"}]}
ACTIONS = [{"type": "set_flag", "flag": "lever_flag"}, {"type": "add_tag", "tag": "pulled"},
           {"type": "emit_event", "event_type": "lever_done"}]


@pytest.fixture(scope="module")
def running(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RealGame]:
    from engine.mcp_server import tools

    base = tmp_path_factory.mktemp("wiring")
    project = new_project(base / "game")
    (Path(project.root) / "assets" / "data" / "items.json").write_text(json.dumps(
        {"items": [{"id": LANTERN, "name": "Lantern"}]}), encoding="utf-8")  # (the project's own data: no writer)
    room = project.add_room(ROOM)
    author(project, room, batch(
        place("Chest", 320, 240, ("RewardChest", {"unlock_event": "chest_open"})),
        place("Lever", 200, 200, ("ActionListRunner", {"listen_events": ["lever_pulled"], "actions": ACTIONS})),
        place("Listener", 240, 200, ("ActionListRunner", {"listen_events": ["dialogue_completed"],
                                                          "event_filter": {"dialogue_id": "gate_talk"},
                                                          "actions": [{"type": "set_flag", "flag": "talked"}]})),
        place("Actor", 120, 300, ("DialogueRunner", {"dialogue_id": "actor_talk", "start_node": "start",
                                                     "script": {"start": {"speaker": "Actor", "text": "Ta-da."}}})),
        place("Stage", 100, 100, ("CutsceneTrigger", {"listen_event": "curtain_up", "cutscene_id": "stage_walk"})),
    ))
    path = project.path(room)
    item = tools.apply_ops([{"type": "set_behaviour_params", "scene_path": path, "entity_id": "Chest",
                             "behaviour_name": "RewardChest", "params": {"item_id": LANTERN}}], root=str(project.root))
    assert item.get("ok"), item
    data = tools.apply_ops([{"type": "add_quest_definition", "quest_id": "deliver", "quest": QUEST},
                            *({"type": "add_cutscene", "id": cid, "steps": steps} for cid, steps in CUTSCENES.items())],
                           root=str(project.root))
    assert data.get("ok"), data
    launch = base / "elsewhere"
    launch.mkdir()
    with real_game(project, launch) as started:
        yield started


@pytest.fixture()
def game(running: RealGame) -> RealGame:
    running.resume()
    running.enter(running.room(ROOM))
    return running


# ---- contract 4 ------------------------------------------------------------------------------------------------
def _opens_cutscene(g: RealGame) -> None:
    controller = g.window.cutscene_controller
    assert {"welcome", "stage_walk"} <= set(controller.cutscenes)
    visits = g.counter("visits")
    assert controller.play_cutscene("welcome")
    g.frames(4)
    assert g.flag("welcomed") and g.counter("visits") == visits + 1


def _opens_quest(g: RealGame) -> None:
    quests = g.window.quest_manager
    assert quests.start_quest("deliver") is not False
    assert quests.is_quest_active("deliver")
    g.window.event_bus.emit("lantern_delivered")
    g.frames(3)
    assert not quests.is_quest_active("deliver"), "its stage completes on the event it was written with"


def _opens_item(g: RealGame) -> None:
    before = g.items(LANTERN)
    g.window.event_bus.emit("chest_open")
    g.frames(2)
    g.interact("Chest")
    assert g.items(LANTERN) == before + 1, "the chest gives the item MCP wrote, from the project's item list"


WRITES: dict[str, Callable[[RealGame], None]] = {"cutscene": _opens_cutscene, "quest": _opens_quest,
                                                 "items": _opens_item}


@pytest.mark.parametrize("written", list(WRITES))
def test_a_studio_or_mcp_write_is_live_in_the_game_that_opens_it(game: RealGame, written: str) -> None:
    WRITES[written](game)


# ---- contract 5 ------------------------------------------------------------------------------------------------
def _action_list(g: RealGame) -> None:
    runner = g.behaviour("Lever", "ActionListRunnerBehaviour")
    g.heard.clear()
    for run in (1, 2):
        g.window.emit_signal("lever_pulled")
        g.frames(4)  # (delivery, then the runner's update runs the list, then its events are delivered)
        assert runner.run_count == run and len(g.events("lever_done")) == run
    assert g.flag("lever_flag") and "pulled" in g.named("Lever").mesh_tags


def _action_list_payload(g: RealGame) -> None:
    runner = g.behaviour("Listener", "ActionListRunnerBehaviour")
    g.window.emit_signal("dialogue_completed", dialogue_id="other_talk")
    g.frames(3)
    assert runner.run_count == 0 and not g.flag("talked"), "a payload that doesn't match: no run"
    g.window.emit_signal("dialogue_completed", dialogue_id="gate_talk")
    g.frames(3)
    assert runner.run_count == 1 and g.flag("talked")


def _cutscene_steps(g: RealGame) -> None:
    actor = g.named("Actor")
    talk = g.behaviour("Actor", "DialogueRunnerBehaviour")
    g.heard.clear()
    g.window.event_bus.emit("curtain_up")  # (the CutsceneTrigger hears it and starts stage_walk)
    g.frames(8)
    assert (actor.center_x, actor.center_y) == (400.0, 300.0), "move_entity found it through the SceneController"
    assert talk.is_running, "start_dialogue reached its target's behaviour"
    assert g.events("scene_done") and not g.window.cutscene_controller.is_running


RUNNERS: dict[str, Callable[[RealGame], None]] = {"action list": _action_list,
                                                  "action list payload filter": _action_list_payload,
                                                  "cutscene steps": _cutscene_steps}


@pytest.mark.parametrize("runner", list(RUNNERS))
def test_runners_run_from_live_events_on_the_real_scene_controller(game: RealGame, runner: str) -> None:
    RUNNERS[runner](game)
