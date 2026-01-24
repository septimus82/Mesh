from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_verify_all_macro_audit_includes_new_objective_macro_case(monkeypatch, tmp_path) -> None:
    import mesh_cli

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
        mesh_cli,
        "_inventory_list_scenes",
        lambda: {"ok": True, "scenes": [], "summary": {"scene_count": 0, "issues_count": 0}},
    )
    monkeypatch.setattr(
        mesh_cli,
        "_inventory_list_worlds",
        lambda: {"ok": True, "worlds": [], "summary": {"world_count": 0, "issues_count": 0}},
    )

    artifacts_dir = tmp_path / "artifacts"
    assert mesh_cli.main(["verify-all", "--artifacts", str(artifacts_dir), "--no-index"]) == 0

    payload = json.loads((artifacts_dir / "macro_audit.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True

    cases = payload["cases"]
    match = next((c for c in cases if c.get("macro_path") == "packs/core_regions/macros/objective_find_cellar.json"), None)
    assert match is not None
    assert match["scene_path"] == "scenes/door_interior.json"
    assert match["args"]["anchor"] == "player"
    assert match["args"]["zone_id"] == "demo_reached_interior_zone"
    assert match["args"]["set_flag"] == "demo.reached_interior"
    assert match["args"]["toast"] == "Objective: Find the cellar"
    assert int(match["will_create"]) >= 1
