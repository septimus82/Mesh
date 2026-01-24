import json

import mesh_cli
from engine.tooling.tool_result import ToolResult


def test_explain_json_schema(monkeypatch, capsys):
    report = {
        "version": 1,
        "target": "worlds/main_world.json",
        "summary": {"errors": 0, "warnings": 1, "checks": 1},
        "runs": [],
        "errors": [],
        "warnings": [{"source": "validate-all", "message": "Scene packs/core/scenes/test_scene.json: Minor issue"}],
        "suggested_next_commands": [],
    }

    monkeypatch.setattr(
        "engine.tooling.explain.DoctorRunner.run_result",
        lambda self, *, world: ToolResult.from_doctor_report_dict(report),
    )

    rc = mesh_cli.main(["explain", "--world", "worlds/main_world.json", "--json"])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == 1
    assert isinstance(payload["summary"], str)
    assert isinstance(payload["root_causes"], list)
    assert isinstance(payload["files"], list)
    assert isinstance(payload["suggested_fixes"], list)
    
    # Check content
    assert len(payload["files"]) > 0
    assert "packs/core/scenes/test_scene.json" in payload["files"][0]
