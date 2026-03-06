from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.diagnostics import clear_diagnostics, error as diag_error, get_diagnostics, sort_diagnostics, warn as diag_warn
from engine.editor.editor_actions import run_editor_action
from engine.editor.editor_problems_controller import ProblemsController
from engine.ui_overlays.problems_panel_overlay import ProblemsPanelOverlay
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
