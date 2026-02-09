from __future__ import annotations

from engine.editor.editor_dock_model import (
    DockInputs,
    build_dock_snapshot,
    compute_active_panel,
    should_focus_project_explorer,
    should_focus_problems_panel,
)


def test_dock_snapshot_deterministic() -> None:
    inputs = DockInputs(left_tab="Outliner", right_tab="Inspector", rev=3)
    snap_a = build_dock_snapshot(inputs)
    snap_b = build_dock_snapshot(inputs)
    assert snap_a == snap_b


def test_focus_helpers() -> None:
    assert should_focus_project_explorer("Project") is True
    assert should_focus_project_explorer("Outliner") is False
    assert should_focus_problems_panel("Problems") is True
    assert should_focus_problems_panel("Inspector") is False


def test_compute_active_panel() -> None:
    assert compute_active_panel("left", "Scene", "Inspector") == "Scene"
    assert compute_active_panel("right", "Scene", "History") == "History"
    assert compute_active_panel("unknown", "Scene", "History") == ""
