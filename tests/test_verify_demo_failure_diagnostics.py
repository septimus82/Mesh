from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import engine.tooling_runtime.verify_demo as verify_demo


pytestmark = [pytest.mark.fast]


def test_verify_demo_failure_writes_log_and_artifact(tmp_path, monkeypatch, capsys) -> None:
    def fake_run(_cmd, capture_output=False, text=False, cwd=None):  # noqa: ARG001
        return SimpleNamespace(
            returncode=2,
            stdout="pytest stdout line\n",
            stderr=(
                "pytest stderr line\n"
                "FileNotFoundError: [WinError 2] No such file or directory: "
                "'D:\\Games\\Mesh\\tests\\temp_trend'\n"
            ),
        )

    monkeypatch.setattr(verify_demo, "iter_missing_paths", lambda _paths: [])
    monkeypatch.setattr(verify_demo.subprocess, "run", fake_run)

    artifacts_dir = tmp_path / "artifacts"
    log_path = artifacts_dir / "verify_demo.log"
    code = verify_demo.run_verify_demo(
        capture_output=True,
        quiet=True,
        log_path=log_path,
        scratch_dir=artifacts_dir / "verify_demo_pytest",
    )

    assert code == 2
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "pytest stdout line" in content
    assert "pytest stderr line" in content

    failure_path = artifacts_dir / "verify_demo_failure.json"
    payload = json.loads(failure_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["exit_code"] == 2
    assert payload["cwd"]
    assert payload["argv"][:3] == ["python", "-m", "pytest"] or payload["argv"][1:3] == ["-m", "pytest"]
    assert payload["basetemp"].endswith("/basetemp") or payload["basetemp"].endswith("\\basetemp")
    assert payload["cache_dir"].endswith("/cache") or payload["cache_dir"].endswith("\\cache")
    assert payload["stdout_head"] == ["pytest stdout line"]
    assert payload["stderr_head"] == [
        "pytest stderr line",
        "FileNotFoundError: [WinError 2] No such file or directory: 'D:\\Games\\Mesh\\tests\\temp_trend'",
    ]
    assert payload["missing_path"] == "D:\\Games\\Mesh\\tests\\temp_trend"

    stderr = capsys.readouterr().err
    assert "VDEMO-001 verify-demo failed exit=2" in stderr
    assert "verify_demo_failure.json" in stderr
    assert "basetemp=" in stderr
    assert "cache_dir=" in stderr
