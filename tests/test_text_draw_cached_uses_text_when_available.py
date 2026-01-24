
import pytest
from unittest.mock import MagicMock
from engine.text_draw import draw_text_cached, TextCache

def test_text_draw_cached_uses_text_when_available(monkeypatch):
    import engine.optional_arcade
    
    # Mock arcade and Text
    mock_arcade = MagicMock()
    mock_text_class = MagicMock()
    mock_text_instance = MagicMock()
    mock_text_class.return_value = mock_text_instance
    
    # Patch arcade INSIDE optional_arcade
    monkeypatch.setattr(engine.optional_arcade, "arcade", mock_arcade)
    monkeypatch.setattr(mock_arcade, "Text", mock_text_class)
    
    cache = TextCache()
    
    # First call: should create Text
    draw_text_cached("test", 10, 20, color=(255, 255, 255), cache=cache)
    
    assert mock_text_class.call_count == 1
    mock_text_instance.draw.assert_called_once()
    assert mock_text_instance.position == (10, 20)
    
    # Second call same params: should REUSE Text
    draw_text_cached("test", 30, 40, color=(255, 255, 255), cache=cache)
    
    assert mock_text_class.call_count == 1
    assert mock_text_instance.draw.call_count == 2
    assert mock_text_instance.position == (30, 40)
    
    # Third call diff params: should create NEW Text
    draw_text_cached("diff", 10, 20, color=(255, 255, 255), cache=cache)
    
    assert mock_text_class.call_count == 2
