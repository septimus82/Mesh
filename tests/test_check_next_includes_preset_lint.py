import pytest
from unittest.mock import patch, MagicMock
from engine.tooling import check

def test_check_next_includes_preset_lint(capsys):
    # Mock validate_pack_dependencies to fail, or just mock the whole flow to fail
    # check.run_check calls a bunch of things.
    # The easiest way to trigger _fail is to have one of the steps return False or raise an exception that is caught?
    # Actually run_check calls functions and checks their return value.
    
    # Let's mock get_content_index to return something that causes failure?
    # Or mock validate_pack_dependencies to return False?
    
    # In run_check:
    # index.build()
    # if not validate_pack_dependencies(index): return _fail()
    
    with patch("engine.tooling.check.get_content_index") as mock_get_index, \
         patch("engine.tooling.check.validate_pack_dependencies", return_value=False):
        
        mock_index = MagicMock()
        mock_get_index.return_value = mock_index
        
        result = check.run_check(world_path="worlds/test_world.json")
        
        assert result is False
        
        out = capsys.readouterr().out
        
        lines = out.splitlines()
        assert "[CHECK] Next:" in lines
        idx = lines.index("[CHECK] Next:")
        assert lines[idx + 1] == "  mesh preset lint"
