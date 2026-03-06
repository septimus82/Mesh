from __future__ import annotations

from pathlib import Path

import pytest


pytestmark = pytest.mark.fast


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
