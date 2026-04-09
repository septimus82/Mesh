"""Tests for Project Browser export flow contract."""

import sys
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from pathlib import Path
import pytest

import engine.optional_arcade
from tests._typing import as_any

# Ensure arcade fallback for headless runs.
if not engine.optional_arcade.has_arcade():
    from engine import arcade_fallback
    engine.optional_arcade.arcade = arcade_fallback

from engine.ui_overlays.menus import MainMenuOverlay

@pytest.fixture(autouse=True)
def clean_tooling_modules():
    yield
    sys.modules.pop("tooling", None)
    sys.modules.pop("tooling.release_web_demo", None)

def _patch_arcade(monkeypatch):
    import engine.optional_arcade as optional_arcade
    if not optional_arcade.has_arcade():
        from engine import arcade_fallback
        optional_arcade.arcade = arcade_fallback

def test_export_web_demo_exists_desktop(monkeypatch):
    _patch_arcade(monkeypatch)
    monkeypatch.setenv("PYGBAG", "0")
    
    window = SimpleNamespace(width=800, height=600, paused=False)
    menu = MainMenuOverlay(as_any(window))
    
    items = menu._items()
    actions = [item[1] for item in items]
    assert "export_web" in actions

def test_export_web_demo_hidden_web(monkeypatch):
    _patch_arcade(monkeypatch)
    monkeypatch.setenv("PYGBAG", "1")
    
    window = SimpleNamespace(width=800, height=600, paused=False)
    menu = MainMenuOverlay(as_any(window))
    
    items = menu._items()
    actions = [item[1] for item in items]
    assert "export_web" not in actions

def test_export_web_demo_success(monkeypatch, tmp_path):
    _patch_arcade(monkeypatch)
    monkeypatch.setenv("PYGBAG", "0")
    monkeypatch.setenv("MESH_REPO_ROOT", str(tmp_path))
    
    # Mock tooling
    mock_tooling = MagicMock()
    # Mock release_web_demo inside tooling
    mock_release = MagicMock()
    mock_tooling.release_web_demo = mock_release
    sys.modules["tooling"] = mock_tooling
    sys.modules["tooling.release_web_demo"] = mock_release
    
    mock_build = MagicMock(return_value=tmp_path / "dist" / "web_demo.zip")
    mock_release.build_and_zip_web_demo = mock_build
    
    window = SimpleNamespace(width=800, height=600, paused=False, player_hud=MagicMock())
    menu = MainMenuOverlay(as_any(window))
    
    # Direct invocation to avoid navigating menu
    menu._attempt_export_web_demo()
    
    mock_build.assert_called_once()
    args, _ = mock_build.call_args
    assert str(args[0]) == str(tmp_path)
    
    # Check toast
    window.player_hud.enqueue_toast.assert_called_once()
    call_args = window.player_hud.enqueue_toast.call_args
    assert "Exported: web_demo.zip" in call_args[0][0]

def test_export_web_demo_failure(monkeypatch, tmp_path):
    _patch_arcade(monkeypatch)
    monkeypatch.setenv("PYGBAG", "0")
    
    mock_tooling = MagicMock()
    mock_release = MagicMock()
    mock_tooling.release_web_demo = mock_release
    sys.modules["tooling"] = mock_tooling
    sys.modules["tooling.release_web_demo"] = mock_release
    
    mock_build = MagicMock(side_effect=Exception("Web build missing"))
    mock_release.build_and_zip_web_demo = mock_build
    
    window = SimpleNamespace(width=800, height=600, paused=False, player_hud=MagicMock())
    menu = MainMenuOverlay(as_any(window))
    
    menu._attempt_export_web_demo()
    
    mock_build.assert_called_once()
    
    # Check failure toast
    window.player_hud.enqueue_toast.assert_called_once()
    call_args = window.player_hud.enqueue_toast.call_args
    assert "Export Failed: Web build missing" in call_args[0][0]
