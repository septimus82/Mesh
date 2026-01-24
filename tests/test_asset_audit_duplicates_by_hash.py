from __future__ import annotations

from pathlib import Path

from engine.tooling.assets_audit import run_asset_audit
from tests.fixture_repo import copy_minipack_repo


def test_asset_audit_duplicates_by_hash(tmp_path: Path) -> None:
    repo_root = copy_minipack_repo(tmp_path)
    path_a = repo_root / "packs" / "core" / "assets" / "dup" / "a.png"
    path_b = repo_root / "packs" / "core" / "fx" / "dup" / "b.png"
    path_a.parent.mkdir(parents=True, exist_ok=True)
    path_b.parent.mkdir(parents=True, exist_ok=True)
    payload = b"same-bytes"
    path_a.write_bytes(payload)
    path_b.write_bytes(payload)

    exit_code, report = run_asset_audit(
        repo_root=repo_root,
        out_path=repo_root / "artifacts" / "asset_audit.json",
        with_duplicates=True,
        write_report=False,
    )

    assert exit_code == 0
    dup_groups = [d for d in report["duplicates"] if d["kind"] == "duplicate_content_hash"]
    assert dup_groups
    paths = dup_groups[0]["paths"]
    assert "packs/core/assets/dup/a.png" in paths
    assert "packs/core/fx/dup/b.png" in paths
