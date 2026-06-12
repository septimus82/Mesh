from __future__ import annotations

import sys
from pathlib import Path

from tests.subprocess_tools import run_checked


def _run_blocking_arcade(code: str, *, cwd: Path) -> "subprocess.CompletedProcess[str]":
    script = r"""
import importlib.abc
import sys

class _BlockArcade(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "arcade" or fullname.startswith("arcade."):
            raise ModuleNotFoundError("No module named 'arcade'")
        return None

sys.meta_path.insert(0, _BlockArcade())
""" + "\n" + code
    return run_checked(
        [sys.executable, "-c", script],
        cwd=str(cwd),
    )


def test_validate_all_import_does_not_load_behaviours_or_arcade() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = _run_blocking_arcade(
        (
            "from engine.behaviours.registry import BEHAVIOUR_REGISTRY\n"
            "print('before=' + str('TriggerZone' in BEHAVIOUR_REGISTRY))\n"
            "import engine.tooling.validate_all\n"
            "print('after_import=' + str('TriggerZone' in BEHAVIOUR_REGISTRY))\n"
            "from engine.behaviours import load_builtin_behaviours\n"
            "load_builtin_behaviours()\n"
            "print('after_load=' + str('TriggerZone' in BEHAVIOUR_REGISTRY))\n"
        ),
        cwd=repo_root,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "before=False" in result.stdout
    assert "after_import=False" in result.stdout
    assert "after_load=True" in result.stdout
