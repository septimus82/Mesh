from __future__ import annotations

import json
from pathlib import Path

from mesh_cli.release_contract import run_release_contract
from tests.fixture_repo import copy_minipack_repo


def test_release_contract_asset_audit_warnings_strict(tmp_path: Path) -> None:
    repo_root = copy_minipack_repo(tmp_path)
    artifacts_dir = tmp_path / "artifacts"
    report_path = tmp_path / "release_report.json"

    extra_path = repo_root / "packs" / "core" / "assets" / "spark.png"
    extra_path.parent.mkdir(parents=True, exist_ok=True)
    extra_path.write_bytes(b"different")

    exit_code = run_release_contract(
        artifacts_dir=artifacts_dir,
        repo_root=repo_root,
        report_path=report_path,
    )
    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["counts"]["warning_count"] >= 1

    strict_report_path = tmp_path / "release_report_strict.json"
    exit_code_strict = run_release_contract(
        artifacts_dir=artifacts_dir,
        repo_root=repo_root,
        report_path=strict_report_path,
        strict=True,
    )
    assert exit_code_strict == 1
