"""Camera and view related editor actions."""

from __future__ import annotations

from typing import Any, Callable

GetEditorFn = Callable[[Any], Any | None]
GetDockSnapshotFn = Callable[[Any], Any]
SetDockTabFn = Callable[[Any, str, str], None]
ToggleDockTabFn = Callable[[Any, str, str], None]


def _set_dock_tab(window: Any, dock: str, tab: str, get_editor: GetEditorFn) -> None:
    editor = get_editor(window)
    dock_ctl = getattr(editor, "dock", None) if editor is not None else None
    setter = getattr(dock_ctl, "apply_tab_change", None) if dock_ctl is not None else None
    if callable(setter):
        setter(editor, dock, tab)


def _toggle_dock_tab(
    window: Any,
    dock: str,
    tab: str,
    get_editor: GetEditorFn,
    get_dock_snapshot: GetDockSnapshotFn,
    set_dock_tab: SetDockTabFn,
) -> None:
    editor = get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    if dock == "left":
        snapshot = get_dock_snapshot(editor)
        dock_ctl = getattr(editor, "dock", None)
        if snapshot is not None and snapshot.left_tab == tab and dock_ctl is not None:
            getter = getattr(dock_ctl, "get_left_collapsed", None)
            toggler = getattr(dock_ctl, "toggle_left_dock", None)
            if callable(getter) and callable(toggler) and not getter():
                toggler(editor)
                return
    elif dock == "right":
        snapshot = get_dock_snapshot(editor)
        dock_ctl = getattr(editor, "dock", None)
        if snapshot is not None and snapshot.right_tab == tab and dock_ctl is not None:
            getter = getattr(dock_ctl, "get_right_collapsed", None)
            toggler = getattr(dock_ctl, "toggle_right_dock", None)
            if callable(getter) and callable(toggler) and not getter():
                toggler(editor)
                return
    set_dock_tab(window, dock, tab)


def _toggle_inspector_panel(window: Any, toggle_dock_tab: ToggleDockTabFn) -> None:
    toggle_dock_tab(window, "right", "Inspector")


def _toggle_outliner_panel(window: Any, toggle_dock_tab: ToggleDockTabFn) -> None:
    toggle_dock_tab(window, "left", "Outliner")


def _toggle_history_panel(window: Any, toggle_dock_tab: ToggleDockTabFn) -> None:
    toggle_dock_tab(window, "right", "History")


def _toggle_problems_panel(window: Any, toggle_dock_tab: ToggleDockTabFn) -> None:
    toggle_dock_tab(window, "right", "Problems")


def _toggle_debug_panel(window: Any, toggle_dock_tab: ToggleDockTabFn) -> None:
    toggle_dock_tab(window, "right", "Debug")


def _toggle_project_explorer_panel(window: Any, toggle_dock_tab: ToggleDockTabFn) -> None:
    toggle_dock_tab(window, "left", "Project")


def _toggle_left_dock(window: Any, get_editor: GetEditorFn) -> None:
    editor = get_editor(window)
    dock_ctl = getattr(editor, "dock", None) if editor is not None else None
    toggler = getattr(dock_ctl, "toggle_left_dock", None) if dock_ctl is not None else None
    if callable(toggler):
        toggler(editor)


def _toggle_right_dock(window: Any, get_editor: GetEditorFn) -> None:
    editor = get_editor(window)
    dock_ctl = getattr(editor, "dock", None) if editor is not None else None
    toggler = getattr(dock_ctl, "toggle_right_dock", None) if dock_ctl is not None else None
    if callable(toggler):
        toggler(editor)


def _toggle_viewport_maximized(window: Any, get_editor: GetEditorFn) -> None:
    editor = get_editor(window)
    toggler = getattr(editor, "toggle_viewport_maximized", None) if editor is not None else None
    if callable(toggler):
        toggler()
