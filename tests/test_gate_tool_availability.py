"""The ruff and mypy gates and the mypy island fail closed when their tool can't run (#624).

Each case runs the real gate (`python -m tooling.<gate>`) in a child process. The tool is made absent for that child,
and for the tool process the gate starts, by a sitecustomize that blocks the import; or it is replaced by a stand-in
package on PYTHONPATH that prints what the case needs and exits with its code.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[1]
_STAND_IN = (
    "import os, sys\n"
    "sys.stdout.write(os.environ['MESH_TEST_TOOL_STDOUT'])\n"
    "sys.stderr.write(os.environ['MESH_TEST_TOOL_STDERR'])\n"
    "raise SystemExit(int(os.environ['MESH_TEST_TOOL_EXIT']))\n"
)
_RUFF_FINDING = (
    '[{"filename": "engine/not_in_baseline.py", "code": "F821", "message": "Undefined name `gate_test_624`",'
    ' "location": {"row": 1, "column": 1}}]'
)
_MYPY_FINDING = (
    "engine/not_in_baseline.py:1: error: Name \"gate_test_624\" is not defined  [name-defined]\n"
    "Found 1 error in 1 file (checked 1 source file)\n"
)


def _run_gate(tmp_path: Path, gate: str, tool: str, *, stdout: str = "", stderr: str = "", exit_code: int = 0,
              absent: bool = False) -> subprocess.CompletedProcess[str]:
    shim = tmp_path / "shim"
    if absent:
        shim.mkdir()
        (shim / "sitecustomize.py").write_text(f"import sys\nsys.modules[{tool!r}] = None\n", encoding="utf-8")
    else:
        (shim / tool).mkdir(parents=True)
        (shim / tool / "__init__.py").write_text("", encoding="utf-8")
        (shim / tool / "__main__.py").write_text(_STAND_IN, encoding="utf-8")
    env = dict(os.environ, MESH_TEST_TOOL_STDOUT=stdout, MESH_TEST_TOOL_STDERR=stderr,
               MESH_TEST_TOOL_EXIT=str(exit_code))
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(shim), env.get("PYTHONPATH", "")]))
    return subprocess.run([sys.executable, "-m", f"tooling.{gate}"], cwd=REPO_ROOT, env=env,
                          capture_output=True, text=True, timeout=120)


def test_ruff_gate_fails_closed_when_ruff_is_absent(tmp_path: Path) -> None:
    result = _run_gate(tmp_path, "ruff_gate", "ruff", absent=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "[ruff-gate] ruff is not available" in result.stderr
    assert "[ruff-gate] ok" not in result.stdout


@pytest.mark.parametrize(("stdout", "stderr", "exit_code"), [
    ("", "No module named ruff\n", 1),       # exit 1 with nothing on stdout: ruff never ran
    ("ruff: error\n", "", 1),               # not JSON
    ('{"not": "a list"}', "", 0),           # JSON, but not a findings list
    ("[]", "error: bad config\n", 2),        # ruff's own error exit
], ids=["empty-exit-1", "not-json", "not-a-list", "exit-2"])
def test_ruff_gate_fails_closed_when_ruff_output_is_unusable(
    tmp_path: Path, stdout: str, stderr: str, exit_code: int
) -> None:
    result = _run_gate(tmp_path, "ruff_gate", "ruff", stdout=stdout, stderr=stderr, exit_code=exit_code)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "[ruff-gate] ruff did not report findings" in result.stderr
    assert "[ruff-gate] ok" not in result.stdout


def test_ruff_gate_still_passes_clean_and_fails_new_findings(tmp_path: Path) -> None:
    clean = _run_gate(tmp_path / "clean", "ruff_gate", "ruff", stdout="[]", exit_code=0)
    assert (clean.returncode, clean.stdout.strip()) == (0, "[ruff-gate] ok"), clean.stderr
    found = _run_gate(tmp_path / "found", "ruff_gate", "ruff", stdout=_RUFF_FINDING, exit_code=1)
    assert found.returncode == 1, found.stdout + found.stderr
    assert "engine/not_in_baseline.py: F821 Undefined name `gate_test_624`" in found.stdout


def test_mypy_gate_fails_closed_when_mypy_is_absent(tmp_path: Path) -> None:
    result = _run_gate(tmp_path, "mypy_gate", "mypy", absent=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "[mypy-gate] mypy is not available" in result.stderr
    assert "[mypy-gate] ok" not in result.stdout


@pytest.mark.parametrize(("stdout", "stderr", "exit_code"), [
    ("", "No module named mypy\n", 1),       # exit 1 with no summary: mypy never ran
    ("", "", 0),                            # exit 0 with no summary
], ids=["no-module-exit-1", "silent-exit-0"])
def test_mypy_gate_fails_closed_when_mypy_reports_nothing(
    tmp_path: Path, stdout: str, stderr: str, exit_code: int
) -> None:
    result = _run_gate(tmp_path, "mypy_gate", "mypy", stdout=stdout, stderr=stderr, exit_code=exit_code)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "[mypy-gate] mypy did not report a result" in result.stderr
    assert "[mypy-gate] ok" not in result.stdout


def test_mypy_gate_still_passes_clean_and_fails_new_errors(tmp_path: Path) -> None:
    clean = _run_gate(tmp_path / "clean", "mypy_gate", "mypy",
                      stdout="Success: no issues found in 1 source file\n", exit_code=0)
    assert (clean.returncode, clean.stdout.strip()) == (0, "[mypy-gate] ok"), clean.stderr
    found = _run_gate(tmp_path / "found", "mypy_gate", "mypy", stdout=_MYPY_FINDING, exit_code=1)
    assert found.returncode == 1, found.stdout + found.stderr
    assert 'engine/not_in_baseline.py: error: Name "gate_test_624" is not defined  [name-defined]' in found.stdout


def test_mypy_island_fails_closed_when_mypy_is_absent(tmp_path: Path) -> None:
    result = _run_gate(tmp_path, "mypy_island", "mypy", absent=True)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "[mypy-island] mypy is not available" in result.stderr
    assert "[mypy-island] ok" not in result.stdout


@pytest.mark.parametrize(("stdout", "stderr", "exit_code"), [
    ("", "Traceback (most recent call last):\nRuntimeError: boom\n", 2),  # a fatal exit: nothing was checked
    ("", "No module named mypy\n", 1),                                   # exit 1 without a single error line
    ("", "INTERNAL ERROR\n", 3),
], ids=["fatal-exit-2", "no-errors-exit-1", "exit-3"])
def test_mypy_island_fails_closed_when_mypy_does_not_check(
    tmp_path: Path, stdout: str, stderr: str, exit_code: int
) -> None:
    result = _run_gate(tmp_path, "mypy_island", "mypy", stdout=stdout, stderr=stderr, exit_code=exit_code)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "[mypy-island] mypy did not check the island" in result.stderr
    assert "[mypy-island] ok" not in result.stdout


def test_mypy_island_still_passes_clean_and_fails_errors(tmp_path: Path) -> None:
    clean = _run_gate(tmp_path / "clean", "mypy_island", "mypy", exit_code=0)  # --no-error-summary: silent when clean
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert "[mypy-island] ok" in clean.stdout
    found = _run_gate(tmp_path / "found", "mypy_island", "mypy", stdout=_MYPY_FINDING, exit_code=1)
    assert found.returncode == 1, found.stdout + found.stderr
    assert 'engine/not_in_baseline.py:1: error: Name "gate_test_624" is not defined' in found.stdout


def test_mypy_island_fails_closed_when_an_island_module_is_missing(monkeypatch: pytest.MonkeyPatch,
                                                                    capsys: pytest.CaptureFixture[str]) -> None:
    """A moved or deleted island module used to drop out of the check silently (and an empty island passed)."""
    from tooling import mypy_island

    monkeypatch.setattr(mypy_island, "TYPED_ISLAND_MODULES", ("engine/not_an_island_module_624.py",))
    monkeypatch.setattr(mypy_island.importlib.util, "find_spec", lambda name, package=None: object())
    assert mypy_island.main([]) == 2
    captured = capsys.readouterr()
    assert "island module not found: engine/not_an_island_module_624.py" in captured.err
    assert "[mypy-island] ok" not in captured.out
