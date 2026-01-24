import json
import pytest
import argparse
from pathlib import Path
from unittest.mock import patch, MagicMock
import mesh_cli
from engine.tooling.plan_types import Plan, Action

def test_apply_plan_ai_safe_requires_touches(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    
    # Create a plan without touches
    plan_path = tmp_path / "unsafe.plan.json"
    plan_data = {
        "wizard": "test",
        "version": 1,
        "inputs": {
            "meta": {} 
        },
        "actions": [
            {"type": "create_scene", "args": {"path": "scenes/test.json", "template": "basic"}, "description": "test"}
        ]
    }
    plan_path.write_text(json.dumps(plan_data), encoding="utf-8")
    
    args = argparse.Namespace(
        command="apply-plan",
        plan_path=str(plan_path),
        no_lint=False,
        dry_run=True,
        run_tests=False,
        ai_safe=True,
        from_triage=False
    )
    
    # Mock dependencies to isolate the check
    with patch("mesh_cli.legacy_impl.plan_linter") as mock_linter, \
         patch("engine.tooling.plan_tester.PlanTester") as MockTester:
        
        # If the check passes, these would be called
        mock_linter.lint_ai_plan.return_value = []
        MockTester.return_value.run_ai_tests.return_value.passed = True
        
        from io import StringIO
        import sys
        captured_out = StringIO()
        monkeypatch.setattr(sys, "stdout", captured_out)
        
        exit_code = mesh_cli._handle_apply_plan(args)
        
        assert exit_code == 1
        output = captured_out.getvalue()
        assert "Failed to apply plan: AI-safe apply requires plan.meta.touches (non-empty)" in output

def test_apply_plan_ai_safe_with_empty_touches_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    
    # Create a plan with EMPTY touches
    plan_path = tmp_path / "empty_touches.plan.json"
    plan_data = {
        "wizard": "test",
        "version": 1,
        "inputs": {
            "meta": {
                "touches": []
            } 
        },
        "actions": [
            {"type": "create_scene", "args": {"path": "scenes/test.json", "template": "basic"}, "description": "test"}
        ]
    }
    plan_path.write_text(json.dumps(plan_data), encoding="utf-8")
    
    args = argparse.Namespace(
        command="apply-plan",
        plan_path=str(plan_path),
        no_lint=False,
        dry_run=True,
        run_tests=False,
        ai_safe=True,
        from_triage=False
    )
    
    with patch("mesh_cli.legacy_impl.plan_linter") as mock_linter, \
         patch("engine.tooling.plan_tester.PlanTester") as MockTester:
        
        mock_linter.lint_ai_plan.return_value = []
        MockTester.return_value.run_ai_tests.return_value.passed = True
        
        from io import StringIO
        import sys
        captured_out = StringIO()
        monkeypatch.setattr(sys, "stdout", captured_out)
        
        exit_code = mesh_cli._handle_apply_plan(args)
        
        assert exit_code == 1
        output = captured_out.getvalue()
        assert "Failed to apply plan: AI-safe apply requires plan.meta.touches (non-empty)" in output

def test_apply_plan_ai_safe_with_touches_passes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    
    # Create a plan WITH touches
    plan_path = tmp_path / "safe.plan.json"
    plan_data = {
        "wizard": "test",
        "version": 1,
        "inputs": {
            "meta": {
                "touches": ["scenes/test.json"]
            } 
        },
        "actions": [
            {"type": "create_scene", "args": {"path": "scenes/test.json", "template": "basic"}, "description": "test"}
        ]
    }
    plan_path.write_text(json.dumps(plan_data), encoding="utf-8")
    
    args = argparse.Namespace(
        command="apply-plan",
        plan_path=str(plan_path),
        no_lint=False,
        dry_run=True,
        run_tests=False,
        ai_safe=True,
        from_triage=False
    )
    
    with patch("mesh_cli.legacy_impl.plan_linter") as mock_linter, \
         patch("engine.tooling.plan_tester.PlanTester") as MockTester:
        
        mock_linter.lint_ai_plan.return_value = []
        MockTester.return_value.run_ai_tests.return_value.passed = True
        
        from io import StringIO
        import sys
        captured_out = StringIO()
        monkeypatch.setattr(sys, "stdout", captured_out)
        
        exit_code = mesh_cli._handle_apply_plan(args)
        
        assert exit_code == 0
        output = captured_out.getvalue()
        assert "AI safety checks passed" in output

def test_plan_executor_enforces_touches_directly(tmp_path):
    """Verify that PlanExecutor enforces touches even when called directly."""
    from engine.tooling.plan_executor import PlanExecutor
    
    plan = Plan(
        wizard="test",
        version=1,
        inputs={"meta": {}}, # No touches
        actions=[]
    )
    
    executor = PlanExecutor(dry_run=True)
    
    # 1. ai_safe=True -> Should raise
    with pytest.raises(ValueError, match="AI-safe apply requires plan.meta.touches"):
        executor.execute(plan, ai_safe=True)
        
    # 2. ai_safe=False -> Should pass
    executor.execute(plan, ai_safe=False)

