"""#622: action lists and cutscenes through the live runtime contracts.

Real runtime: a hidden GameWindow, a real room file loaded by the real SceneController, sprites whose behaviours
live in ``mesh_behaviours_runtime``, and the game's own frame (``on_update``: the tick that runs the cutscene and
calls ``_deliver_events_to_behaviours``). Before the fix ActionListRunner heard nothing there (it had only
``handle_event``), cutscene steps called a ``find_sprite`` the SceneController doesn't have, and both read an
``entity.behaviours`` that real sprites don't carry.
"""
from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

from engine import optional_arcade
from tests._b01_arena import PIC, Arena, close_window, make_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

HERO = {"id": "hero", "name": "Hero", "tag": "player", "x": 50, "y": 50, "sprite": PIC}
GATE = {"id": "gate", "name": "Gate", "x": 120, "y": 80, "sprite": PIC,
        "behaviours": ["Timer", "DialogueRunner"],
        "behaviour_config": {
            "Timer": {"duration": 30.0, "auto_start": False, "timer_id": "gate_timer"},
            "DialogueRunner": {"dialogue_id": "gate_talk", "start_node": "start",
                               "script": {"start": {"speaker": "Gate", "text": "Creak."}}},
        }}
LEVER = {"id": "lever", "name": "Lever", "x": 0, "y": 0, "sprite": PIC,
         "behaviours": ["ActionListRunner"],
         "behaviour_config": {"ActionListRunner": {
             "listen_events": ["lever_pulled"],
             "actions": [
                 {"type": "set_flag", "flag": "gate_open"},
                 {"type": "start_timer", "target": "Gate", "timer_id": "gate_timer"},
                 {"type": "start_dialogue", "target": "Gate", "dialogue_id": "gate_talk"},
                 {"type": "add_tag", "tag": "pulled"},
                 {"type": "emit_event", "event_type": "gate_opened"},
             ]}}}


@pytest.fixture()
def arena(tmp_path: Path) -> Iterator[Arena]:
    window = make_window()
    try:
        yield Arena(window, tmp_path)
    finally:
        close_window(window)


def _behaviour(sprite: Any, type_name: str) -> Any:
    found = [b for b in sprite.mesh_behaviours_runtime if type(b).__name__ == type_name]
    assert len(found) == 1, (type_name, sprite.mesh_behaviours_runtime)
    return found[0]


def _frames(window: Any, count: int) -> None:
    for _ in range(count):
        window.on_update(1 / 60)


def test_action_list_runs_from_the_live_event_delivery(arena: Arena) -> None:
    arena.write_room(HERO, GATE, LEVER)
    arena.enter()
    window = arena.window
    lever, gate = arena.by_id("lever"), arena.by_id("gate")
    runner = _behaviour(lever, "ActionListRunnerBehaviour")
    timer, dialogue = _behaviour(gate, "TimerBehaviour"), _behaviour(gate, "DialogueRunnerBehaviour")
    assert not timer.is_running and not dialogue.is_running

    handled: list[str] = []  # every route into the runner goes through handle_event: count them
    real_handle = runner.handle_event
    runner.handle_event = lambda event_type, payload: (handled.append(event_type), real_handle(event_type, payload))[1]
    opened: list[Any] = []
    window.event_bus.subscribe("gate_opened", opened.append)

    window.emit_signal("lever_pulled")
    _frames(window, 4)  # delivery, then the runner's update runs the list, then its events are delivered

    assert window.get_flag("gate_open") is True  # set_flag
    assert timer.is_running  # start_timer: found on the target's mesh_behaviours_runtime
    assert dialogue.is_running  # start_dialogue: likewise
    assert "pulled" in lever.mesh_tags  # add_tag
    assert len(opened) == 1  # emit_event
    assert handled == ["lever_pulled"] and runner.run_count == 1  # one event, one delivery, one run

    window.emit_signal("lever_pulled")
    _frames(window, 4)
    assert handled == ["lever_pulled", "lever_pulled"] and runner.run_count == 2 and len(opened) == 2


def test_cutscene_steps_find_targets_through_the_scene_controller(arena: Arena) -> None:
    arena.write_room(HERO, GATE)
    arena.enter()
    window = arena.window
    gate = arena.by_id("gate")
    dialogue = _behaviour(gate, "DialogueRunnerBehaviour")
    focused: list[tuple[float, float]] = []
    cc = window.cutscene_controller
    real_set = cc._set_camera_position
    cc._set_camera_position = lambda x, y: (focused.append((x, y)), real_set(x, y))[1]
    cc.register_cutscenes([{"id": "gate_scene", "steps": [
        {"type": "move_entity", "entity": "Gate", "x": 200, "y": 90, "duration": 0},
        {"type": "camera_focus", "entity": "Gate"},
        {"type": "start_dialogue", "target": "Gate", "dialogue_id": "gate_talk"},
    ]}])

    assert cc.play_cutscene("gate_scene")
    _frames(window, 4)

    assert (gate.center_x, gate.center_y) == (200.0, 90.0)  # move_entity
    assert focused == [(200.0, 90.0)]  # camera_focus on the moved sprite
    assert dialogue.is_running  # targeted start_dialogue, read from mesh_behaviours_runtime
    assert not cc.is_running


def test_cutscene_missing_target_is_a_logged_no_op(arena: Arena) -> None:
    arena.write_room(HERO, GATE)
    arena.enter()
    window = arena.window
    cc = window.cutscene_controller
    cc.register_cutscenes([{"id": "ghost_scene", "steps": [
        {"type": "move_entity", "entity": "Nobody", "x": 5, "y": 5, "duration": 1.0},
        {"type": "camera_focus", "entity": "Nobody"},
        {"type": "set_flag", "flag": "after_ghost"},
    ]}])

    records: list[logging.LogRecord] = []
    handler = logging.Handler(logging.WARNING)
    handler.emit = records.append  # type: ignore[method-assign]
    logger = logging.getLogger("engine.cutscene_controller")  # (engine loggers don't propagate: caplog misses them)
    logger.addHandler(handler)
    try:
        assert cc.play_cutscene("ghost_scene")
        _frames(window, 4)  # no AttributeError out of the frame
    finally:
        logger.removeHandler(handler)

    assert window.get_flag("after_ghost") is True  # the missing-target steps ended; the next step ran
    assert not cc.is_running
    assert [r.getMessage() for r in records] == ["[Mesh][Cutscene] 'ghost_scene': target 'Nobody' is not in the scene"] * 2


def test_cutscene_lookup_errors_are_not_swallowed() -> None:
    """Only a missing target is guarded: a failing lookup still raises (no silent catch-all)."""
    from engine.cutscene_controller import CutsceneController

    def broken(_identifier: Any) -> Any:
        raise RuntimeError("index corrupt")

    cc = CutsceneController(SimpleNamespace(scene_controller=SimpleNamespace(find_entity=broken)))
    cc.register_cutscenes([{"id": "c", "steps": [{"type": "move_entity", "entity": "Gate", "x": 1, "y": 1}]}])
    cc.play_cutscene("c")
    with pytest.raises(RuntimeError, match="index corrupt"):
        cc.update(0.016)


def test_runner_stands_down_where_a_harness_owns_the_gameplay_bus() -> None:
    """The episode/campaign harnesses route their gameplay bus to handle_event themselves: on_event must not add a
    second run there (the QuestHook rule)."""
    from engine.behaviours.action_list_runner import ActionListRunnerBehaviour
    from engine.events import MeshEvent
    from engine.scene_controller import SceneController

    window = SimpleNamespace(gameplay_event_bus=object(), strict_mode=True)
    sprite = SimpleNamespace(mesh_id="lever", mesh_name="Lever", mesh_tags=[], mesh_entity_data={})
    runner = ActionListRunnerBehaviour(sprite, window, listen_events=["lever_pulled"],
                                       actions=[{"type": "add_tag", "tag": "pulled"}])
    sprite.mesh_behaviours_runtime = [runner]
    sc = object.__new__(SceneController)
    sc.layers = {"entities": [sprite]}
    sc.window = window
    sc._deliver_events_to_behaviours([MeshEvent(type="lever_pulled", payload={})])
    assert runner.run_count == 0
