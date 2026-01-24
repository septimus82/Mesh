from __future__ import annotations

from pathlib import Path

from engine.tooling.assets_audit import run_asset_audit
from tests.fixture_repo import copy_minipack_repo


def test_asset_audit_ok_minipack(tmp_path: Path) -> None:
    repo_root = copy_minipack_repo(tmp_path)
    exit_code, report = run_asset_audit(
        repo_root=repo_root,
        out_path=repo_root / "artifacts" / "asset_audit.json",
        write_report=False,
    )

    assert exit_code == 0
    assert report["summary"]["ok"] is True
    assert report["errors"] == []
