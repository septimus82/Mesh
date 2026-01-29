from __future__ import annotations

from typing import Any, Optional

from engine.editor.scene_lint_model import SceneLintIssue
from engine.editor.problems_jump_model import choose_jump_target, JumpTarget

SEVERITY_RANK = {
    "error": 3,
    "warning": 2,
    "info": 1,
}

class ProblemsController:
    """Controller for the Problems panel."""

    def __init__(self) -> None:
        self.issues: list[SceneLintIssue] = []
        self.issues_rev: int = 0
        self.query: str = ""
        self.selected_index: int = 0
        self.scroll_y: int = 0
        self.preview_open: bool = False
    
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

    def set_query(self, query: str) -> None:
        """Set the search query."""
        if self.query == query:
            return
        self.query = query
        self.selected_index = 0
        self.scroll_y = 0

    def get_filtered_issues(self) -> list[SceneLintIssue]:
        """Get issues matching the search query."""
        if not self.query:
            return self.issues
        q = self.query.lower()
        
        # Filter logic similar to scene_lint_model.filter_lint_issues
        # Matches against message, kind, issue_id, entity_id
        filtered = []
        for issue in self.issues:
            if (q in issue.message.lower() or
                q in issue.kind.lower() or
                q in issue.issue_id.lower() or
                (issue.entity_id and q in issue.entity_id.lower())):
                filtered.append(issue)
        return filtered

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
        
        return {
            "rows": visible_subset,
            "start_index": start_idx,
            "total_count": total_count,
            "selected_index": self.selected_index,
            "scroll_y": self.scroll_y,
            "query": self.query,
            "preview_open": self.preview_open,
        }

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
