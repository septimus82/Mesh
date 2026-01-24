import mesh_cli
import engine.tooling.verify_demo


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


def test_mesh_cli_main_strips_double_dash_before_forwarding(monkeypatch) -> None:
    captured = {}

    def _fake_run_verify_demo(pytest_args, **_kwargs):
        captured["pytest_args"] = list(pytest_args)
        return 0

    monkeypatch.setattr(engine.tooling.verify_demo, "run_verify_demo", _fake_run_verify_demo)
    rc = mesh_cli.main(["verify-demo", "--", "--maxfail=1"])
    assert rc == 0
    assert captured["pytest_args"] == ["--maxfail=1"]
