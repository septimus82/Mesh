"""Integration tests for Problems panel controller wiring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from engine import optional_arcade
from engine.editor.state import EditorDirtyState
from engine.editor.scene_lint_model import SceneLintIssue
from engine.editor_controller import EditorModeController
from engine.ui_overlays.problems_panel_overlay import ProblemsPanelOverlay
from tests._dock_stub import make_dock_stub
from tests._search_stub import attach_search_stub
from tests._session_stub import make_session_stub


class StubHud:
    def __init__(self) -> None:
        self.toasts: list[str] = []

    def enqueue_toast(self, text: str, seconds: float = 2.5) -> None:  # noqa: ARG002
        self.toasts.append(text)


class StubSceneController:
    def __init__(self, scene: dict) -> None:
        self._loaded_scene_data = scene
        self.reload_calls = 0

    def reload_scene(self) -> None:
        self.reload_calls += 1


@dataclass
class StubWindow:
    scene_controller: StubSceneController
    width: int = 1280
    height: int = 720
    strict_mode: bool = False
    player_hud: StubHud | None = None


class StubController:
    def __init__(self, scene: dict, repo_root: Path) -> None:
        self.window = StubWindow(StubSceneController(scene), player_hud=StubHud())
        self.active = True
        self.dock = make_dock_stub(left_tab="Project", right_tab="Problems")
        
        from engine.editor.editor_problems_controller import ProblemsController
        self.problems = ProblemsController()
        
        self._repo_root_override = repo_root
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        self.scene_dirty = False
        self.dirty_state = EditorDirtyState()
        self.palette_filter_active = False
        self.hierarchy_filter_active = False
        self.hierarchy_rename_active = False
        self.animation_edit_active = False
        self.inspector_edit_active = False
        self.command_palette_active = False
        self.entity_panels_filter_active = False
        self.scene_browser_filter_active = False
        self.asset_browser_filter_active = False
        self._unsaved_changes_pending = False
        self.scene_browser_active = False
        from types import SimpleNamespace
        self.unsaved_confirm = SimpleNamespace(is_open=False)
        self.session = make_session_stub()
        self.search = attach_search_stub(self)
        
        # Stub for _selection_ctl needed by problems_jump_to_selected
        class StubSelectionCtl:
            primary_selected_id: str | None = None
        self._selection_ctl = StubSelectionCtl()
        
        # Stub for project_explorer needed by _reveal_in_project_explorer
        class StubProjectExplorer:
            def reveal_path(self, path: str, viewport_height: int, row_height: int) -> bool:
                return True
        self.project_explorer = StubProjectExplorer()

    def _open_scene_by_id(self, scene_id: str) -> bool:
        """Stub: Always succeed for tests."""
        return True

    def _toast_problems(self, message: str, seconds: float = 2.5) -> None:
        """Stub: No-op for tests."""
        pass

    def _reveal_in_project_explorer(self, path: str) -> bool:
        """Stub: Always succeed for tests."""
        return True

    def _get_repo_root(self):
        return self._repo_root_override

    def _autosave_workspace(self) -> None:
        return

    def _refresh_entity_panels_list(self, *, sync_selected: bool = False) -> None:  # noqa: ARG002
        return

    def _refresh_hierarchy_list(self) -> None:
        return

    def _refresh_inspector_items(self) -> None:
        return

    def get_effective_dock_widths(self, window_w: int):  # noqa: ARG002
        return self.dock.get_effective_dock_widths(window_w)

    def scan_scene_problems(self) -> int:
        return EditorModeController.scan_scene_problems(self)

    def get_filtered_problems(self):
        return EditorModeController.get_filtered_problems(self)

    def _clamp_problems_selection(self) -> None:
        return EditorModeController._clamp_problems_selection(self)

    def _problems_input_blocked(self) -> bool:
        return EditorModeController._problems_input_blocked(self)

    def _apply_selected_problem_fix(self, *, advance: bool) -> bool:
        return EditorModeController._apply_selected_problem_fix(self, advance=advance)

    def _apply_all_safe_problem_fixes(self) -> bool:
        return EditorModeController._apply_all_safe_problem_fixes(self)

    def _open_problems_preview(self) -> bool:
        return EditorModeController._open_problems_preview(self)

    def _close_problems_preview(self) -> None:
        return EditorModeController._close_problems_preview(self)

    def apply_selected_problem_fix(self) -> bool:
        return EditorModeController.apply_selected_problem_fix(self)

    def apply_fix_all_safe(self) -> bool:
        return EditorModeController.apply_fix_all_safe(self)

    def _apply_scene_fix_update(self, new_scene: dict) -> None:
        return EditorModeController._apply_scene_fix_update(self, new_scene)

    def _refresh_after_scene_fix(self) -> None:
        return EditorModeController._refresh_after_scene_fix(self)

    def _handle_problems_input(self, key: int, modifiers: int) -> bool:
        return EditorModeController._handle_problems_input(self, key, modifiers)

    def problems_jump_to_selected(self) -> bool:
        return EditorModeController.problems_jump_to_selected(self)

    def _problems_handle_mouse_click(self, x: float, y: float, button: int) -> bool:
        return EditorModeController._problems_handle_mouse_click(self, x, y, button)

    def _problems_toast_no_fix(self) -> None:
        return EditorModeController._problems_toast_no_fix(self)

    def _push_command(self, cmd: dict) -> None:
        return EditorModeController._push_command(self, cmd)

    def _mark_dirty(self) -> None:
        return EditorModeController._mark_dirty(self)


def test_scan_builds_issues(tmp_path: Path) -> None:
    scene = {"entities": [{"entity_id": ""}]}
    ctrl = StubController(scene, tmp_path)
    ctrl._prefab_resolver = lambda _: True

    count = ctrl.scan_scene_problems()
    assert count == 1
    assert ctrl.problems.issues


def test_apply_selected_fix_pushes_undo_and_dirty(tmp_path: Path) -> None:
    scene = {"entities": [{"entity_id": ""}]}
    ctrl = StubController(scene, tmp_path)
    ctrl._prefab_resolver = lambda _: True
    ctrl.scan_scene_problems()

    assert ctrl.apply_selected_problem_fix() is True
    assert ctrl.undo_stack
    assert ctrl.dirty_state.is_dirty is True
    assert ctrl.window.scene_controller._loaded_scene_data["entities"][0]["entity_id"] == "entity_1"


def test_fix_all_safe_single_undo(tmp_path: Path) -> None:
    scene = {"entities": [{"id": "dup"}, {"id": "dup"}, {"entity_id": ""}]}
    ctrl = StubController(scene, tmp_path)
    ctrl._prefab_resolver = lambda _: True
    ctrl.scan_scene_problems()

    assert ctrl.apply_fix_all_safe() is True
    assert len(ctrl.undo_stack) == 1


def test_fix_all_safe_skips_risky_and_toasts(tmp_path: Path) -> None:
    scene = {"entities": [{"id": "dup"}, {"id": "dup"}]}
    ctrl = StubController(scene, tmp_path)
    ctrl._prefab_resolver = lambda _: True
    ctrl.scan_scene_problems()
    safe_issue = ctrl.problems.issues[0]
    risky_issue = SceneLintIssue(
        issue_id="risky",
        kind=safe_issue.kind,
        message=safe_issue.message,
        entity_id=safe_issue.entity_id,
        scene_id=safe_issue.scene_id,
        severity=safe_issue.severity,
        risk="risky",
        fix_kind=safe_issue.fix_kind,
        fixable=safe_issue.fixable,
        meta=safe_issue.meta,
    )
    ctrl.problems.set_issues([risky_issue, safe_issue])

    assert ctrl.apply_fix_all_safe() is True
    assert ctrl.window.scene_controller._loaded_scene_data["entities"][1]["id"].startswith("dup_fix_")
    assert ctrl.window.player_hud is not None
    assert any("Applied 1 safe fixes" in toast for toast in ctrl.window.player_hud.toasts)


def test_fix_all_safe_no_safe_does_not_mutate(tmp_path: Path) -> None:
    scene = {"entities": [{"id": "dup"}, {"id": "dup"}]}
    ctrl = StubController(scene, tmp_path)
    ctrl._prefab_resolver = lambda _: True
    ctrl.scan_scene_problems()
    safe_issue = ctrl.problems.issues[0]
    risky_issue = SceneLintIssue(
        issue_id="risky",
        kind=safe_issue.kind,
        message=safe_issue.message,
        entity_id=safe_issue.entity_id,
        scene_id=safe_issue.scene_id,
        severity=safe_issue.severity,
        risk="risky",
        fix_kind=safe_issue.fix_kind,
        fixable=safe_issue.fixable,
        meta=safe_issue.meta,
    )
    ctrl.problems.set_issues([risky_issue])

    assert ctrl.apply_fix_all_safe() is True
    assert ctrl.window.scene_controller._loaded_scene_data == scene
    assert ctrl.window.player_hud is not None
    assert any("Applied 0 safe fixes" in toast for toast in ctrl.window.player_hud.toasts)


def test_search_focus_blocks_enter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)

    scene = {"entities": [{"entity_id": ""}]}
    ctrl = StubController(scene, tmp_path)
    ctrl._prefab_resolver = lambda _: True
    ctrl.scan_scene_problems()
    ctrl.search._search_focus = "problems"

    # Enter is now handled by the action system, not _handle_problems_input
    # The panel handler returns False to defer to the action system
    handled = ctrl._handle_problems_input(arcade_stub.key.ENTER, 0)
    assert handled is False  # Defers to action system
    # With search focus, the action system's enabled check should still work
    # Preview remains closed since we jump instead
    assert not ctrl.undo_stack


def test_overlay_draw_noop_headless(tmp_path: Path) -> None:
    scene = {"entities": []}
    controller = StubController(scene, tmp_path)
    controller.active = False
