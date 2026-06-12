import os
from unittest.mock import MagicMock, patch

import pytest

from engine.actions import _toggle_shadowcast_debug
from engine.lighting import LightManager


@pytest.fixture
def mock_window():
    window = MagicMock()
    window.player_hud = MagicMock()
    return window

@pytest.fixture
def light_manager(mock_window, mock_arcade_lighting):
    lm = LightManager(mock_window)
    lm.enabled = True
    lm._layer = MagicMock()
    lm._create_layer = MagicMock(return_value=lm._layer)
    mock_window.lighting = lm
    yield lm

def test_debug_default_from_env(mock_window, mock_arcade_lighting):
    with patch.dict(os.environ, {"MESH_SHADOWCAST_DEBUG": "1"}):
        lm = LightManager(mock_window)
        assert lm.shadowcast_debug_enabled is True

    with patch.dict(os.environ, {"MESH_SHADOWCAST_DEBUG": "0"}):
        lm = LightManager(mock_window)
        assert lm.shadowcast_debug_enabled is False

def test_toggle_debug_action(light_manager, mock_window):
    # Start disabled
    light_manager.shadowcast_debug_enabled = False

    # Toggle ON
    _toggle_shadowcast_debug(mock_window)

    assert light_manager.shadowcast_debug_enabled is True
    mock_window.player_hud.enqueue_toast.assert_called_with("Lighting: Debug rays ON")

    # Toggle OFF
    _toggle_shadowcast_debug(mock_window)

    assert light_manager.shadowcast_debug_enabled is False
    mock_window.player_hud.enqueue_toast.assert_called_with("Lighting: Debug rays OFF")

def test_snapshot_uses_flag_not_env(light_manager, mock_window):
    # Ensure environment is OFF
    with patch.dict(os.environ, {"MESH_SHADOWCAST_DEBUG": "0"}):
        # Enable flag manually
        light_manager.shadowcast_debug_enabled = True

        # Setup mocks
        light_manager._static_configs = [{"x": 0, "y": 0, "radius": 100, "enabled": True}]
        light_manager._cast_ray = MagicMock(return_value={"hit": (0,0)})

        # Get snapshot
        snapshot = light_manager.get_lighting_snapshot()

        # Should include shadowcast data because flag is True
        assert "shadowcast" in snapshot

        # Disable flag
        light_manager.shadowcast_debug_enabled = False

        # Get snapshot
        snapshot = light_manager.get_lighting_snapshot()

        # Should NOT include shadowcast data
        assert "shadowcast" not in snapshot
