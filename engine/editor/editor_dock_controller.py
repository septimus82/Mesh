from __future__ import annotations

import logging
from typing import Any

from engine.editor.editor_dock_model import (
    LEFT_DOCK_TABS,
    RIGHT_DOCK_TABS,
    DockInputs,
    DockStateSnapshot,
    build_dock_snapshot,
    should_focus_problems_panel,
    should_focus_project_explorer,
)
from engine.editor.editor_shell_layout import DOCK_WIDTH
from engine.swallowed_exceptions import _log_swallow


class EditorDockController:
    def __init__(
        self,
        session: Any | None,
        left_tab: str = "Outliner",
        right_tab: str = "Inspector",
        left_w: int | None = None,
        right_w: int | None = None,
        left_collapsed: bool = False,
        right_collapsed: bool = False,
        viewport_maximized: bool = False,
    ) -> None:
        self._session = session
        self._left_tab = str(left_tab)
        self._right_tab = str(right_tab)
        self._left_w = int(DOCK_WIDTH if left_w is None else left_w)
        self._right_w = int(DOCK_WIDTH if right_w is None else right_w)
        self._left_collapsed = bool(left_collapsed)
        self._right_collapsed = bool(right_collapsed)
        self._prev_left_collapsed = bool(left_collapsed)
        self._prev_right_collapsed = bool(right_collapsed)
        self._viewport_maximized = bool(viewport_maximized)
        self._drag_active: str | None = None
        self._drag_start_x = 0.0
        self._drag_start_w = 0
        self._hover_tab: tuple[str, str] | None = None
        self._hover_tab_rect: tuple[float, float, float, float] | None = None
        self._rev = 0
        self._snapshot: DockStateSnapshot | None = None
        self._sync_session_focus()

    @property
    def left_tab(self) -> str:
        return self._left_tab

    @property
    def right_tab(self) -> str:
        return self._right_tab

    def get_snapshot(self) -> DockStateSnapshot:
        if self._snapshot is None:
            inputs = DockInputs(
                left_tab=self._left_tab,
                right_tab=self._right_tab,
                rev=self._rev,
            )
            self._snapshot = build_dock_snapshot(inputs)
        return self._snapshot

    def set_left_tab(self, tab: str, *, force: bool = False) -> bool:
        if not force and tab not in LEFT_DOCK_TABS:
            return False
        if not force and tab == self._left_tab:
            return False
        self._left_tab = str(tab)
        self._invalidate()
        self._sync_session_focus()
        return True

    def set_right_tab(self, tab: str, *, force: bool = False) -> bool:
        if not force and tab not in RIGHT_DOCK_TABS:
            return False
        if not force and tab == self._right_tab:
            return False
        self._right_tab = str(tab)
        self._invalidate()
        self._sync_session_focus()
        return True

    def set_active_tab(self, dock: str, tab: str, *, force: bool = False) -> bool:
        if dock == "left":
            return self.set_left_tab(tab, force=force)
        if dock == "right":
            return self.set_right_tab(tab, force=force)
        return False

    def get_left_width(self) -> int:
        return self._left_w

    def set_left_width(self, value: int) -> None:
        self._left_w = int(value)

    def get_right_width(self) -> int:
        return self._right_w

    def set_right_width(self, value: int) -> None:
        self._right_w = int(value)

    def get_left_collapsed(self) -> bool:
        return self._left_collapsed

    def set_left_collapsed(self, value: bool) -> None:
        self._left_collapsed = bool(value)

    def get_right_collapsed(self) -> bool:
        return self._right_collapsed

    def set_right_collapsed(self, value: bool) -> None:
        self._right_collapsed = bool(value)

    def get_prev_left_collapsed(self) -> bool:
        return self._prev_left_collapsed

    def set_prev_left_collapsed(self, value: bool) -> None:
        self._prev_left_collapsed = bool(value)

    def get_prev_right_collapsed(self) -> bool:
        return self._prev_right_collapsed

    def set_prev_right_collapsed(self, value: bool) -> None:
        self._prev_right_collapsed = bool(value)

    def get_viewport_maximized(self) -> bool:
        return self._viewport_maximized

    def set_viewport_maximized(self, value: bool) -> None:
        self._viewport_maximized = bool(value)

    def get_drag_active(self) -> str | None:
        return self._drag_active

    def set_drag_active(self, value: str | None) -> None:
        self._drag_active = value

    def set_hover_tab(
        self,
        dock: str | None,
        tab: str | None,
        rect: tuple[float, float, float, float] | None,
    ) -> None:
        if dock is not None and tab is not None:
            self._hover_tab = (dock, tab)
            self._hover_tab_rect = rect
        else:
            self._hover_tab = None
            self._hover_tab_rect = None

    def get_hover_tab(self) -> tuple[str, str] | None:
        return self._hover_tab

    def get_hover_tab_rect(self) -> tuple[float, float, float, float] | None:
        return self._hover_tab_rect

    def begin_drag(self, host: Any, which: str, mouse_x: float) -> bool:
        if not getattr(host, "active", False):
            return False
        if which not in ("left", "right"):
            return False

        self._drag_active = which
        self._drag_start_x = float(mouse_x)
        self._drag_start_w = self._left_w if which == "left" else self._right_w

        if hasattr(host, "_menu_active"):
            host._menu_active = None
        panels = getattr(host, "panels", None)
        if panels is not None:
            close_ctx = getattr(panels, "close_context_menu", None)
            if callable(close_ctx):
                close_ctx()

        logger = logging.getLogger(__name__)
        logger.info("[Editor] Begin dock drag: %s", which)
        return True

    def update_drag(self, host: Any, mouse_x: float, window_width: int) -> bool:
        if self._drag_active is None:
            return False

        from engine.editor.editor_shell_layout import clamp_dock_width  # noqa: PLC0415

        delta = float(mouse_x) - self._drag_start_x
        if self._drag_active == "left":
            new_w = int(self._drag_start_w + delta)
            clamped = clamp_dock_width(new_w, window_width, self._right_w)
            if clamped != self._left_w:
                self._left_w = clamped
                return True
        else:
            new_w = int(self._drag_start_w - delta)
            clamped = clamp_dock_width(new_w, window_width, self._left_w)
            if clamped != self._right_w:
                self._right_w = clamped
                return True

        return False

    def end_drag(self, host: Any) -> bool:
        if self._drag_active is None:
            return False

        logger = logging.getLogger(__name__)
        logger.info("[Editor] End dock drag: %s, left_w=%d, right_w=%d",
                    self._drag_active, self._left_w, self._right_w)

        self._drag_active = None
        self._drag_start_x = 0.0
        self._drag_start_w = 0

        autosave = getattr(host, "_autosave_workspace", None)
        if callable(autosave):
            autosave()
        return True

    def toggle_left_dock(self, host: Any) -> None:
        if self._viewport_maximized:
            return
        self._left_collapsed = not self._left_collapsed
        autosave = getattr(host, "_autosave_workspace", None)
        if callable(autosave):
            autosave()
        try:
            from engine.editor.editor_ui_state import save_editor_ui_state_for_editor  # noqa: PLC0415

            save_editor_ui_state_for_editor(host)
        except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
            _log_swallow("EDIT-001", "engine/editor/editor_dock_controller.py pass-only blanket swallow")
            pass

    def toggle_right_dock(self, host: Any) -> None:
        if self._viewport_maximized:
            return
        self._right_collapsed = not self._right_collapsed
        autosave = getattr(host, "_autosave_workspace", None)
        if callable(autosave):
            autosave()
        try:
            from engine.editor.editor_ui_state import save_editor_ui_state_for_editor  # noqa: PLC0415

            save_editor_ui_state_for_editor(host)
        except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
            _log_swallow("EDIT-002", "engine/editor/editor_dock_controller.py pass-only blanket swallow")
            pass

    def toggle_viewport_maximized(self, host: Any) -> None:
        if self._viewport_maximized:
            self._viewport_maximized = False
            self._left_collapsed = self._prev_left_collapsed
            self._right_collapsed = self._prev_right_collapsed
        else:
            self._prev_left_collapsed = self._left_collapsed
            self._prev_right_collapsed = self._right_collapsed
            self._viewport_maximized = True
        autosave = getattr(host, "_autosave_workspace", None)
        if callable(autosave):
            autosave()
        try:
            from engine.editor.editor_ui_state import save_editor_ui_state_for_editor  # noqa: PLC0415

            save_editor_ui_state_for_editor(host)
        except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
            _log_swallow("EDIT-003", "engine/editor/editor_dock_controller.py pass-only blanket swallow")
            pass

    def get_effective_dock_widths(self, window_w: int) -> tuple[int, int]:
        from engine.editor.editor_shell_layout import resolve_effective_dock_widths  # noqa: PLC0415

        return resolve_effective_dock_widths(
            left_collapsed=self._left_collapsed,
            right_collapsed=self._right_collapsed,
            viewport_maximized=self._viewport_maximized,
            left_w=self._left_w,
            right_w=self._right_w,
            window_width=window_w,
        )

    def apply_tab_change(self, host: Any, dock: str, tab: str) -> bool:
        if not getattr(host, "active", False):
            return False

        # Close any open menus/context menus
        if hasattr(host, "_menu_active"):
            host._menu_active = None
        panels = getattr(host, "panels", None)
        if panels is not None:
            close_ctx = getattr(panels, "close_context_menu", None)
            if callable(close_ctx):
                close_ctx()

        if dock == "left":
            if tab not in LEFT_DOCK_TABS:
                return False
            if not self.set_left_tab(tab):
                return False

            if tab == "Project":
                host.scene_browser_active = False
                host.entity_panels_active = False
                refresh_rows = getattr(host, "_refresh_project_explorer_rows", None)
                if callable(refresh_rows):
                    refresh_rows()
            elif tab == "Scene":
                host.scene_browser_active = True
            elif tab == "Outliner":
                host.entity_panels_active = True
                host.entity_panels_focus = getattr(host, "ENTITY_PANEL_FOCUS_OUTLINER", "outliner")
                host._entity_panels_selected_id = host._entity_panels_selected_id_value()
                refresh = getattr(host, "_refresh_entity_panels_list", None)
                if callable(refresh):
                    refresh(sync_selected=True)

            logger = logging.getLogger(__name__)
            logger.info("[Editor] Left dock tab switched to %s", tab)
            search = getattr(host, "search", None)
            sync_focus = getattr(search, "sync_search_focus", None) if search is not None else None
            if callable(sync_focus):
                sync_focus()
            autosave = getattr(host, "_autosave_workspace", None)
            if callable(autosave):
                autosave()
            try:
                from engine.editor.editor_ui_state import save_editor_ui_state_for_editor  # noqa: PLC0415

                save_editor_ui_state_for_editor(host)
            except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
                _log_swallow("EDIT-004", "engine/editor/editor_dock_controller.py pass-only blanket swallow")
                pass
            return True

        if dock == "right":
            if tab not in RIGHT_DOCK_TABS:
                return False
            if not self.set_right_tab(tab):
                return False
            if tab != "Problems":
                problems = getattr(host, "problems", None)
                if problems is not None:
                    closer = getattr(problems, "close_preview", None)
                    if callable(closer):
                        closer(host)
                    else:
                        try:
                            problems.preview_open = False
                        except Exception:
                            _log_swallow("EDIT-005", "engine/editor/editor_dock_controller.py pass-only blanket swallow")
                            pass

            if tab == "Inspector":
                host.entity_panels_active = True
                host.entity_panels_focus = getattr(host, "ENTITY_PANEL_FOCUS_INSPECTOR", "inspector")
            elif tab == "Assets":
                host.asset_browser_active = True
                refresh_assets = getattr(host, "refresh_asset_browser", None)
                if callable(refresh_assets):
                    refresh_assets()
            elif tab == "History":
                history = getattr(host, "history", None)
                if history is not None and hasattr(history, "on_open_tab"):
                    history.on_open_tab()
            elif tab == "Problems":
                if not getattr(host, "_problems_issues", []):
                    host.scan_scene_problems()
                problems = getattr(host, "problems", None)
                if problems is not None:
                    refresher = getattr(problems, "refresh_structured_diagnostics", None)
                    if callable(refresher):
                        refresher()
                    seen = getattr(problems, "mark_diagnostics_seen", None)
                    if callable(seen):
                        seen()

            logger = logging.getLogger(__name__)
            logger.info("[Editor] Right dock tab switched to %s", tab)
            search = getattr(host, "search", None)
            sync_focus = getattr(search, "sync_search_focus", None) if search is not None else None
            if callable(sync_focus):
                sync_focus()
            autosave = getattr(host, "_autosave_workspace", None)
            if callable(autosave):
                autosave()
            try:
                from engine.editor.editor_ui_state import save_editor_ui_state_for_editor  # noqa: PLC0415

                save_editor_ui_state_for_editor(host)
            except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
                _log_swallow("EDIT-006", "engine/editor/editor_dock_controller.py pass-only blanket swallow")
                pass
            return True

        return False

    def _invalidate(self) -> None:
        self._rev += 1
        self._snapshot = None

    def _sync_session_focus(self) -> None:
        if self._session is None:
            return
        project_focus = should_focus_project_explorer(self._left_tab)
        problems_focus = should_focus_problems_panel(self._right_tab)
        setter = getattr(self._session, "set_project_explorer_focused", None)
        if callable(setter):
            setter(project_focus)
        setter = getattr(self._session, "set_problems_panel_focused", None)
        if callable(setter):
            setter(problems_focus)
