from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.diagnostics import clear_diagnostics, error as diag_error, get_diagnostics, sort_diagnostics, warn as diag_warn
from engine.editor.editor_actions import run_editor_action
from engine.editor.editor_problems_controller import ProblemsController
from engine.editor.scene_lint_model import (
    SceneLintIssue,
    build_scene_lint_issues,
    format_issue_severity_tag,
)
from engine.ui_overlays.problems_panel_overlay import ProblemsPanelOverlay, format_problem_row_label
from tests._dock_stub import make_dock_stub


pytestmark = [pytest.mark.fast]


def test_problems_panel_can_be_created() -> None:
    window = SimpleNamespace(editor_controller=None, width=1280, height=720)
    overlay = ProblemsPanelOverlay(window)
    assert overlay is not None


def test_editor_problems_toggle_action_alias_opens_and_closes() -> None:
    class _StubController:
        def __init__(self) -> None:
            self.active = True
            self.dock = make_dock_stub(left_tab="Outliner", right_tab="Inspector")

        def set_dock_tab(self, dock: str, tab: str) -> None:
            if dock == "left":
                self.dock.set_left_tab(tab, force=True)
                self.dock.set_left_collapsed(False)
            else:
                self.dock.set_right_tab(tab, force=True)
                self.dock.set_right_collapsed(False)

    controller = _StubController()
    window = SimpleNamespace(editor_controller=controller)

    assert run_editor_action("editor.problems.toggle", controller, window) is True
    assert controller.dock.right_tab == "Problems"
    assert controller.dock.get_right_collapsed() is False

    assert run_editor_action("editor.problems.toggle", controller, window) is True
    assert controller.dock.get_right_collapsed() is True

    assert run_editor_action("editor.problems.toggle", controller, window) is True
    assert controller.dock.get_right_collapsed() is False


def test_structured_diagnostics_order_matches_sort_diagnostics() -> None:
    clear_diagnostics()
    try:
        diag_warn("z.warn", "last warning", "tests.editor_problems")
        diag_error("a.error", "first error", "tests.editor_problems", location="scene.json:1")
        diag_warn("m.warn", "middle warning", "tests.editor_problems")
        diag_error("a.error", "second error", "tests.editor_problems", location="scene.json:2")

        controller = ProblemsController(include_structured_diagnostics=True)
        controller.refresh_structured_diagnostics()

        diagnostics_only = [
            issue
            for issue in controller.get_filtered_issues()
            if isinstance(getattr(issue, "meta", None), dict) and str(issue.meta.get("diagnostic_code", "")).strip()
        ]
        actual_codes = [str(issue.meta.get("diagnostic_code", "")) for issue in diagnostics_only]
        expected_codes = [diag.code for diag in sort_diagnostics(get_diagnostics())]
        assert actual_codes == expected_codes

        payload = controller.get_provider_payload(viewport_height=120, row_height=18.0, overscan=0)
        counts = payload.get("severity_counts", {})
        assert counts == {"error": 2, "warning": 2, "info": 0}
    finally:
        clear_diagnostics()


def test_problem_list_includes_severity_badge_with_risk_tag() -> None:
    issue = SceneLintIssue(
        issue_id="warn",
        kind="MISSING_ASSET",
        message="Missing asset",
        entity_id="item",
        scene_id=None,
        severity="WARN",
        risk="safe",
        fix_kind="clear_asset",
        fixable=True,
        meta={},
    )

    assert format_problem_row_label(issue).startswith("[WARN] [SAFE] MISSING_ASSET:")


def test_diagnostic_problem_list_normalizes_warning_badge() -> None:
    issue = SceneLintIssue(
        issue_id="diag",
        kind="DIAG001",
        message="Diagnostic message",
        entity_id=None,
        scene_id="source.py",
        severity="warning",
        risk="safe",
        fix_kind=None,
        fixable=False,
        meta={"diagnostic_code": "DIAG001"},
    )

    assert format_problem_row_label(issue) == "[WARN] DIAG001: Diagnostic message"


def test_provider_payload_counts_warn_as_warning() -> None:
    ctrl = ProblemsController()
    warn_issue = SceneLintIssue("id1", "K", "Warn", "e1", "s1", "WARN", "safe", None, False)
    error_issue = SceneLintIssue("id2", "K", "Error", "e1", "s1", "ERROR", "safe", None, False)
    info_issue = SceneLintIssue("id3", "K", "Info", "e1", "s1", "INFO", "safe", None, False)

    ctrl.set_issues([warn_issue, error_issue, info_issue])

    payload = ctrl.get_provider_payload(90, 18)
    assert payload["severity_counts"] == {"error": 1, "warning": 1, "info": 1}


def test_format_issue_severity_tag_normalizes_warning_alias() -> None:
    issue = build_scene_lint_issues(
        {"entities": [{"id": "item", "sprite": "assets/missing.png"}]},
        Path("."),
        prefab_resolver=lambda _: True,
    )[0]
    assert issue.severity == "WARN"
    assert format_issue_severity_tag(issue) == "[WARN]"
