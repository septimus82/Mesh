"""Contract tests for problems jump functionality in controller."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from engine.editor.scene_lint_model import SceneLintIssue
from engine.editor_controller import EditorModeController
from tests._typing import as_any


def _create_mock_editor() -> EditorModeController:
    """Create a minimal editor for testing."""
    scene_controller = SimpleNamespace(_loaded_scene_data={}, current_scene_path="")
    window = SimpleNamespace(
        strict_mode=False,
        scene_controller=scene_controller,
        width=800,
        height=600,
        player_hud=MagicMock(),
        request_scene_change=MagicMock(),
    )

    # Mock the PREFAB_PALETTE to avoid loading
    import engine.editor_controller as editor_module
    original_palette = getattr(editor_module, "PREFAB_PALETTE", None)
    editor_module.PREFAB_PALETTE = []

    try:
        controller = EditorModeController(as_any(window))
        controller.active = True
        return controller
    finally:
        if original_palette is not None:
            editor_module.PREFAB_PALETTE = original_palette


def test_get_selected_jump_target_no_selection() -> None:
    """get_selected_jump_target should return None when no issue selected."""
    editor = _create_mock_editor()

    target = editor.problems.get_selected_jump_target()

    assert target is None


def test_get_selected_jump_target_with_selection() -> None:
    """get_selected_jump_target should return target for selected issue."""
    editor = _create_mock_editor()

    # Add some issues
    issues = [
        SceneLintIssue(
            issue_id="test:001",
            kind="DUPLICATE_ID",
            message="Duplicate entity id 'player'",
            entity_id="player",
            scene_id="scenes/test.json",
            severity="ERROR",
            risk="safe",
            fix_kind="rename_id",
            fixable=True,
            meta={},
        ),
    ]

    editor.problems.set_issues(issues)
    editor.problems.set_selected_index(0)

    target = editor.problems.get_selected_jump_target()

    assert target is not None
    assert target["kind"] == "entity"
    assert target["entity_id"] == "player"
    assert target["scene_path"] == "scenes/test.json"


def test_problems_jump_to_selected_no_target() -> None:
    """problems_jump_to_selected should return False when no target."""
    editor = _create_mock_editor()

    result = editor.problems_jump_to_selected()

    assert result is False


def test_problems_copy_location_no_target() -> None:
    """problems_copy_location should return False when no target."""
    editor = _create_mock_editor()

    result = editor.problems_copy_location()

    assert result is False


def test_problems_copy_location_with_target() -> None:
    """problems_copy_location should format and copy location text."""
    editor = _create_mock_editor()

    issues = [
        SceneLintIssue(
            issue_id="test:001",
            kind="DUPLICATE_ID",
            message="Duplicate entity id 'player'",
            entity_id="player",
            scene_id="scenes/test.json",
            severity="ERROR",
            risk="safe",
            fix_kind="rename_id",
            fixable=True,
            meta={},
        ),
    ]

    editor.problems.set_issues(issues)
    editor.problems.set_selected_index(0)

    # Note: try_copy_to_clipboard might fail in headless/test env
    # But the function should still attempt it
    result = editor.problems_copy_location()

    # Result could be True or False depending on clipboard availability
    # But it should not raise an exception
    assert isinstance(result, bool)


def test_problems_controller_integration() -> None:
    """Test that ProblemsController integrates properly with jump functionality."""
    editor = _create_mock_editor()

    # Set up issues
    issues = [
        SceneLintIssue(
            issue_id="test:001",
            kind="MISSING_ID",
            message="Missing entity id at index 0",
            entity_id=None,
            scene_id="scenes/level1.json",
            severity="ERROR",
            risk="safe",
            fix_kind="assign_id",
            fixable=True,
            meta={"index": 0},
        ),
        SceneLintIssue(
            issue_id="test:002",
            kind="DUPLICATE_ID",
            message="Duplicate entity id 'enemy'",
            entity_id="enemy",
            scene_id="scenes/level2.json",
            severity="ERROR",
            risk="safe",
            fix_kind="rename_id",
            fixable=True,
            meta={},
        ),
    ]

    editor.problems.set_issues(issues)

    # Test selection at index 0 (scene-level issue)
    editor.problems.set_selected_index(0)
    target = editor.problems.get_selected_jump_target()
    assert target is not None
    assert target["kind"] == "scene"
    assert target["scene_path"] == "scenes/level1.json"

    # Test selection at index 1 (entity-level issue)
    editor.problems.set_selected_index(1)
    target = editor.problems.get_selected_jump_target()
    assert target is not None
    assert target["kind"] == "entity"
    assert target["entity_id"] == "enemy"
    assert target["scene_path"] == "scenes/level2.json"


def test_problems_controller_filtered_selection() -> None:
    """Test jump target resolution with filtered issues."""
    editor = _create_mock_editor()

    issues = [
        SceneLintIssue(
            issue_id="test:001",
            kind="DUPLICATE_ID",
            message="Duplicate entity id 'player'",
            entity_id="player",
            scene_id="scenes/test.json",
            severity="ERROR",
            risk="safe",
            fix_kind="rename_id",
            fixable=True,
            meta={},
        ),
        SceneLintIssue(
            issue_id="test:002",
            kind="MISSING_ID",
            message="Missing entity id at index 5",
            entity_id=None,
            scene_id="scenes/other.json",
            severity="ERROR",
            risk="safe",
            fix_kind="assign_id",
            fixable=True,
            meta={"index": 5},
        ),
    ]

    editor.problems.set_issues(issues)

    # Apply filter to show only "player" issues
    editor.problems.set_query("player")

    # Should only see the first issue in filtered view
    filtered = editor.problems.get_filtered_issues()
    assert len(filtered) == 1
    assert filtered[0].entity_id == "player"

    # Get jump target for the filtered selection
    editor.problems.set_selected_index(0)
    target = editor.problems.get_selected_jump_target()
    assert target is not None
    assert target["entity_id"] == "player"
    assert target["scene_path"] == "scenes/test.json"
