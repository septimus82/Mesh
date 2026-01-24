import pytest
import json
import sys
from unittest.mock import patch, MagicMock
from engine.tooling import check

def test_mesh_check_fails_on_preset_lint_error(capsys):
    # Mock config with bad preset
    mock_config = MagicMock()
    mock_config.presets = {
        "bad-preset": {
            "description": "A bad preset",
            "steps": [
                {"cmd": "python", "args": ["-c", "print(1)"]}
            ]
        }
    }
    
    with patch("engine.tooling.check.load_config", return_value=mock_config):
        # Expect sys.exit(2)
        with pytest.raises(SystemExit) as excinfo:
            check.run_check()
        
        assert excinfo.value.code == 2
        
        captured = capsys.readouterr()
        stdout = captured.out.strip()
        
        # Parse JSON
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            pytest.fail(f"Output is not valid JSON: {stdout}")
            
        assert data["version"] == 1
        assert data["ok"] is False
        assert data["stage"] == "preset_lint"
        assert "policy" in data
        assert "issues" in data
        assert len(data["issues"]) > 0
        assert data["issues"][0]["preset"] == "bad-preset"
