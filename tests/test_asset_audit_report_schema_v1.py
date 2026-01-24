from __future__ import annotations

from pathlib import Path

from engine.tooling.assets_audit import run_asset_audit
from tests.fixture_repo import copy_minipack_repo


def test_asset_audit_report_schema_v1(tmp_path: Path) -> None:
    repo_root = copy_minipack_repo(tmp_path)
    exit_code, report = run_asset_audit(
        repo_root=repo_root,
        out_path=repo_root / "artifacts" / "asset_audit.json",
        write_report=False,
    )

    assert exit_code == 0
    assert report["schema_version"] == 1
    assert isinstance(report["repo_root"], str)
    assert isinstance(report["packs_scanned"], int)
    assert isinstance(report["files_scanned"], int)
    assert isinstance(report["errors"], list)
    assert isinstance(report.get("warnings", []), list)
    assert isinstance(report.get("orphans", []), list)
    assert isinstance(report.get("duplicates", []), list)

    summary = report["summary"]
    assert isinstance(summary["ok"], bool)
    assert isinstance(summary["error_count"], int)
    assert isinstance(summary["missing_files"], int)
    assert isinstance(summary["invalid_values"], int)
    assert isinstance(summary["warning_count"], int)
    assert isinstance(summary["cross_pack_refs"], int)
    assert isinstance(summary["orphan_count"], int)
    assert isinstance(summary["duplicate_groups"], int)
