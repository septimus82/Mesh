from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_verify_all_room_audit_includes_micro_dungeon_cases(monkeypatch, tmp_path: Path) -> None:
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

    expected_cases = json.loads((repo_root / "worlds" / "main_world.json").read_text(encoding="utf-8"))["room_audit_cases"]
    assert len(expected_cases) == 3

    payload = json.loads((artifacts_dir / "room_audit.json").read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert len(cases) == 3

    expected_keys = sorted(
        [
            (
                c["from_scene"],
                c["to_scene"],
                c["stamp_path"],
                c["door_macro"],
            )
            for c in expected_cases
        ]
    )
    actual_keys = sorted(
        [
            (
                c["from_scene"],
                c["to_scene"],
                c["stamp_path"],
                c["door_macro"],
            )
            for c in cases
        ]
    )
    assert actual_keys == expected_keys
