import json
import pytest
import argparse
from pathlib import Path
from engine.tooling import plan_fix_command, plan_linter
from engine.tooling.plan_types import Plan, Action

def test_plan_fix_from_doctor_end_to_end(tmp_path):
    # 1. Create a fake doctor report
    report = {
        "errors": [
            {
                "source": "doctor",
                "message": "Scene 'scenes/missing_scene.json' not found",
                "file": "scenes/missing_scene.json"
            },
            {
                "source": "validate-all",
                "message": "Validation failed for 'scenes/broken_scene.json'",
                "file": "scenes/broken_scene.json"
            }
        ],
        "warnings": []
    }
    
    report_path = tmp_path / "doctor_report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    
    out_plan_path = tmp_path / "fix.plan.json"
    
    # 2. Invoke the command logic
    args = argparse.Namespace(
        last=False,
        path=str(report_path),
        out=str(out_plan_path)
    )
    
    exit_code = plan_fix_command.run_plan_fix_command(args)
    
    assert exit_code == 0
    assert out_plan_path.exists()
    
    # 3. Verify content
    plan_data = json.loads(out_plan_path.read_text(encoding="utf-8"))
    
    assert plan_data["wizard"] == "fix-from-doctor"
    assert plan_data["version"] == 1
    assert plan_data["meta"]["source"] == "doctor"
    # Normalize path separators for comparison
    assert Path(plan_data["meta"]["artifact"]).as_posix() == report_path.as_posix()
    
    # Check touches
    touches = plan_data["meta"].get("touches", [])
    assert "scenes/broken_scene.json" in touches
    assert "scenes/missing_scene.json" in touches
    assert len(touches) == 2
    
    actions = plan_data["actions"]
    assert len(actions) == 2
    
    # Check deterministic order (file path)
    # broken_scene.json comes before missing_scene.json
    assert actions[0]["type"] == "validate"
    assert actions[0]["args"]["scene_path"] == "scenes/broken_scene.json"
    
    assert actions[1]["type"] == "create_scene"
    assert actions[1]["args"]["path"] == "scenes/missing_scene.json"
    
    # 4. Run real lint-ai
    plan_obj = Plan.from_dict(plan_data)
    
    issues = plan_linter.lint_ai_plan(plan_obj)
    
    # If there are issues, print them for debugging
    if issues:
        print("\nLint issues:")
        for issue in issues:
            print(f"{issue.severity}: {issue.message} (Action {issue.action_index})")
            
    assert len(issues) == 0

def test_plan_fix_from_doctor_outside_roots(tmp_path):
    report = {
        "errors": [
            {
                "source": "doctor",
                "message": "Bad file",
                "file": "engine/bad_file.py"
            }
        ],
        "warnings": []
    }
    
    report_path = tmp_path / "doctor_report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    out_plan_path = tmp_path / "fix.plan.json"
    
    args = argparse.Namespace(
        last=False,
        path=str(report_path),
        out=str(out_plan_path)
    )
    
    exit_code = plan_fix_command.run_plan_fix_command(args)
    assert exit_code == 0
    
    plan_data = json.loads(out_plan_path.read_text(encoding="utf-8"))
    
    # Should be unfixable
    assert len(plan_data["actions"]) == 0
    assert "engine/bad_file.py" in plan_data["meta"]["unfixable"]
    assert len(plan_data["meta"]["notes"]) > 0
    assert "outside allowed roots" in plan_data["meta"]["notes"][0]

def test_plan_fix_policy_sync():
    """Ensure fix-from-doctor and lint-ai share the exact same allowed path policy."""
    test_paths = [
        ("scenes/good.json", True),
        ("packs/good.json", True),
        ("worlds/good.json", True),
        ("assets/good.json", True),
        ("engine/bad.py", False),
        ("root_file.json", False),
        ("other/bad.json", False),
    ]

    for path, expected_allowed in test_paths:
        # 1. Check lint-ai policy
        # Create a minimal plan with an action using this path
        plan = Plan(
            wizard="test",
            version=1,
            inputs={},
            actions=[
                Action(
                    type="create_scene",
                    args={"path": path, "template": "basic"},
                    description="test"
                )
            ]
        )
        
        issues = plan_linter.lint_ai_plan(plan)
        has_path_error = any(i.code == "UNSAFE_PATH" for i in issues)
        
        if expected_allowed:
            assert not has_path_error, f"lint-ai should allow {path}"
        else:
            assert has_path_error, f"lint-ai should reject {path}"

        # 2. Check fix-from-doctor policy
        # Create a fake report with an issue in this file
        report = {
            "errors": [
                {
                    "source": "doctor",
                    "message": f"Missing {path}",
                    "file": path
                }
            ],
            "warnings": []
        }
        
        fix_plan = plan_fix_command.generate_fix_plan(report, "dummy_artifact")
        
        # Check if it was rejected by root enforcement
        was_rejected_by_policy = path in fix_plan.inputs["meta"]["unfixable"]
        
        if expected_allowed:
            assert not was_rejected_by_policy, f"fix-from-doctor should allow {path} (not in unfixable)"
            # We don't strictly require an action here, just that it wasn't blocked by policy
        else:
            assert was_rejected_by_policy, f"fix-from-doctor should reject {path} (must be in unfixable)"

def test_plan_fix_from_doctor_unmapped_issues(tmp_path):
    report = {
        "errors": [
            {
                "source": "unknown_source",
                "message": "Some weird error",
                "file": "scenes/weird.json"
            }
        ],
        "warnings": []
    }
    
    report_path = tmp_path / "doctor_report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    out_plan_path = tmp_path / "fix.plan.json"
    
    args = argparse.Namespace(
        last=False,
        path=str(report_path),
        out=str(out_plan_path)
    )
    
    exit_code = plan_fix_command.run_plan_fix_command(args)
    assert exit_code == 0
    
    plan_data = json.loads(out_plan_path.read_text(encoding="utf-8"))
    assert len(plan_data["actions"]) == 0
    
    notes = plan_data["meta"]["notes"]
    assert len(notes) == 1
    assert "Unfixable unknown_source: Some weird error" in notes[0]
    
    # Lint should still pass (empty plan is valid?)
    plan_obj = Plan.from_dict(plan_data)
    issues = plan_linter.lint_ai_plan(plan_obj)
    assert len(issues) == 0
