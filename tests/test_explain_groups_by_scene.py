import mesh_cli
from engine.tooling.tool_result import ToolResult


def test_explain_groups_by_scene(monkeypatch, capsys):
    report = {
        "version": 1,
        "target": "worlds/main_world.json",
        "summary": {"errors": 1, "warnings": 0, "checks": 1},
        "runs": [],
        "errors": [{"source": "validate-all", "message": "Scene packs/core/scenes/test_scene.json: Bad thing"}],
        "warnings": [],
        "suggested_next_commands": [],
    }

    def fake_run_result(self, *, world):
        assert world == "worlds/main_world.json"
        return ToolResult.from_doctor_report_dict(report)

    monkeypatch.setattr("engine.tooling.explain.DoctorRunner.run_result", fake_run_result)

    rc = mesh_cli.main(["explain", "--world", "worlds/main_world.json"])
    assert rc == 1

    out = capsys.readouterr().out
    assert "[EXPLAIN] scene: packs/core/scenes/test_scene.json" in out
