from __future__ import annotations

from pathlib import Path

from engine.tooling.assets_audit import run_asset_audit
from tests.fixture_repo import copy_minipack_repo


def test_asset_audit_orphans_detects_unused(tmp_path: Path) -> None:
    repo_root = copy_minipack_repo(tmp_path)
    orphan_path = repo_root / "packs" / "core" / "assets" / "unused.png"
    orphan_path.parent.mkdir(parents=True, exist_ok=True)
    orphan_path.write_bytes(b"unused")

    exit_code, report = run_asset_audit(
        repo_root=repo_root,
        out_path=repo_root / "artifacts" / "asset_audit.json",
        with_orphans=True,
        write_report=False,
    )

    assert exit_code == 0
    assert report["summary"]["orphan_count"] == 1
    paths = {entry["path"] for entry in report["orphans"]}
    assert "packs/core/assets/unused.png" in paths
