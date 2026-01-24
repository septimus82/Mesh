import unittest
from unittest.mock import MagicMock, patch
import argparse
import json
import os
from pathlib import Path
from engine.tooling import triage_command

class TestMeshTriageArtifacts(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path("tests/temp_triage_artifacts")
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir = Path("artifacts")
        
        # Ensure artifacts dir exists (it might not in test env)
        if not self.artifacts_dir.exists():
            self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import shutil
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir)
        
        # Clean up artifacts created during test
        for f in ["triage_last_doctor.json", "triage_last_explain.json"]:
            p = self.artifacts_dir / f
            if p.exists():
                p.unlink()

    def test_triage_write_artifacts(self):
        # Mock DoctorRunner and ExplainRunner to avoid running real checks
        with patch("engine.tooling.triage_command.DoctorRunner") as MockDoctorRunner, \
             patch("engine.tooling.triage_command.ExplainRunner") as MockExplainRunner, \
             patch("engine.tooling.triage_command.plan_fix_command.generate_fix_plan") as mock_generate_plan:
            
            # Setup Doctor Result
            mock_result = MagicMock()
            mock_result.exit_code = 1
            mock_result.to_doctor_report_dict.return_value = {"issues": ["some_issue"]}
            
            mock_doctor_instance = MockDoctorRunner.return_value
            mock_doctor_instance.run_result.return_value = mock_result
            
            # Setup Explain Result
            mock_explain_instance = MockExplainRunner.return_value
            mock_explain_instance._last_failure_path = "artifacts/last_failure.json"
            mock_explain_instance.explain_result.return_value = '{"explanation": "some explanation", "action_hints": []}'
            
            # Setup Plan Generation
            mock_plan = MagicMock()
            mock_plan.wizard = "fix_wizard"
            mock_plan.version = 1
            mock_plan.inputs = {"meta": {"description": "Fix plan"}, "some_input": "value"}
            mock_plan.actions = []
            mock_generate_plan.return_value = mock_plan
            
            # Run command
            out_plan = self.tmp_dir / "fix_plan.json"
            args = argparse.Namespace(
                world="worlds/test.json",
                out=str(out_plan),
                write_artifacts=True
            )
            
            # Capture stdout to check for printed paths
            with patch("builtins.print") as mock_print:
                triage_command.run_triage_command(args)
                
                # Verify files exist
                doctor_artifact = self.artifacts_dir / "triage_last_doctor.json"
                explain_artifact = self.artifacts_dir / "triage_last_explain.json"
                
                self.assertTrue(doctor_artifact.exists(), "Doctor artifact should exist")
                self.assertTrue(explain_artifact.exists(), "Explain artifact should exist")
                
                # Verify content
                with open(doctor_artifact, "r") as f:
                    data = json.load(f)
                    self.assertEqual(data, {"issues": ["some_issue"]})
                    
                with open(explain_artifact, "r") as f:
                    data = json.load(f)
                    self.assertEqual(data["explanation"], "some explanation")
                    self.assertIn("plan_meta", data)
                    self.assertEqual(data["plan_meta"]["touches"], [])
                    self.assertEqual(data["plan_meta"]["unfixable"], [])
                
                # Verify output mentions artifacts
                printed_text = "\n".join(call.args[0] for call in mock_print.call_args_list)
                self.assertIn("artifacts/triage_last_doctor.json", printed_text)
                self.assertIn("artifacts/triage_last_explain.json", printed_text)

    def test_triage_no_write_artifacts(self):
        # Mock DoctorRunner and ExplainRunner
        with patch("engine.tooling.triage_command.DoctorRunner") as MockDoctorRunner, \
             patch("engine.tooling.triage_command.ExplainRunner") as MockExplainRunner, \
             patch("engine.tooling.triage_command.plan_fix_command.generate_fix_plan") as mock_generate_plan:
            
            mock_result = MagicMock()
            mock_result.exit_code = 1
            mock_result.to_doctor_report_dict.return_value = {"issues": ["some_issue"]}
            MockDoctorRunner.return_value.run_result.return_value = mock_result
            
            MockExplainRunner.return_value._last_failure_path = "artifacts/last_failure.json"
            MockExplainRunner.return_value.explain_result.return_value = '{"explanation": "some explanation"}'
            
            mock_plan = MagicMock()
            mock_plan.wizard = "fix_wizard"
            mock_plan.version = 1
            mock_plan.inputs = {"meta": {"description": "Fix plan"}}
            mock_plan.actions = []
            mock_generate_plan.return_value = mock_plan
            
            out_plan = self.tmp_dir / "fix_plan.json"
            args = argparse.Namespace(
                world="worlds/test.json",
                out=str(out_plan),
                write_artifacts=False
            )
            
            triage_command.run_triage_command(args)
            
            # Verify files do NOT exist
            doctor_artifact = self.artifacts_dir / "triage_last_doctor.json"
            explain_artifact = self.artifacts_dir / "triage_last_explain.json"
            
            self.assertFalse(doctor_artifact.exists(), "Doctor artifact should NOT exist")
            self.assertFalse(explain_artifact.exists(), "Explain artifact should NOT exist")
