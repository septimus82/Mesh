import mesh_cli


def test_pipeline_stops_on_plan_failure(monkeypatch, capsys):
    def fake_apply(*, plan_path, ai_safe, dry_run, no_lint, run_tests):
        return 1

    def fake_validate(argv=None):
        raise AssertionError("validate-all should not run after apply-plan failure")

    monkeypatch.setattr("engine.tooling.pipeline_runner.apply_plan", fake_apply)
    monkeypatch.setattr("engine.tooling.pipeline_runner.validate_all.main", fake_validate)

    rc = mesh_cli.main(["pipeline", "plan.json", "worlds/main_world.json"])
    assert rc == 1

    out = capsys.readouterr().out
    assert "[PIPELINE] apply-plan -> FAILED" in out
    assert "[PIPELINE] validate-all" not in out
