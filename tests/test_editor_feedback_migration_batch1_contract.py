from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from engine.editor.editor_problems_actions_controller import EditorProblemsActionsController
from engine.editor.editor_problems_controller import ProblemsController
from engine.editor_controller import EditorModeController


pytestmark = [pytest.mark.fast]


class _StubFeedback:
    def __init__(self) -> None:
        self.emissions: list[tuple[str, str, float | None]] = []

    def info(self, message: str, *, ttl: float | None = None) -> None:
        self.emissions.append(("info", str(message), ttl))

    def warning(self, message: str, *, ttl: float | None = None) -> None:
        self.emissions.append(("warning", str(message), ttl))

    def error(self, message: str, *, ttl: float | None = None, sticky: bool = False) -> None:  # noqa: ARG002
        self.emissions.append(("error", str(message), ttl))


def _actions_editor() -> SimpleNamespace:
    return SimpleNamespace(
        feedback=_StubFeedback(),
        window=SimpleNamespace(),
        problems=SimpleNamespace(get_selected_jump_target=lambda: None),
        project_explorer_actions=SimpleNamespace(reveal_path=lambda _path: True),
        _selection_ctl=SimpleNamespace(primary_selected_id=None),
        _open_scene_by_id=lambda scene_path: scene_path != "missing_scene.json",
    )


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, ("info", "Opened scene: demo.json", None)),
        ({"severity": "warning", "seconds": 2.5}, ("warning", "Opened scene: demo.json", 2.5)),
        ({"severity": "error", "seconds": 2.5}, ("error", "Opened scene: demo.json", 2.5)),
    ],
)
def test_problems_actions_toast_routes_default_warning_and_error(kwargs, expected) -> None:
    editor = _actions_editor()
    EditorProblemsActionsController(editor)._toast("Opened scene: demo.json", **kwargs)
    assert editor.feedback.emissions == [expected]


def test_jump_to_selected_failed_scene_emits_error_feedback() -> None:
    editor = _actions_editor()
    editor.problems = SimpleNamespace(
        get_selected_jump_target=lambda: {"kind": "scene", "scene_path": "missing_scene.json"}
    )

    assert EditorProblemsActionsController(editor).jump_to_selected() is False
    assert editor.feedback.emissions == [("error", "Failed to load scene: missing_scene.json", None)]


def test_copy_location_clipboard_unavailable_emits_warning_feedback() -> None:
    editor = _actions_editor()
    editor.problems = SimpleNamespace(
        get_selected_jump_target=lambda: {
            "kind": "entity",
            "path": "scene.json",
            "scene_path": "scene.json",
            "entity_id": "entity_1",
        }
    )

    with patch("engine.tooling_runtime.clipboard.try_copy_to_clipboard", return_value=False):
        assert EditorProblemsActionsController(editor).copy_location() is False
    assert editor.feedback.emissions == [("warning", "Clipboard unavailable (headless/web)", None)]


@pytest.mark.parametrize(
    ("helper", "args", "expected"),
    [
        ("_toast_problem_fixed", (), ("info", "Problem fixed", 2.5)),
        ("_toast_safe_summary", (1, 2), ("info", "Applied 1 safe fixes (2 skipped: risky)", 2.5)),
        (
            "_toast_safe_summary",
            (0, 3),
            ("warning", "Applied 0 safe fixes (3 skipped: risky)", 2.5),
        ),
        ("_toast_no_fix", (), ("warning", "No fix available", 2.5)),
    ],
)
def test_problems_controller_helpers_emit_locked_feedback_severity(helper, args, expected) -> None:
    editor = SimpleNamespace(feedback=_StubFeedback())
    problems = ProblemsController()

    if helper == "_toast_safe_summary":
        getattr(problems, helper)(editor, applied=args[0], skipped=args[1])
    else:
        getattr(problems, helper)(editor)
    assert editor.feedback.emissions == [expected]


def test_scan_scene_problems_emits_info_feedback() -> None:
    editor = SimpleNamespace(
        feedback=_StubFeedback(),
        window=SimpleNamespace(scene_controller=SimpleNamespace(_loaded_scene_data={"entities": []})),
        problems=SimpleNamespace(scan_scene=lambda _scene, _root, _resolver: ("issue",)),
        _get_repo_root=lambda: Path("."),
    )

    assert EditorModeController.scan_scene_problems(editor) == 1
    assert editor.feedback.emissions == [("info", "Problems scanned", 2.5)]
