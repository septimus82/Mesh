from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_verify_all_writes_encounter_coverage_matrix_artifact(monkeypatch, tmp_path) -> None:
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

    matrix_path = artifacts_dir / "encounter_coverage_matrix.json"
    assert matrix_path.exists()
    payload = json.loads(matrix_path.read_text(encoding="utf-8"))

    assert payload["ok"] is True
    assert payload["difficulties"] == ["easy", "hard"]
    rows = payload["rows"]
    assert rows

    def _require_row(encounter_set_id: str, difficulty: str) -> dict:
        row = next(
            (r for r in rows if r.get("encounter_set_id") == encounter_set_id and r.get("difficulty") == difficulty),
            None,
        )
        assert row is not None
        return row

    def _assert_easy_has_cheap_candidates(encounter_set_id: str) -> None:
        row = _require_row(encounter_set_id, "easy")
        assert int(row.get("eligible_count", 0)) >= 1
        cheapest = row.get("cheapest_candidate_cost")
        assert cheapest is not None
        assert float(cheapest) <= 2.0

    for encounter_set_id in (
        "moss_encounters",
        "crypt_encounters",
        "ruins_encounters",
        "forge_encounters",
        "magma_encounters",
        "void_encounters",
    ):
        _assert_easy_has_cheap_candidates(encounter_set_id)
        _require_row(encounter_set_id, "hard")

    ordering = [(row.get("encounter_set_id"), row.get("difficulty")) for row in rows]
    assert ordering == sorted(ordering)
