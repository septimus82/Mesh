"""Tests for Web Preview contract."""

import sys
from unittest.mock import MagicMock
from types import SimpleNamespace
from pathlib import Path
import pytest

import engine.optional_arcade

# Ensure arcade fallback for headless runs.
if not engine.optional_arcade.has_arcade():
    from engine import arcade_fallback
    engine.optional_arcade.arcade = arcade_fallback

from engine.ui_overlays.menus import MainMenuOverlay

def _patch_arcade(monkeypatch):
    import engine.optional_arcade as optional_arcade
    if not optional_arcade.has_arcade():
        from engine import arcade_fallback
        optional_arcade.arcade = arcade_fallback

def test_web_preview_hidden_on_web(monkeypatch):
    _patch_arcade(monkeypatch)
    monkeypatch.setenv("PYGBAG", "1")
    
    window = SimpleNamespace(width=800, height=600, paused=False)
    menu = MainMenuOverlay(window) # type: ignore
    
    items = menu._items()
    actions = [item[1] for item in items]
    assert "run_web_preview" not in actions

def test_web_preview_success(monkeypatch, tmp_path):
    _patch_arcade(monkeypatch)
    monkeypatch.setenv("PYGBAG", "0")
    monkeypatch.setenv("MESH_REPO_ROOT", str(tmp_path))
    
    # Mock tooling
    mock_tooling = MagicMock()
    mock_preview = MagicMock()
    mock_tooling.web_preview = mock_preview
    sys.modules["tooling"] = mock_tooling
    sys.modules["tooling.web_preview"] = mock_preview
    
    mock_start = MagicMock(return_value=(8000, "http://localhost:8000"))
    mock_preview.start_web_preview = mock_start
    
    window = SimpleNamespace(width=800, height=600, paused=False, player_hud=MagicMock())
    menu = MainMenuOverlay(window) # type: ignore
    
    menu._attempt_run_web_preview()
    
    mock_start.assert_called_once()
    args, _ = mock_start.call_args
    assert str(args[0]) == str(tmp_path)
    
    # Check toast
    window.player_hud.enqueue_toast.assert_called_once()
    call_args = window.player_hud.enqueue_toast.call_args
    assert "Preview: http://localhost:8000" in call_args[0][0]

def test_web_preview_missing_build(monkeypatch, tmp_path):
    _patch_arcade(monkeypatch)
    monkeypatch.setenv("PYGBAG", "0")
    
    mock_tooling = MagicMock()
    mock_preview = MagicMock()
    mock_tooling.web_preview = mock_preview
    sys.modules["tooling"] = mock_tooling
    sys.modules["tooling.web_preview"] = mock_preview
    
    mock_start = MagicMock(side_effect=FileNotFoundError("No build"))
    mock_preview.start_web_preview = mock_start
    
    window = SimpleNamespace(width=800, height=600, paused=False, player_hud=MagicMock())
    menu = MainMenuOverlay(window) # type: ignore
    
    menu._attempt_run_web_preview()
    
    mock_start.assert_called_once()
    
    # Check toast
    window.player_hud.enqueue_toast.assert_called_once()
    call_args = window.player_hud.enqueue_toast.call_args
    assert "Build web demo first" in call_args[0][0]
