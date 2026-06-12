"""Contract tests for Problems panel preview/apply split."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from engine import optional_arcade
from engine.editor.scene_lint_model import SceneLintIssue
from engine.editor.state import EditorDirtyState
from engine.editor_controller import EditorModeController
from engine.ui_overlays.problems_panel_overlay import (
    build_problems_preview_lines,
    format_problem_row_label,
)
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
        self.dock = make_dock_stub(left_tab="Outliner", right_tab="Problems")
        self.session = make_session_stub()

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

    @property
    def _problems_search(self) -> str:
        return self.problems.query

    @_problems_search.setter
    def _problems_search(self, value: str):
        self.problems.set_query(value)

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

    def _problems_toast_no_fix(self) -> None:
        return EditorModeController._problems_toast_no_fix(self)

    def _handle_problems_input(self, key: int, modifiers: int) -> bool:
        return EditorModeController._handle_problems_input(self, key, modifiers)

    def problems_jump_to_selected(self) -> bool:
        return EditorModeController.problems_jump_to_selected(self)

    def _apply_scene_fix_update(self, new_scene: dict) -> None:
        return EditorModeController._apply_scene_fix_update(self, new_scene)

    def _refresh_after_scene_fix(self) -> None:
        return EditorModeController._refresh_after_scene_fix(self)

    def _push_command(self, cmd: dict) -> None:
        return EditorModeController._push_command(self, cmd)

    def _mark_dirty(self) -> None:
        return EditorModeController._mark_dirty(self)


def test_enter_jumps_to_problem(tmp_path: Path) -> None:
    """Enter key is now handled by action system, so _handle_problems_input returns False.

    The action editor.problems.jump_to_selected handles the actual jump.
    """
    scene = {"entities": [{"entity_id": ""}]}
    ctrl = StubController(scene, tmp_path)
    ctrl._prefab_resolver = lambda _: True
    ctrl.scan_scene_problems()

    # Enter is now handled by the action system, not _handle_problems_input
    handled = ctrl._handle_problems_input(optional_arcade.arcade.key.ENTER, 0)
    assert handled is False  # Defers to action system
    # Jump does not open preview
    assert ctrl.problems.preview_open is False
    # Jump does not apply fixes
    assert not ctrl.undo_stack


def test_ctrl_enter_jumps_to_problem(tmp_path: Path) -> None:
    """Ctrl+Enter is now handled by action system, so _handle_problems_input returns False.

    The action editor.problems.jump_to_selected_ctrl handles the actual jump.
    """
    scene = {"entities": [{"entity_id": ""}]}
    ctrl = StubController(scene, tmp_path)
    ctrl._prefab_resolver = lambda _: True
    ctrl.scan_scene_problems()

    # Ctrl+Enter is now handled by the action system, not _handle_problems_input
    handled = ctrl._handle_problems_input(optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.MOD_CTRL)
    assert handled is False  # Defers to action system
    # Jump does not apply fixes
    assert not ctrl.undo_stack


def test_shift_enter_applies_and_advances(tmp_path: Path) -> None:
    scene = {"entities": [{"entity_id": ""}, {"id": "dup"}, {"id": "dup"}]}
    ctrl = StubController(scene, tmp_path)
    ctrl._prefab_resolver = lambda _: True
    ctrl.scan_scene_problems()

    handled = ctrl._handle_problems_input(optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.MOD_SHIFT)
    assert handled is True
    issues = ctrl.get_filtered_problems()
    assert issues
    assert 0 <= ctrl.problems.selected_index < len(issues)


def test_escape_closes_preview_then_panel(tmp_path: Path) -> None:
    scene = {"entities": [{"entity_id": ""}]}
    ctrl = StubController(scene, tmp_path)
    ctrl._prefab_resolver = lambda _: True
    ctrl.scan_scene_problems()
    ctrl._open_problems_preview()

    ctrl._handle_problems_input(optional_arcade.arcade.key.ESCAPE, 0)
    assert ctrl.problems.preview_open is False
    assert ctrl.dock.right_tab == "Problems"

    ctrl._handle_problems_input(optional_arcade.arcade.key.ESCAPE, 0)
    assert ctrl.dock.right_tab == "Inspector"


def test_apply_non_fixable_emits_toast(tmp_path: Path) -> None:
    scene = {"entities": [{"id": "ok"}]}
    ctrl = StubController(scene, tmp_path)
    ctrl.problems.issues = [
        SceneLintIssue(
            issue_id="custom",
            kind="CUSTOM",
            message="Not fixable",
            entity_id="ok",
            scene_id=None,
            severity="WARN",
            risk="safe",
            fix_kind=None,
            fixable=False,
            meta={},
        )
    ]

    handled = ctrl._handle_problems_input(optional_arcade.arcade.key.X, 0)
    assert handled is True
    assert not ctrl.undo_stack
    assert ctrl.window.player_hud is not None
    assert ctrl.window.player_hud.toasts


def test_search_focus_blocks_ctrl_enter_jump(tmp_path: Path) -> None:
    """Search focus should block Ctrl+Enter jump but Enter still jumps."""
    scene = {"entities": [{"entity_id": ""}]}
    ctrl = StubController(scene, tmp_path)
    ctrl._prefab_resolver = lambda _: True
    ctrl.scan_scene_problems()
    ctrl.search._search_focus = "problems"

    # Enter with search focus: jump is still called (but search_focus check happens earlier for certain actions)
    ctrl._handle_problems_input(optional_arcade.arcade.key.ENTER, 0)
    # Preview is not opened since we jump instead
    assert ctrl.problems.preview_open is False
    assert not ctrl.undo_stack

    # Ctrl+Enter with search focus: blocked, returns early
    ctrl._handle_problems_input(optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.MOD_CTRL)
    assert not ctrl.undo_stack


def test_problem_list_risk_tags() -> None:
    safe_issue = SceneLintIssue(
        issue_id="safe",
        kind="DUPLICATE_ID",
        message="Duplicate id",
        entity_id="dup",
        scene_id=None,
        severity="WARN",
        risk="safe",
        fix_kind="rename_id",
        fixable=True,
        meta={},
    )
    risky_issue = SceneLintIssue(
        issue_id="risky",
        kind="INVALID_PREFAB_REF",
        message="Invalid prefab ref",
        entity_id="bad",
        scene_id=None,
        severity="WARN",
        risk="risky",
        fix_kind="clear_prefab",
        fixable=True,
        meta={},
    )
    assert "[SAFE]" in format_problem_row_label(safe_issue)
    assert "[RISKY]" in format_problem_row_label(risky_issue)


def test_problem_preview_risk_lines() -> None:
    safe_issue = SceneLintIssue(
        issue_id="safe",
        kind="DUPLICATE_ID",
        message="Duplicate id",
        entity_id="dup",
        scene_id=None,
        severity="WARN",
        risk="safe",
        fix_kind="rename_id",
        fixable=True,
        meta={},
    )
    risky_issue = SceneLintIssue(
        issue_id="risky",
        kind="INVALID_PREFAB_REF",
        message="Invalid prefab ref",
        entity_id="bad",
        scene_id=None,
        severity="WARN",
        risk="risky",
        fix_kind="clear_prefab",
        fixable=True,
        meta={},
    )
    safe_lines = build_problems_preview_lines(safe_issue, True)
    risky_lines = build_problems_preview_lines(risky_issue, True)
    assert any("Risk: SAFE" in line for line in safe_lines)
    assert any("Risk: RISKY (skipped by Fix All Safe)" in line for line in risky_lines)
