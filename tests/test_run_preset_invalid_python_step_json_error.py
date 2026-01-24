import pytest
import json
import argparse
from unittest.mock import patch, MagicMock
from engine.tooling import preset_commands

def test_run_preset_invalid_python_step_json_error(capsys):
    """
    Verify that invalid preset steps output a single line of preset-lint stage JSON.
    """
    # Mock config
    mock_config = MagicMock()
    mock_config.presets = {
        "bad-preset": {
            "steps": [
                {"cmd": "python", "args": ["-c", "print(1)"]}
            ]
        }
    }
    
    with patch("engine.tooling.preset_commands.load_config", return_value=mock_config):
        args = argparse.Namespace(name="bad-preset")
        
        expected = preset_commands.build_preset_lint_stage_result(mock_config)
        expected_line = json.dumps(expected, sort_keys=True) + "\n"

        # Expect sys.exit(2)
        with pytest.raises(SystemExit) as excinfo:
            preset_commands.run_preset_command(args)
        
        assert excinfo.value.code == 2
        
        captured = capsys.readouterr()
        stdout = captured.out
        assert stdout == expected_line
        
        # Parse JSON
        try:
            data = json.loads(stdout.strip())
        except json.JSONDecodeError:
            pytest.fail(f"Output is not valid JSON: {stdout!r}")
            
        assert data == expected
        assert data["stage"] == "preset_lint"
        
        # Ensure no other output (splitlines should be length 1)
        assert len(stdout.splitlines()) == 1
