from __future__ import annotations

from engine.editor.debug_bundle_diff_model import diff_debug_bundles, format_debug_bundle_diff_text


def _bundle_base() -> dict:
    return {
        "world": {"current": "w1"},
        "lighting": {"plan_digest": "l1"},
        "render": {"plan_digest": "r1"},
        "quests": {
            "inspector_state": {
                "total_quests": 1,
                "active_count": 1,
                "completed_count": 0,
                "inactive_count": 0,
                "quests": [
                    {
                        "id": "quest_a",
                        "status": "active",
                        "progress": "1/2",
                        "current_stage": {"id": "stage_1"},
                    }
                ],
            },
            "diagnostics": [
                {
                    "quest_id": "quest_a",
                    "step_id": "stage_1",
                    "event_type": "hit",
                    "matched": False,
                    "reason": "missing flag",
                }
            ],
        },
        "cutscene": {
            "summary": {
                "is_running": False,
                "script_id": "",
                "command_index": 0,
                "command_count": 0,
                "current_command": "",
                "current_label": "",
                "wait_remaining": 0.0,
            }
        },
        "events": {
            "event_type_filter": "",
            "entity_id_filter": "",
            "limit": 5,
            "total_events": 2,
            "filtered_count": 2,
        },
    }


def test_debug_bundle_diff_detects_changes_and_is_deterministic() -> None:
    bundle_a = _bundle_base()
    bundle_b = _bundle_base()
    bundle_b["world"]["current"] = "w2"
    bundle_b["lighting"]["plan_digest"] = "l2"
    bundle_b["quests"]["inspector_state"]["total_quests"] = 2
    bundle_b["quests"]["inspector_state"]["quests"].append(
        {
            "id": "quest_b",
            "status": "inactive",
            "progress": "",
            "awaiting_stage": "stage_x",
        }
    )
    bundle_b["quests"]["diagnostics"] = [
        {
            "quest_id": "quest_b",
            "step_id": "stage_x",
            "event_type": "start",
            "matched": True,
            "reason": "ok",
        }
    ]
    bundle_b["cutscene"]["summary"]["is_running"] = True
    bundle_b["events"]["filtered_count"] = 3

    diff = diff_debug_bundles(bundle_a, bundle_b)
    assert diff.changed is True
    assert any(entry.path == "world.current" for entry in diff.digests)
    assert diff.quests_added == ("quest_b",)
    assert diff.diagnostics_removed == ("quest_a:stage_1 hit [no-match] missing flag",)
    assert diff.diagnostics_added == ("quest_b:stage_x start [match] ok",)
    assert any(entry.path == "cutscene.summary.is_running" for entry in diff.cutscene_summary)
    assert any(entry.path == "events.summary.filtered_count" for entry in diff.event_summary)

    text_a = format_debug_bundle_diff_text(diff)
    text_b = format_debug_bundle_diff_text(diff)
    assert text_a == text_b
    assert "world.current: w1 -> w2" in text_a
