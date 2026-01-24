import mesh_cli


def test_pipeline_stops_on_validation_failure(monkeypatch, capsys):
    def fake_apply(*, plan_path, ai_safe, dry_run, no_lint, run_tests):
        return 0

    def fake_validate(argv=None):
        return 2

    def fake_demo():
        raise AssertionError("demo should not run after validate-all failure")

    monkeypatch.setattr("engine.tooling.pipeline_runner.apply_plan", fake_apply)
    monkeypatch.setattr("engine.tooling.pipeline_runner.validate_all.main", fake_validate)
    monkeypatch.setattr("engine.tooling.pipeline_runner.launch_demo", fake_demo)

    rc = mesh_cli.main(["pipeline", "plan.json", "worlds/main_world.json", "--demo"])
    assert rc == 2

    out = capsys.readouterr().out
    assert "[PIPELINE] apply-plan -> ok" in out
    assert "[PIPELINE] validate-all -> FAILED" in out
    assert "[PIPELINE] demo" not in out
    assert "[PIPELINE] Next:" in out
    assert "mesh doctor --world worlds/main_world.json" in out
    assert "mesh explain --last" in out
