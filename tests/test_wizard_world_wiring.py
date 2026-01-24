import pytest
import json
from unittest.mock import patch, MagicMock
from engine.tooling import wizard_command

class TestWizardWorldWiring:
    @pytest.fixture
    def mock_deps(self):
        with patch("engine.tooling.plan_executor.scaffold"), \
             patch("engine.tooling.plan_executor.polish"), \
             patch("engine.tooling.plan_executor.UnifiedValidator"), \
             patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.exists") as mock_exists, \
             patch("pathlib.Path.open", new_callable=MagicMock) as mock_file_open, \
             patch("pathlib.Path.write_text"):
            
            mock_exists.return_value = True
            yield {
                "exists": mock_exists,
                "open": mock_file_open
            }

    def test_wire_world_action(self, mock_deps):
        """Test that wire_world action is added."""
        argv = ["new-questline", "--name-prefix", "test", "--into-world", "worlds/main.json", "--link-from", "hub", "--dry-run"]
        
        with patch("engine.tooling.wizard_command._print_plan") as mock_print:
            wizard_command.main(argv)
            ctx = mock_print.call_args[0][0]
            
            action = next(a for a in ctx.actions if a.type == "wire_world")
            assert action.args["world_path"] == "worlds/main.json"
            assert action.args["link_from"] == "hub"

    def test_wire_world_execution(self, mock_deps):
        """Test execution of wire_world."""
        # Setup world data
        world_data = {"scenes": {"hub": {"path": "scenes/hub.json"}}, "links": []}
        
        mock_file = MagicMock()
        mock_deps["open"].return_value.__enter__.return_value = mock_file
        mock_file.read.return_value = json.dumps(world_data)
        
        # Run just the action logic
        action_args = {
            "world_path": "worlds/main.json",
            "scene_path": "scenes/new.json",
            "scene_id": "new_scene",
            "link_from": "hub"
        }
        
        # Patch json.load to return our data (since we mock open, we need to handle read)
        # Actually we can just patch json.load
        with patch("json.load", return_value=world_data):
            
            from engine.tooling.plan_executor import PlanExecutor
            executor = PlanExecutor()
            with patch.object(executor, "_track_file"), \
                 patch.object(executor, "_write_file") as mock_write:
                executor._wire_world(action_args)
            
                assert mock_write.called
                args, _ = mock_write.call_args
                path, content = args
                world_out = json.loads(content)
                
                assert "new_scene" in world_out["scenes"]
                assert any(l["from"] == "hub" and l["to"] == "new_scene" for l in world_out["links"])
