from __future__ import annotations

import json
from pathlib import Path

from engine.tooling.assets_audit import run_asset_audit
from engine.tooling.assets_fix import fix_missing_assets_from_audit
from tests.fixture_repo import copy_minipack_repo, mutate_file


def test_asset_audit_mass_fix_stub_files(tmp_path: Path) -> None:
    repo_root = copy_minipack_repo(tmp_path)

    mutate_file(
        repo_root,
        "packs/core/scenes/test_scene.json",
        lambda payload: _inject_missing_sprite(payload),
    )
    _allow_external_assets(repo_root)

    audit_path = repo_root / "artifacts" / "asset_audit.json"
    exit_code, report = run_asset_audit(
        repo_root=repo_root,
        out_path=audit_path,
        write_report=True,
    )

    assert exit_code == 2
    assert report["summary"]["missing_files"] == 1

    fix_report = fix_missing_assets_from_audit(
        repo_root=repo_root,
        audit_path=audit_path,
        out_path=repo_root / "artifacts" / "asset_audit_fix.json",
        mode="stub",
    )

    created_files = fix_report.get("created_files", [])
    assert "assets/sprites/missing_test_guard.png" in created_files
    assert (repo_root / "assets" / "sprites" / "missing_test_guard.png").exists()

    exit_code, report = run_asset_audit(
        repo_root=repo_root,
        out_path=repo_root / "artifacts" / "asset_audit_after.json",
        write_report=False,
    )

    assert exit_code == 0
    assert report["summary"]["ok"] is True


def _inject_missing_sprite(payload: dict) -> dict:
    entities = list(payload.get("entities", []))
    if entities:
        entity = dict(entities[0])
        entity["sprite"] = "assets/sprites/missing_test_guard.png"
        entities[0] = entity
    payload["entities"] = entities
    return payload


def _allow_external_assets(repo_root: Path) -> None:
    pack_path = repo_root / "packs" / "core" / "pack.json"
    payload = json.loads(pack_path.read_text(encoding="utf-8"))
    payload["asset_audit"] = {"allow_external": ["assets/**"]}
    pack_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
