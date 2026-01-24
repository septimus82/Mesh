from pathlib import Path

import mesh_cli
from engine.tooling.tool_result import ToolResult


def test_explain_from_doctor_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)

    report = {
        "version": 1,
        "target": "worlds/main_world.json",
        "summary": {"errors": 1, "warnings": 0, "checks": 1},
        "runs": [],
        "errors": [{"source": "validate-all", "message": "Scene packs/core/scenes/test_scene.json: Broken"}],
        "warnings": [],
        "suggested_next_commands": [],
    }

    monkeypatch.setattr(
        "engine.tooling.doctor.DoctorRunner.run_result",
        lambda self, *, world: ToolResult.from_doctor_report_dict(report),
    )

    rc = mesh_cli.main(["doctor", "--world", "worlds/main_world.json"])
    assert rc == 1

    last_path = Path(".mesh/reports/doctor_last_failure.json")
    assert last_path.exists()

    capsys.readouterr()
    rc2 = mesh_cli.main(["explain", "--last"])
    assert rc2 == 1
    out = capsys.readouterr().out
    assert "[EXPLAIN] scene: packs/core/scenes/test_scene.json" in out
