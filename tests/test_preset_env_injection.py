import argparse
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from engine.tooling import preset_commands


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.presets = {
        "test_preset_with_env": {
            "description": "Test preset",
            "env": {
                "TEST_VAR": "123",
                "ANOTHER_VAR": "abc"
            },
            "steps": [
                {"cmd": "noop"}
            ]
        },
        "test_preset_no_env": {
            "description": "Test preset no env",
            "steps": [
                {"cmd": "noop"}
            ]
        }
    }
    return config

@pytest.fixture
def mock_mesh_cli_module():
    mock_module = MagicMock()
    mock_module.main.return_value = 0
    with patch.dict(sys.modules, {"mesh_cli": mock_module}):
        yield mock_module

def test_preset_env_injection(mock_config, mock_mesh_cli_module):
    # We need to patch load_config to return our mock config
    with patch("engine.tooling.preset_commands.load_config", return_value=mock_config):

        # We also need to verify that env vars are set DURING execution
        # We can do this by making mesh_cli.main check the env vars

        def check_env(args):
            assert os.environ.get("TEST_VAR") == "123"
            assert os.environ.get("ANOTHER_VAR") == "abc"
            assert os.environ.get("MESH_ACTIVE_PRESET") == "test_preset_with_env"
            return 0

        mock_mesh_cli_module.main.side_effect = check_env

        args = argparse.Namespace(name="test_preset_with_env")
        preset_commands.run_preset_command(args)

        # Verify env vars are cleaned up
        assert "TEST_VAR" not in os.environ
        assert "ANOTHER_VAR" not in os.environ
        assert "MESH_ACTIVE_PRESET" not in os.environ

def test_preset_env_cleanup_on_failure(mock_config, mock_mesh_cli_module):
    with patch("engine.tooling.preset_commands.load_config", return_value=mock_config):

        # Simulate failure
        mock_mesh_cli_module.main.side_effect = Exception("Boom")

        args = argparse.Namespace(name="test_preset_with_env")

        with pytest.raises(Exception, match="Boom"):
            preset_commands.run_preset_command(args)

        # Verify env vars are cleaned up even after exception
        assert "TEST_VAR" not in os.environ
        assert "ANOTHER_VAR" not in os.environ
        assert "MESH_ACTIVE_PRESET" not in os.environ

def test_preset_overwrites_and_restores(mock_config, mock_mesh_cli_module):
    with patch("engine.tooling.preset_commands.load_config", return_value=mock_config):

        # Set an existing env var
        os.environ["TEST_VAR"] = "original"

        def check_env(args):
            assert os.environ.get("TEST_VAR") == "123"
            return 0

        mock_mesh_cli_module.main.side_effect = check_env

        args = argparse.Namespace(name="test_preset_with_env")
        preset_commands.run_preset_command(args)

        # Verify it is restored
        assert os.environ["TEST_VAR"] == "original"
        del os.environ["TEST_VAR"]

def test_lighting_shadowmask_demo_config_exists():
    # Verify the actual config has the preset and it has the correct env vars
    # This reads the REAL config file
    from engine.config import load_config
    config = load_config()

    assert "lighting-shadowmask-demo" in config.presets
    preset = config.presets["lighting-shadowmask-demo"]
    assert preset["env"]["MESH_SHADOWCAST_MASK"] == "1"
    assert "MESH_SHADOWCAST_DEBUG" not in preset["env"]

    # Verify it uses Variant E
    steps = preset.get("steps", [])
    assert len(steps) > 0
    args = steps[0].get("args", [])
    assert "worlds/golden_slice_variant_e.json" in args

def test_lighting_shadowmask_demo_debug_config_exists():
    # Verify the debug preset exists and has both env vars
    from engine.config import load_config
    config = load_config()

    assert "lighting-shadowmask-demo-debug" in config.presets
    preset = config.presets["lighting-shadowmask-demo-debug"]
    assert preset["env"]["MESH_SHADOWCAST_MASK"] == "1"
    assert preset["env"]["MESH_SHADOWCAST_DEBUG"] == "1"

    # Verify it uses Variant E
    steps = preset.get("steps", [])
    assert len(steps) > 0
    args = steps[0].get("args", [])
    assert "worlds/golden_slice_variant_e.json" in args
