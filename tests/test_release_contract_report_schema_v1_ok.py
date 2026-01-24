from __future__ import annotations

import argparse
import json
from pathlib import Path

from mesh_cli.release_contract import release_contract_command, validate_release_report_v1
from tests.fixture_repo import copy_minipack_repo


def test_release_contract_report_schema_v1_ok(tmp_path: Path, monkeypatch) -> None:
    repo_root = copy_minipack_repo(tmp_path)
    runner_root = tmp_path / "runner"
    runner_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(runner_root)

    report_path = repo_root / "artifacts" / "release_report.json"
    args = argparse.Namespace(
        artifacts="artifacts",
        repo_root=str(repo_root),
        report=str(report_path),
    )
    rc = release_contract_command(args)
    assert rc == 0

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    validate_release_report_v1(payload)
