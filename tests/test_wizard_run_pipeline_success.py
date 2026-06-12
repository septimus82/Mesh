
import mesh_cli
from engine.tooling.tool_result import ToolResult


def test_wizard_run_pipeline_success(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    calls = []

    def fake_run_pipeline_result(**kwargs):
        calls.append(kwargs)
        return ToolResult.success()

    monkeypatch.setattr("engine.tooling.wizard_command.run_pipeline_result", fake_run_pipeline_result)

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
            "--run",
        ]
    )
    assert rc == 0

    assert calls and calls[0]["plan_path"] == str(plan_path)
    assert calls[0]["path"] == "worlds/main_world.json"
    assert calls[0]["ai_safe"] is True
