from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def _run_blocking_arcade(code: str, *, cwd: Path) -> subprocess.CompletedProcess[str]:
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
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.fast
def test_mesh_cli_imports_do_not_require_arcade(tmp_path: Path) -> None:
    # Importing the CLI (and building the parser) must not require arcade.
    repo_root = Path(__file__).resolve().parents[1]
    result = _run_blocking_arcade(
        "import mesh_cli\nimport mesh_cli.legacy_impl\nfrom mesh_cli.main import create_parser\ncreate_parser()\nprint('ok')\n",
        cwd=repo_root,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "ok" in result.stdout


@pytest.mark.integration
@pytest.mark.slow
def test_mesh_cli_verify_all_runs_headless_without_arcade(tmp_path: Path) -> None:
    # verify-all must run without arcade so CI can execute tooling gates headlessly.
    repo_root = Path(__file__).resolve().parents[1]
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    result = _run_blocking_arcade(
        (
            "from mesh_cli.main import main\n"
            f"raise SystemExit(int(main(['verify-all','--artifacts',{artifacts_dir.as_posix()!r}])))\n"
        ),
        cwd=repo_root,
    )
    assert result.returncode == 0, result.stderr + result.stdout
