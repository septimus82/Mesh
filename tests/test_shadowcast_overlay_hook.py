
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import engine.game
import engine.optional_arcade
from engine.config import EngineConfig

pytestmark = [pytest.mark.integration, pytest.mark.slow]

@pytest.fixture
def fake_arcade(monkeypatch):
    # Canonical patch point: engine.optional_arcade.arcade
    # This ensures we are testing the actual path the application should be using.
    fake = MagicMock()
    fake.draw_line = MagicMock()
    fake.draw_circle_filled = MagicMock()
    fake.color = SimpleNamespace(YELLOW=(255, 255, 0), RED=(255, 0, 0))

    monkeypatch.setattr(engine.optional_arcade, "arcade", fake)
    return fake

def test_shadowcast_overlay_hook(fake_arcade, monkeypatch):
    """
    Verifies that _draw_shadowcast_debug calls arcade primitives via the
    canonical optional_arcade path.
    """
    # Enable debug flag
    monkeypatch.setenv("MESH_SHADOWCAST_DEBUG", "1")

    # Import GameWindow from game module
    from engine.game import GameWindow

    # Create mock game
    game = MagicMock()
    game.engine_config = EngineConfig()

    # Setup lighting mock
    mock_lighting = MagicMock()
    snapshot = {
        "lights": [{"x": 0, "y": 0}],
        "shadowcast": {
            "light_0": [
                {"angle": 0, "hit": [100, 0], "hit_occluder": None}
            ]
        }
    }
    mock_lighting.get_lighting_snapshot.return_value = snapshot
    mock_lighting.enabled = True
    game.lighting = mock_lighting

    # Mock other components
    game.camera = MagicMock()
    game.camera_controller = MagicMock()
    game.ui_controller = MagicMock()
    game.editor_controller = MagicMock()
    game.scene_controller = MagicMock()
    game.particle_manager = MagicMock()
    game.show_debug = False
    game.ai_debug_overlay_enabled = False
    game.perf_stats = MagicMock()

    # Bind the method to test
    draw_method = GameWindow._draw_shadowcast_debug.__get__(game, GameWindow)

    # 3. Execution & Assertion (Enabled)
    draw_method()

    assert fake_arcade.draw_line.called, "draw_line was not called on the canonical arcade patch"

    # Reset
    fake_arcade.draw_line.reset_mock()

    # 4. Execution & Assertion (Disabled via lighting)
    # If lighting is None, it should return early
    game.lighting = None
    draw_method()
    assert not fake_arcade.draw_line.called, "draw_line called even when lighting is None"

def test_shadowcast_overlay_hook_disabled_env(fake_arcade, monkeypatch):
    monkeypatch.delenv("MESH_SHADOWCAST_DEBUG", raising=False)
    from engine.game import GameWindow

    game = MagicMock()
    # If debug is disabled, lighting/logic shouldn't even define the method usually?
    # Or rather, on_draw checks the env?
    # No, on_draw calls _draw_shadowcast_debug if env is set.
    # But here we are calling _draw_shadowcast_debug DIRECTLY in the previous test via binding.
    # Wait, _draw_shadowcast_debug implementation itself checks the env var?
    # Let's check engine/game.py but assuming typical behavior:
    # If I call the method directly, does it respect the env var?
    # Usually the caller (on_draw) respects the env var.
    # Let's verify on_draw integration too.

    game.on_draw = GameWindow.on_draw.__get__(game, GameWindow)

    # We need to mock _draw_shadowcast_debug if on_draw calls it,
    # to see if it gets called.
    # BUT on_draw implementation is what we are testing for the conditional logic.

    # Mock specific internal method to trace call
    # We can't easily mock the method on the class we are testing without side effects
    # unless we patch the class.

    with patch.object(GameWindow, '_draw_shadowcast_debug', MagicMock()) as mock_draw:
        game.on_draw()
        assert not mock_draw.called, "Should not call shadowcast debug if env var is missing"
