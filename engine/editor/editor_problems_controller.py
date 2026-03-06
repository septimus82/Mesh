from __future__ import annotations

from typing import Any, Callable, Optional

from pathlib import Path

from engine.diagnostics import Diagnostic, get_diagnostics, sort_diagnostics
from engine.editor.scene_lint_model import SceneLintIssue
from engine.editor.problems_jump_model import choose_jump_target, JumpTarget
from engine.editor.scene_lint_model import build_scene_lint_issues
import engine.optional_arcade as optional_arcade

from engine.editor.editor_dock_query import get_dock_snapshot, get_effective_dock_widths
from engine.editor.scene_lint_model import (
    PROBLEMS_LINE_HEIGHT,
    compute_problems_panel_layout,
    compute_problems_window,
)
from engine.editor_tooltips_model import _is_modal_open_state, _is_text_input_active_state

SEVERITY_RANK = {
    "error": 3,
    "warning": 2,
    "info": 1,
}

class ProblemsController:
    """Controller for the Problems panel."""

    def __init__(self, *, include_structured_diagnostics: bool = False) -> None:
        self.issues: list[SceneLintIssue] = []
        self.diagnostic_issues: list[SceneLintIssue] = []
        self.issues_rev: int = 0
        self.query: str = ""
        self.selected_index: int = 0
        self.scroll_y: int = 0
        self.preview_open: bool = False
        self._include_structured_diagnostics = bool(include_structured_diagnostics)
        self._last_diagnostic_signature: tuple[tuple[str, str, str, str, str, str], ...] = ()
        self._new_error_indicator: bool = False
    
    def set_issues(self, issues: list[SceneLintIssue]) -> None:
        """Set the list of issues and sort them deterministically."""
        def sort_key(issue: SceneLintIssue) -> tuple[int, str, int, str]:
            # Severity (desc) -> negated rank for asc sort
            sev_rank = SEVERITY_RANK.get(issue.severity.lower(), 0)
            
            # Path (scene_id)
            path = issue.scene_id or ""
            
            # Line (index/entity_id) - heuristic
            # Try to get index from meta, else 0
            line = 0
            if isinstance(issue.meta, dict):
                val = issue.meta.get("index")
                if isinstance(val, int):
                    line = val
            
            # Code (kind)
            code = issue.kind or ""
            
            return (-sev_rank, path, line, code)

        self.issues = sorted(issues, key=sort_key)
        self.issues_rev += 1
        
        # Reset selection details if needed? 
        # Usually we want to preserve selection if possible, but indices shift.
        # For v1, resetting or clamping is safest. 
        # Existing logic in EditorController was _clamp_problems_selection.
        self._clamp_selection()

    def scan_scene(
        self,
        scene_data: dict[str, Any] | None,
        repo_root: Path,
        prefab_resolver: Callable[[str], bool],
    ) -> list[SceneLintIssue]:
        """Scan a scene payload and update issues deterministically."""
        if not isinstance(scene_data, dict):
            scene_data = {}
        issues = build_scene_lint_issues(scene_data, repo_root, prefab_resolver=prefab_resolver)
        self.set_issues(issues)
        return issues

    def refresh_structured_diagnostics(self) -> None:
        """Refresh editor-visible structured diagnostics from the engine sink."""
        if not self._include_structured_diagnostics:
            self.diagnostic_issues = []
            return
        ordered = tuple(sort_diagnostics(get_diagnostics()))
        signature = tuple(
            (
                str(item.level.value),
                str(item.code),
                str(item.message),
                str(item.source or ""),
                str(item.location or ""),
                str(item.hint or ""),
            )
            for item in ordered
        )
        if signature == self._last_diagnostic_signature:
            return

        prev_errors = sum(1 for issue in self.diagnostic_issues if str(issue.severity).lower() == "error")
        self.diagnostic_issues = [self._to_problem_issue(item, idx) for idx, item in enumerate(ordered)]
        self._last_diagnostic_signature = signature
        next_errors = sum(1 for issue in self.diagnostic_issues if str(issue.severity).lower() == "error")
        if next_errors > prev_errors:
            self._new_error_indicator = True
        self.issues_rev += 1
        self._clamp_selection()

    def mark_diagnostics_seen(self) -> None:
        self._new_error_indicator = False

    def has_new_error_indicator(self) -> bool:
        return bool(self._new_error_indicator)

    def get_severity_counts(self) -> dict[str, int]:
        self.refresh_structured_diagnostics()
        counts = {"error": 0, "warning": 0, "info": 0}
        for issue in self._all_issues():
            sev = str(getattr(issue, "severity", "") or "").strip().lower()
            if sev in counts:
                counts[sev] += 1
        return counts

    def set_query(self, query: str) -> None:
        """Set the search query."""
        if self.query == query:
            return
        self.query = query
        self.selected_index = 0
        self.scroll_y = 0

    def get_filtered_issues(self) -> list[SceneLintIssue]:
        """Get issues matching the search query."""
        all_issues = self._all_issues()
        if not self.query:
            return all_issues
        q = self.query.lower()
        
        # Filter logic similar to scene_lint_model.filter_lint_issues
        # Matches against message, kind, issue_id, entity_id
        filtered = []
        for issue in all_issues:
            if (q in issue.message.lower() or
                q in issue.kind.lower() or
                q in issue.issue_id.lower() or
                (issue.entity_id and q in issue.entity_id.lower()) or
                q in str(issue.meta.get("diagnostic_source", "")).lower() or
                q in str(issue.meta.get("diagnostic_location", "")).lower()):
                filtered.append(issue)
        return filtered

    def _all_issues(self) -> list[SceneLintIssue]:
        if not self._include_structured_diagnostics:
            return list(self.issues)
        # Keep diagnostics in their canonical deterministic order, then scene lint issues.
        return [*self.diagnostic_issues, *self.issues]

    def move_selection(self, delta: int) -> None:
        """Move the selection index."""
        filtered = self.get_filtered_issues()
        if not filtered:
            self.selected_index = 0
            return
        
        new_idx = self.selected_index + delta
        self.selected_index = max(0, min(new_idx, len(filtered) - 1))
        self._ensure_visible()

    def set_selected_index(self, index: int) -> None:
        """Set selected index explicitly."""
        self.selected_index = index
        self._clamp_selection()
        self._ensure_visible()

    def get_selected_issue(self) -> Optional[SceneLintIssue]:
        """Get the currently selected issue."""
        filtered = self.get_filtered_issues()
        if 0 <= self.selected_index < len(filtered):
            return filtered[self.selected_index]
        return None

    def get_provider_payload(self, viewport_height: int, row_height: float, overscan: int = 5) -> dict[str, Any]:
        """Get the payload for the UI provider.
        
        Updates scroll_y to ensure selection is within view.
        """
        self.refresh_structured_diagnostics()
        filtered = self.get_filtered_issues()
        total_count = len(filtered)
        
        # Auto-scroll Logic
        visible_count = int(viewport_height / row_height) if row_height > 0 else 1
        current_scroll_idx = int(self.scroll_y / row_height) if row_height > 0 else 0
        max_scroll = max(0, total_count - visible_count)
        
        # Adjust scroll to keep selection visible
        if self.selected_index < current_scroll_idx:
            current_scroll_idx = self.selected_index
        elif self.selected_index >= current_scroll_idx + visible_count:
            current_scroll_idx = self.selected_index - visible_count + 1
            
        current_scroll_idx = max(0, min(current_scroll_idx, max_scroll))
        self.scroll_y = int(current_scroll_idx * row_height)
        
        # Windowing
        start_idx = max(0, current_scroll_idx - overscan)
        end_idx = min(total_count, current_scroll_idx + visible_count + overscan)
        
        visible_subset = filtered[start_idx:end_idx]
        counts = self.get_severity_counts()
        
        return {
            "rows": visible_subset,
            "start_index": start_idx,
            "total_count": total_count,
            "selected_index": self.selected_index,
            "scroll_y": self.scroll_y,
            "query": self.query,
            "preview_open": self.preview_open,
            "severity_counts": counts,
            "has_new_errors": bool(self._new_error_indicator),
        }

    def _to_problem_issue(self, diag: Diagnostic, index: int) -> SceneLintIssue:
        context = dict(diag.context) if isinstance(diag.context, dict) else {}
        source = str(diag.source or context.get("source", "") or "").strip()
        location = str(
            diag.location
            or context.get("location", "")
            or context.get("pointer", "")
            or ""
        ).strip()
        hint = str(diag.hint or "").strip()
        return SceneLintIssue(
            issue_id=f"diagnostic:{index}:{diag.code}",
            kind=str(diag.code),
            message=str(diag.message),
            entity_id=None,
            scene_id=(source or None),
            severity=str(diag.severity).upper(),
            risk="safe",
            fix_kind=None,
            fixable=False,
            meta={
                "diagnostic_code": str(diag.code),
                "diagnostic_source": source,
                "diagnostic_location": location,
                "diagnostic_hint": hint,
                "diagnostic_context": dict(sorted(context.items(), key=lambda item: str(item[0]))),
            },
        )

    def _clamp_selection(self) -> None:
        filtered_len = len(self.get_filtered_issues())
        if filtered_len == 0:
            self.selected_index = 0
            self.preview_open = False
        else:
            self.selected_index = max(0, min(self.selected_index, filtered_len - 1))

    def _ensure_visible(self) -> None:
        # get_provider_payload will handle the actual scrolling calculation
        # but we need to ensure next call updates scroll_y.
        # Since scroll_y is state, get_provider_payload updates it.
        # But if we want to support "headless" validity, we might want to update it here?
        # Typically UI requests payload and that updates scroll. 
        pass

    def get_selected_jump_target(self) -> JumpTarget | None:
        """Get the jump target for the currently selected issue.
        
        Returns None if no issue is selected.
        """
        issue = self.get_selected_issue()
        if issue is None:
            return None
        return choose_jump_target(issue)

    def handle_input(self, editor: Any, key: int, modifiers: int) -> bool:
        if not getattr(editor, "active", False):
            return False
        snapshot = get_dock_snapshot(editor)
        if snapshot is None or snapshot.right_tab != "Problems":
            return False
        if self.input_blocked(editor):
            return True

        issues = self.get_filtered_issues()
        count = len(issues)
        if count <= 0:
            return True

        search_focus = editor.search.is_panel_search_focused("problems")
        if key in (optional_arcade.arcade.key.ESCAPE, optional_arcade.arcade.key.B):
            if self.preview_open:
                self.preview_open = False
                return True
            dock_ctl = getattr(editor, "dock", None)
            setter = getattr(dock_ctl, "apply_tab_change", None) if dock_ctl is not None else None
            if callable(setter):
                setter(editor, "right", "Inspector")
            return True

        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN, optional_arcade.arcade.key.A):
            # Shift+Enter: apply fix and advance
            if modifiers & optional_arcade.arcade.key.MOD_SHIFT and not (modifiers & optional_arcade.arcade.key.MOD_CTRL):
                if search_focus:
                    return True
                return self.apply_selected_fix(editor, advance=True)
            # Ctrl+Shift+Enter: apply all safe fixes
            if modifiers & optional_arcade.arcade.key.MOD_CTRL and modifiers & optional_arcade.arcade.key.MOD_SHIFT:
                if search_focus:
                    return True
                return self.apply_all_safe_fixes(editor)
            # Plain Enter and Ctrl+Enter are handled by editor action system
            # (editor.problems.jump_to_selected and editor.problems.jump_to_selected_ctrl)
            return False

        if key == optional_arcade.arcade.key.X:
            if search_focus:
                return True
            self.apply_selected_fix(editor, advance=False)
            return True

        # Ctrl+Shift+C is handled by editor action system (editor.problems.copy_location)

        if key == optional_arcade.arcade.key.UP:
            self.selected_index = max(0, self.selected_index - 1)
            return True
        if key == optional_arcade.arcade.key.DOWN:
            self.selected_index = min(count - 1, self.selected_index + 1)
            return True

        return False

    def handle_mouse_click(self, editor: Any, x: float, y: float, button: int) -> bool:
        if not getattr(editor, "active", False):
            return False
        snapshot = get_dock_snapshot(editor)
        if snapshot is None or snapshot.right_tab != "Problems":
            return False
        if self.input_blocked(editor):
            return True
        if editor.search.is_panel_search_focused("problems"):
            return True
        if button != optional_arcade.arcade.MOUSE_BUTTON_LEFT:
            return True

        from engine.editor.editor_shell_layout import (  # noqa: PLC0415
            compute_editor_shell_layout,
        )

        window = getattr(editor, "window", None)
        window_w = int(getattr(window, "width", 1280) or 1280)
        window_h = int(getattr(window, "height", 720) or 720)
        left_w, right_w = get_effective_dock_widths(editor, window_w)

        layout = compute_editor_shell_layout(window_w, window_h, left_w, right_w)
        dock = layout.right_dock
        if not dock.contains_point(x, y):
            return False

        panel = compute_problems_panel_layout(dock)
        if panel.scan_rect.contains_point(x, y):
            scanner = getattr(editor, "scan_scene_problems", None)
            if callable(scanner):
                scanner()
            return True
        if panel.fix_all_rect.contains_point(x, y):
            fixer = getattr(editor, "apply_fix_all_safe", None)
            if callable(fixer):
                fixer()
            return True

        if not panel.list_rect.contains_point(x, y):
            return True

        issues = self.get_filtered_issues()
        if not issues:
            return True

        visible_capacity = int(panel.list_rect.height / PROBLEMS_LINE_HEIGHT)
        start_idx, visible = compute_problems_window(
            self.selected_index, len(issues), visible_capacity
        )

        row_y = panel.list_rect.top
        for idx in range(start_idx, start_idx + visible):
            row_top = row_y
            row_bottom = row_y - PROBLEMS_LINE_HEIGHT
            if row_bottom <= y <= row_top:
                self.selected_index = idx
                return True
            row_y -= PROBLEMS_LINE_HEIGHT

        return True

    def input_blocked(self, editor: Any) -> bool:
        from engine.editor.editor_panels_query import panels_is_open  # noqa: PLC0415

        if panels_is_open(editor, "unsaved_confirm"):
            return True
        if editor.search.is_panel_search_focused("problems"):
            return _is_modal_open_state(editor)
        return _is_text_input_active_state(editor) or _is_modal_open_state(editor)

    def open_preview(self, _editor: Any) -> bool:
        issues = self.get_filtered_issues()
        if not issues:
            self.preview_open = False
            return False
        self._clamp_selection()
        self.preview_open = True
        return True

    def close_preview(self, _editor: Any) -> None:
        self.preview_open = False

    def toggle_preview(self, editor: Any) -> bool:
        if self.preview_open:
            self.close_preview(editor)
            return True
        return self.open_preview(editor)

    def apply_selected_fix(self, editor: Any, *, advance: bool) -> bool:
        issues = self.get_filtered_issues()
        if not issues:
            return False
        if not (0 <= self.selected_index < len(issues)):
            return False
        issue = issues[self.selected_index]
        if not getattr(issue, "fixable", False):
            self._toast_no_fix(editor)
            return False

        from engine.editor.scene_lint_ops import (  # noqa: PLC0415
            apply_fix_command,
            build_fix_command_for_issue,
        )

        scene = getattr(getattr(editor, "window", None), "scene_controller", None)
        scene_data = getattr(scene, "_loaded_scene_data", None) if scene is not None else None
        if not isinstance(scene_data, dict):
            return False

        repo_root = getattr(editor, "_get_repo_root", None)
        root = repo_root() if callable(repo_root) else None

        cmd = build_fix_command_for_issue(scene_data, issue, root)
        if cmd is None:
            self._toast_no_fix(editor)
            return False

        prior_index = self.selected_index
        new_scene = apply_fix_command(scene_data, cmd, root)
        self._apply_scene_fix_update(editor, new_scene)
        pusher = getattr(editor, "_push_command", None)
        if callable(pusher):
            pusher(cmd.to_dict())
        self._refresh_after_scene_fix(editor)
        scanner = getattr(editor, "scan_scene_problems", None)
        if callable(scanner):
            scanner()

        if advance:
            issues = self.get_filtered_issues()
            if issues:
                self.selected_index = min(prior_index, len(issues) - 1)
            else:
                self.preview_open = False

        self._toast_problem_fixed(editor)
        return True

    def apply_all_safe_fixes(self, editor: Any) -> bool:
        from engine.editor.scene_lint_ops import (  # noqa: PLC0415
            apply_fix_all,
            is_fix_safe,
        )

        issues = self.get_filtered_issues()
        scene = getattr(getattr(editor, "window", None), "scene_controller", None)
        scene_data = getattr(scene, "_loaded_scene_data", None) if scene is not None else None
        if not isinstance(scene_data, dict):
            return False

        repo_root = getattr(editor, "_get_repo_root", None)
        root = repo_root() if callable(repo_root) else None

        new_scene, cmd = apply_fix_all(scene_data, issues, root)
        applied = len(cmd.commands)
        skipped = sum(1 for issue in issues if not is_fix_safe(issue))

        if applied <= 0:
            self._toast_safe_summary(editor, applied, skipped)
            return True

        self._apply_scene_fix_update(editor, new_scene)
        pusher = getattr(editor, "_push_command", None)
        if callable(pusher):
            pusher(cmd.to_dict())
        self._refresh_after_scene_fix(editor)
        scanner = getattr(editor, "scan_scene_problems", None)
        if callable(scanner):
            scanner()
        self._toast_safe_summary(editor, applied, skipped)
        return True

    def _apply_scene_fix_update(self, editor: Any, new_scene: dict[str, Any]) -> None:
        scene = getattr(getattr(editor, "window", None), "scene_controller", None)
        if scene is None:
            return
        scene._loaded_scene_data = new_scene

    def _refresh_after_scene_fix(self, editor: Any) -> None:
        scene = getattr(getattr(editor, "window", None), "scene_controller", None)
        if scene is not None:
            reloader = getattr(scene, "reload_scene", None)
            if callable(reloader):
                reloader()
        refresher = getattr(editor, "_refresh_entity_panels_list", None)
        if callable(refresher):
            refresher(sync_selected=True)
        refresher = getattr(editor, "_refresh_hierarchy_list", None)
        if callable(refresher):
            refresher()
        refresher = getattr(editor, "_refresh_inspector_items", None)
        if callable(refresher):
            refresher()

    def _toast_problem_fixed(self, editor: Any) -> None:
        from engine.i18n import tr  # noqa: PLC0415

        hud = getattr(getattr(editor, "window", None), "player_hud", None)
        toaster = getattr(hud, "enqueue_toast", None) if hud is not None else None
        if callable(toaster):
            toaster(tr("UI_PROBLEM_FIXED"), seconds=2.5)

    def _toast_safe_summary(self, editor: Any, applied: int, skipped: int) -> None:
        from engine.i18n import tr  # noqa: PLC0415

        hud = getattr(getattr(editor, "window", None), "player_hud", None)
        toaster = getattr(hud, "enqueue_toast", None) if hud is not None else None
        if callable(toaster):
            toaster(
                tr("UI_PROBLEMS_APPLIED_SAFE_SUMMARY").format(applied=applied, skipped=skipped),
                seconds=2.5,
            )

    def _toast_no_fix(self, editor: Any) -> None:
        from engine.i18n import tr  # noqa: PLC0415

        hud = getattr(getattr(editor, "window", None), "player_hud", None)
        toaster = getattr(hud, "enqueue_toast", None) if hud is not None else None
        if callable(toaster):
            toaster(tr("UI_NO_FIX_AVAILABLE"), seconds=2.5)
