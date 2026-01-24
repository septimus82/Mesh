import pytest
from tests import arcade_stub

def test_arcade_stub_keys_exist():
    """Verify that the arcade stub includes common keys."""
    keys = arcade_stub.key
    
    # Letters
    assert keys.A == 97
    assert keys.Z == 122
    
    # Numbers
    assert keys.KEY_0 == 48
    assert keys.KEY_9 == 57
    
    # Formatting
    assert keys.SPACE == 32
    assert keys.ENTER == 65293
    assert keys.ESCAPE == 65307
    assert keys.BACKSPACE == 65288
    
    # Modifiers
    assert keys.LSHIFT == 65505
    
    # Arrows
    assert keys.UP == 65362
    
    # Function keys
    assert keys.F1 == 65470
    assert keys.F12 == 65481

def test_arcade_stub_colors_exist():
    """Verify common colors."""
    colors = arcade_stub.color
    assert colors.WHITE == (255, 255, 255)
    assert colors.BLACK == (0, 0, 0)
    assert len(colors.TRANSPARENT_BLACK) == 4

def test_arcade_stub_classes():
    """Verify stub classes can be instantiated."""
    win = arcade_stub.Window()
    assert win.width == 800
    
    sprite = arcade_stub.Sprite()
    assert sprite.scale == 1.0
    
    s_list = arcade_stub.SpriteList()
    s_list.append(sprite)
    assert len(s_list) == 1
    
    # Check inheritance
    assert isinstance(s_list, list)

def test_arcade_stub_gl_constants():
    """Verify GL constants."""
    assert arcade_stub.gl.GL_NEAREST == 0
