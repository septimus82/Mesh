from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_encounter_audit_compact_rows_for_door_field_match_golden(verify_all_audit_artifacts: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    artifacts_dir = verify_all_audit_artifacts  # (one verify-all of this checkout, shared: conftest.py)

    compact_path = artifacts_dir / "encounter_audit_compact.json"
    payload = json.loads(compact_path.read_text(encoding="utf-8"))

    rows = [r for r in payload.get("rows", []) if r.get("scene_path") == "scenes/door_field.json"]
    assert rows

    subset_keys = [
        "difficulty",
        "encounter_preset_id",
        "encounter_budget",
        "boss_budget_reserve",
        "spawn_count",
        "elite_count",
        "mini_boss_count",
        "total_spawn_cost",
        "elite_cost_share",
        "mini_boss_cost_share",
    ]

    wanted_difficulties = ["easy", "hard"]
    rows_by_difficulty = {str(r.get("difficulty")): r for r in rows}
    missing = [d for d in wanted_difficulties if d not in rows_by_difficulty]
    assert not missing, f"missing expected door_field difficulties: {missing} (found: {sorted(rows_by_difficulty)})"

    projected_rows = [{k: rows_by_difficulty[d].get(k) for k in subset_keys} for d in wanted_difficulties]
    actual = {"scene_path": "scenes/door_field.json", "rows": projected_rows}

    golden_path = repo_root / "tests" / "golden" / "encounter_audit_compact_door_field.json"
    expected = json.loads(golden_path.read_text(encoding="utf-8"))

    actual_text = json.dumps(actual, indent=2, sort_keys=True) + "\n"
    expected_text = json.dumps(expected, indent=2, sort_keys=True) + "\n"
    assert actual_text == expected_text
