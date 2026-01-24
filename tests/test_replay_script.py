from __future__ import annotations

import json
from pathlib import Path

from engine.tooling.replay_script import load_replay_script, run_replay_script


def test_replay_script_zone_sequence_grants_rewards_and_sets_anchor():
    script = {
        "flags_sample_limit": 50,
        "steps": [
            {"emit": "entered_zone", "zone_id": "VariantGStartZone2"},
            {"emit": "entered_zone", "zone_id": "VariantGGoalZone2"},
            {"dump_state": True},
        ],
    }

    final_state = run_replay_script(script)

    # From assets/data/quests.json quest ridge2_variant_g_beacon reward.
    assert final_state["gold"] == 25
    assert final_state["last_zone_id"] == "VariantGGoalZone2"
    assert "ridge2_variant_g_beacon_complete" in final_state["flags_sample"]


def test_replay_script_expect_state_passes_when_partial_matches_final_dump():
    script = {
        "flags_sample_limit": 50,
        "steps": [
            {"emit": "entered_zone", "zone_id": "VariantGStartZone2"},
            {"emit": "entered_zone", "zone_id": "VariantGGoalZone2"},
        ],
        "expect_state": {
            "gold": 25,
            "last_zone_id": "VariantGGoalZone2",
            "save_format_version": 1,
        },
    }

    final_state = run_replay_script(script)
    assert final_state["gold"] == 25


def test_replay_script_expect_state_mismatch_raises_deterministic_error():
    script = {
        "steps": [
            {"emit": "entered_zone", "zone_id": "VariantGStartZone2"},
            {"emit": "entered_zone", "zone_id": "VariantGGoalZone2"},
        ],
        "expect_state": {
            "last_zone_id": "ZoneA",
        },
    }

    try:
        run_replay_script(script)
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert str(exc) == "expect_state mismatch: last_zone_id expected 'ZoneA' got 'VariantGGoalZone2'"


def test_replay_script_expect_state_file_passes(tmp_path):
    expect_path = tmp_path / "expected.json"
    expect_path.write_text(json.dumps({"gold": 0}), encoding="utf-8")

    script_path = tmp_path / "script.json"
    script_path.write_text(
        json.dumps(
            {
                "steps": [{"dump_state": True}],
                "expect_state_file": "expected.json",
            }
        ),
        encoding="utf-8",
    )

    script = load_replay_script(Path(script_path))
    final_state = run_replay_script(script, script_path=Path(script_path))
    assert final_state["gold"] == 0


def test_replay_script_expect_state_file_mismatch_raises_exact_error(tmp_path):
    expect_path = tmp_path / "expected.json"
    expect_path.write_text(json.dumps({"gold": 1}), encoding="utf-8")

    script_path = tmp_path / "script.json"
    script_path.write_text(
        json.dumps(
            {
                "steps": [{"dump_state": True}],
                "expect_state_file": "expected.json",
            }
        ),
        encoding="utf-8",
    )

    script = load_replay_script(Path(script_path))
    try:
        run_replay_script(script, script_path=Path(script_path))
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert str(exc) == "expect_state mismatch: gold expected 1 got 0"


def test_replay_script_rejects_both_expect_state_and_expect_state_file(tmp_path):
    script_path = tmp_path / "script.json"
    script_path.write_text(
        json.dumps(
            {
                "steps": [{"dump_state": True}],
                "expect_state": {"gold": 0},
                "expect_state_file": "expected.json",
            }
        ),
        encoding="utf-8",
    )

    script = load_replay_script(Path(script_path))
    try:
        run_replay_script(script, script_path=Path(script_path))
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert str(exc) == "expect_state and expect_state_file are mutually exclusive"
