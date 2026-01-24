from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_verify_all_writes_stamp_audit_artifact(monkeypatch, tmp_path) -> None:
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

    path = artifacts_dir / "stamp_audit.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert int(payload["case_count"]) >= 1
    cases = payload["cases"]
    assert isinstance(cases, list) and cases

    expected = json.loads((repo_root / "worlds" / "main_world.json").read_text(encoding="utf-8"))["stamp_audit_cases"][0]
    expected_scene = expected["scene_path"]
    expected_stamp = expected["stamp_path"]

    match = next(
        (c for c in cases if c.get("scene_path") == expected_scene and c.get("stamp_path") == expected_stamp),
        None,
    )
    assert match is not None
    assert match["origin"] == expected["origin"]
    assert match.get("id_prefix") == expected.get("id_prefix")

    assert int(match["tile_change_count"]) == 90
    assert int(match["entity_change_count"]) == 2
    assert len(match["tile_changes"]) == 90
    assert len(match["tile_changes"]) <= 200

    assert match["entity_changes"] == [
        {
            "action": "add",
            "id": "stamp_audit_sandbox_audit_torch1_1_1_0_0",
            "prefab_id": "torch_wisp",
            "x": 56.0,
            "y": 56.0,
        },
        {
            "action": "add",
            "id": "stamp_audit_sandbox_audit_torch2_1_1_0_0",
            "prefab_id": "torch_wisp",
            "x": 136.0,
            "y": 56.0,
        },
    ]
