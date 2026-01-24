from __future__ import annotations

import json
from pathlib import Path

from mesh_cli.release_contract import run_release_contract
from tests.fixture_repo import copy_minipack_repo


def test_release_contract_includes_asset_audit_step(tmp_path: Path) -> None:
    repo_root = copy_minipack_repo(tmp_path)
    artifacts_dir = tmp_path / "artifacts"
    report_path = tmp_path / "release_report.json"

    exit_code = run_release_contract(
        artifacts_dir=artifacts_dir,
        repo_root=repo_root,
        report_path=report_path,
    )

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    step_names = [step["name"] for step in report["steps"]]
    assert "asset-audit" in step_names
    audit_path = artifacts_dir / "asset_audit.json"
    assert audit_path.exists()
    payload = json.loads(audit_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
