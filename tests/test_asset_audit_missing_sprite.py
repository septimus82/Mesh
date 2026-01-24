from __future__ import annotations

from pathlib import Path

from engine.tooling.assets_audit import run_asset_audit
from tests.fixture_repo import copy_minipack_repo, mutate_file


def test_asset_audit_missing_sprite(tmp_path: Path) -> None:
    repo_root = copy_minipack_repo(tmp_path)

    mutate_file(
        repo_root,
        "packs/core/scenes/test_scene.json",
        lambda payload: _inject_missing_sprite(payload),
    )

    exit_code, report = run_asset_audit(
        repo_root=repo_root,
        out_path=repo_root / "artifacts" / "asset_audit.json",
        write_report=False,
    )

    assert exit_code == 2
    assert report["summary"]["ok"] is False
    assert report["summary"]["error_count"] == 1
    error = report["errors"][0]
    assert error["kind"] == "missing_file"
    assert error["json_path"] == "/entities/0/sprite"


def _inject_missing_sprite(payload: dict) -> dict:
    entities = list(payload.get("entities", []))
    if entities:
        entity = dict(entities[0])
        entity["sprite"] = "packs/core/sprites/missing.png"
        entities[0] = entity
    payload["entities"] = entities
    return payload
