from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_encounter_audit_compact_rows_for_door_field_match_golden(monkeypatch, tmp_path) -> None:
    import mesh_cli
    import mesh_cli.legacy_impl as mesh_cli_legacy

    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)

    monkeypatch.setattr(mesh_cli.verify_demo, "run_verify_demo", lambda *_a, **_k: 0)
    monkeypatch.setattr(
        mesh_cli.replay_suite,
        "run_replay_suite",
        lambda _folder: {"failed": 0, "passed": 1, "total": 1, "results": []},
    )
    monkeypatch.setattr(mesh_cli.validate_all, "main", lambda _argv: 0)

    import engine.tooling.asset_doctor as asset_doctor

    monkeypatch.setattr(
        asset_doctor,
        "doctor_assets",
        lambda **_kwargs: {"ok": True, "errors": [], "warnings": [], "fixes": []},
    )
    monkeypatch.setattr(
        mesh_cli_legacy,
        "_inventory_list_scenes",
        lambda: {"ok": True, "scenes": [], "summary": {"scene_count": 0, "issues_count": 0}},
    )
    monkeypatch.setattr(
        mesh_cli_legacy,
        "_inventory_list_worlds",
        lambda: {"ok": True, "worlds": [], "summary": {"world_count": 0, "issues_count": 0}},
    )

    artifacts_dir = tmp_path / "artifacts"
    assert mesh_cli.main(["verify-all", "--artifacts", str(artifacts_dir), "--no-index"]) == 0

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
