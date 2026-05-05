from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from engine.editor.asset_ops.editor_file_ops_controller import EditorFileOpsController
from engine.editor.editor_actions_parts import core_actions, project_explorer_actions
from engine.editor.project_explorer.editor_project_explorer_actions_controller import (
    EditorProjectExplorerActionsController,
)

pytestmark = [pytest.mark.fast]


class _Feedback:
    def __init__(self) -> None:
        self.emissions = []

    def info(self, message: str, *, ttl: float | None = None) -> None:
        self.emissions.append(("info", str(message), ttl))

    def warning(self, message: str, *, ttl: float | None = None) -> None:
        self.emissions.append(("warning", str(message), ttl))

    def error(self, message: str, *, ttl: float | None = None, sticky: bool = False) -> None:  # noqa: ARG002
        self.emissions.append(("error", str(message), ttl))


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, ("info", "Moved file", None)),
        ({"severity": "info", "seconds": 2.5}, ("info", "Moved file", 2.5)),
        ({"severity": "warning", "seconds": 2.5}, ("warning", "Moved file", 2.5)),
        ({"severity": "error", "seconds": 2.5}, ("error", "Moved file", 2.5)),
    ],
)
def test_file_ops_toast_routes_default_info_and_explicit_severities(kwargs, expected) -> None:
    controller = NS(feedback=_Feedback(), window=NS())
    EditorFileOpsController(controller)._toast("Moved file", **kwargs)
    assert controller.feedback.emissions == [expected]


@pytest.mark.parametrize(
    ("recents", "expected"),
    [
        ([], ("warning", "No recents to clear", 2.5)),
        (["scene.json"], ("info", "Recents cleared", 2.5)),
    ],
)
def test_project_explorer_clear_recents_emits_locked_severity(recents, expected) -> None:
    project = NS(recents=list(recents), clear_recents=lambda: recents.clear())
    editor = NS(feedback=_Feedback(), window=NS(), project_explorer=project, _autosave_workspace=lambda: None)
    assert EditorProjectExplorerActionsController(editor).clear_recents() is True
    assert editor.feedback.emissions == [expected]


def test_project_explorer_reveal_without_target_emits_warning_feedback() -> None:
    editor = NS(
        feedback=_Feedback(),
        window=NS(scene_controller=NS(current_scene_path=None)),
        project_explorer=NS(),
        _get_selected_entity_json_for_inspector=lambda: None,
    )
    assert EditorProjectExplorerActionsController(editor).reveal_current_in_explorer() is False
    assert editor.feedback.emissions == [("warning", "UI_NO_REVEAL_TARGET", 2.5)]


def test_project_explorer_prompt_move_without_handler_emits_warning_feedback() -> None:
    editor = NS(feedback=_Feedback(), window=NS())
    assert EditorProjectExplorerActionsController(editor).prompt_move_destination(lambda _dest: None) is False
    assert editor.feedback.emissions == [
        ("warning", "Safe Move: Select specific folder logic pending UI", 2.5)
    ]


def test_project_explorer_action_safe_move_without_prompt_emits_warning_feedback() -> None:
    editor = NS(
        active=True,
        feedback=_Feedback(),
        project_explorer=NS(selection_count=lambda: 1),
        file_ops=NS(can_safe_move_selected_asset=lambda: True),
    )
    window = NS(editor_controller=editor)
    project_explorer_actions._safe_move_selected_asset(window)
    assert editor.feedback.emissions == [
        ("warning", "Safe Move: Select specific folder logic pending UI", 2.5)
    ]


def test_project_explorer_inline_rename_error_emits_error_feedback() -> None:
    project = NS(
        commit_inline_rename=lambda: (False, None),
        get_inline_rename_commit_result=lambda: (False, None, "bad/name"),
    )
    editor = NS(active=True, feedback=_Feedback(), project_explorer=project)
    project_explorer_actions._inline_rename_commit(NS(editor_controller=editor))
    assert editor.feedback.emissions == [("error", "Rename failed: bad/name", 2.5)]


def test_core_inline_rename_error_emits_error_feedback() -> None:
    project = NS(
        inline_rename_active=True,
        get_inline_rename_commit_result=lambda: (False, None, "bad/name"),
    )
    editor = NS(feedback=_Feedback(), project_explorer=project)
    core_actions._action_refactor_rename_commit(NS(editor_controller=editor))
    assert editor.feedback.emissions == [("error", "Rename failed: bad/name", 2.5)]
