import json
import pytest
import argparse
from pathlib import Path
from unittest.mock import patch, MagicMock
import mesh_cli

def test_apply_plan_from_triage_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    
    # Setup artifacts
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    
    plan_path = artifacts_dir / "triage_last_plan.json"
    plan_data = {
        "wizard": "fix-from-doctor",
        "version": 1,
        "inputs": {
            "meta": {
                "touches": ["some/file.json"]
            }
        },
        "actions": []
    }
    plan_path.write_text(json.dumps(plan_data), encoding="utf-8")
    
    # Mock PlanExecutor to avoid actual execution
    with patch("mesh_cli.ai.PlanExecutor") as MockExecutor, \
         patch("mesh_cli.ai.plan_linter") as mock_linter, \
         patch("engine.tooling.plan_tester.PlanTester") as MockTester:
        
        mock_executor_instance = MockExecutor.return_value
        mock_executor_instance.execute.return_value = True
        mock_executor_instance.summary = {}
        
        mock_linter.lint_ai_plan.return_value = []
        mock_linter.lint_plan.return_value = []
        
        # Mock PlanTester
        MockTester.return_value.run_ai_tests.return_value.passed = True
        
        args = argparse.Namespace(
            command="apply-plan",
            from_triage=True,
            plan_path=None,
            no_lint=False,
            dry_run=False,
            run_tests=False,
            ai_safe=False # Should be forced to True
        )
        
        # Capture stdout
        from io import StringIO
        import sys
        captured_out = StringIO()
        monkeypatch.setattr(sys, "stdout", captured_out)
        
        exit_code = mesh_cli._handle_apply_plan(args)
        
        assert exit_code == 0
        assert args.ai_safe == True
        assert Path(args.plan_path).resolve() == plan_path.resolve()
        
        output = captured_out.getvalue()
        assert "Using triage plan" in output
        assert "Next commands:" in output
        assert "mesh preset lint" in output
        assert f"mesh plan test-ai --path {args.plan_path}" in output

def test_apply_plan_from_triage_missing_artifact(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    
    # No artifacts dir
    
    args = argparse.Namespace(
         command="apply-plan",
         from_triage=True,
         plan_path=None,
         no_lint=False,
         dry_run=False,
         run_tests=False,
         ai_safe=False
    )
    
    from io import StringIO
    import sys
    captured_out = StringIO()
    monkeypatch.setattr(sys, "stdout", captured_out)
    
    exit_code = mesh_cli._handle_apply_plan(args)
    
    assert exit_code == 1
    output = captured_out.getvalue()
    assert "Error: No triage plan found" in output
