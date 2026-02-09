"""
Integration tests for EditorFileOpsController refactor V2.2 (Robustness).
"""
import pytest
import json
import os
import shutil
from unittest.mock import MagicMock, patch
from pathlib import Path
from engine.editor.editor_file_ops_controller import EditorFileOpsController, FsStep
from engine.editor.asset_refactor_model import Replacement

class MockRow:
    def __init__(self, rel_path, is_dir=False):
        self.entry = MagicMock()
        self.entry.rel_path = rel_path
        self.entry.path = rel_path # Absolute path handled by test setup often
        self.entry.is_dir = is_dir

@pytest.fixture
def mock_controller(tmp_path):
    mc = MagicMock()
    mc.window.repo_root = tmp_path
    mc.project_explorer = MagicMock()
    mc.state = MagicMock()
    mc.state.current_scene_path = None
    mc.state.current_scene_data = None
    mc.confirm_modal = MagicMock() # Mock the modal
    mc._push_command = MagicMock()
    return mc

@pytest.fixture
def file_ops(mock_controller):
    return EditorFileOpsController(mock_controller)

def setup_repo(root: Path):
    (root / "assets").mkdir(exist_ok=True)
    (root / "scenes").mkdir(exist_ok=True)
    
def test_rename_workflow_v2(file_ops, tmp_path):
    # Setup
    setup_repo(tmp_path)
    old = tmp_path / "assets/old.png"
    old.write_text("x", encoding="utf-8")
    
    scene = tmp_path / "scenes/s1.json"
    scene_data = {"entities": [{"id": "e1", "sprite": "assets/old.png"}]}
    scene.write_text(json.dumps(scene_data), encoding="utf-8")
    
    # Mock Selection
    mock_row = MagicMock()
    mock_row.entry.path = str(old)
    mock_row.entry.is_dir = False
    
    with patch.object(file_ops, "_get_selected_project_row", return_value=mock_row):
        file_ops.request_safe_rename_refactor("new.png")
        
    # Check Plan
    plan = file_ops._pending_refactor_plan
    assert plan is not None
    assert plan.op_kind == "rename"
    assert "Confirm Safe Rename" in file_ops.controller.confirm_modal.request_confirmation.call_args[1]["title"]
    
    # Execute Plan
    file_ops.execute_pending_refactor()
    
    # Verify
    assert not old.exists()
    assert (tmp_path / "assets/new.png").exists()
    
    new_data = json.loads(scene.read_text(encoding="utf-8"))
    assert new_data["entities"][0]["sprite"] == "assets/new.png"

def test_rollback_on_json_failure(file_ops, tmp_path):
    # Setup: Rename A -> B. JSON update will fail. Check A is restored.
    setup_repo(tmp_path)
    old = tmp_path / "assets/a.png"
    old.write_text("content", encoding="utf-8")
    
    scene = tmp_path / "scenes/test.json"
    scene.write_text(json.dumps({"entities": [{"id": "e_fail", "sprite": "assets/a.png"}]}), encoding="utf-8")
    
    mock_row = MagicMock()
    mock_row.entry.path = str(old)
    
    with patch.object(file_ops, "_get_selected_project_row", return_value=mock_row):
        file_ops.request_safe_rename_refactor("b.png")
        
    assert file_ops._pending_refactor_plan is not None
    
    # Mock json write to fail
    with patch("engine.editor.persistence_utils.write_atomic_utf8", side_effect=IOError("Disk Full")):
        file_ops.execute_pending_refactor()
        
    # Verify Rollback
    # JSON update failed, so FS move should not have happened (or rolled back if order was FS first)
    # Our new logic: JSON update BEFORE FS move.
    
    # So FS should be untouched.
    assert old.exists()
    assert not (tmp_path / "assets/b.png").exists()
    
    # And JSON should be intact
    data = json.loads(scene.read_text(encoding="utf-8"))
    assert data["entities"][0]["sprite"] == "assets/a.png"
    
    # Plan cleared
    assert file_ops._pending_refactor_plan is None

def test_rollback_on_fs_failure(file_ops, tmp_path):
    # Setup: Move A -> B. Replacements applied to JSON. FS Move fails. 
    # Logic: JSONs applied first. Then FS.
    # If FS fails, JSONs must be restored.
    
    setup_repo(tmp_path)
    old = tmp_path / "assets/a.png"
    old.write_text("content", encoding="utf-8")
    
    scene = tmp_path / "scenes/test.json"
    scene.write_text(json.dumps({"entities": [{"id": "e_fs", "sprite": "assets/a.png"}]}), encoding="utf-8")
    
    mock_row = MagicMock()
    mock_row.entry.path = str(old)

    # Need mocks for validation phases inside request_safe_rename
    with patch.object(file_ops, "_get_selected_project_row", return_value=mock_row):
        file_ops.request_safe_rename_refactor("b.png")

    assert file_ops._pending_refactor_plan is not None

    # Mock os.replace to fail
    with patch("os.replace", side_effect=OSError("Access Denied")):
        file_ops.execute_pending_refactor()
        
    # Verify Rollback
    # JSones should be restored to original "assets/a.png"
    data = json.loads(scene.read_text(encoding="utf-8"))
    assert data["entities"][0]["sprite"] == "assets/a.png"
    
    # FS should be original
    assert old.exists()
    assert not (tmp_path / "assets/b.png").exists()

def test_delete_workflow(file_ops, tmp_path):
    setup_repo(tmp_path)
    target = tmp_path / "assets/junk.png"
    target.write_text("junk", encoding="utf-8")
    
    scene = tmp_path / "scenes/s.json"
    scene.write_text(json.dumps({"entities": [{"id": "e_del", "sprite": "assets/junk.png"}]}), encoding="utf-8")
    
    file_ops.request_safe_delete_refactor(["assets/junk.png"])
    
    plan = file_ops._pending_refactor_plan
    assert plan.op_kind == "delete"
    op_id = plan.op_id
    trash_path = tmp_path / ".mesh_trash" / op_id / "assets/junk.png"
    
    file_ops.execute_pending_refactor()
    
    assert not target.exists()
    assert trash_path.exists()
    
    # Check scene ref cleared?
    # Our mapping was "junk" -> ""
    data = json.loads(scene.read_text(encoding="utf-8"))
    assert data["entities"][0]["sprite"] == ""

def test_delete_rollback_on_json_failure(file_ops, tmp_path):
    setup_repo(tmp_path)
    target = tmp_path / "assets/junk.png"
    target.write_text("junk", encoding="utf-8")
    scene = tmp_path / "scenes/s.json"
    scene.write_text(json.dumps({"entities": [{"id": "e_del", "sprite": "assets/junk.png"}]}), encoding="utf-8")
    file_ops.request_safe_delete_refactor(["assets/junk.png"])
    plan = file_ops._pending_refactor_plan
    op_id = plan.op_id
    trash_path = tmp_path / ".mesh_trash" / op_id / "assets/junk.png"

    with patch("engine.editor.persistence_utils.write_atomic_utf8", side_effect=IOError("Disk Full")):
        file_ops.execute_pending_refactor()

    # Restore original file
    assert target.exists()
    assert not trash_path.exists()
    data = json.loads(scene.read_text(encoding="utf-8"))
    assert data["entities"][0]["sprite"] == "assets/junk.png"

def test_delete_staging_failure_does_not_change_json(file_ops, tmp_path):
    setup_repo(tmp_path)
    target = tmp_path / "assets/junk.png"
    target.write_text("junk", encoding="utf-8")
    scene = tmp_path / "scenes/s.json"
    scene.write_text(json.dumps({"entities": [{"id": "e_del", "sprite": "assets/junk.png"}]}), encoding="utf-8")
    file_ops.request_safe_delete_refactor(["assets/junk.png"])

    with patch("os.replace", side_effect=OSError("Locked")), patch("shutil.move", side_effect=OSError("Locked")):
        file_ops.execute_pending_refactor()

    assert target.exists()
    data = json.loads(scene.read_text(encoding="utf-8"))
    assert data["entities"][0]["sprite"] == "assets/junk.png"

def test_purge_trash_removes_op_folder(file_ops, tmp_path):
    setup_repo(tmp_path)
    target = tmp_path / "assets/junk.png"
    target.write_text("junk", encoding="utf-8")
    scene = tmp_path / "scenes/s.json"
    scene.write_text(json.dumps({"entities": [{"id": "e_del", "sprite": "assets/junk.png"}]}), encoding="utf-8")
    file_ops.request_safe_delete_refactor(["assets/junk.png"])
    plan = file_ops._pending_refactor_plan
    op_id = plan.op_id
    trash_root = tmp_path / ".mesh_trash" / op_id
    file_ops.execute_pending_refactor()
    assert trash_root.exists()
    file_ops.purge_trash(op_id)
    assert not trash_root.exists()

def test_move_workflow(file_ops, tmp_path):
    setup_repo(tmp_path)
    (tmp_path / "assets/sub").mkdir()
    old = tmp_path / "assets/sub/x.png"
    old.write_text("x", encoding="utf-8")
    
    scene = tmp_path / "scenes/m.json"
    scene.write_text(json.dumps({"entities": [{"id": "e_mov", "sprite": "assets/sub/x.png"}]}), encoding="utf-8")
    
    mock_row = MagicMock()
    mock_row.entry.path = str(old)
    
    with patch.object(file_ops, "_get_selected_project_row", return_value=mock_row):
        file_ops.request_safe_move_refactor("assets") # Move up one level
        
    file_ops.execute_pending_refactor()
    
    assert not old.exists()
    assert (tmp_path / "assets/x.png").exists()
    
    data = json.loads(scene.read_text(encoding="utf-8"))
    assert data["entities"][0]["sprite"] == "assets/x.png"

def test_refactor_op_id_deterministic(file_ops):
    fs_steps = [FsStep("assets/a.png", "assets/b.png", "move")]
    mods = {"scenes/s.json": [Replacement("e1", "sprite", "assets/a.png", "assets/b.png", "k")]}
    op_id_1 = file_ops._compute_refactor_op_id("move", fs_steps, mods)
    op_id_2 = file_ops._compute_refactor_op_id("move", fs_steps, mods)
    assert op_id_1 == op_id_2
