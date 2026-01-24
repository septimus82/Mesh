import pytest
from engine.palette_mode import get_state, PaletteState

def test_lists_sorted_deterministic():
    state = get_state()
    state.reset()
    state.refresh_lists()
    
    # Check stamps sorted
    stamps = state.stamps
    assert stamps == sorted(stamps, key=lambda x: (x.pack_id, x.id))
    
    # Check brushes sorted
    brushes = state.brushes
    assert brushes == sorted(brushes, key=lambda x: (x.pack_id, x.id))
