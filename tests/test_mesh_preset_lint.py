import pytest
import json
import argparse
from unittest.mock import patch, MagicMock
from engine.tooling import preset_commands

def test_mesh_preset_lint(capsys):
    """
    Test mesh preset lint command.
    """
    # Mock config
    mock_config = MagicMock()
    mock_config.presets = {
        "good-preset": {
            "description": "A good preset",
            "steps": [
                {"cmd": "python", "args": ["-m", "pytest", "-q"]}
            ]
        },
        "bad-env": {
            "description": "A preset with bad env",
            "env": {"bad": "ok", "GOOD": "no/slash"},
            "steps": [
                {"cmd": "python", "args": ["-m", "pytest", "-q"]}
            ],
        },
        "bad-preset": {
            "description": "A bad preset",
            "steps": [
                {"cmd": "python", "args": ["-c", "print(1)"]}
            ]
        },
        "bad-schema": {
            # Missing description
            "steps": []
        }
    }
    
    with patch("engine.tooling.preset_commands.load_config", return_value=mock_config):
        args = argparse.Namespace()
        
        # Run lint
        ret = preset_commands.run_preset_lint_command(args)
        
        assert ret == 2
        
        captured = capsys.readouterr()
        stdout = captured.out.strip()
        
        # Parse JSON
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            pytest.fail(f"Output is not valid JSON: {stdout}")
            
        assert data["version"] == 1
        assert data["ok"] is False
        assert "policy" in data
        assert data["policy"]["version"] == 1
        assert data["presets_checked"] == 4
        assert "issues" in data
        
        issues = data["issues"]
        assert isinstance(issues, list)
        assert issues
        for item in issues:
            assert isinstance(item, dict)
            assert set(["id", "preset", "step_index", "message"]).issubset(set(item.keys()))

        env_issues = [i for i in issues if i["preset"] == "bad-env" and i["id"] == "preset_env_invalid"]
        assert env_issues
        
        # Check bad-preset error
        bad_preset_issues = [e for e in issues if e["preset"] == "bad-preset"]
        assert len(bad_preset_issues) == 1
        assert bad_preset_issues[0]["step_index"] == 0
        assert bad_preset_issues[0]["id"] == "preset_step_invalid"
        assert "must start with" in bad_preset_issues[0]["message"]
        
        # Check bad-schema error
        bad_schema_issues = [e for e in issues if e["preset"] == "bad-schema"]
        assert len(bad_schema_issues) >= 1
        assert any("Missing 'description'" in e["message"] for e in bad_schema_issues)

def test_mesh_preset_lint_success(capsys):
    """
    Test mesh preset lint command with all good presets.
    """
    # Mock config
    mock_config = MagicMock()
    mock_config.presets = {
        "good-preset": {
            "description": "A good preset",
            "steps": [
                {"cmd": "python", "args": ["-m", "pytest", "-q"]}
            ]
        }
    }
    
    with patch("engine.tooling.preset_commands.load_config", return_value=mock_config):
        args = argparse.Namespace()
        
        # Run lint
        ret = preset_commands.run_preset_lint_command(args)
        
        assert ret == 0
        
        captured = capsys.readouterr()
        stdout = captured.out.strip()
        
        # Parse JSON
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            pytest.fail(f"Output is not valid JSON: {stdout}")
            
        assert data["version"] == 1
        assert data["ok"] is True
        assert "policy" in data
        assert data["policy"]["version"] == 1
        assert data["presets_checked"] == 1
        assert "issues" in data
        assert data["issues"] == []
