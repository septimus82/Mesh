from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_encounter_headroom_rows_for_key_scenes_match_golden(monkeypatch, tmp_path) -> None:
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

    headroom_path = artifacts_dir / "encounter_headroom.json"
    payload = json.loads(headroom_path.read_text(encoding="utf-8"))
    rows = payload.get("rows", [])
    assert isinstance(rows, list) and rows

    wanted_scenes = {
        "scenes/door_field.json",
        "packs/core_regions/scenes/Ashen_hub.json",
        "packs/core_regions/scenes/Ashen_interior.json",
    }
    wanted_difficulties = {"easy", "hard"}
    subset_keys = ["scene_path", "difficulty", "budget", "effective_budget", "total_spawn_cost", "headroom", "utilization"]

    filtered = [
        {k: row.get(k) for k in subset_keys}
        for row in rows
        if row.get("scene_path") in wanted_scenes and row.get("difficulty") in wanted_difficulties
    ]
    filtered = sorted(filtered, key=lambda r: (str(r.get("scene_path") or ""), str(r.get("difficulty") or "")))

    golden_path = repo_root / "tests" / "golden" / "encounter_headroom_key_scenes.json"
    expected = json.loads(golden_path.read_text(encoding="utf-8"))

    actual_text = json.dumps(filtered, indent=2, sort_keys=True) + "\n"
    expected_text = json.dumps(expected, indent=2, sort_keys=True) + "\n"
    assert actual_text == expected_text
