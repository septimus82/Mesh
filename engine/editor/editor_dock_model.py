from __future__ import annotations

from dataclasses import dataclass

from engine.editor.dock_tab_registry import LEFT_DOCK_TABS, RIGHT_DOCK_TABS


@dataclass(frozen=True, slots=True)
class DockInputs:
    left_tab: str
    right_tab: str
    rev: int


@dataclass(frozen=True, slots=True)
class DockStateSnapshot:
    left_tab: str
    right_tab: str
    rev: int


def build_dock_snapshot(inputs: DockInputs) -> DockStateSnapshot:
    return DockStateSnapshot(
        left_tab=str(inputs.left_tab),
        right_tab=str(inputs.right_tab),
        rev=int(inputs.rev),
    )


def should_focus_project_explorer(left_tab: str) -> bool:
    return left_tab == "Project"


def should_focus_problems_panel(right_tab: str) -> bool:
    return right_tab == "Problems"


def compute_active_panel(dock: str, left_tab: str, right_tab: str) -> str:
    if dock == "left":
        return left_tab
    if dock == "right":
        return right_tab
    return ""
