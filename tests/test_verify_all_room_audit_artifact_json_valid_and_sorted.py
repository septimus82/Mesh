from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_verify_all_writes_room_audit_artifact(monkeypatch, tmp_path: Path) -> None:
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

    path = artifacts_dir / "room_audit.json"
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert int(payload["case_count"]) == 3
    cases = payload["cases"]
    assert isinstance(cases, list) and cases

    expected = json.loads((repo_root / "worlds" / "main_world.json").read_text(encoding="utf-8"))["room_audit_cases"][0]
    match = next(
        (
            c
            for c in cases
            if c.get("from_scene") == expected["from_scene"]
            and c.get("to_scene") == expected["to_scene"]
            and c.get("stamp_path") == expected["stamp_path"]
            and c.get("door_macro") == expected["door_macro"]
        ),
        None,
    )
    assert match is not None
    assert int(match["will_create"]) == 0
    assert int(match["will_update"]) == 1
    assert int(match["entity_change_count"]) == 1
    assert int(match["config_change_count"]) == 1

    assert all("\\" not in str(c.get("from_scene") or "") for c in cases)
    assert all("\\" not in str(c.get("to_scene") or "") for c in cases)
    assert all("\\" not in str(c.get("stamp_path") or "") for c in cases)
    assert all("\\" not in str(c.get("door_macro") or "") for c in cases)


def test_room_audit_cases_are_sorted_deterministically(monkeypatch, tmp_path: Path) -> None:
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

    payload = json.loads((artifacts_dir / "room_audit.json").read_text(encoding="utf-8"))
    cases = payload["cases"]
    keys = [
        (
            str(c.get("from_scene") or ""),
            str(c.get("to_scene") or ""),
            str(c.get("stamp_path") or ""),
            str(c.get("door_macro") or ""),
        )
        for c in cases
    ]
    assert keys == sorted(keys)
