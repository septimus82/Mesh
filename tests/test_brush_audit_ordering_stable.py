from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_brush_audit_tile_ordering_is_deterministic(monkeypatch, tmp_path) -> None:
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

    payload = json.loads((artifacts_dir / "brush_audit.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True

    for case in payload["cases"]:
        tile_changes = case.get("tile_changes") or []
        assert isinstance(tile_changes, list)
        tile_keys = [(str(r.get("layer_id") or ""), int(r.get("y") or 0), int(r.get("x") or 0)) for r in tile_changes]
        assert tile_keys == sorted(tile_keys)
