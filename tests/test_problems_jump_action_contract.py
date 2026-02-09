"""Contract tests for Problems Jump action registration and enablement."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from engine.editor.editor_actions import (
    EditorAction,
    _enabled_problems_can_jump,
    _enabled_problems_panel_active,
    find_action,
    get_editor_actions,
    get_menu_actions,
    get_palette_actions,
)
from engine.editor.shortcut_resolver_model import normalize_shortcut_text
from tests._dock_stub import make_dock_stub


class _FakeProblemsController:
    """Fake ProblemsController for testing enablement."""

    def __init__(self, target: dict[str, Any] | None = None) -> None:
        self._target = target

    def get_selected_jump_target(self) -> dict[str, Any] | None:
        return self._target


class _FakeEditorController:
    """Fake EditorController for testing enablement."""

    def __init__(
        self,
        right_dock_tab: str = "Inspector",
        problems_ctl: _FakeProblemsController | None = None,
    ) -> None:
        self.dock = make_dock_stub(left_tab="Outliner", right_tab=right_dock_tab)
        self.problems = problems_ctl or _FakeProblemsController()


def test_problems_jump_action_registered() -> None:
    """The editor.problems.jump_to_selected action should be in the registry."""
    actions = get_editor_actions(None, None)
    action = find_action(actions, "editor.problems.jump_to_selected")
    assert action is not None
    assert action.id == "editor.problems.jump_to_selected"
    assert action.shortcut == "Enter"
    assert "jump" in action.keywords
    assert "problem" in action.keywords


def test_problems_jump_ctrl_action_registered() -> None:
    """The editor.problems.jump_to_selected_ctrl action should be in the registry."""
    actions = get_editor_actions(None, None)
    action = find_action(actions, "editor.problems.jump_to_selected_ctrl")
    assert action is not None
    assert action.id == "editor.problems.jump_to_selected_ctrl"
    assert normalize_shortcut_text(action.shortcut) == "Ctrl+Enter"


def test_problems_copy_location_action_registered() -> None:
    """The editor.problems.copy_location action should be in the registry."""
    actions = get_editor_actions(None, None)
    action = find_action(actions, "editor.problems.copy_location")
    assert action is not None
    assert action.id == "editor.problems.copy_location"
    assert normalize_shortcut_text(action.shortcut) == "Ctrl+Shift+L"
    assert "copy" in action.keywords
    assert "location" in action.keywords


def test_problems_jump_in_palette() -> None:
    """Jump to Problem should be discoverable in command palette."""
    actions = get_palette_actions(None, None)
    ids = [a.id for a in actions]
    assert "editor.problems.jump_to_selected" in ids


def test_problems_copy_in_palette() -> None:
    """Copy Problem Location should be discoverable in command palette."""
    actions = get_palette_actions(None, None)
    ids = [a.id for a in actions]
    assert "editor.problems.copy_location" in ids


def test_problems_jump_in_menu() -> None:
    """Jump to Problem should appear in menus."""
    actions = get_menu_actions(None, None)
    ids = [a.id for a in actions]
    assert "editor.problems.jump_to_selected" in ids


def test_problems_copy_in_menu() -> None:
    """Copy Problem Location should appear in menus."""
    actions = get_menu_actions(None, None)
    ids = [a.id for a in actions]
    assert "editor.problems.copy_location" in ids


# ─────────────────────────────────────────────────────────────────────────────
# Enablement Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_enabled_problems_panel_active_true() -> None:
    """_enabled_problems_panel_active returns True when Problems tab is active."""
    controller = _FakeEditorController(right_dock_tab="Problems")
    assert _enabled_problems_panel_active(controller, None) is True


def test_enabled_problems_panel_active_false() -> None:
    """_enabled_problems_panel_active returns False when Problems tab is not active."""
    controller = _FakeEditorController(right_dock_tab="Inspector")
    assert _enabled_problems_panel_active(controller, None) is False


def test_enabled_problems_can_jump_false_when_wrong_panel() -> None:
    """_enabled_problems_can_jump returns False when Problems tab is not active."""
    problems_ctl = _FakeProblemsController(target={"kind": "scene", "scene_path": "test.json"})
    controller = _FakeEditorController(right_dock_tab="Inspector", problems_ctl=problems_ctl)
    assert _enabled_problems_can_jump(controller, None) is False


def test_enabled_problems_can_jump_false_when_no_target() -> None:
    """_enabled_problems_can_jump returns False when no jump target."""
    problems_ctl = _FakeProblemsController(target=None)
    controller = _FakeEditorController(right_dock_tab="Problems", problems_ctl=problems_ctl)
    assert _enabled_problems_can_jump(controller, None) is False


def test_enabled_problems_can_jump_false_when_unsupported_target() -> None:
    """_enabled_problems_can_jump returns False for unsupported target kinds."""
    problems_ctl = _FakeProblemsController(target={"kind": "none"})
    controller = _FakeEditorController(right_dock_tab="Problems", problems_ctl=problems_ctl)
    assert _enabled_problems_can_jump(controller, None) is False


def test_enabled_problems_can_jump_true_for_scene() -> None:
    """_enabled_problems_can_jump returns True for valid scene target."""
    problems_ctl = _FakeProblemsController(target={"kind": "scene", "scene_path": "test.json"})
    controller = _FakeEditorController(right_dock_tab="Problems", problems_ctl=problems_ctl)
    assert _enabled_problems_can_jump(controller, None) is True


def test_enabled_problems_can_jump_true_for_entity() -> None:
    """_enabled_problems_can_jump returns True for valid entity target."""
    problems_ctl = _FakeProblemsController(
        target={"kind": "entity", "scene_path": "test.json", "entity_id": "test_entity"}
    )
    controller = _FakeEditorController(right_dock_tab="Problems", problems_ctl=problems_ctl)
    assert _enabled_problems_can_jump(controller, None) is True
