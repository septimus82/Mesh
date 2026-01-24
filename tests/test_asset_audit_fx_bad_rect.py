from __future__ import annotations

from pathlib import Path

from engine.tooling.assets_audit import run_asset_audit
from tests.fixture_repo import copy_minipack_repo, mutate_file


def test_asset_audit_fx_bad_rect(tmp_path: Path) -> None:
    repo_root = copy_minipack_repo(tmp_path)

    mutate_file(
        repo_root,
        "packs/core/fx/presets.json",
        lambda payload: _inject_bad_rect(payload),
    )

    exit_code, report = run_asset_audit(
        repo_root=repo_root,
        out_path=repo_root / "artifacts" / "asset_audit.json",
        write_report=False,
    )

    assert exit_code == 2
    assert report["summary"]["ok"] is False
    assert report["errors"]
    kinds = {err["kind"] for err in report["errors"]}
    assert kinds.intersection({"bad_rect", "invalid_value"})


def _inject_bad_rect(payload: dict) -> dict:
    presets = dict(payload.get("presets", {}))
    spark = dict(presets.get("spark_hit", {}))
    spark["rect"] = [-1, 0, 16, 16]
    presets["spark_hit"] = spark
    payload["presets"] = presets
    return payload
