from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.subprocess_tools import run_checked

pytestmark = [pytest.mark.integration]


def _run_blocking_arcade(code: str, *, cwd: Path) -> "subprocess.CompletedProcess[str]":
    import subprocess  # Only needed for type hint
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


def test_validate_all_strict_headless_no_arcade(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    scene_path = tmp_path / "headless_scene.json"
    scene_path.write_text(json.dumps({"name": "Headless", "entities": []}), encoding="utf-8")

    code = (
        "from engine.tooling import validate_all\n"
        f"raise SystemExit(int(validate_all.main([{scene_path.as_posix()!r},'--strict','--schema-strict'])))\n"
    )
    result = _run_blocking_arcade(code, cwd=repo_root)
    assert result.returncode == 0, result.stderr + result.stdout
