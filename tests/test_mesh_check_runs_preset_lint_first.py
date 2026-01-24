import pytest
from unittest.mock import patch, MagicMock
from engine.tooling import check

def test_mesh_check_runs_preset_lint_first(capsys):
    # Mock config with good preset
    mock_config = MagicMock()
    mock_config.presets = {
        "good-preset": {
            "description": "A good preset",
            "steps": [
                {"cmd": "python", "args": ["-m", "pytest"]}
            ]
        }
    }
    
    # Mock get_content_index to fail (so we don't run the whole check)
    # Actually, let's just let it run until it hits something we can mock to fail gracefully.
    # validate_pack_dependencies returning errors causes _fail() which returns False.
    
    with patch("engine.tooling.check.load_config", return_value=mock_config), \
         patch("engine.tooling.check.get_content_index") as mock_get_index, \
         patch("engine.tooling.check.validate_pack_dependencies", return_value=["Some dependency error"]):
        
        mock_index = MagicMock()
        mock_get_index.return_value = mock_index
        
        # It should return False because of dependency error
        result = check.run_check()
        
        assert result is False
        
        captured = capsys.readouterr()
        stdout = captured.out
        
        # Assert that it proceeded past lint
        assert "[Mesh][Check] Running quality gate..." in stdout
        assert "[Mesh][Check] Pack dependency errors:" in stdout
        
        # Assert that it didn't print lint JSON
        assert '"stage": "preset_lint"' not in stdout
