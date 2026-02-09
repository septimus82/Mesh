from __future__ import annotations

from engine.editor.quest_debug_model import build_quest_debug_lines, build_quest_debug_view_model
from engine.quest_runtime.runner import StepCompletionDiagnostic


def test_quest_debug_view_model_sorted_and_formatted() -> None:
    inspector_state = {
        "total_quests": 2,
        "active_count": 1,
        "completed_count": 0,
        "inactive_count": 1,
        "quests": [
            {
                "id": "quest_b",
                "title": "B Quest",
                "status": "inactive",
                "progress": "0/1",
                "current_stage": None,
                "awaiting_stage": None,
                "completed_stages": [],
            },
            {
                "id": "quest_a",
                "title": "A Quest",
                "status": "active",
                "progress": "1/3",
                "current_stage": {
                    "id": "step_1",
                    "title": "Start",
                    "text": "",
                    "has_complete_trigger": True,
                    "has_requirements": False,
                },
                "awaiting_stage": "step_2",
                "completed_stages": ["step_0"],
            },
        ],
    }
    diagnostics = [
        StepCompletionDiagnostic(
            quest_id="quest_b",
            step_id="step_2",
            event_type="on_enter",
            matched=False,
            reason="missing key",
        ),
        StepCompletionDiagnostic(
            quest_id="quest_a",
            step_id="step_1",
            event_type="on_enter",
            matched=True,
            reason="matched",
        ),
    ]

    view_model = build_quest_debug_view_model(inspector_state, diagnostics)
    assert [q.quest_id for q in view_model.quests] == ["quest_a", "quest_b"]

    lines = build_quest_debug_lines(view_model)
    assert lines[0] == "Quest Debug"
    assert "- quest_a [active] 1/3" in lines
    assert "- quest_b [inactive] 0/1" in lines
    assert "  step: step_1 Start" in lines

    idx_a = lines.index("- quest_a [active] 1/3")
    idx_b = lines.index("- quest_b [inactive] 0/1")
    assert idx_a < idx_b

    assert "Diagnostics:" in lines
    assert "  quest_a:step_1 on_enter [match] matched" in lines
    assert "  quest_b:step_2 on_enter [no-match] missing key" in lines
