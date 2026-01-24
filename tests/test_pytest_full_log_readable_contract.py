from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def test_pytest_full_log_is_utf8_and_has_durations(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    fake_repo = tmp_path / "fake_repo"
    tests_dir = fake_repo / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    (tests_dir / "test_sample.py").write_text(
        "def test_sample_pass():\n"
        "    assert True\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["MESH_PYTEST_FULL_REPO_ROOT"] = str(fake_repo)
    result = subprocess.run(
        [sys.executable, "-m", "tooling.pytest_full", "--timeout-s", "60"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    log_path = fake_repo / "artifacts" / "pytest_full.log"
    log_text = log_path.read_text(encoding="utf-8")
    assert "--durations" in log_text
    assert "test_sample" in log_text
