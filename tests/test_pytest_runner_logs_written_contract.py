from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.subprocess_tools import run_checked

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _write_failing_test(repo_root: Path) -> None:
    tests_dir = repo_root / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_fail.py").write_text(
        "def test_fail():\n"
        "    assert False\n",
        encoding="utf-8",
    )


def test_pytest_runner_logs_written_on_failure(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    _write_failing_test(repo_root)

    full = run_checked(
        [sys.executable, "-m", "tooling.pytest_full", "--repo-root", str(repo_root)],
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert full.returncode != 0
    assert (repo_root / "artifacts" / "pytest_full.log").exists()

    fast = run_checked(
        [sys.executable, "-m", "tooling.pytest_fast", "--repo-root", str(repo_root)],
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert fast.returncode != 0
    assert (repo_root / "artifacts" / "pytest_fast.log").exists()
