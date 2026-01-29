"""Contract tests for problems_jump_model."""

from __future__ import annotations

from engine.editor.problems_jump_model import (
    JumpTarget,
    choose_jump_target,
    format_location_text,
    is_jump_supported,
)
from engine.editor.scene_lint_model import SceneLintIssue


def test_choose_jump_target_entity_issue() -> None:
    """Entity-specific issues should return entity jump target."""
    issue = SceneLintIssue(
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
    )

    target = choose_jump_target(issue)

    assert target["kind"] == "entity"
    assert target["entity_id"] == "player"
    assert target["scene_path"] == "scenes/test.json"
    assert target["path"] == "scenes/test.json"
    assert target["line"] is None
    assert target["col"] is None


def test_choose_jump_target_scene_issue() -> None:
    """Scene-level issues should return scene jump target."""
    issue = SceneLintIssue(
        issue_id="test:002",
        kind="SCENE_METADATA",
        message="Scene missing metadata",
        entity_id=None,
        scene_id="scenes/dungeon.json",
        severity="WARN",
        risk="safe",
        fix_kind=None,
        fixable=False,
        meta={},
    )

    target = choose_jump_target(issue)

    assert target["kind"] == "scene"
    assert target["entity_id"] is None
    assert target["scene_path"] == "scenes/dungeon.json"
    assert target["path"] == "scenes/dungeon.json"


def test_choose_jump_target_no_scene() -> None:
    """Issues without scene_id should return none target."""
    issue = SceneLintIssue(
        issue_id="test:003",
        kind="UNKNOWN",
        message="Generic issue",
        entity_id=None,
        scene_id=None,
        severity="INFO",
        risk="safe",
        fix_kind=None,
        fixable=False,
        meta={},
    )

    target = choose_jump_target(issue)

    assert target["kind"] == "none"
    assert target["entity_id"] is None
    assert target["scene_path"] is None
    assert target["path"] is None


def test_format_location_text_path_only() -> None:
    """Format location with path only."""
    target: JumpTarget = {
        "kind": "scene",
        "path": "scenes/test.json",
        "entity_id": None,
        "scene_path": "scenes/test.json",
        "line": None,
        "col": None,
    }

    result = format_location_text(target)
    assert result == "scenes/test.json"


def test_format_location_text_path_with_line() -> None:
    """Format location with path and line."""
    target: JumpTarget = {
        "kind": "file",
        "path": "engine/test.py",
        "entity_id": None,
        "scene_path": None,
        "line": 42,
        "col": None,
    }

    result = format_location_text(target)
    assert result == "engine/test.py:42"


def test_format_location_text_path_with_line_and_col() -> None:
    """Format location with path, line, and col."""
    target: JumpTarget = {
        "kind": "file",
        "path": "engine/test.py",
        "entity_id": None,
        "scene_path": None,
        "line": 42,
        "col": 15,
    }

    result = format_location_text(target)
    assert result == "engine/test.py:42:15"


def test_format_location_text_no_path() -> None:
    """Format location without path should return empty string."""
    target: JumpTarget = {
        "kind": "none",
        "path": None,
        "entity_id": None,
        "scene_path": None,
        "line": None,
        "col": None,
    }

    result = format_location_text(target)
    assert result == ""


def test_is_jump_supported_scene() -> None:
    """Scene targets should be supported."""
    target: JumpTarget = {
        "kind": "scene",
        "path": "scenes/test.json",
        "entity_id": None,
        "scene_path": "scenes/test.json",
        "line": None,
        "col": None,
    }

    assert is_jump_supported(target) is True


def test_is_jump_supported_entity() -> None:
    """Entity targets should be supported."""
    target: JumpTarget = {
        "kind": "entity",
        "path": "scenes/test.json",
        "entity_id": "player",
        "scene_path": "scenes/test.json",
        "line": None,
        "col": None,
    }

    assert is_jump_supported(target) is True


def test_is_jump_supported_file() -> None:
    """File targets should be supported."""
    target: JumpTarget = {
        "kind": "file",
        "path": "engine/test.py",
        "entity_id": None,
        "scene_path": None,
        "line": 42,
        "col": 15,
    }

    assert is_jump_supported(target) is True


def test_is_jump_supported_none() -> None:
    """None targets should not be supported."""
    target: JumpTarget = {
        "kind": "none",
        "path": None,
        "entity_id": None,
        "scene_path": None,
        "line": None,
        "col": None,
    }

    assert is_jump_supported(target) is False


def test_choose_jump_target_deterministic() -> None:
    """choose_jump_target should be deterministic for same input."""
    issue = SceneLintIssue(
        issue_id="test:004",
        kind="MISSING_ID",
        message="Missing entity id",
        entity_id=None,
        scene_id="scenes/test.json",
        severity="ERROR",
        risk="safe",
        fix_kind="assign_id",
        fixable=True,
        meta={"index": 5},
    )

    target1 = choose_jump_target(issue)
    target2 = choose_jump_target(issue)

    assert target1 == target2
    assert target1["kind"] == "scene"
    assert target1["scene_path"] == "scenes/test.json"
