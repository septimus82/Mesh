from unittest.mock import MagicMock
from engine.editor.editor_project_explorer_controller import ProjectExplorerController, ProjectExplorerDisplayRow, SelectionState
from engine.editor.project_explorer_inline_rename_model import InlineRenameState

def test_begin_inline_rename_handles_folders():
    ctrl = ProjectExplorerController(MagicMock())
    
    # Preempt ensure_rows triggering refresh
    ctrl.tree_rev = 1

    # Mock single selection
    ctrl.selection_state = SelectionState(primary_index=0, selected_indices=frozenset({0}), anchor_index=0)
    
    # Mock row as folder
    folder_entry = MagicMock()
    folder_entry.is_dir = True
    folder_entry.rel_path = "assets/sprites"
    
    row = ProjectExplorerDisplayRow(kind="entry", entry=folder_entry, recent=None, header=None)
    ctrl.selectable_rows = [row]
    ctrl.cached_rows = [row] # needed?
    
    # Act
    ok = ctrl.begin_inline_rename("assets/sprites")
    
    # Assert
    assert ok is True
    assert ctrl.inline_rename_state is not None
    assert ctrl.inline_rename_state.is_dir is True
    assert ctrl.inline_rename_state.original_stem == "sprites"
    assert ctrl.inline_rename_state.original_ext == "" # No extension logic for folders

def test_commit_inline_rename_folders():
    ctrl = ProjectExplorerController(MagicMock())
    
    # Setup state manually
    ctrl.inline_rename_state = InlineRenameState(
        original_path="assets/sprites",
        original_basename="sprites",
        original_stem="sprites",
        original_ext="",
        current_text="new_sprites",
        selection_start=0,
        selection_end=0,
        is_dir=True
    )
    
    # Act
    should_commit, name, err = ctrl.get_inline_rename_commit_result()
    
    # Assert
    assert should_commit is True
    assert name == "new_sprites"
    assert err is None

def test_commit_inline_rename_folders_no_extension_added():
    ctrl = ProjectExplorerController(MagicMock())
    
    # If user types "new.folder", it should stay "new.folder" (n .folder considered extension)
    ctrl.inline_rename_state = InlineRenameState(
        original_path="assets/folder",
        original_basename="folder",
        original_stem="folder",
        original_ext="",
        current_text="new.folder",
        selection_start=0,
        selection_end=0,
        is_dir=True
    )
    
    should_commit, name, err = ctrl.get_inline_rename_commit_result()
    assert should_commit is True
    assert name == "new.folder"
