import argparse
import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from engine.tooling import triage_command
from engine.tooling.plan_types import Action, Plan


def test_mesh_triage_warns_and_skips_plan_artifact_on_invalid_touches(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()

    # Pre-create plan artifact to ensure invalid run removes it.
    stale_plan = artifacts_dir / "triage_last_plan.json"
    stale_plan.write_text('{"stale": true}\n', encoding="utf-8")

    with patch("engine.tooling.triage_command.DoctorRunner") as MockDoctorRunner, patch(
        "engine.tooling.triage_command.ExplainRunner"
    ) as MockExplainRunner, patch(
        "engine.tooling.triage_command.plan_fix_command.generate_fix_plan"
    ) as mock_generate_plan:
        mock_result = MagicMock()
        mock_result.exit_code = 1
        mock_result.to_doctor_report_dict.return_value = {"version": 1, "errors": [], "warnings": []}
        MockDoctorRunner.return_value.run_result.return_value = mock_result

        mock_explain_instance = MockExplainRunner.return_value
        mock_explain_instance._last_failure_path = Path("artifacts/last_failure.json")
        mock_explain_instance.explain_result.return_value = json.dumps(
            {"version": 1, "analysis": "x", "action_hints": []}
        )

        # Invalid: missing/empty touches for an action target.
        mock_plan = Plan(
            wizard="fix-from-doctor",
            version=1,
            inputs={"meta": {"touches": [], "unfixable": []}},
            actions=[Action(type="create_scene", args={"path": "missing.json", "template": "empty"}, description="c")],
        )
        mock_generate_plan.return_value = mock_plan

        out_plan = tmp_path / "plan.json"
        args = argparse.Namespace(world="world.json", out=str(out_plan), write_artifacts=True)

        from io import StringIO
        import sys

        captured = StringIO()
        monkeypatch.setattr(sys, "stdout", captured)
        rc = triage_command.run_triage_command(args)

    assert rc == 0

    output = captured.getvalue()
    match = re.search(r"(\{.*\})", output, re.DOTALL)
    assert match, output
    payload = json.loads(match.group(1))
    assert "warnings" in payload
    assert {"id": "plan_invalid_touches", "message": "Plan invalid: touches mismatch"} in payload["warnings"]

    assert (artifacts_dir / "triage_last_doctor.json").exists()
    assert (artifacts_dir / "triage_last_explain.json").exists()
    assert not (artifacts_dir / "triage_last_plan.json").exists()
