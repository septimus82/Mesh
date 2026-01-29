from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from tests.subprocess_tools import run_checked

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def test_pytest_full_runs_unfiltered(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    fake_repo = tmp_path / "fake_repo"
    tests_dir = fake_repo / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    (fake_repo / "pytest.ini").write_text(
        "[pytest]\n"
        "addopts = -m fast\n"
        "markers =\n"
        "    slow: slow tests\n"
        "    e2e: e2e tests\n",
        encoding="utf-8",
    )

    (tests_dir / "test_full_suite.py").write_text(
        "from pathlib import Path\n"
        "import pytest\n"
        "\n"
        "@pytest.mark.slow\n"
        "def test_slow_runs():\n"
        "    Path('slow_ran.txt').write_text('ok', encoding='utf-8')\n"
        "\n"
        "@pytest.mark.e2e\n"
        "def test_e2e_runs():\n"
        "    Path('e2e_ran.txt').write_text('ok', encoding='utf-8')\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["MESH_PYTEST_FULL_REPO_ROOT"] = str(fake_repo)
    result = run_checked(
        [sys.executable, "-m", "tooling.pytest_full"],
        cwd=repo_root,
        env=env,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert (fake_repo / "slow_ran.txt").exists()
    assert (fake_repo / "e2e_ran.txt").exists()
