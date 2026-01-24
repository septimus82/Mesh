
import pytest
import sys
from unittest.mock import MagicMock, patch
from typing import Any

# Define fake arcade structures
class FakeText:
    instantiation_count = 0
    draw_count = 0

    def __init__(self, text, x, y, color=(255, 255, 255, 255), size=12, **kwargs):
        FakeText.instantiation_count += 1
        self.text = text
        self.x = x
        self.y = y
        self.position = (x, y)
        self.rotation = 0

    def draw(self):
        FakeText.draw_count += 1

def fake_draw_text(*args, **kwargs):
    raise AssertionError("TRIPWIRE: arcade.draw_text() was called! Use draw_text_cached() instead.")

def fake_get_fps():
    return 60.0

@pytest.fixture
def tripwire_environment(monkeypatch):
    """
    Sets up a fake arcade environment where draw_text raises an error.
    """
    FakeText.instantiation_count = 0
    FakeText.draw_count = 0

    mock_arcade = MagicMock()
    mock_arcade.Text = FakeText
    mock_arcade.draw_text = fake_draw_text
    mock_arcade.get_fps = fake_get_fps
    
    # Must define Window as a class so subclasses aren't treated as Mocks
    class FakeWindow:
        def __init__(self, *args, **kwargs):
            pass
    mock_arcade.Window = FakeWindow
    
    # Needs color constants
    mock_arcade.color = MagicMock()
    mock_arcade.color.GREEN = (0, 255, 0, 255)
    mock_arcade.color.YELLOW = (255, 255, 0, 255)
    mock_arcade.color.CYAN = (0, 255, 255, 255)

    # Patch engine.optional_arcade.arcade effectively
    import engine.optional_arcade

    # Save original references
    orig_opt_arcade = engine.optional_arcade.arcade

    try:
        # Patch the canonical reference
        monkeypatch.setattr(engine.optional_arcade, "arcade", mock_arcade)
        
        yield mock_arcade

    finally:
        # Explicitly restore to ensure no leaks even if monkeypatch fails contextually
        engine.optional_arcade.arcade = orig_opt_arcade
        # engine.game.arcade and engine.text_draw.arcade no longer exist as static refs
        # so no need to restore them (they now point to optional_arcade.arcade)


def test_perf_overlay_draw_uses_cached_text(tripwire_environment):
    from engine.ui_overlays.perf import PerfOverlay
    from engine.text_draw import TextCache
    
    # Setup window mock
    window = MagicMock()
    window.width = 800
    window.height = 600
    window.text_cache = TextCache()
    
    # Setup stats mock
    stats = MagicMock()
    stats.snapshot.return_value.metrics = {"frame_total_ms": MagicMock(p95=16, max=20)}
    stats.snapshot.return_value.meta = {"counters": {"render_sprites_submitted": 100}}
    window.perf_stats = stats
    
    overlay = PerfOverlay(window)
    overlay.visible = True
    
    # Act
    overlay.draw()
    
    # Assert
    # 1. No assertions raised by fake_draw_text (implicit)
    # 2. FakeText was instantiated
    assert FakeText.instantiation_count > 0, "No text objects created"
    
    initial_instantiation_count = FakeText.instantiation_count
    
    # Act 2 - Redraw
    overlay.draw()
    
    # Assert 2
    assert FakeText.instantiation_count == initial_instantiation_count, "Text objects should be reused (cached)"
    assert FakeText.draw_count > initial_instantiation_count, "Text should be drawn multiple times"


def test_game_debug_overlay_uses_cached_text(tripwire_environment):
    from engine.game import GameWindow
    from engine.text_draw import TextCache

    # Verify patching worked
    import engine.game
    # assert engine.game.arcade is tripwire_environment

    if hasattr(GameWindow, "_draw_debug_output"):
        pass
    else:
        pytest.fail("DEBUG: _draw_debug_output MISSING")

    # We can't really instantiate GameWindow easily because of super().__init__, 
    # so let's patch GameWindow explicitly or just import the class and call the method unbound?
    # Calling unbound method with mock self is easiest.
    
    mock_self = MagicMock()
    mock_self.height = 600
    mock_self.width = 800
    mock_self.text_cache = TextCache()
    mock_self.encounter_debug_overlay = False
    
    # Act
    lines = ["Debug Line 1", "Debug Line 2"]
    GameWindow._draw_debug_output(mock_self, lines)
    
    # Assert
    assert FakeText.instantiation_count == 2
    
    # Redraw
    GameWindow._draw_debug_output(mock_self, lines)
    assert FakeText.instantiation_count == 2, "Should reuse text objects"

