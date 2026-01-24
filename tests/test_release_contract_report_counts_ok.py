from __future__ import annotations

import argparse
import json
from pathlib import Path

from mesh_cli.release_contract import release_contract_command
from tests.fixture_repo import copy_minipack_repo, mutate_file


def test_release_contract_report_counts_ok(tmp_path: Path, monkeypatch) -> None:
    repo_root = copy_minipack_repo(tmp_path)
    runner_root = tmp_path / "runner"
    runner_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(runner_root)
    mutate_file(
        repo_root,
        "packs/core/fx/presets.json",
        lambda payload: {
            "schema_version": 1,
            "presets": {
                "spark_hit": {"sprite": "packs/core/fx/spark.png"},
                "spark_small": {"sprite": "packs/core/fx/spark.png"},
            },
        },
    )

    report_path = repo_root / "artifacts" / "release_report.json"
    args = argparse.Namespace(
        artifacts="artifacts",
        repo_root=str(repo_root),
        report=str(report_path),
    )
    rc = release_contract_command(args)
    assert rc == 0

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["counts"]["presets_validated"] == 2
    assert payload["counts"]["content_files_checked"] == 1
    assert payload["counts"]["errors"] == 0

    steps = payload["steps"]
    step_by_name = {step["name"]: step for step in steps}
    assert step_by_name["pack-validate"]["outputs"]["presets_validated"] == 2
    assert step_by_name["content-contract"]["outputs"]["files_checked"] == 1
