from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.slow, pytest.mark.integration]
from pathlib import Path


def test_room_audit_ordering_stable(monkeypatch, tmp_path: Path) -> None:
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

    payload = json.loads((artifacts_dir / "room_audit.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True
    cases = payload["cases"]
    assert isinstance(cases, list)

    last = None
    for case in cases:
        key = (
            str(case.get("from_scene") or ""),
            str(case.get("to_scene") or ""),
            str(case.get("stamp_path") or ""),
            str(case.get("door_macro") or ""),
        )
        if last is not None:
            assert last <= key
        last = key
        for field in ("will_create", "will_update", "entity_change_count", "config_change_count"):
            assert isinstance(case.get(field), int)
            assert int(case.get(field)) >= 0
