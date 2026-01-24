from __future__ import annotations

from pathlib import Path

from engine.tooling.assets_audit import run_asset_audit
from tests.fixture_repo import copy_minipack_repo, write_text


def test_asset_audit_ownership_cross_pack_error(tmp_path: Path) -> None:
    repo_root = copy_minipack_repo(tmp_path)
    alpha_root = repo_root / "packs" / "alpha"
    write_text(
        repo_root,
        "packs/alpha/pack.json",
        '{"id": "alpha", "version": "1.0.0"}\n',
    )
    write_text(
        repo_root,
        "packs/alpha/scenes/alpha_scene.json",
        """
        {
          "entities": [
            {
              "name": "test",
              "sprite": "packs/core/fx/spark.png"
            }
          ]
        }
        """.strip()
        + "\n",
    )

    exit_code, report = run_asset_audit(
        repo_root=repo_root,
        out_path=repo_root / "artifacts" / "asset_audit.json",
        write_report=False,
    )

    assert exit_code == 2
    assert report["summary"]["ok"] is False
    kinds = {err["kind"] for err in report["errors"]}
    assert "cross_pack_reference" in kinds
    assert alpha_root.exists()
