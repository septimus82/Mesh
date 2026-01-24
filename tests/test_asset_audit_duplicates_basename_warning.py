from __future__ import annotations

from pathlib import Path

from engine.tooling.assets_audit import run_asset_audit
from tests.fixture_repo import copy_minipack_repo


def test_asset_audit_duplicates_basename_warning(tmp_path: Path) -> None:
    repo_root = copy_minipack_repo(tmp_path)
    extra_path = repo_root / "packs" / "core" / "assets" / "spark.png"
    extra_path.parent.mkdir(parents=True, exist_ok=True)
    extra_path.write_bytes(b"different")

    exit_code, report = run_asset_audit(
        repo_root=repo_root,
        out_path=repo_root / "artifacts" / "asset_audit.json",
        with_duplicates=True,
        write_report=False,
    )

    assert exit_code == 0
    warnings = {w["kind"] for w in report["warnings"]}
    assert "duplicate_basename_collision" in warnings
    dup_groups = [d for d in report["duplicates"] if d["kind"] == "duplicate_basename_collision"]
    assert dup_groups
