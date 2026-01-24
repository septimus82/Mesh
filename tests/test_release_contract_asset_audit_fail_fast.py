from __future__ import annotations

import json
from pathlib import Path

from mesh_cli.release_contract import run_release_contract
from tests.fixture_repo import copy_minipack_repo, mutate_file


def test_release_contract_asset_audit_fail_fast(tmp_path: Path) -> None:
    repo_root = copy_minipack_repo(tmp_path)
    artifacts_dir = tmp_path / "artifacts"
    report_path = tmp_path / "release_report.json"

    mutate_file(
        repo_root,
        "packs/core/scenes/test_scene.json",
        lambda payload: _inject_missing_sprite(payload),
    )

    exit_code = run_release_contract(
        artifacts_dir=artifacts_dir,
        repo_root=repo_root,
        report_path=report_path,
    )

    assert exit_code == 2
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["summary"]["failed_step"] == "asset-audit"
    step_names = [step["name"] for step in report["steps"]]
    assert "content-contract" not in step_names


def _inject_missing_sprite(payload: dict) -> dict:
    entities = list(payload.get("entities", []))
    if entities:
        entity = dict(entities[0])
        entity["sprite"] = "packs/core/sprites/missing.png"
        entities[0] = entity
    payload["entities"] = entities
    return payload
