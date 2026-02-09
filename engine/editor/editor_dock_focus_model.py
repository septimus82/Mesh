from __future__ import annotations

from typing import Mapping

FOCUS_PROJECT_EXPLORER = "project_explorer"
FOCUS_PROBLEMS = "problems"
FOCUS_INSPECTOR = "inspector"
FOCUS_OUTLINER = "outliner"
FOCUS_ASSETS = "assets"
FOCUS_HISTORY = "history"
FOCUS_DEBUG = "debug"
FOCUS_NONE = "none"


def derive_focus_from_dock(
    left_tab: str,
    right_tab: str,
    session_flags: Mapping[str, bool],
) -> str:
    if left_tab == "Project":
        return FOCUS_PROJECT_EXPLORER
    if left_tab == "Outliner":
        return FOCUS_OUTLINER
    if left_tab == "Assets":
        return FOCUS_ASSETS
    if left_tab == "History":
        return FOCUS_HISTORY
    if left_tab == "Problems":
        return FOCUS_PROBLEMS

    if bool(session_flags.get("project_explorer_focused", False)):
        return FOCUS_PROJECT_EXPLORER

    if right_tab == "Inspector":
        return FOCUS_INSPECTOR
    if right_tab == "History":
        return FOCUS_HISTORY
    if right_tab == "Problems":
        return FOCUS_PROBLEMS
    if right_tab == "Debug":
        return FOCUS_DEBUG

    return FOCUS_NONE
