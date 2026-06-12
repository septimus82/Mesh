from pathlib import Path

import pytest

import engine.tooling.verify_demo
import mesh_cli

pytestmark = [pytest.mark.fast]


def test_mesh_cli_parser_accepts_verify_demo_command() -> None:
    parser = mesh_cli.create_parser()
    args = parser.parse_args(["verify-demo"])
    assert args.command == "verify-demo"
    assert getattr(args, "pytest_args", []) == []


def test_mesh_cli_parser_accepts_verify_demo_passthrough_after_double_dash() -> None:
    parser = mesh_cli.create_parser()
    args = parser.parse_args(["verify-demo", "--", "--maxfail=1"])
    assert args.command == "verify-demo"
    assert getattr(args, "pytest_args") == ["--", "--maxfail=1"]


def test_mesh_cli_parser_accepts_verify_demo_artifacts_ci_bundle_compat_flags() -> None:
    parser = mesh_cli.create_parser()
    args = parser.parse_args(["verify-demo", "--artifacts", "artifacts", "--ci-bundle"])
    assert args.command == "verify-demo"
    assert getattr(args, "artifacts") == "artifacts"
    assert getattr(args, "ci_bundle") is True
    assert getattr(args, "pytest_args", []) == []


def test_mesh_cli_main_strips_double_dash_before_forwarding(monkeypatch) -> None:
    captured = {}

    def _fake_run_verify_demo(pytest_args, **_kwargs):
        captured["pytest_args"] = list(pytest_args)
        return 0

    monkeypatch.setattr(engine.tooling.verify_demo, "run_verify_demo", _fake_run_verify_demo)
    rc = mesh_cli.main(["verify-demo", "--", "--maxfail=1"])
    assert rc == 0
    assert captured["pytest_args"] == ["--maxfail=1"]


def test_mesh_cli_main_accepts_verify_demo_without_compat_flags(monkeypatch, capsys) -> None:
    captured = {}

    def _fake_run_verify_demo(pytest_args, **_kwargs):
        captured["pytest_args"] = list(pytest_args)
        captured["kwargs"] = dict(_kwargs)
        return 0

    monkeypatch.setattr(engine.tooling.verify_demo, "run_verify_demo", _fake_run_verify_demo)
    rc = mesh_cli.main(["verify-demo"])

    assert rc == 0
    assert captured["pytest_args"] == []
    assert captured["kwargs"] == {
        "capture_output": True,
        "quiet": True,
        "log_path": None,
        "scratch_dir": None,
    }
    assert capsys.readouterr().out == '{\n  "code": 0,\n  "ok": true\n}\n'


def test_mesh_cli_main_accepts_verify_demo_artifacts_ci_bundle_compat_flags(monkeypatch, capsys) -> None:
    captured = {}

    def _fake_run_verify_demo(pytest_args, **_kwargs):
        captured["pytest_args"] = list(pytest_args)
        captured["kwargs"] = dict(_kwargs)
        return 0

    monkeypatch.setattr(engine.tooling.verify_demo, "run_verify_demo", _fake_run_verify_demo)
    rc = mesh_cli.main(["verify-demo", "--artifacts", "artifacts", "--ci-bundle"])

    assert rc == 0
    assert captured["pytest_args"] == []
    assert captured["kwargs"] == {
        "capture_output": True,
        "quiet": True,
        "log_path": Path("artifacts") / "verify_demo.log",
        "scratch_dir": Path("artifacts") / "verify_demo_pytest",
    }
    assert capsys.readouterr().out == '{\n  "code": 0,\n  "ok": true\n}\n'
