from unittest.mock import MagicMock, call

import pytest

from engine.actions import _toggle_shadowcast_debug, _toggle_shadowmask


@pytest.fixture
def mock_window():
    window = MagicMock()
    window.player_hud = MagicMock()
    # Ensure the seen attribute is not set initially
    if hasattr(window, "_mesh_lighting_toggle_tip_seen"):
        delattr(window, "_mesh_lighting_toggle_tip_seen")

    # Mock lighting
    window.lighting = MagicMock()
    window.lighting.toggle_shadowmask.return_value = True
    window.lighting.toggle_shadowcast_debug.return_value = True

    return window

def test_lighting_tip_appears_once_on_shadowmask_toggle(mock_window):
    # First toggle
    _toggle_shadowmask(mock_window)

    # Verify standard toast AND tip toast
    mock_window.player_hud.enqueue_toast.assert_has_calls([
        call("Lighting: Shadow mask ON"),
        call("Tip: F6 Shadow mask", seconds=4.0)
    ])

    # Reset mocks to check second call cleanly
    mock_window.player_hud.enqueue_toast.reset_mock()

    # Second toggle
    mock_window.lighting.toggle_shadowmask.return_value = False
    _toggle_shadowmask(mock_window)

    # Verify standard toast ONLY
    mock_window.player_hud.enqueue_toast.assert_called_once_with("Lighting: Shadow mask OFF")

def test_lighting_tip_appears_once_on_debug_toggle(mock_window):
    # First toggle
    _toggle_shadowcast_debug(mock_window)

    # Verify standard toast AND tip toast
    mock_window.player_hud.enqueue_toast.assert_has_calls([
        call("Lighting: Debug rays ON"),
        call("Tip: F6 Shadow mask", seconds=4.0)
    ])

    # Reset mocks
    mock_window.player_hud.enqueue_toast.reset_mock()

    # Second toggle
    mock_window.lighting.toggle_shadowcast_debug.return_value = False
    _toggle_shadowcast_debug(mock_window)

    # Verify standard toast ONLY
    mock_window.player_hud.enqueue_toast.assert_called_once_with("Lighting: Debug rays OFF")

def test_lighting_tip_shared_state_between_actions(mock_window):
    # Toggle shadowmask first -> shows tip
    _toggle_shadowmask(mock_window)

    mock_window.player_hud.enqueue_toast.assert_has_calls([
        call("Lighting: Shadow mask ON"),
        call("Tip: F6 Shadow mask", seconds=4.0)
    ])

    mock_window.player_hud.enqueue_toast.reset_mock()

    # Toggle debug rays next -> NO tip (already seen)
    _toggle_shadowcast_debug(mock_window)

    mock_window.player_hud.enqueue_toast.assert_called_once_with("Lighting: Debug rays ON")
