"""Tests for Workspace Persistence contract."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.workspace_settings import (
    WorkspaceSettings,
    load_workspace,
    save_workspace,
    get_workspace_path,
    resolve_workspace_path,
)
from engine.editor_controller import EditorModeController

def test_workspace_settings_defaults():
    s = WorkspaceSettings()
    assert s.entity_panels_open is False
    assert s.outliner_focus == "outliner"
    assert s.last_scene_id is None


def test_resolve_workspace_path_explicit():
    """Test resolve_workspace_path with explicit repo_root."""
    from pathlib import Path
    root = Path("/some/path")
    assert resolve_workspace_path(root) == root / "workspace.json"


def test_workspace_roundtrip(tmp_path):
    settings = WorkspaceSettings(
        entity_panels_open=True,
        light_occluder_tool="occluder",
        last_scene_id="scene_123",
        last_camera_center=[100.0, 200.0]
    )
    
    save_workspace(tmp_path, settings)
    loaded = load_workspace(tmp_path)
    
    assert loaded.entity_panels_open is True
    assert loaded.light_occluder_tool == "occluder"
    assert loaded.last_scene_id == "scene_123"
    assert loaded.last_camera_center == [100.0, 200.0] 
    
    # Verify file content
    data = json.loads(get_workspace_path(tmp_path).read_text("utf-8"))
    assert data["last_scene_id"] == "scene_123"

def test_workspace_corrupt_file(tmp_path):
    p = get_workspace_path(tmp_path)
    p.write_text("{invalid_json", encoding="utf-8")
    
    loaded = load_workspace(tmp_path)
    # Should fallback to default
    assert loaded.entity_panels_open is False
    assert loaded.last_scene_id is None

def test_editor_controller_load_apply(tmp_path, monkeypatch):
    """Test that EditorController applies settings from workspace."""
    # Setup workspace file
    settings = WorkspaceSettings(
        entity_panels_open=True,
        scene_switcher_open=True,
        light_occluder_tool="light",
        last_scene_id="test_scene",
        last_camera_center=[50.0, 50.0]
    )
    save_workspace(tmp_path, settings)
    
    monkeypatch.setenv("PYGBAG", "0")
    
    # Mock window
    window = MagicMock()
    window.current_scene_key = "default"
    window.camera = MagicMock()
    
    # Create controller with repo_root override
    editor = EditorModeController(window)
    editor._repo_root_override = tmp_path
    # Manually call load_workspace since it was already called in __init__ with wrong path
    editor.load_workspace()
    
    assert editor.entity_panels_active is True
    assert editor.scene_switcher_active is True
    assert editor.lights_tool_active is True
    assert editor.occluder_tool_active is False
    
    # Check scene load call
    window.load_scene.assert_called_with("test_scene")
    
    # Check camera position was set (load_workspace sets camera.position directly)
    assert window.camera.position == (50.0, 50.0)

def test_editor_controller_save(tmp_path, monkeypatch):
    monkeypatch.setenv("PYGBAG", "0")
    
    window = MagicMock()
    window.current_scene_key = "saved_scene"
    
    editor = EditorModeController(window)
    editor._repo_root_override = tmp_path
    # Set camera position AFTER creating controller, since load_workspace() in __init__
    # may overwrite camera.position from the real workspace.json
    window.camera.position = (123.0, 456.0)
    
    # Modify state
    editor.entity_panels_active = True
    editor.occluder_tool_active = True
    editor.lights_tool_active = False
    
    editor.save_workspace()
    
    loaded = load_workspace(tmp_path)
    assert loaded.entity_panels_open is True
    assert loaded.light_occluder_tool == "occluder"
    assert loaded.last_scene_id == "saved_scene"
    assert loaded.last_camera_center == [123.0, 456.0]

