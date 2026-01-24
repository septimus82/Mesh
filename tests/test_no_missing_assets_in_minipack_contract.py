from __future__ import annotations

import json
from pathlib import Path

from mesh_cli.main import main as mesh_main
from tests.fixture_repo import copy_minipack_repo


def test_no_missing_assets_in_minipack_contract(tmp_path: Path) -> None:
    repo_root = copy_minipack_repo(tmp_path)
    out_path = repo_root / "artifacts" / "asset_audit.json"

    rc = mesh_main(
        [
            "assets",
            "audit",
            "--repo-root",
            str(repo_root),
            "--out",
            str(out_path),
        ]
    )
    assert rc == 0

    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report.get("errors") == []
    assert report.get("summary", {}).get("missing_files") == 0
