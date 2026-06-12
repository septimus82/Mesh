import os

import pytest

from engine.config import load_config
from engine.tooling.preset_policy import validate_preset_python_step as _validate_python_step


def test_preset_python_step_policy_existing_presets():
    """
    Verify that all existing presets in config.json pass the python step policy.
    """
    config = load_config()
    presets = getattr(config, "presets", {})

    for preset_name, preset in presets.items():
        steps = []
        if isinstance(preset, list):
            steps = preset
        elif isinstance(preset, dict):
            steps = preset.get("steps", [])

        if not steps:
            continue

        for step in steps:
            cmd = step.get("cmd")
            args = step.get("args", [])

            if cmd == "python":
                try:
                    _validate_python_step(args)
                except ValueError as e:
                    pytest.fail(f"Preset '{preset_name}' failed validation: {e}")

def test_preset_python_step_policy_negative_cases():
    """
    Verify that the validator correctly rejects unsafe or disallowed arguments.
    """

    # 1. Empty args
    with pytest.raises(ValueError, match="cannot be empty"):
        _validate_python_step([])

    # 2. Invalid start
    with pytest.raises(ValueError, match="must start with"):
        _validate_python_step(["-c", "print(1)"])

    with pytest.raises(ValueError, match="must start with"):
        _validate_python_step(["script.py"])

    with pytest.raises(ValueError, match="must start with"):
        _validate_python_step(["-m", "pip", "install", "x"])

    # 3. Disallowed flags
    with pytest.raises(ValueError, match="cannot use '-c'"):
        _validate_python_step(["-m", "pytest", "-c", "config.ini"])

    # 4. Path safety: ".."
    with pytest.raises(ValueError, match="contains disallowed '..'"):
        _validate_python_step(["mesh_cli.py", "run-preset", ".."])

    with pytest.raises(ValueError, match="contains disallowed '..'"):
        _validate_python_step(["-m", "pytest", "-q", "../outside"])

    # 5. Path safety: Absolute paths
    # We need to construct an absolute path that works on the current OS
    abs_path = os.path.abspath("some/file")
    with pytest.raises(ValueError, match="is an absolute path"):
        _validate_python_step(["mesh_cli.py", abs_path])

    # 6. Path safety: Backslashes
    with pytest.raises(ValueError, match="contains disallowed backslash"):
        _validate_python_step(["mesh_cli.py", "some\\path"])

    # 7. Recursion: run-preset
    with pytest.raises(ValueError, match="no recursion"):
        _validate_python_step(["mesh_cli.py", "run-preset", "golden_slice"])

    # 8. Pytest flags
    with pytest.raises(ValueError, match="cannot use '--lf'"):
        _validate_python_step(["-m", "pytest", "-q", "--lf"])

    with pytest.raises(ValueError, match="cannot use '-k'"):
        _validate_python_step(["-m", "pytest", "-q", "-k", "something"])

    with pytest.raises(ValueError, match="must be in 'tests/'"):
        _validate_python_step(["-m", "pytest", "-q", "engine/"])

def test_preset_python_step_policy_valid_cases():
    """
    Verify valid cases pass.
    """
    _validate_python_step(["-m", "pytest", "-q", "tests/test_something.py"])
    _validate_python_step(["-m", "pytest", "-q"])
    _validate_python_step(["mesh_cli.py", "preset", "lint"])
    _validate_python_step(["mesh_cli.py", "check", "--full"])
