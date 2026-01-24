import mesh_cli
from engine.tooling.tool_result import ToolResult


def test_wizard_run_pipeline_failure_calls_doctor(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        "engine.tooling.wizard_command.run_pipeline_result",
        lambda **kwargs: ToolResult.failure(exit_code=2),
    )

    report = {
        "version": 1,
        "target": "worlds/main_world.json",
        "summary": {"errors": 1, "warnings": 0, "checks": 1},
        "runs": [],
        "errors": [{"source": "validate-all", "message": "Scene scenes/test_scene.json: Broken"}],
        "warnings": [],
        "suggested_next_commands": [],
    }

    monkeypatch.setattr(
        "engine.tooling.wizard_command.DoctorRunner.run_result",
        lambda self, *, world: ToolResult.from_doctor_report_dict(report),
    )
    monkeypatch.setattr(
        "engine.tooling.wizard_command.DoctorRunner.format_report",
        lambda self, report, *, quiet, json_output: "[DOCTOR]\n",
    )
    monkeypatch.setattr(
        "engine.tooling.wizard_command.ExplainRunner.explain_result",
        lambda self, result, *, json_output: "[EXPLAIN]\n",
    )
    monkeypatch.setattr(
        "engine.tooling.wizard_command.ExplainRunner.store_last_failure",
        lambda self, report: None,
    )

    rc = mesh_cli.main(
        [
            "wizard",
            "new-puzzle",
            "--scene",
            "scenes/test_scene.json",
            "--plan",
            "out_plan.json",
            "--world",
            "worlds/main_world.json",
            "--run",
        ]
    )
    assert rc == 2

    out = capsys.readouterr().out
    assert "[DOCTOR]" in out
    assert "[EXPLAIN]" in out
