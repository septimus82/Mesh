import mesh_cli
from engine.tooling.tool_result import ToolResult


def test_explain_outputs_fix_commands(monkeypatch, capsys):
    report = {
        "version": 1,
        "target": "worlds/main_world.json",
        "summary": {"errors": 1, "warnings": 0, "checks": 1},
        "runs": [],
        "errors": [{"source": "validate-all", "message": "Scene packs/core/scenes/test_scene.json: Missing ref"}],
        "warnings": [],
        "suggested_next_commands": [],
    }

    monkeypatch.setattr(
        "engine.tooling.explain.DoctorRunner.run_result",
        lambda self, *, world: ToolResult.from_doctor_report_dict(report),
    )

    rc = mesh_cli.main(["explain", "--world", "worlds/main_world.json"])
    assert rc == 1

    out = capsys.readouterr().out
    assert "    - mesh validate-all packs/core/scenes/test_scene.json" in out
