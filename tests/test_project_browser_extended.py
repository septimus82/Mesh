"""Tests for Project Browser open and remove flows."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import engine.optional_arcade
from tests._typing import as_any

# Ensure arcade fallback for headless runs.
if not engine.optional_arcade.has_arcade():
    from engine import arcade_fallback
    engine.optional_arcade.arcade = arcade_fallback

from engine.ui_overlays.menus import MainMenuOverlay
from engine.projects import add_recent_project, get_recent_projects

def _patch_arcade(monkeypatch):
    import engine.optional_arcade as optional_arcade
    # Re-apply mock if needed or just rely on global check
    if not optional_arcade.has_arcade():
        from engine import arcade_fallback
        optional_arcade.arcade = arcade_fallback

def test_project_browser_open_flow(tmp_path, monkeypatch):
    _patch_arcade(monkeypatch)
    monkeypatch.setenv("PYGBAG", "0")
    
    # Setup valid project
    proj = tmp_path / "valid_project"
    proj.mkdir()
    (proj / "config.json").write_text("{}", encoding="utf-8")
    
    window = SimpleNamespace(width=800, height=600, paused=False)
    menu = MainMenuOverlay(as_any(window))
    menu.open()
    
    # Mock project items to select "Open Existing Project..."
    # Assuming it is last or we filter for it
    mock_items = [{"root": "", "label": "Open Existing Project...", "kind": "open"}]
    with patch.object(menu, "_project_items", return_value=mock_items):
        menu._project_index = 0
        menu.on_key_press(engine.optional_arcade.arcade.key.ENTER)
        
        assert menu.state == "open_project_path"
        
        # Test 1: Invalid Path
        menu.on_text(str(tmp_path / "non_existent"))
        menu.on_key_press(engine.optional_arcade.arcade.key.ENTER)
        assert menu.state == "open_project_path"
        assert "Invalid" in menu._open_error
        
        # Clear path (backspace simulation or just overwrite in test logic via reset)
        menu._open_path = "" 
        menu._open_error = ""
        
        # Test 2: Valid Path
        menu.on_text(str(proj))
        with patch.object(menu, "_apply_project_root") as mock_apply:
            menu.on_key_press(engine.optional_arcade.arcade.key.ENTER)
            mock_apply.assert_called_with(str(proj))
            assert menu.state == "main"
            assert menu._open_error == ""

def test_project_remove_recent(tmp_path, monkeypatch):
    _patch_arcade(monkeypatch)
    monkeypatch.setenv("MESH_REPO_ROOT", str(tmp_path))
    monkeypatch.setenv("MESH_PROJECTS_PATH", str(tmp_path / "projects.json"))
    monkeypatch.setenv("PYGBAG", "0")
    
    # Add some recents
    p1 = tmp_path / "p1"
    p2 = tmp_path / "p2"
    p1.mkdir(); p2.mkdir()
    add_recent_project(str(p1))
    add_recent_project(str(p2))
    
    # Verify setup
    recents = get_recent_projects()
    assert len(recents) == 2
    
    window = SimpleNamespace(width=800, height=600, paused=False)
    menu = MainMenuOverlay(as_any(window))
    menu.open()
    
    # Select first recent (order is usually FIFO or LIFO? implementation uses append so LIFO-ish if we use set logic.. check implementation)
    # projects.py: add_recent_project appends to list if new?
    # Actually add_recent_project reads payload, appends, writes. 
    # get_recent_projects filters.
    
    # Let's trust _project_items returns them.
    # p1 added first, then p2.
    # get_recent_projects preserves order.
    # menus.py _project_items iterates get_recent_projects()
    
    # Select index 0 (p1)
    menu.state = "project_browser"
    
    # We must patch _project_items to NOT be mocked so we test actual removal integration?
    # Or at least rely on get_recent_projects() working.
    # But menus.py imports get_recent_projects locally inside methods.
    
    # Let's perform the action
    # We need to ensure menu sees the items.
    # Since we set env vars, real get_recent_projects should work.
    
    items = menu._project_items()
    # p2 was added last, so it is first in the list (MRU)
    # items[0] should be p2
    assert items[0]["root"] == str(p2.resolve())
    
    menu._project_index = 0 # Select p2
    menu.on_key_press(engine.optional_arcade.arcade.key.DELETE)
    
    # Verify removal
    recents_after = get_recent_projects()
    assert str(p2.resolve()) not in recents_after
    assert str(p1.resolve()) in recents_after
    
    # Verify index clamping if needed (not strictly needed since we were at 0 and length > 0)
