from __future__ import annotations

from engine.editor.cutscene_debug_model import build_cutscene_debug_lines, build_cutscene_debug_view_model
from engine.gameplay_event_bus import GameplayEvent


def test_cutscene_debug_view_model_extracts_label_and_events() -> None:
    inspector_state = {
        "script_id": "intro",
        "is_running": True,
        "completed": False,
        "command_index": 2,
        "command_count": 5,
        "current_command_type": "emit_event",
        "wait_remaining": 1.25,
        "emitted_count": 3,
        "branch_count": 1,
    }
    command_list = [
        {"index": 0, "type": "label", "name": "start"},
        {"index": 1, "type": "wait", "duration": 0.5},
        {"index": 2, "type": "emit_event", "event_type": "cutscene_jump"},
        {"index": 3, "type": "label", "name": "mid"},
        {"index": 4, "type": "goto", "target": "end"},
    ]
    events = [
        GameplayEvent(
            event_type="cutscene_a",
            payload={"a": 1},
            sequence=2,
            source_entity="",
            source_behaviour="CutsceneRunner",
        ),
        GameplayEvent(
            event_type="cutscene_b",
            payload={},
            sequence=1,
            source_entity="",
            source_behaviour="CutsceneRunner",
        ),
    ]

    view_model = build_cutscene_debug_view_model(inspector_state, command_list, events)

    assert view_model.current_label == "start"
    assert view_model.current_command == "emit cutscene_jump"
    assert [e.sequence for e in view_model.recent_events] == [1, 2]

    lines = build_cutscene_debug_lines(view_model)
    assert "Label: start" in lines
    assert "Command: 3/5 emit cutscene_jump" in lines
    assert "  #1 cutscene_b (empty)" in lines
    assert "  #2 cutscene_a a" in lines
