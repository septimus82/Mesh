from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.fast


class _MypyResult:
    returncode = 1
    stderr = ""

    def __init__(self, stdout: str) -> None:
        self.stdout = stdout


def _run_gate_with_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    baseline: str,
    output: str,
    argv: list[str] | None = None,
) -> int:
    from tooling import mypy_gate

    baseline_path = tmp_path / "mypy_baseline.txt"
    baseline_path.write_text(baseline, encoding="utf-8")
    monkeypatch.setattr(mypy_gate, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(mypy_gate, "BASELINE_PATH", baseline_path)
    monkeypatch.setattr(mypy_gate.subprocess, "run", lambda *_args, **_kwargs: _MypyResult(output))
    return mypy_gate.main(argv or [])


def test_mypy_gate_collects_diagnostics_and_uses_stable_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from tooling import mypy_gate

    monkeypatch.setattr(mypy_gate, "_repo_root", lambda: tmp_path)

    captured: dict[str, object] = {}

    class _Result:
        returncode = 0
        stdout = "Success: no issues found in 3 source files\n"
        stderr = ""

    def _fake_run(cmd, cwd=None, capture_output=None, text=None):
        captured["cmd"] = list(cmd)
        captured["cwd"] = cwd
        return _Result()

    monkeypatch.setattr(mypy_gate.subprocess, "run", _fake_run)

    exit_code = mypy_gate.main([])
    assert exit_code == 0

    diagnostics = mypy_gate.get_last_run_diagnostics()
    assert isinstance(diagnostics, dict)
    assert diagnostics["schema_version"] == 1
    assert diagnostics["python_version"]
    assert diagnostics["files_checked"] == 3
    assert "Success: no issues found in 3 source files" in str(diagnostics["summary"])
    assert isinstance(diagnostics["wall_time_seconds"], float)
    assert diagnostics["wall_time_seconds"] >= 0.0

    cache = diagnostics["cache"]
    assert isinstance(cache, dict)
    assert cache["enabled"] is True
    assert cache["incremental"] is True
    cache_dir = str(cache["cache_dir"])
    assert cache_dir.endswith("/.mypy_cache/mypy_gate")

    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert "--incremental" in cmd
    assert "--cache-dir" in cmd
    cache_idx = cmd.index("--cache-dir")
    assert cmd[cache_idx + 1] == str(tmp_path / ".mypy_cache" / "mypy_gate")


def test_mypy_gate_allows_line_drift_with_same_normalized_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    baseline = 'engine/example.py:10: error: "object" has no attribute "name"  [attr-defined]\n'
    output = 'engine/example.py:99: error: "object" has no attribute "name"  [attr-defined]\nFound 1 error in 1 file\n'

    assert _run_gate_with_output(monkeypatch, tmp_path, baseline=baseline, output=output) == 0


def test_mypy_gate_fails_on_new_normalized_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline = 'engine/example.py:10: error: "object" has no attribute "name"  [attr-defined]\n'
    output = 'engine/example.py:99: error: "object" has no attribute "other"  [attr-defined]\nFound 1 error in 1 file\n'

    assert _run_gate_with_output(monkeypatch, tmp_path, baseline=baseline, output=output) == 1
    assert 'engine/example.py: error: "object" has no attribute "other"  [attr-defined]' in capsys.readouterr().out


def test_mypy_gate_fails_on_duplicate_growth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    baseline = 'engine/example.py:10: error: Returning Any from function declared to return "bool"  [no-any-return]\n'
    output = (
        'engine/example.py:10: error: Returning Any from function declared to return "bool"  [no-any-return]\n'
        'engine/example.py:20: error: Returning Any from function declared to return "bool"  [no-any-return]\n'
        "Found 2 errors in 1 file\n"
    )

    assert _run_gate_with_output(monkeypatch, tmp_path, baseline=baseline, output=output) == 1
    assert capsys.readouterr().out.count("Returning Any from function declared to return") == 1


def test_mypy_gate_update_baseline_writes_normalized_occurrences(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from tooling import mypy_gate

    output = (
        'engine/example.py:10: error: Name "rows" already defined on line 8  [no-redef]\n'
        'engine/example.py:20: error: Name "rows" already defined on line 18  [no-redef]\n'
        "Found 2 errors in 1 file\n"
    )

    assert _run_gate_with_output(monkeypatch, tmp_path, baseline="", output=output, argv=["--update-baseline"]) == 0
    lines = [line.strip() for line in mypy_gate.BASELINE_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines == [
        'engine/example.py: error: Name "rows" already defined on line <line>  [no-redef]',
        'engine/example.py: error: Name "rows" already defined on line <line>  [no-redef]',
    ]
