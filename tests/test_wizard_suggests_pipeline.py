
import mesh_cli


def test_wizard_suggests_pipeline(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("wizard should not run pipeline unless --run/--apply is set")

    monkeypatch.setattr("engine.tooling.wizard_command.run_pipeline_result", fail_if_called)

    plan_path = tmp_path / "out_plan.json"
    rc = mesh_cli.main(
        [
            "wizard",
            "new-puzzle",
            "--scene",
            "scenes/test_scene.json",
            "--plan",
            str(plan_path),
            "--world",
            "worlds/main_world.json",
        ]
    )
    assert rc == 0

    out = capsys.readouterr().out
    assert "Next step:" in out
    assert f"mesh pipeline --plan {plan_path} --world worlds/main_world.json --ai-safe" in out
