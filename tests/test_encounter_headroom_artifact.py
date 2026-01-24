from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_verify_all_writes_encounter_headroom_artifact(monkeypatch, tmp_path) -> None:
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

    path = artifacts_dir / "encounter_headroom.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["scene_count"] >= 1
    rows = payload["rows"]
    assert isinstance(rows, list) and rows

    door_easy = next(
        (
            r
            for r in rows
            if r.get("scene_path") == "scenes/door_field.json" and str(r.get("difficulty") or "") == "easy"
        ),
        None,
    )
    assert door_easy is not None
    util = float(door_easy.get("utilization"))
    assert 0.0 <= util <= 1.5

    ashen_magma_easy = next(
        (
            r
            for r in rows
            if r.get("scene_path") == "packs/core_regions/scenes/Ashen_interior.json"
            and str(r.get("difficulty") or "") == "easy"
        ),
        None,
    )
    assert ashen_magma_easy is not None
    assert float(ashen_magma_easy.get("utilization")) <= 0.65

    ashen_void_easy = next(
        (
            r
            for r in rows
            if r.get("scene_path") == "packs/core_regions/scenes/Ashen_hub.json" and str(r.get("difficulty") or "") == "easy"
        ),
        None,
    )
    assert ashen_void_easy is not None
    assert float(ashen_void_easy.get("utilization")) <= 0.70
