from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def _run_blocked_arcade_pytest(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    script = r"""
import importlib.abc
import pytest
import sys

class _BlockArcade(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "arcade" or fullname.startswith("arcade."):
            raise ModuleNotFoundError("No module named 'arcade'")
        return None

sys.meta_path.insert(0, _BlockArcade())
raise SystemExit(pytest.main(%s))
""" % (repr(args),)
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.fast
def test_fast_suite_does_not_require_arcade() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = _run_blocked_arcade_pytest(
        [
            "-q",
            "-W",
            "error",
            "--strict-markers",
            "-m",
            "fast",
            "tests/test_pytest_fast_headless_contract.py",
            "tests/test_no_arcade_static_imports_policy.py",
        ],
        cwd=repo_root,
    )
    assert result.returncode == 0, result.stderr + result.stdout
