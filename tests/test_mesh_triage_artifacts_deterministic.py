import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from engine.tooling import triage_command
from engine.tooling.plan_types import Action, Plan


def test_mesh_triage_artifacts_deterministic(tmp_path, monkeypatch):
    """
    Ensure triage artifacts are byte-for-byte deterministic.
    """
    monkeypatch.chdir(tmp_path)

    # Setup minimal world
    world_path = tmp_path / "world.json"
    world_path.write_text(json.dumps({"scenes": {"missing": {"path": "missing.json"}}}, indent=2))

    # Mock Doctor, Explain, PlanFix to return stable results
    # Note: We must patch where they are imported in triage_command, not where they are defined
    with patch("engine.tooling.triage_command.DoctorRunner") as MockDoctor, \
         patch("engine.tooling.triage_command.ExplainRunner") as MockExplain, \
         patch("engine.tooling.plan_fix_command.generate_fix_plan") as mock_gen_plan:

        # Doctor Result
        mock_doctor_instance = MockDoctor.return_value
        mock_result = MagicMock()
        mock_result.exit_code = 1
        mock_result.to_doctor_report_dict.return_value = {
            "version": 1,
            "issues": [{"code": "MISSING_SCENE", "message": "Scene missing"}]
        }
        mock_doctor_instance.run_result.return_value = mock_result

        # Explain Result
        mock_explain_instance = MockExplain.return_value
        mock_explain_instance._last_failure_path = Path("artifacts/last_failure.json")
        mock_explain_instance.explain_result.return_value = json.dumps({
            "version": 1,
            "analysis": "Missing scene",
            "action_hints": [{"suggested_action": "create_scene", "target": "missing.json"}]
        })

        # Plan Result
        mock_plan = Plan(
            wizard="fix-from-doctor",
            version=1,
            inputs={"meta": {"touches": ["missing.json"], "unfixable": []}},
            actions=[
                Action(type="create_scene", args={"path": "missing.json", "template": "empty"}, description="Create missing scene")
            ]
        )
        mock_gen_plan.return_value = mock_plan

        # Run 1
        args = argparse.Namespace(world="world.json", out="plan.json", write_artifacts=True)
        triage_command.run_triage_command(args)

        artifacts_dir = tmp_path / "artifacts"
        doctor1 = (artifacts_dir / "triage_last_doctor.json").read_bytes()
        explain1 = (artifacts_dir / "triage_last_explain.json").read_bytes()
        plan1 = (artifacts_dir / "triage_last_plan.json").read_bytes()

        # Run 2
        triage_command.run_triage_command(args)

        doctor2 = (artifacts_dir / "triage_last_doctor.json").read_bytes()
        explain2 = (artifacts_dir / "triage_last_explain.json").read_bytes()
        plan2 = (artifacts_dir / "triage_last_plan.json").read_bytes()

        # Assert Determinism
        assert doctor1 == doctor2, "Doctor artifact not deterministic"
        assert explain1 == explain2, "Explain artifact not deterministic"
        assert plan1 == plan2, "Plan artifact not deterministic"

        # Assert Structure
        doctor_json = json.loads(doctor1)
        assert "version" in doctor_json

        explain_json = json.loads(explain1)
        assert "version" in explain_json

        plan_json = json.loads(plan1)
        assert "meta" in plan_json
        assert "touches" in plan_json["meta"]
        # Check touches sorted
        assert plan_json["meta"]["touches"] == sorted(plan_json["meta"]["touches"])
