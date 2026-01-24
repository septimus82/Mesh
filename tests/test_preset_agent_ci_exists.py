import pytest
from engine.config import load_config

def test_preset_agent_ci_exists():
    """
    Verify that the 'agent-ci' preset exists and contains the required safety gates.
    """
    config = load_config()
    presets = getattr(config, "presets", {})
    
    assert "agent-ci" in presets, "agent-ci preset missing from config.json"
    
    preset = presets["agent-ci"]
    assert preset["description"] == "Agent safety + determinism gates"
    
    steps = preset.get("steps", [])
    assert len(steps) == 10, f"Expected 10 steps, found {len(steps)}"
    
    # Step 1: Preset Lint
    assert steps[0]["cmd"] == "python"
    assert steps[0]["args"] == ["mesh_cli.py", "preset", "lint"]
    
    expected_tests = [
        "tests/test_agent_rules_doc_guard.py",
        "tests/test_plan_executor_write_seam_gate.py",
        "tests/test_mesh_assist_diff_coverage_contract.py",
        "tests/test_plan_action_classification_guard.py",
        "tests/test_plan_schema_sync_guard.py",
        "tests/test_plan_schema_metadata_coverage.py",
        "tests/test_plan_schema_ai_out_deterministic.py",
        "tests/test_mesh_triage_artifacts_deterministic.py",
        "tests/test_mesh_assist_summary_json_deterministic.py"
    ]
    
    for i, test_file in enumerate(expected_tests):
        step = steps[i+1]
        assert step["cmd"] == "python"
        args = step["args"]
        # args should be ["-m", "pytest", "-q", test_file]
        assert args == ["-m", "pytest", "-q", test_file], f"Step {i+2} mismatch. Expected to run {test_file}"
