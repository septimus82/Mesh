import mesh_cli


def test_pipeline_happy_path(monkeypatch, capsys):
    calls = []

    def fake_apply(*, plan_path, ai_safe, dry_run, no_lint, run_tests):
        calls.append(("apply", plan_path, ai_safe, dry_run))
        return 0

    def fake_validate(argv=None):
        calls.append(("validate", list(argv or [])))
        return 0

    def fake_demo(**kwargs):
        calls.append(("demo",))
        return 0

    monkeypatch.setattr("engine.tooling.pipeline_runner.apply_plan", fake_apply)
    monkeypatch.setattr("engine.tooling.pipeline_runner.validate_all.main", fake_validate)
    monkeypatch.setattr("engine.tooling.pipeline_runner.launch_demo", fake_demo)

    rc = mesh_cli.main(["pipeline", "plan.json", "worlds/main_world.json", "--demo"])
    assert rc == 0

    out = capsys.readouterr().out
    assert "[PIPELINE] apply-plan -> ok" in out
    assert "[PIPELINE] validate-all -> ok" in out
    assert "[PIPELINE] demo -> ok" in out

    assert calls == [
        ("apply", "plan.json", False, False),
        ("validate", ["worlds/main_world.json"]),
        ("demo",),
    ]
