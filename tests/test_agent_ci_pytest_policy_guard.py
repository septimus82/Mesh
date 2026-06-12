import pytest

from engine.config import load_config
from engine.tooling.preset_policy import validate_preset_python_step as _validate_python_step


def test_agent_ci_pytest_policy_guard():
    """
    Enforce strict policy on agent-ci preset steps to ensure they remain
    compliant, quiet, and focused on tests.
    """
    config = load_config()
    presets = getattr(config, "presets", {})

    assert "agent-ci" in presets, "agent-ci preset missing"
    preset = presets["agent-ci"]
    steps = preset.get("steps", [])

    lint_steps_found = 0

    for i, step in enumerate(steps):
        cmd = step.get("cmd")
        args = step.get("args", [])

        if cmd == "python":
            # 1. Validate using the standard preset validator
            try:
                _validate_python_step(args)
            except ValueError as e:
                pytest.fail(f"agent-ci step {i} failed validation: {e}")

            # Check for lint step
            if len(args) >= 3 and args[0] == "mesh_cli.py" and args[1] == "preset" and args[2] == "lint":
                lint_steps_found += 1
                continue

            # Check for pytest steps
            if len(args) >= 2 and args[0] == "-m" and args[1] == "pytest":
                # 2. Assert quiet mode
                assert "-q" in args, f"agent-ci step {i} must use -q for quiet output"

                # 3. Assert targets are in tests/
                # Filter out flags (starting with -) and the initial command parts
                targets = [arg for arg in args[2:] if not arg.startswith("-")]
                for target in targets:
                    assert target.startswith("tests/"), f"agent-ci step {i} target '{target}' must be in tests/"

    # 4. Assert exactly one lint step
    assert lint_steps_found == 1, f"agent-ci must have exactly 1 lint step, found {lint_steps_found}"
