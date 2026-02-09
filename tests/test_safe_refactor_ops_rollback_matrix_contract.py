
"""
Rollback Matrix contract tests for Safe Refactor Ops.
Simulates failure modes (network, disk full, permission denied) to ensure atomicity.
"""
import pytest
import json
import shutil
import os
from unittest.mock import MagicMock, patch, call
from pathlib import Path

from engine.editor.editor_file_ops_controller import EditorFileOpsController, PendingRefactorPlan, FsStep
from engine.editor.asset_refactor_model import Replacement

@pytest.fixture
def mock_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "scenes").mkdir()
    (repo / "assets").mkdir()
    return repo

@pytest.fixture
def ops_ctrl(mock_repo):
    """Refactor Controller with mocked Editor environment."""
    ctrl = MagicMock()
    ctrl.window.repo_root = mock_repo
    
    # Mock confirmation modal
    ctrl.confirm_modal = MagicMock()
    
    # Mock project_explorer
    ctrl.project_explorer = MagicMock()
    
    ops = EditorFileOpsController(ctrl)
    
    # Disable Toast
    ops._toast = MagicMock()
    ops._show_error_modal = MagicMock()
    
    return ops

def setup_plan(ops_ctrl, mock_repo):
    """Sets up a pending plan with 2 files to update and 1 move."""
    scene1 = mock_repo / "scenes/s1.json"
    scene1.write_text('{"entities": [{"sprite": "assets/old.png"}]}', encoding="utf-8")
    
    scene2 = mock_repo / "scenes/s2.json"
    scene2.write_text('{"entities": [{"sprite": "assets/old.png"}]}', encoding="utf-8")
    
    asset = mock_repo / "assets/old.png"
    asset.touch()
    
    plan = PendingRefactorPlan(
        op_kind="move",
        op_id=ops_ctrl._compute_refactor_op_id(
            "move",
            [FsStep("assets/old.png", "assets/new.png", "move")],
            {
                "scenes/s1.json": [Replacement("e1", "sprite", "assets/old.png", "assets/new.png", "k")],
                "scenes/s2.json": [Replacement("e2", "sprite", "assets/old.png", "assets/new.png", "k")],
            },
        ),
        fs_steps=[FsStep("assets/old.png", "assets/new.png", "move")],
        json_updates={
            "scenes/s1.json": [Replacement("e1", "sprite", "assets/old.png", "assets/new.png", "k")],
            "scenes/s2.json": [Replacement("e2", "sprite", "assets/old.png", "assets/new.png", "k")]
        },
        preview_lines=["Move assets/old.png -> assets/new.png"],
        trash_moves=[]
    )
    ops_ctrl._pending_refactor_plan = plan
    return plan

def test_rollback_json_write_fails_early(ops_ctrl, mock_repo):
    setup_plan(ops_ctrl, mock_repo)
    
    with patch("engine.editor.persistence_utils.write_atomic_utf8", side_effect=OSError("Disk Full")):
        ops_ctrl.execute_pending_refactor()
        
    assert ops_ctrl._show_error_modal.called
    assert "Refactor Aborted" in ops_ctrl._show_error_modal.call_args[0][0]
    
    assert (mock_repo / "assets/old.png").exists()
    assert not (mock_repo / "assets/new.png").exists()
    assert ops_ctrl._pending_refactor_plan is None

def test_rollback_json_write_fails_late(ops_ctrl, mock_repo):
    setup_plan(ops_ctrl, mock_repo)
    
    def side_effect(path, content):
        if "s2.json" in str(path):
            raise OSError("Permission Denied")
        return None
        
    with patch("engine.editor.persistence_utils.write_atomic_utf8", side_effect=side_effect):
        ops_ctrl.execute_pending_refactor()
        
    assert ops_ctrl._show_error_modal.called
    assert ops_ctrl._pending_refactor_plan is None

def test_rollback_fs_move_fails(ops_ctrl, mock_repo):
    setup_plan(ops_ctrl, mock_repo)
    
    with patch("engine.editor.persistence_utils.write_atomic_utf8"):
        with patch("os.replace", side_effect=OSError("File Locked")):
             ops_ctrl.execute_pending_refactor()
             
    assert ops_ctrl._show_error_modal.called
    assert "File System Error" in ops_ctrl._show_error_modal.call_args[0][0]

def test_rollback_fs_multi_step_fails_v2(ops_ctrl, mock_repo):
    """Fail on 2nd move, verify 1st move rolled back (cleaner mock)."""
    (mock_repo / "assets/a.png").touch()
    (mock_repo / "assets/b.png").touch()
    
    plan = PendingRefactorPlan(
        op_kind="move",
        op_id=ops_ctrl._compute_refactor_op_id(
            "move",
            [
                FsStep("assets/a.png", "assets/a_new.png", "move"),
                FsStep("assets/b.png", "assets/b_new.png", "move"),
            ],
            {},
        ),
        fs_steps=[
            FsStep("assets/a.png", "assets/a_new.png", "move"),
            FsStep("assets/b.png", "assets/b_new.png", "move")
        ],
        json_updates={},
        preview_lines=[],
        trash_moves=[]
    )
    ops_ctrl._pending_refactor_plan = plan
    
    # We use a real replace (unpatched) or manual side effect that writes to disk
    # so that rollback logic (which checks dst.exists()) works.
    original_replace = os.replace
    
    def side_effect(src, dst):
        s_str = str(src)
        if "b.png" in s_str:
            raise OSError("Fail B")
        # Perform real move for A
        original_replace(src, dst)
        
    with patch("os.replace", side_effect=side_effect) as mock_replace:
        ops_ctrl.execute_pending_refactor()
    
    # Assert Rollback happened
    # A should be back at original
    assert (mock_repo / "assets/a.png").exists()
    assert not (mock_repo / "assets/a_new.png").exists()
    
    # B should be at original (failed)
    assert (mock_repo / "assets/b.png").exists()

def test_confirm_modal_cancel(ops_ctrl, mock_repo):
    """Verify cancellation clears state."""
    (mock_repo / "assets/file.png").touch()
    
    # Setup mocks for selection
    ops_ctrl.controller.project_explorer.selectable_rows = ["row1"]
    ops_ctrl.controller.project_explorer.selected_paths.return_value = ["assets/file.png"]
    
    ops_ctrl.list_repo_json_assets = MagicMock(return_value=[])
    
    # 2. Request Move
    with patch.object(ops_ctrl.controller.confirm_modal, "request_confirmation") as mock_modal_req:
        res = ops_ctrl.request_safe_move_refactor("assets/target")
        assert res is True
        assert ops_ctrl._pending_refactor_plan is not None
        
        # 3. Simulate Cancel
        on_cancel = mock_modal_req.call_args.kwargs["on_cancel"]
        on_cancel()
        
        # 4. Assert State Cleared
        assert ops_ctrl._pending_refactor_plan is None
        assert ops_ctrl.controller.confirm_modal.close.called
