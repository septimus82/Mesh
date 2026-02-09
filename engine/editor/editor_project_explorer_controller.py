from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from engine.editor.project_explorer_model import (
    ProjectExplorerDisplayRow,
    ProjectExplorerRecentItem,
    scan_project_tree,
    build_project_explorer_display_rows,
    clamp_selection_on_selectables,
    push_recent,
    coerce_recent_items,
    recent_items_to_payloads,
    activation_intent_for_display_row,
    ProjectRow,
)
from engine.editor.project_explorer_perf_model import compute_filter_key
from engine.editor.project_explorer_selection_model import (
    SelectionState,
    select_single,
    toggle_index,
    select_range,
    select_all,
    clear_selection,
    move_primary,
    selected_indices_sorted,
    selection_summary,
)
from engine.editor.project_explorer_power_tools_model import invert_selection
from engine.editor.project_explorer_inline_rename_model import (
    InlineRenameState,
    create_inline_rename_state,
    append_rename_text,
    handle_rename_backspace,
    handle_rename_delete,
    should_commit_rename,
    get_final_rename_name,
    move_cursor_left,
    move_cursor_right,
    move_cursor_home,
    move_cursor_end,
    move_cursor_word_left,
    move_cursor_word_right,
    delete_prev_word,
    delete_next_word,
)
from engine.editor.project_explorer_context_menu_model import (
    ContextMenuItem,
    ProjectExplorerSelectionPayload,
    build_project_explorer_context_menu,
    clamp_menu_index,
    first_selectable_index,
    find_index_by_action_id,
    next_selectable_index,
    hit_test_menu_item,
    CONTEXT_MENU_WIDTH,
    CONTEXT_MENU_ITEM_HEIGHT,
    CONTEXT_MENU_PADDING_Y,
)
from engine.editor.project_explorer_context_menu_layout_model import clamp_menu_rect
from engine.editor.project_explorer_power_tools_model import compute_common_parent

if TYPE_CHECKING:
    from pathlib import Path
    from engine.editor_controller import EditorModeController


class ProjectExplorerController:
    """Controller for the Project Explorer panel."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        
        # State
        self.tree_rev: int = 0
        self.project_rows: list[ProjectRow] = []
        
        # Filtering & Caching
        self.filter_cache_key: Optional[str] = None
        self.search_query: str = ""
        self.cached_rows: list[ProjectExplorerDisplayRow] = []
        self.selectable_rows: list[ProjectExplorerDisplayRow] = []
        
        # Selection
        self.selection_state = SelectionState(primary_index=0, selected_indices=frozenset(), anchor_index=None)
        self.scroll_y: int = 0
        
        # Recents
        self.recents_rev: int = 0
        self.recents: list[ProjectExplorerRecentItem] = []
        
        # Inline Rename State
        self.inline_rename_state: Optional[InlineRenameState] = None

        # Context Menu State
        self.context_menu_open: bool = False
        self.context_menu_index: Optional[int] = None
        self.context_menu_hover_index: Optional[int] = None
        self.context_menu_items: list[ContextMenuItem] = []
        self.context_menu_anchor: tuple[int, int] = (0, 0)
        self.context_menu_width: int = CONTEXT_MENU_WIDTH
        self.context_menu_height: int = 0
        self.context_menu_last_action_id: Optional[str] = None
        self.context_menu_selection_key: tuple[str, ...] | None = None
        self._editor: Optional["EditorModeController"] = None

    def set_repo_root(self, repo_root: Path) -> None:
        """Update repo root (e.g. on workspace load)."""
        self.repo_root = repo_root
        # Invalidate
        self.project_rows = []
        self.tree_rev = 0
        self.filter_cache_key = None

    def refresh_tree(self) -> None:
        """Rescan the project tree from disk."""
        self.project_rows = scan_project_tree(self.repo_root)
        self.tree_rev += 1
        self._filter_rows()

    def set_query(self, query: str) -> None:
        """Set the search query."""
        if self.search_query != query:
            self.search_query = query
            self._filter_rows()

    def set_selected_index(self, index: int) -> None:
        """Set the selected row index."""
        self._set_selection_single(index)

    def move_selection(self, delta: int, extend: bool = False) -> None:
        """Move the selection up or down."""
        length = len(self.selectable_rows)
        if length <= 0:
            return
        next_state = move_primary(self.selection_state, delta, extend)
        next_state = self._clamp_selection_state(next_state, length)
        self._apply_selection_state(next_state)

    @property
    def selected_index(self) -> int:
        return self.selection_state.primary_index

    @selected_index.setter
    def selected_index(self, index: int) -> None:
        self._set_selection_single(index)

    def get_selected_row(self) -> Optional[ProjectExplorerDisplayRow]:
        """Get the currently selected row."""
        self.ensure_rows()
        if not self.selectable_rows:
            return None
        if not self.selection_state.selected_indices:
            return None

        self.selection_state = self._clamp_selection_state(self.selection_state, len(self.selectable_rows))
        return self.selectable_rows[self.selection_state.primary_index]

    def ensure_rows(self) -> None:
        """Ensure rows are loaded and filtered."""
        if not self.project_rows and self.tree_rev == 0:
            self.refresh_tree()
        elif not self.cached_rows and self.project_rows:
             # Case where rows exist but filter hasn't run or was cleared
             self._filter_rows()

    def _filter_rows(self) -> None:
        """Recompute filtered rows based on state."""
        combined_rev = self.tree_rev * 1000 + self.recents_rev
        cache_key = compute_filter_key(self.search_query, None, combined_rev)
        
        if cache_key == self.filter_cache_key and self.cached_rows:
            return

        display_rows, selectable_rows = build_project_explorer_display_rows(
            self.project_rows,
            self.recents,
            self.search_query,
        )
        self.cached_rows = display_rows
        self.selectable_rows = selectable_rows
        self.filter_cache_key = cache_key
        # Re-clamp selection
        self.selection_state = self._clamp_selection_state(
            self.selection_state, len(selectable_rows)
        )

    def get_provider_payload(self, viewport_height: int = 720, row_height: float = 18.0, overscan: int = 5) -> dict[str, Any]:
        """Get the payload for the UI provider.
        
        Updates scroll_y to ensure selection is visible.
        """
        self.ensure_rows()
        
        # 1. Ensure selection visibility (Auto-Scroll)
        # Map selectable index to display index
        # Optimization: cache this map? For now, we linear scan.
        selected_row = self.get_selected_row()
        display_index = 0
        if selected_row and self.cached_rows:
            try:
                display_index = self.cached_rows.index(selected_row)
            except ValueError:
                display_index = 0
        
        visible_count = int(viewport_height / row_height) if row_height > 0 else 1
        current_scroll_idx = int(self.scroll_y / row_height) if row_height > 0 else 0
        
        # Clamp scroll to valid range
        total_rows = len(self.cached_rows)
        max_scroll = max(0, total_rows - visible_count)
        
        # Adjust for visibility
        if display_index < current_scroll_idx:
            current_scroll_idx = display_index
        elif display_index >= current_scroll_idx + visible_count:
            current_scroll_idx = display_index - visible_count + 1
            
        current_scroll_idx = max(0, min(current_scroll_idx, max_scroll))
        self.scroll_y = int(current_scroll_idx * row_height)
        
        # 2. Compute Window
        start_idx = max(0, current_scroll_idx - overscan)
        end_idx = min(total_rows, current_scroll_idx + visible_count + overscan)
        
        visible_subset = self.cached_rows[start_idx:end_idx]
        
        selection_count = len(self.selection_state.selected_indices)
        primary_path = self.primary_path(self.selectable_rows)
        selected_paths = self.selected_paths(self.selectable_rows)
        selected_ids = [
            id(self.selectable_rows[i])
            for i in selected_indices_sorted(self.selection_state)
            if 0 <= i < len(self.selectable_rows)
        ]
        return {
            "rows": visible_subset,
            "start_index": start_idx,
            "total_count": total_rows,
            "selectable_rows": self.selectable_rows,
            "selected_index": self.selection_state.primary_index,
            "scroll_y": self.scroll_y,
            "search_query": self.search_query,
            "recents": recent_items_to_payloads(self.recents),
            # Helper for UI to highlight
            "selected_row_id": id(selected_row) if selected_row else None,
            "selected_row_ids": selected_ids,
            "primary_path": primary_path,
            "selected_paths": selected_paths,
            "selection_count": selection_count,
            "has_multi": selection_count > 1,
        }

    # Recents Management
    
    def set_recents(self, recents: Any) -> None:
        """Load recents from storage."""
        self.recents = coerce_recent_items(recents)
        self.recents_rev += 1
        self._filter_rows()
        
    def get_recents_payload(self) -> list[dict[str, Any]]:
        """Get recents for storage."""
        return recent_items_to_payloads(self.recents)
        
    def push_recent_item(self, item: ProjectExplorerRecentItem) -> None:
        """Add an item to recents."""
        self.recents = push_recent(self.recents, item)
        self.recents_rev += 1
        self._filter_rows()
        
    def clear_recents(self) -> None:
        """Clear all recent items."""
        self.recents = []
        self.recents_rev += 1
        self._filter_rows()

    def copy_selected_path(self) -> Optional[str]:
        """Return the path of the selected item."""
        return self.primary_path(self.selectable_rows)

    def clear_selection(self) -> None:
        self._apply_selection_state(clear_selection(self.selection_state))

    def select_all(self) -> None:
        self.ensure_rows()
        self._apply_selection_state(select_all(self.selection_state, len(self.selectable_rows)))

    def invert_selection(self) -> None:
        self.ensure_rows()
        length = len(self.selectable_rows)
        if length <= 0:
            self._apply_selection_state(clear_selection(self.selection_state))
            return
        inverted = invert_selection(range(length), self.selection_state.selected_indices)
        if not inverted:
            self._apply_selection_state(clear_selection(self.selection_state))
            return
        primary = self.selection_state.primary_index
        if primary not in inverted:
            primary = min(inverted)
        self._apply_selection_state(SelectionState(
            primary_index=primary,
            selected_indices=frozenset(inverted),
            anchor_index=primary,
        ))

    def set_selection_by_path(self, path: str) -> None:
        if not path:
            return
        self.ensure_rows()
        for idx, row in enumerate(self.selectable_rows):
            entry = getattr(row, "entry", None)
            if entry is not None and str(getattr(entry, "rel_path", "")) == str(path):
                self._set_selection_single(idx)
                return

    def _toggle_selection_by_path(self, path: str) -> None:
        if not path:
            return
        self.ensure_rows()
        for idx, row in enumerate(self.selectable_rows):
            entry = getattr(row, "entry", None)
            if entry is not None and str(getattr(entry, "rel_path", "")) == str(path):
                next_state = toggle_index(self.selection_state, idx)
                next_state = self._clamp_selection_state(next_state, len(self.selectable_rows))
                self._apply_selection_state(next_state)
                return

    def selected_paths(self, rows: list[ProjectExplorerDisplayRow] | None = None) -> list[str]:
        rows = rows if rows is not None else self.selectable_rows
        paths: list[str] = []
        for idx in selected_indices_sorted(self.selection_state):
            if 0 <= idx < len(rows):
                row = rows[idx]
                entry = getattr(row, "entry", None)
                if entry is not None:
                    path = str(getattr(entry, "rel_path", ""))
                    if path:
                        paths.append(path)
                        continue
                recent = getattr(row, "recent", None)
                if recent is not None:
                    path = str(getattr(recent, "rel_path", ""))
                    if path:
                        paths.append(path)
        return sorted(set(paths))

    def primary_path(self, rows: list[ProjectExplorerDisplayRow] | None = None) -> Optional[str]:
        rows = rows if rows is not None else self.selectable_rows
        if not rows:
            return None
        idx = self.selection_state.primary_index
        if idx < 0 or idx >= len(rows):
            return None
        row = rows[idx]
        entry = getattr(row, "entry", None)
        if entry is not None:
            path = str(getattr(entry, "rel_path", ""))
            return path or None
        recent = getattr(row, "recent", None)
        if recent is not None:
            path = str(getattr(recent, "rel_path", ""))
            return path or None
        return None

    def selection_count(self) -> int:
        return len(self.selection_state.selected_indices)

    def open_context_menu(
        self,
        x: int,
        y: int,
        editor: "EditorModeController",
        *,
        active_scopes: tuple[str, ...],
    ) -> None:
        """Open the context menu at the given screen position."""
        self.ensure_rows()
        self._editor = editor

        selection_count = self.selection_count()
        selected_paths = self.selected_paths(self.selectable_rows)
        selection_key = tuple(sorted(set(str(p) for p in selected_paths if str(p).strip())))
        has_common_parent = bool(compute_common_parent(selected_paths)) if len(selected_paths) > 1 else False

        # Capability checks (avoid hasattr chains)
        file_ops = getattr(editor, "file_ops", None)
        can_rename = selection_count == 1
        can_move = selection_count > 0
        can_delete = selection_count > 0
        if file_ops is not None:
            can_rename = bool(getattr(file_ops, "can_safe_rename_selected_asset", lambda: can_rename)())
            can_move = bool(
                getattr(file_ops, "can_safe_move_selected_assets_folder", lambda: can_move)()
                or getattr(file_ops, "can_safe_move_selected_asset", lambda: can_move)()
            )
            can_delete = bool(getattr(file_ops, "can_delete_selected_assets", lambda paths: can_delete)(selected_paths))
        can_rename = bool(can_rename and selection_count == 1)
        can_move = bool(can_move and selection_count > 0)
        can_delete = bool(can_delete and selection_count > 0)

        # Reveal target (scene path or entity selection)
        window = getattr(editor, "window", None)
        can_reveal = False
        if window is not None:
            sc = getattr(window, "scene_controller", None)
            scene_path = getattr(sc, "current_scene_path", None) if sc is not None else None
            if scene_path:
                can_reveal = True
        if getattr(editor, "_primary_selected_id", None):
            can_reveal = True

        can_copy_paths = selection_count > 0
        can_copy_common_parent = selection_count > 1 and has_common_parent
        can_select_all = True
        can_clear_selection = True
        can_invert_selection = True

        payload = ProjectExplorerSelectionPayload(
            selection_count=selection_count,
            has_common_parent=has_common_parent,
            can_rename=can_rename,
            can_move=can_move,
            can_delete=can_delete,
            can_reveal=can_reveal,
            can_copy_paths=can_copy_paths,
            can_copy_common_parent=can_copy_common_parent,
            can_select_all=can_select_all,
            can_clear_selection=can_clear_selection,
            can_invert_selection=can_invert_selection,
        )

        from engine.editor.editor_actions import get_editor_actions  # noqa: PLC0415

        actions = get_editor_actions(editor, window)
        self.context_menu_items = build_project_explorer_context_menu(payload, actions, active_scopes)
        self.context_menu_height = (
            len(self.context_menu_items) * CONTEXT_MENU_ITEM_HEIGHT
        ) + (CONTEXT_MENU_PADDING_Y * 2)

        self.context_menu_anchor = (int(x), int(y))

        # Selection persistence: only keep last action if selection is unchanged.
        if self.context_menu_selection_key != selection_key:
            self.context_menu_last_action_id = None
        self.context_menu_selection_key = selection_key

        preferred_index = find_index_by_action_id(self.context_menu_items, self.context_menu_last_action_id)
        if preferred_index is None:
            preferred_index = first_selectable_index(self.context_menu_items)
        self.context_menu_index = preferred_index
        self.context_menu_hover_index = None
        self.context_menu_open = True

        panels = getattr(editor, "panels", None)
        if panels and hasattr(panels, "open_project_context_menu"):
            panels.open_project_context_menu()
        else:
            ui_stack = getattr(editor, "ui_layers", None)
            if ui_stack:
                ui_stack.push_modal("project_context_menu")

    def close_context_menu(self, editor: "EditorModeController") -> None:
        if not self.context_menu_open:
            return
        self.context_menu_open = False
        self.context_menu_items = []
        self.context_menu_hover_index = None
        self._editor = None
        panels = getattr(editor, "panels", None)
        if panels and hasattr(panels, "close_project_context_menu"):
            panels.close_project_context_menu()
        else:
            ui_stack = getattr(editor, "ui_layers", None)
            if ui_stack:
                ui_stack.pop_modal("project_context_menu")

    def move_context_menu_selection(self, delta: int) -> None:
        if not self.context_menu_open or not self.context_menu_items:
            return
        self.context_menu_index = next_selectable_index(
            self.context_menu_items, self.context_menu_index, delta
        )
        index = self.context_menu_index
        if index is not None:
            item = self.context_menu_items[clamp_menu_index(index, self.context_menu_items)]
            if item.kind == "action" and item.enabled:
                self.context_menu_last_action_id = item.action_id

    def activate_context_menu_item(self, editor: "EditorModeController") -> bool:
        if not self.context_menu_open or not self.context_menu_items:
            return False
        if self.context_menu_index is None:
            return False
        index = clamp_menu_index(self.context_menu_index, self.context_menu_items)
        item = self.context_menu_items[index]
        if item.kind != "action" or not item.enabled or not item.action_id:
            return False
        from engine.editor.editor_actions import run_editor_action  # noqa: PLC0415

        self.close_context_menu(editor)
        return bool(run_editor_action(item.action_id, editor, getattr(editor, "window", None)))

    def _context_menu_position(self, editor: "EditorModeController") -> tuple[int, int]:
        window = getattr(editor, "window", None)
        vp_w = int(getattr(window, "width", 1280) or 1280)
        vp_h = int(getattr(window, "height", 720) or 720)
        ax, ay = self.context_menu_anchor
        return clamp_menu_rect(ax, ay, self.context_menu_width, self.context_menu_height, vp_w, vp_h)

    def handle_context_menu_mouse_move(self, x: float, y: float) -> bool:
        if not self.context_menu_open:
            return False
        editor = self._editor
        if editor is None:
            return False
        mx, my = self._context_menu_position(editor)
        local_x = x - mx
        local_y = y - my
        idx = hit_test_menu_item(local_x, local_y, len(self.context_menu_items))
        if idx is None:
            self.context_menu_hover_index = None
        else:
            self.context_menu_hover_index = idx
        return True

    def handle_context_menu_mouse_press(
        self,
        x: float,
        y: float,
        button: int,
        editor: "EditorModeController",
    ) -> bool:
        if not self.context_menu_open:
            return False
        mx, my = self._context_menu_position(editor)
        w, h = self.context_menu_width, self.context_menu_height
        if not (mx <= x <= mx + w and my <= y <= my + h):
            self.close_context_menu(editor)
            return True
        if button == 1:
            if self.context_menu_hover_index is not None:
                self.context_menu_index = clamp_menu_index(
                    self.context_menu_hover_index, self.context_menu_items
                )
                item = self.context_menu_items[self.context_menu_index]
                if item.kind == "action" and item.enabled:
                    self.context_menu_last_action_id = item.action_id
                self.activate_context_menu_item(editor)
        return True

    def get_context_menu_payload(self) -> dict[str, Any]:
        window = getattr(getattr(self, "_editor", None), "window", None)
        vp_w = int(getattr(window, "width", 1280) or 1280)
        vp_h = int(getattr(window, "height", 720) or 720)
        ax, ay = self.context_menu_anchor
        return {
            "open": self.context_menu_open,
            "items": list(self.context_menu_items),
            "index": self.context_menu_index,
            "hover_index": self.context_menu_hover_index,
            "anchor_x": ax,
            "anchor_y": ay,
            "preferred_width": self.context_menu_width,
            "row_height": CONTEXT_MENU_ITEM_HEIGHT,
            "height": self.context_menu_height,
            "viewport_w": vp_w,
            "viewport_h": vp_h,
        }

    def apply_post_move_selection(
        self,
        old_paths: list[str],
        new_paths: list[str],
        primary_old: str | None,
    ) -> None:
        if not new_paths:
            return
        mapping = {
            old: new
            for old, new in zip(old_paths, new_paths)
            if old and new
        }
        primary_new = mapping.get(primary_old or "") if primary_old else None
        ordered_new = sorted(set(p for p in new_paths if p))
        if not ordered_new:
            return
        primary_target = primary_new or ordered_new[0]
        self.ensure_rows()
        index_by_path: dict[str, int] = {}
        for idx, row in enumerate(self.selectable_rows):
            entry = getattr(row, "entry", None)
            if entry is None:
                continue
            path = str(getattr(entry, "rel_path", ""))
            if path:
                index_by_path[path] = idx
        selected_indices = {index_by_path[p] for p in ordered_new if p in index_by_path}
        if not selected_indices:
            return
        primary_idx = index_by_path.get(primary_target, min(selected_indices))
        next_state = SelectionState(
            primary_index=primary_idx,
            selected_indices=frozenset(selected_indices),
            anchor_index=primary_idx,
        )
        next_state = self._clamp_selection_state(next_state, len(self.selectable_rows))
        self._apply_selection_state(next_state)

    def handle_click(self, index: int, *, ctrl: bool = False, shift: bool = False) -> None:
        length = len(self.selectable_rows)
        if length <= 0:
            return
        index = clamp_selection_on_selectables(index, length)
        if shift:
            next_state = select_range(self.selection_state, index)
        elif ctrl:
            next_state = toggle_index(self.selection_state, index)
        else:
            next_state = select_single(self.selection_state, index)
        next_state = self._clamp_selection_state(next_state, length)
        self._apply_selection_state(next_state)

    def _apply_selection_state(self, state: SelectionState) -> None:
        self.selection_state = state
        if self.inline_rename_state is not None and len(state.selected_indices) > 1:
            self.inline_rename_state = None

    def _set_selection_single(self, index: int) -> None:
        length = len(self.selectable_rows)
        if length <= 0:
            self.selection_state = SelectionState(primary_index=0, selected_indices=frozenset(), anchor_index=None)
            return
        index = clamp_selection_on_selectables(index, length)
        self._apply_selection_state(select_single(self.selection_state, index))

    @staticmethod
    def _clamp_selection_state(state: SelectionState, length: int) -> SelectionState:
        if length <= 0:
            return SelectionState(primary_index=0, selected_indices=frozenset(), anchor_index=None)
        if not state.selected_indices and state.primary_index < 0:
            anchor = state.anchor_index
            if anchor is not None and (anchor < 0 or anchor >= length):
                anchor = None
            return SelectionState(primary_index=-1, selected_indices=frozenset(), anchor_index=anchor)
        primary = clamp_selection_on_selectables(state.primary_index, length)
        selected = {i for i in state.selected_indices if 0 <= i < length}
        if not selected:
            selected = {primary}
        if primary not in selected:
            selected.add(primary)
        anchor = state.anchor_index
        if anchor is not None and (anchor < 0 or anchor >= length):
            anchor = None
        return SelectionState(primary_index=primary, selected_indices=frozenset(selected), anchor_index=anchor)

    # -------------------------------------------------------------------------
    # Inline Rename Methods
    # -------------------------------------------------------------------------
    
    @property
    def inline_rename_active(self) -> bool:
        """Check if inline rename mode is active."""
        return self.inline_rename_state is not None

    def begin_inline_rename(self, path: str) -> bool:
        """Begin inline rename for the given path.
        
        Args:
            path: The relative path to rename.
            
        Returns:
            True if rename mode was started, False if path is not renameable.
        """
        if len(self.selection_state.selected_indices) > 1:
            return False

        is_dir = False
        selected_row = self.get_selected_row()
        if selected_row and selected_row.entry:
            is_dir = getattr(selected_row.entry, "is_dir", False)
        
        state = create_inline_rename_state(path, is_dir=is_dir)
        if state is None:
            return False
        self.inline_rename_state = state
        return True


    def cancel_inline_rename(self) -> None:
        """Cancel inline rename mode without committing."""
        self.inline_rename_state = None

    def get_inline_rename_commit_result(self) -> tuple[bool, Optional[str], Optional[str]]:
        """Check if rename should be committed and get the new name.
        
        Returns:
            Tuple of (should_commit, new_name, error_message).
            If should_commit is True, new_name is the final filename.
            If should_commit is False, error_message explains why (or None if just no change).
        """
        if self.inline_rename_state is None:
            return (False, None, None)
        
        state = self.inline_rename_state
        should_commit, normalized_name, error = should_commit_rename(
            state.original_stem,
            state.current_text,
            state.original_ext,
            is_dir=state.is_dir,
        )
        
        if should_commit and normalized_name:
            return (True, normalized_name, None)
        return (False, None, error)

    def commit_inline_rename(self) -> tuple[bool, Optional[str]]:
        """Commit the inline rename and return the new name.
        
        This method checks validity and returns the new name if valid.
        The actual file rename is handled by the caller (EditorFileOpsController).
        
        Returns:
            Tuple of (success, new_name). If success is False, new_name is None.
        """
        should_commit, new_name, error = self.get_inline_rename_commit_result()
        
        if should_commit and new_name:
            # Clear state - caller will handle actual rename
            self.inline_rename_state = None
            return (True, new_name)
        else:
            # Don't clear state on error - let user continue editing
            # But if no change, just cancel
            if error is None:  # No change, not an error
                self.inline_rename_state = None
            return (False, None)

    def handle_rename_text_input(self, text: str) -> bool:
        """Handle text input during inline rename.
        
        Args:
            text: The text to append.
            
        Returns:
            True if handled, False if not in rename mode.
        """
        if self.inline_rename_state is None:
            return False
        
        if text and text.isprintable():
            self.inline_rename_state = append_rename_text(self.inline_rename_state, text)
            return True
        return False

    def handle_rename_backspace(self) -> bool:
        """Handle backspace key during inline rename.
        
        Returns:
            True if handled, False if not in rename mode.
        """
        if self.inline_rename_state is None:
            return False
        
        self.inline_rename_state = handle_rename_backspace(self.inline_rename_state)
        return True

    def handle_rename_delete(self) -> bool:
        """Handle delete key during inline rename.
        
        Returns:
            True if handled, False if not in rename mode.
        """
        if self.inline_rename_state is None:
            return False
        
        self.inline_rename_state = handle_rename_delete(self.inline_rename_state)
        return True

    def handle_rename_cursor_left(self, shift: bool = False) -> bool:
        """Handle left arrow key during inline rename.
        
        Args:
            shift: If True, extend selection.
            
        Returns:
            True if handled, False if not in rename mode.
        """
        if self.inline_rename_state is None:
            return False
        
        self.inline_rename_state = move_cursor_left(self.inline_rename_state, shift)
        return True

    def handle_rename_cursor_right(self, shift: bool = False) -> bool:
        """Handle right arrow key during inline rename.
        
        Args:
            shift: If True, extend selection.
            
        Returns:
            True if handled, False if not in rename mode.
        """
        if self.inline_rename_state is None:
            return False
        
        self.inline_rename_state = move_cursor_right(self.inline_rename_state, shift)
        return True

    def handle_rename_cursor_home(self, shift: bool = False) -> bool:
        """Handle home key during inline rename.
        
        Args:
            shift: If True, extend selection.
            
        Returns:
            True if handled, False if not in rename mode.
        """
        if self.inline_rename_state is None:
            return False
        
        self.inline_rename_state = move_cursor_home(self.inline_rename_state, shift)
        return True

    def handle_rename_cursor_end(self, shift: bool = False) -> bool:
        """Handle end key during inline rename.
        
        Args:
            shift: If True, extend selection.
            
        Returns:
            True if handled, False if not in rename mode.
        """
        if self.inline_rename_state is None:
            return False
        
        self.inline_rename_state = move_cursor_end(self.inline_rename_state, shift)
        return True

    def handle_rename_cursor_word_left(self, shift: bool = False) -> bool:
        """Handle Ctrl+Left during inline rename.

        Args:
            shift: If True, extend selection.

        Returns:
            True if handled, False if not in rename mode.
        """
        if self.inline_rename_state is None:
            return False

        self.inline_rename_state = move_cursor_word_left(self.inline_rename_state, shift)
        return True

    def handle_rename_cursor_word_right(self, shift: bool = False) -> bool:
        """Handle Ctrl+Right during inline rename.

        Args:
            shift: If True, extend selection.

        Returns:
            True if handled, False if not in rename mode.
        """
        if self.inline_rename_state is None:
            return False

        self.inline_rename_state = move_cursor_word_right(self.inline_rename_state, shift)
        return True

    def handle_rename_delete_prev_word(self) -> bool:
        """Handle Ctrl+Backspace during inline rename.

        Returns:
            True if handled, False if not in rename mode.
        """
        if self.inline_rename_state is None:
            return False

        self.inline_rename_state = delete_prev_word(self.inline_rename_state)
        return True

    def handle_rename_delete_next_word(self) -> bool:
        """Handle Ctrl+Delete during inline rename.

        Returns:
            True if handled, False if not in rename mode.
        """
        if self.inline_rename_state is None:
            return False

        self.inline_rename_state = delete_next_word(self.inline_rename_state)
        return True

    def get_rename_display_text(self) -> Optional[str]:
        """Get the display text for the rename editor (stem + extension).
        
        Returns:
            The full display text, or None if not renaming.
        """
        if self.inline_rename_state is None:
            return None
        return self.inline_rename_state.current_text + self.inline_rename_state.original_ext

    def get_rename_original_path(self) -> Optional[str]:
        """Get the original path being renamed.
        
        Returns:
            The original path, or None if not renaming.
        """
        if self.inline_rename_state is None:
            return None
        return self.inline_rename_state.original_path
        
    def reveal_path(self, target_path: str, viewport_height: int, row_height: int) -> bool:
        """Reveal a file path in the project explorer."""
        from engine.editor.project_explorer_reveal_model import (
            compute_reveal_scroll_index,
            normalize_repo_relative_path,
        )

        target_norm = normalize_repo_relative_path(target_path)
        if not target_norm:
            return False

        self.ensure_rows()
        if not self.selectable_rows:
            return False

        # Helper to extract path from row
        def get_row_path(row: ProjectExplorerDisplayRow) -> str:
            entry = row.entry
            if entry is not None:
                return str(getattr(entry, "rel_path", "") or "")
            recent = row.recent
            if recent is not None:
                return str(getattr(recent, "rel_path", "") or "")
            return ""

        visible_count = max(1, int(viewport_height / row_height))
        
        row_idx, scroll_start = compute_reveal_scroll_index(
            self.selectable_rows, target_norm, get_row_path, visible_count
        )
        
        if row_idx is None:
            return False

        self.selected_index = row_idx
        # If the model gives us a scroll target, we can use it.
        # Assuming scroll_y is in pixels, we multiply by row_height
        if scroll_start is not None:
             self.scroll_y = scroll_start * row_height
             
        return True
