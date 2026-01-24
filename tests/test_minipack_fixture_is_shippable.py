from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pytest

from mesh_cli.release_contract import release_contract_command, validate_release_report_v1
from tests.fixture_repo import copy_minipack_repo

pytestmark = [pytest.mark.slow, pytest.mark.integration]


def test_minipack_fixture_is_shippable(tmp_path: Path, monkeypatch) -> None:
    repo_root = copy_minipack_repo(tmp_path)
    runner_root = tmp_path / "runner"
    runner_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(runner_root)

    artifacts_dir = repo_root / "artifacts"
    report_path = artifacts_dir / "release_report.json"
    args = argparse.Namespace(
        repo_root=str(repo_root),
        artifacts=str(artifacts_dir),
        report=str(report_path),
    )
    rc = release_contract_command(args)
    workspace_root = Path.cwd().resolve()
    canary_dir = workspace_root / "artifacts" / "canary"
    canary_dir.mkdir(parents=True, exist_ok=True)
    canary_report = canary_dir / "release_report.json"
    assert report_path.exists()
    shutil.copy2(report_path, canary_report)
    canary_log = canary_dir / "content_contract.log"
    source_log = artifacts_dir / "content_contract.log"
    if source_log.exists():
        shutil.copy2(source_log, canary_log)

    assert canary_report.exists()
    if source_log.exists():
        assert canary_log.exists()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    validate_release_report_v1(payload)
    assert rc == 0
