from pathlib import Path
from unittest.mock import MagicMock

import pytest

import engine.tooling_runtime.verify_demo as runtime_verify_demo
from engine.tooling.verify_demo import build_verify_demo_pytest_cmd, run_verify_demo


pytestmark = [pytest.mark.fast]


def test_verify_demo_builds_deterministic_pytest_cmd(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)

    captured = {}

    def _fake_run(cmd, capture_output=False, text=False, cwd=None):  # noqa: ARG001
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return MagicMock(returncode=0)

    monkeypatch.setattr("engine.tooling.verify_demo.subprocess.run", _fake_run)

    rc = run_verify_demo()
    assert rc == 0
    assert captured["cmd"] == build_verify_demo_pytest_cmd()


def test_verify_demo_appends_pytest_passthrough_args(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)

    captured = {}

    def _fake_run(cmd, capture_output=False, text=False, cwd=None):  # noqa: ARG001
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return MagicMock(returncode=0)

    monkeypatch.setattr("engine.tooling.verify_demo.subprocess.run", _fake_run)

    extra = ["--maxfail=1"]
    rc = run_verify_demo(extra)
    assert rc == 0
    assert captured["cmd"] == build_verify_demo_pytest_cmd() + extra


def test_verify_demo_uses_artifacts_scoped_pytest_scratch_when_log_path_provided(monkeypatch, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)

    captured = {}

    def _fake_run(cmd, capture_output=False, text=False, cwd=None):  # noqa: ARG001
        captured["cmd"] = list(cmd)
        captured["cwd"] = cwd
        return MagicMock(returncode=0)

    monkeypatch.setattr("engine.tooling.verify_demo.subprocess.run", _fake_run)

    artifacts_dir = tmp_path / "artifacts"
    log_path = artifacts_dir / "verify_demo.log"
    rc = run_verify_demo(capture_output=True, quiet=True, log_path=log_path)

    assert rc == 0
    cmd = captured["cmd"]
    assert cmd[: len(build_verify_demo_pytest_cmd())] == build_verify_demo_pytest_cmd()
    assert cmd[len(build_verify_demo_pytest_cmd())] == "--basetemp"
    basetemp = Path(cmd[len(build_verify_demo_pytest_cmd()) + 1])
    assert basetemp.parent.parent == artifacts_dir / "verify_demo_pytest"
    assert basetemp.name == "basetemp"
    assert cmd[len(build_verify_demo_pytest_cmd()) + 2 :] == [
        "-o",
        f"cache_dir={(basetemp.parent / 'cache').as_posix()}",
    ]
    assert captured["cwd"] == str(root)
    assert not (artifacts_dir / "verify_demo_failure.json").exists()


def test_verify_demo_run_paths_are_distinct_across_back_to_back_runs(monkeypatch, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)

    captured: list[list[str]] = []

    def _fake_run(cmd, capture_output=False, text=False, cwd=None):  # noqa: ARG001
        captured.append(list(cmd))
        return MagicMock(returncode=0)

    monkeypatch.setattr("engine.tooling.verify_demo.subprocess.run", _fake_run)

    scratch_dir = tmp_path / "artifacts" / "verify_demo_pytest"
    assert run_verify_demo(capture_output=True, quiet=True, scratch_dir=scratch_dir) == 0
    assert run_verify_demo(capture_output=True, quiet=True, scratch_dir=scratch_dir) == 0

    first_basetemp = Path(captured[0][len(build_verify_demo_pytest_cmd()) + 1])
    second_basetemp = Path(captured[1][len(build_verify_demo_pytest_cmd()) + 1])
    assert first_basetemp != second_basetemp
    assert first_basetemp.parent.parent == scratch_dir
    assert second_basetemp.parent.parent == scratch_dir
    assert not (tmp_path / "artifacts" / "verify_demo_failure.json").exists()


def test_verify_demo_success_does_not_require_or_create_shared_tests_temp_dirs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runtime_verify_demo, "iter_missing_paths", lambda _paths: [])

    def _fake_run(cmd, capture_output=False, text=False, cwd=None):  # noqa: ARG001
        return MagicMock(returncode=0)

    monkeypatch.setattr("engine.tooling.verify_demo.subprocess.run", _fake_run)

    shared_dirs = [
        tmp_path / "tests" / "temp_trend",
        tmp_path / "tests" / "temp_audit_auto",
    ]
    for shared_dir in shared_dirs:
        assert not shared_dir.exists()

    scratch_dir = tmp_path / "artifacts" / "verify_demo_pytest"
    assert run_verify_demo(capture_output=True, quiet=True, scratch_dir=scratch_dir) == 0
    assert run_verify_demo(capture_output=True, quiet=True, scratch_dir=scratch_dir) == 0

    for shared_dir in shared_dirs:
        assert not shared_dir.exists()


def test_verify_demo_strict_guard_rejects_selection_changing_flags(monkeypatch, capsys) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)

    # Should fail before attempting to spawn pytest.
    monkeypatch.setattr(
        "engine.tooling.verify_demo.subprocess.run",
        lambda *a, **k: MagicMock(returncode=0),
    )

    rc = run_verify_demo(["-k", "smoke"])
    assert rc != 0
    _ = capsys.readouterr()
