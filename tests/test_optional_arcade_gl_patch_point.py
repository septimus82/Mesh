
import pytest
from unittest.mock import MagicMock
import engine.optional_arcade

def test_optional_arcade_gl_patch_point(monkeypatch) -> None:
    """If GL is present, ensure we can patch it via optional_arcade."""
    
    if not engine.optional_arcade.arcade_gl:
        pytest.skip("Arcade GL not available")
        
    mock_buffer = MagicMock()
    monkeypatch.setattr(engine.optional_arcade.arcade_gl, "BufferDescription", mock_buffer)
    
    assert engine.optional_arcade.arcade_gl.BufferDescription is mock_buffer
