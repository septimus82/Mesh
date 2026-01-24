import os
import pytest
from unittest.mock import MagicMock, patch
from engine.lighting import LightManager

@pytest.fixture
def mock_window():
    window = MagicMock()
    window.width = 800
    window.height = 600
    return window

@pytest.fixture
def light_manager_factory(mock_window, mock_arcade_lighting):
    """Factory to create LightManager with patched internals."""
    def _create():
        lm = LightManager(mock_window)
        # Ensure it thinks it's available so it tries to rebuild
        lm.available = True
        lm._create_layer = MagicMock(return_value=MagicMock())
        return lm
    return _create

def test_shadowmask_toggle_persists_across_scene_config(light_manager_factory):
    # 1. Start with default (False)
    with patch.dict(os.environ, {}, clear=True):
        lm = light_manager_factory()
        assert lm.shadowmask_enabled is False
        assert lm._shadowmask_overridden is False

        # 2. Toggle ON
        lm.toggle_shadowmask()
        assert lm.shadowmask_enabled is True
        assert lm._shadowmask_overridden is True

        # 3. Simulate scene load (configure_scene_lights triggers _rebuild_layer)
        # We pass some dummy config to ensure it processes something
        lm.configure_scene_lights([{"x": 100, "y": 100, "radius": 50}])

        # 4. Verify it stays ON
        assert lm.shadowmask_enabled is True
        assert lm._shadowmask_overridden is True

        # 5. Toggle OFF
        lm.toggle_shadowmask()
        assert lm.shadowmask_enabled is False
        assert lm._shadowmask_overridden is True

        # 6. Simulate another scene load
        lm.configure_scene_lights([{"x": 200, "y": 200, "radius": 50}])

        # 7. Verify it stays OFF
        assert lm.shadowmask_enabled is False
        assert lm._shadowmask_overridden is True

def test_shadowcast_debug_toggle_persists_across_scene_config(light_manager_factory):
    # 1. Start with default (False)
    with patch.dict(os.environ, {}, clear=True):
        lm = light_manager_factory()
        assert lm.shadowcast_debug_enabled is False
        assert lm._shadowcast_debug_overridden is False

        # 2. Toggle ON
        lm.toggle_shadowcast_debug()
        assert lm.shadowcast_debug_enabled is True
        assert lm._shadowcast_debug_overridden is True

        # 3. Simulate scene load
        lm.configure_scene_lights([{"x": 100, "y": 100, "radius": 50}])

        # 4. Verify it stays ON
        assert lm.shadowcast_debug_enabled is True
        assert lm._shadowcast_debug_overridden is True

        # 5. Toggle OFF
        lm.toggle_shadowcast_debug()
        assert lm.shadowcast_debug_enabled is False
        assert lm._shadowcast_debug_overridden is True

        # 6. Simulate another scene load
        lm.configure_scene_lights([{"x": 200, "y": 200, "radius": 50}])

        # 7. Verify it stays OFF
        assert lm.shadowcast_debug_enabled is False
        assert lm._shadowcast_debug_overridden is True

def test_env_seeds_only_when_not_overridden(light_manager_factory):
    # Case 1: Env var sets it to ON (1)
    with patch.dict(os.environ, {"MESH_SHADOWCAST_MASK": "1", "MESH_SHADOWCAST_DEBUG": "1"}):
        lm = light_manager_factory()
        
        # Initially seeded from env
        assert lm.shadowmask_enabled is True
        assert lm.shadowcast_debug_enabled is True
        assert lm._shadowmask_overridden is False
        assert lm._shadowcast_debug_overridden is False

        # Toggle OFF (override)
        lm.toggle_shadowmask()
        lm.toggle_shadowcast_debug()
        
        assert lm.shadowmask_enabled is False
        assert lm.shadowcast_debug_enabled is False
        assert lm._shadowmask_overridden is True
        assert lm._shadowcast_debug_overridden is True

        # Simulate scene load - should NOT revert to env var
        lm.configure_scene_lights([{"x": 100, "y": 100, "radius": 50}])
        
        assert lm.shadowmask_enabled is False
        assert lm.shadowcast_debug_enabled is False

    # Case 2: Env var sets it to OFF (0)
    with patch.dict(os.environ, {"MESH_SHADOWCAST_MASK": "0", "MESH_SHADOWCAST_DEBUG": "0"}):
        lm = light_manager_factory()
        
        # Initially seeded from env
        assert lm.shadowmask_enabled is False
        assert lm.shadowcast_debug_enabled is False
        
        # Toggle ON (override)
        lm.toggle_shadowmask()
        lm.toggle_shadowcast_debug()
        
        assert lm.shadowmask_enabled is True
        assert lm.shadowcast_debug_enabled is True
        assert lm._shadowmask_overridden is True
        assert lm._shadowcast_debug_overridden is True
        
        # Simulate scene load - should NOT revert to env var
        lm.configure_scene_lights([{"x": 100, "y": 100, "radius": 50}])
        
        assert lm.shadowmask_enabled is True
        assert lm.shadowcast_debug_enabled is True
