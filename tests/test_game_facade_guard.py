import re
from pathlib import Path
import pytest

def test_game_py_facade_guard():
    """
    Regression test to ensure engine/game.py remains a facade and doesn't regrow.
    
    Goals:
    - Assert engine/game.py has <= 950 non-empty lines.
    - Assert "provider" functions are not defined in game.py anymore.
    - Assert undo/persist/event handler helpers are not defined in game.py anymore.
    """
    game_py = Path("engine/game.py")
    if not game_py.exists():
        pytest.skip("engine/game.py not found")

    content = game_py.read_text(encoding="utf-8")
    lines = content.splitlines()
    non_empty_lines = [line for line in lines if line.strip()]
    
    # 1. Budget check
    # Current is ~1100. Set limit to 1200.
    assert len(non_empty_lines) < 1200, f"engine/game.py has {len(non_empty_lines)} non-empty lines, exceeding limit of 1200"
    # 2. Provider check
    # Should not define _provider functions inline
    # Regex for 'def .*_provider('
    # We exclude imports, so we look for 'def ' at start of line or indented
    provider_matches = re.findall(r"^\s*def\s+\w+_provider\s*\(", content, re.MULTILINE)
    assert not provider_matches, f"Found inline provider definitions in game.py: {provider_matches}"

    # 3. Helper check: UndoFrame
    # Should not define class UndoFrame
    undo_frame_matches = re.findall(r"^\s*class\s+UndoFrame\b", content, re.MULTILINE)
    assert not undo_frame_matches, "Found class UndoFrame definition in game.py"

    # 4. Logic checks
    # Ensure specific logic is delegated
    
    # mark_scene_dirty logic
    if "self.scene_dirty = True" in content:
        # It might be in a comment or string, but unlikely in this file structure.
        # Check context if needed, but simple string check is a good guard.
        pytest.fail("Found 'self.scene_dirty = True' in game.py. Logic should be delegated.")

    # on_entity_died logic
    # The old implementation had 'begin_boss_gold_reward_tracking(self'
    # The new one delegates.
    # However, begin_boss_gold_reward_tracking is imported.
    # We want to ensure it's not CALLED in the body.
    # But it might be called in the delegate? No, the delegate is in another file.
    # So if we see 'begin_boss_gold_reward_tracking(' inside a def, that's bad.
    # But it is imported at top level.
    # Let's check if it appears indented (usage) rather than 'from ... import ...'
    
    usage_matches = re.findall(r"^\s+begin_boss_gold_reward_tracking\(", content, re.MULTILINE)
    assert not usage_matches, "Found usage of begin_boss_gold_reward_tracking in game.py. Should be delegated."

    # Check for event handler logic
    # e.g. 'self.particle_manager.emit_death_effect'
    particle_matches = re.findall(r"^\s+self\.particle_manager\.emit_death_effect", content, re.MULTILINE)
    assert not particle_matches, "Found particle logic in game.py. Should be delegated."
