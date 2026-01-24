import pytest
from unittest.mock import MagicMock
from engine.ui import HelpOverlay

def test_help_overlay_includes_lighting_demos():
    # Mock window
    window = MagicMock()
    window.width = 800
    window.height = 600
    
    # Instantiate HelpOverlay
    help_overlay = HelpOverlay(window)
    
    # Check body text content
    body_text = help_overlay._body_text
    
    # Assertions
    assert "Lighting demos:" in body_text
    assert "mesh run-preset lighting-shadowmask-demo" in body_text
    assert "mesh run-preset lighting-shadowmask-demo-debug" in body_text
    
    # Ensure it's at the end (optional, but good for structure check)
    lines = body_text.split("\n")
    # We expect at least 2 lines for the demos + header + spacer
    assert len(lines) > 15 
