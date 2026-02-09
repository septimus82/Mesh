from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.subprocess_tools import run_checked


def _run_blocked_arcade_pytest(args: list[str], *, cwd: Path) -> "subprocess.CompletedProcess[str]":
    import subprocess  # Only needed for type hint
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
    return run_checked(
        [sys.executable, "-c", script],
        cwd=str(cwd),
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
            "-p",
            "no:cacheprovider",
            "-m",
            "fast",
            "tests/test_pytest_fast_headless_contract.py",
            "tests/test_no_arcade_static_imports_policy.py",
        ],
        cwd=repo_root,
    )
    assert result.returncode == 0, result.stderr + result.stdout
