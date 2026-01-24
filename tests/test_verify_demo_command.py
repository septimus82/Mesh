from pathlib import Path
from unittest.mock import MagicMock

from engine.tooling.verify_demo import build_verify_demo_pytest_cmd, run_verify_demo


def test_verify_demo_builds_deterministic_pytest_cmd(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)

    captured = {}

    def _fake_run(cmd, capture_output=False):  # noqa: ARG001
        captured["cmd"] = cmd
        return MagicMock(returncode=0)

    monkeypatch.setattr("engine.tooling.verify_demo.subprocess.run", _fake_run)

    rc = run_verify_demo()
    assert rc == 0
    assert captured["cmd"] == build_verify_demo_pytest_cmd()


def test_verify_demo_appends_pytest_passthrough_args(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)

    captured = {}

    def _fake_run(cmd, capture_output=False):  # noqa: ARG001
        captured["cmd"] = cmd
        return MagicMock(returncode=0)

    monkeypatch.setattr("engine.tooling.verify_demo.subprocess.run", _fake_run)

    extra = ["--maxfail=1"]
    rc = run_verify_demo(extra)
    assert rc == 0
    assert captured["cmd"] == build_verify_demo_pytest_cmd() + extra


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
