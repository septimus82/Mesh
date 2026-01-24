from __future__ import annotations

from pathlib import Path

from engine.tooling.assets_audit import run_asset_audit
from tests.fixture_repo import copy_minipack_repo, write_text


def test_asset_audit_orphans_allowlist(tmp_path: Path) -> None:
    repo_root = copy_minipack_repo(tmp_path)
    orphan_path = repo_root / "packs" / "core" / "assets" / "dev" / "keep.png"
    orphan_path.parent.mkdir(parents=True, exist_ok=True)
    orphan_path.write_bytes(b"unused")

    write_text(
        repo_root,
        "packs/core/pack.json",
        '{"id": "core", "version": "1.0.0", "asset_audit": {"allow_orphans": ["assets/dev/*"]}}\n',
    )

    exit_code, report = run_asset_audit(
        repo_root=repo_root,
        out_path=repo_root / "artifacts" / "asset_audit.json",
        with_orphans=True,
        write_report=False,
    )

    assert exit_code == 0
    paths = {entry["path"] for entry in report["orphans"]}
    assert "packs/core/assets/dev/keep.png" not in paths
