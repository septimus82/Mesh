
"""
End-to-End integration tests for Safe Refactor Ops v2.4+
Exercises filesystem and JSON updates with rollback scenarios.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from engine.editor.editor_confirm_modal_controller import EditorConfirmModalController
from engine.editor.editor_file_ops_controller import EditorFileOpsController


@pytest.fixture
def repo(tmp_path):
    """Setup a standard asset repo layout."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/sprites").mkdir()
    (tmp_path / "scenes").mkdir()
    (tmp_path / "engine").mkdir()
    (tmp_path / "engine/__init__.py").touch()
    return tmp_path

@pytest.fixture
def editor(repo):
    """Stub editor controller wired to temp repo."""
    ctrl = MagicMock()
    # Ensure window has repo_root
    ctrl.window = MagicMock()
    ctrl.window.repo_root = repo # Important!
    ctrl.scene_controller = MagicMock()

    # Real Confirm Modal (logic only)
    ctrl.confirm_modal = EditorConfirmModalController(ctrl)

    # Mock Project Explorer
    proj = MagicMock()
    proj.selectable_rows = []
    proj._selected_paths_return = []
    proj.selected_paths.side_effect = lambda rows: proj._selected_paths_return
    ctrl.project_explorer = proj

    # Real File Ops
    ops = EditorFileOpsController(ctrl)
    ctrl.file_ops = ops

    return ctrl

def create_scene(repo, name, ref_path):
    data = {"entities": [{"id": "ent1", "sprite": ref_path}]}
    path = repo / name
    path.parent.mkdir(exist_ok=True, parents=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path

def test_refactor_rename_e2e(repo, editor):
    old_file = repo / "assets/sprites/hero.png"
    old_file.touch()
    create_scene(repo, "scenes/level1.json", "assets/sprites/hero.png")

    editor.project_explorer._selected_paths_return = ["assets/sprites/hero.png"]

    row = MagicMock()
    row.entry.path = str(old_file)
    row.entry.rel_path = "assets/sprites/hero.png"
    editor.file_ops._get_selected_project_row = MagicMock(return_value=row)

    with patch.object(editor.confirm_modal, "request_confirmation") as mock_conf:
        editor.file_ops.request_safe_rename_refactor("hero_new.png")
        assert mock_conf.called
        args = mock_conf.call_args
        assert "Rename" in args.kwargs["title"]
        args.kwargs["on_confirm"]()

    assert not old_file.exists()
    assert (repo / "assets/sprites/hero_new.png").exists()

    with open(repo / "scenes/level1.json") as f:
        d = json.load(f)
    assert d["entities"][0]["sprite"] == "assets/sprites/hero_new.png"

def test_refactor_move_multi_e2e(repo, editor):
    # Setup
    p1 = repo / "assets/a.png"
    p2 = repo / "assets/b.png"
    p1.touch()
    p2.touch()
    create_scene(repo, "scenes/level2.json", "assets/a.png")

    editor.project_explorer._selected_paths_return = ["assets/a.png", "assets/b.png"]
    (repo / "assets/sub").mkdir()

    # Ensuring list_repo_json_assets returns correct relative paths
    with patch.object(editor.confirm_modal, "request_confirmation") as mock_conf, \
         patch.object(editor.file_ops, "list_repo_json_assets", return_value=["scenes/level2.json"]):

        success = editor.file_ops.request_safe_move_refactor("assets/sub")
        assert success
        mock_conf.call_args.kwargs["on_confirm"]()

    assert (repo / "assets/sub/a.png").exists()
    assert (repo / "assets/sub/b.png").exists()
    assert not (repo / "assets/a.png").exists()

    with open(repo / "scenes/level2.json") as f:
        d = json.load(f)
    assert d["entities"][0]["sprite"] == "assets/sub/a.png"

def test_web_runtime_preview_only(repo, editor):
    with patch("sys.platform", "emscripten"):
        # Force cache clear if needed, but not easy.
        # Rely on EditorFileOpsController._is_web_runtime calling sys.platform

        src = repo / "assets/web.png"
        src.touch()
        editor.project_explorer._selected_paths_return = ["assets/web.png"]
        (repo / "assets/d").mkdir()

        with patch.object(editor.confirm_modal, "request_confirmation") as mock_conf:
            editor.file_ops.request_safe_move_refactor("assets/d")

            # Setup toast mock
            editor.file_ops._toast = MagicMock()

            mock_conf.call_args.kwargs["on_confirm"]()

            # Assert FS unchanged
            assert src.exists()
            assert not (repo / "assets/d/web.png").exists()
            assert editor.file_ops._toast.called

def test_refactor_rollback_on_json_failure(repo, editor):
    src = repo / "assets/rollback.png"
    src.touch()
    create_scene(repo, "scenes/rollback.json", "assets/rollback.png")

    editor.project_explorer._selected_paths_return = ["assets/rollback.png"]
    (repo / "assets/dest").mkdir()

    def fail_write(*args, **kwargs):
        raise OSError("Forced Write Failure")

    with patch.object(editor.confirm_modal, "request_confirmation") as mock_conf, \
         patch.object(editor.file_ops, "list_repo_json_assets", return_value=["scenes/rollback.json"]):

        editor.file_ops.request_safe_move_refactor("assets/dest")

        # Patch write_atomic_utf8 where it is used.
        with patch("engine.editor.persistence_utils.write_atomic_utf8", side_effect=fail_write):
            editor.file_ops._toast = MagicMock()
            editor.file_ops._show_error_modal = MagicMock()

            mock_conf.call_args.kwargs["on_confirm"]()

    # Assert FS rolled back
    assert src.exists()
    assert not (repo / "assets/dest/rollback.png").exists()

    with open(repo / "scenes/rollback.json") as f:
        d = json.load(f)
    assert d["entities"][0]["sprite"] == "assets/rollback.png"
