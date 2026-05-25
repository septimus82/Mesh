from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.editor.editor_dock_query import get_effective_dock_widths
from engine.editor.editor_shell_layout import TAB_HEADER_HEIGHT, compute_editor_shell_layout
from engine.editor.project_explorer.project_explorer_model import (
    format_project_action_label,
    format_project_recent_label,
    format_project_row_label,
)
from engine.ui_overlays.entity_panels_overlay import EntityPanelsOverlay
from engine.ui_overlays.project_explorer_overlay import (
    ProjectExplorerOverlay,
    _build_project_explorer_scrolllist,
)
from engine.ui_overlays.widgets import Rect
from tests._dock_stub import DockStub


pytestmark = pytest.mark.fast


def _window_for_entity_panels(
    *,
    width: int = 1280,
    height: int = 720,
    left_tab: str = "Outliner",
    right_tab: str = "Inspector",
    left_w: int = 320,
    right_w: int = 320,
) -> SimpleNamespace:
    dock = DockStub(left_tab=left_tab, right_tab=right_tab, left_w=left_w, right_w=right_w)
    inspector_lines = lambda: (_ for _ in ()).throw(AssertionError("legacy inspector path called"))
    controller = SimpleNamespace(
        active=True,
        entity_panels_active=True,
        dock=dock,
        _entity_panels_outliner_lines=lambda: ["OUTLINER", "> entity_1"],
        _entity_panels_inspector_lines=inspector_lines,
    )
    return SimpleNamespace(width=width, height=height, editor_controller=controller)


def test_entity_panels_overlay_does_not_draw_right_inspector_without_outliner(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _window_for_entity_panels(left_tab="Project", right_tab="Inspector")
    overlay = EntityPanelsOverlay(window)
    calls: list[tuple[list[str], float, float, float]] = []
    monkeypatch.setattr(overlay, "_draw_outliner_panel", lambda *args: calls.append(args))

    overlay.draw()

    assert calls == []


@pytest.mark.parametrize(
    ("width", "height", "left_w", "right_w"),
    [
        (1280, 720, 320, 320),
        (1600, 900, 420, 300),
        (1024, 768, 260, 280),
    ],
)
def test_entity_panels_overlay_outliner_uses_left_dock_bounds(
    monkeypatch: pytest.MonkeyPatch,
    width: int,
    height: int,
    left_w: int,
    right_w: int,
) -> None:
    window = _window_for_entity_panels(width=width, height=height, left_w=left_w, right_w=right_w)
    overlay = EntityPanelsOverlay(window)
    calls: list[tuple[list[str], float, float, float]] = []
    monkeypatch.setattr(overlay, "_draw_outliner_panel", lambda *args: calls.append(args))

    overlay.draw()

    controller = window.editor_controller
    effective_left_w, effective_right_w = get_effective_dock_widths(controller, width)
    expected_dock = compute_editor_shell_layout(width, height, effective_left_w, effective_right_w).left_dock
    assert len(calls) == 1
    lines, start_x, start_y, panel_width = calls[0]
    assert lines == ["OUTLINER", "> entity_1"]
    assert start_x == pytest.approx(expected_dock.left + 8.0)
    assert start_y == pytest.approx(expected_dock.top - TAB_HEADER_HEIGHT - 8.0)
    assert panel_width == pytest.approx(expected_dock.width - 16.0)


def test_project_explorer_row_list_imports_project_line_height(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.editor.widgets import panel_primitives

    class DummyPanel:
        def __init__(self, *_args, **_kwargs) -> None:
            return

        def add_row(self, row: object) -> object:
            return row

        def draw(self) -> None:
            return

    monkeypatch.setattr(panel_primitives, "EditorPanelBase", DummyPanel)
    row = SimpleNamespace(kind="header", header="PROJECT", entry=None, recent=None, enabled=True)
    panel_rect = Rect(x=8.0, y=20.0, width=240.0, height=80.0)
    formatter_args = {
        "format_project_action_label": format_project_action_label,
        "format_project_recent_label": format_project_recent_label,
        "format_project_row_label": format_project_row_label,
    }
    scroll_list = _build_project_explorer_scrolllist(
        rows=[row],
        panel_list_rect=panel_rect,
        row_height=18.0,
        start_index=0,
        scroll_y=0.0,
        selected_row_id=None,
        **formatter_args,
    )
    overlay = ProjectExplorerOverlay(SimpleNamespace())

    overlay._draw_project_explorer_row_list(
        rows=[row],
        scroll_list=scroll_list,
        panel_list_rect=panel_rect,
        selected_row_id=None,
        selected_row_ids=set(),
        has_multi=False,
        rename_active=False,
        rename_path=None,
        rename_text="",
        rename_cursor=0,
        rename_sel_start=0,
        rename_sel_end=0,
        **formatter_args,
    )
