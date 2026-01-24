import pytest
from unittest.mock import patch, MagicMock
from engine.tooling import wizard_command
from pathlib import Path

class TestWizardPackTarget:
    @pytest.fixture
    def mock_deps(self):
        with patch("engine.tooling.plan_executor.scaffold"), \
             patch("engine.tooling.plan_executor.polish"), \
             patch("engine.tooling.plan_executor.UnifiedValidator"), \
             patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.exists") as mock_exists, \
             patch("pathlib.Path.open", new_callable=MagicMock), \
             patch("pathlib.Path.write_text"):
            
            yield {"exists": mock_exists}

    def test_pack_path_resolution(self, mock_deps):
        """Test that paths are resolved to pack directory."""
        argv = ["new-questline", "--name-prefix", "test", "--pack", "my_pack", "--dry-run"]
        
        mock_deps["exists"].return_value = True # Pack exists
        
        # Capture context to check plan
        with patch("engine.tooling.wizard_command._print_plan") as mock_print:
            wizard_command.main(argv)
            ctx = mock_print.call_args[0][0]
            
            # Check scene path
            scene_action = next(a for a in ctx.actions if a.type == "create_scene")
            path_str = scene_action.args["path"]
            assert "packs" in path_str and "my_pack" in path_str

    def test_pack_auto_init(self, mock_deps):
        """Test that init_pack action is added if pack missing."""
        argv = ["new-questline", "--name-prefix", "test", "--pack", "new_pack", "--dry-run"]
        
        # Mock pack root not exists
        # We need to ensure ctx.root.exists() returns False
        # In wizard_command, ctx.root is Path("packs") / "new_pack"
        
        mock_deps["exists"].return_value = False
        
        with patch("engine.tooling.wizard_command._print_plan") as mock_print:
            wizard_command.main(argv)
            ctx = mock_print.call_args[0][0]
            
            assert ctx.actions[0].type == "init_pack"
            assert ctx.actions[0].args["id"] == "new_pack"
