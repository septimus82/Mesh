"""Contract tests for debug panels click-to-select behavior."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from engine import optional_arcade
from engine.gameplay_event_bus import GameplayEventBus
from engine.workspace_settings import WorkspaceSettings
from engine.editor.editor_debug_panels_controller import EditorDebugPanelsController
from engine.editor.editor_shell_layout import compute_editor_shell_layout
from engine.editor.debug_panels_model import (
    DEBUG_PANEL_LINE_HEIGHT,
    DEBUG_PANEL_PADDING,
    compute_debug_panel_content_bounds,
)
from tests._dock_stub import make_dock_stub
from tests._search_stub import attach_search_stub
from tests._session_stub import make_session_stub


@dataclass
class StubWindow:
    gameplay_event_bus: GameplayEventBus
    width: int = 1280
    height: int = 720


class StubController:
    def __init__(self, bus: GameplayEventBus) -> None:
        self.active = True
        self.window = StubWindow(bus)
        self.dock = make_dock_stub(right_tab="Debug")
        self.search = attach_search_stub(self)
        self.session = make_session_stub()
        self.workspace_data = WorkspaceSettings()
        self.debug_panels = EditorDebugPanelsController(self)
        self._unsaved_changes_pending = False
        self.scene_browser_active = False
        self.palette_filter_active = False
        self.hierarchy_filter_active = False
        self.hierarchy_rename_active = False
        self.animation_edit_active = False
        self.inspector_edit_active = False
        self.entity_panels_filter_active = False
        self.scene_browser_filter_active = False
        self.asset_browser_filter_active = False
        self.unsaved_confirm = SimpleNamespace(is_open=False)

    def _autosave_workspace(self) -> None:
        return

    def get_effective_dock_widths(self, window_w: int):
        return self.dock.get_effective_dock_widths(window_w)


def test_click_event_row_dispatches_select_action(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)

    bus = GameplayEventBus()
    bus.emit("alpha", source_entity="hero_123", source_behaviour="Test")
    bus.drain()

    controller = StubController(bus)

    lines = controller.debug_panels.build_visible_lines(controller.window.width, controller.window.height)
    target_index = next(
        idx for idx, line in enumerate(lines) if line.source_entity == "hero_123"
    )

    left_w, right_w = controller.dock.get_effective_dock_widths(controller.window.width)
    layout = compute_editor_shell_layout(
        controller.window.width,
        controller.window.height,
        left_w,
        right_w,
    )
    dock = layout.right_dock
    content_top, _content_bottom, _max_lines = compute_debug_panel_content_bounds(dock)

    x = dock.left + DEBUG_PANEL_PADDING + 4
    y = content_top - (target_index * DEBUG_PANEL_LINE_HEIGHT) - (DEBUG_PANEL_LINE_HEIGHT / 2)

    called: dict[str, str] = {}

    def _run_editor_action(action_id: str) -> bool:
        called["action"] = action_id
        return True

    controller.run_editor_action = _run_editor_action  # type: ignore[assignment]

    handled = controller.debug_panels.handle_mouse_click(x, y, arcade_stub.MOUSE_BUTTON_LEFT)
    assert handled is True
    assert called.get("action") == "editor.debug.event.select_entity"
    assert controller.debug_panels.consume_pending_select_entity_id() == "hero_123"


def test_click_event_row_without_source_entity_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)

    bus = GameplayEventBus()
    bus.emit("alpha")
    bus.drain()

    controller = StubController(bus)

    lines = controller.debug_panels.build_visible_lines(controller.window.width, controller.window.height)
    target_index = next(
        idx for idx, line in enumerate(lines) if line.kind == "event" and line.source_entity is None
    )

    left_w, right_w = controller.dock.get_effective_dock_widths(controller.window.width)
    layout = compute_editor_shell_layout(
        controller.window.width,
        controller.window.height,
        left_w,
        right_w,
    )
    dock = layout.right_dock
    content_top, _content_bottom, _max_lines = compute_debug_panel_content_bounds(dock)

    x = dock.left + DEBUG_PANEL_PADDING + 4
    y = content_top - (target_index * DEBUG_PANEL_LINE_HEIGHT) - (DEBUG_PANEL_LINE_HEIGHT / 2)

    called: dict[str, str] = {}

    def _run_editor_action(action_id: str) -> bool:
        called["action"] = action_id
        return True

    controller.run_editor_action = _run_editor_action  # type: ignore[assignment]

    handled = controller.debug_panels.handle_mouse_click(x, y, arcade_stub.MOUSE_BUTTON_LEFT)
    assert handled is True
    assert called == {}
    assert controller.debug_panels.consume_pending_select_entity_id() == ""
