"""Contract tests for debug panel focus and input routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from engine import optional_arcade
from engine.editor.editor_debug_panels_controller import EditorDebugPanelsController
from engine.editor_runtime import input as editor_input
from engine.workspace_settings import WorkspaceSettings
from tests._dock_stub import make_dock_stub
from tests._search_stub import attach_search_stub
from tests._session_stub import make_session_stub


class PanelsStub:
    def __init__(self) -> None:
        self._command_palette_open = False

    def dispatch_input(self, _key: int, _modifiers: int) -> bool:
        return False

    def toggle_command_palette(self) -> bool:
        self._command_palette_open = not self._command_palette_open
        return self._command_palette_open

    def is_command_palette_open(self) -> bool:
        return self._command_palette_open


@dataclass
class StubController:
    active: bool = True
    dock: object = field(default_factory=lambda: make_dock_stub(right_tab="Debug"))
    session: object = field(default_factory=make_session_stub)
    panels: PanelsStub = field(default_factory=PanelsStub)
    workspace_data: WorkspaceSettings = field(default_factory=WorkspaceSettings)
    search: object | None = None
    debug_panels: EditorDebugPanelsController | None = None
    entity_panels_active: bool = False
    asset_browser_active: bool = False
    entity_panels_filter_active: bool = False
    _alt_dup_active: bool = False
    _marquee_active: bool = False
    _find_everything_open: bool = False
    _inspector_text_edit_active: bool = False
    dialogue_panel_active: bool = False
    dialogue_editing: bool = False
    animation_active: bool = False
    animation_editing: bool = False
    palette_active: bool = False
    palette_filter_active: bool = False
    hierarchy_active: bool = False
    hierarchy_rename_active: bool = False
    hierarchy_filter_active: bool = False
    unsaved_confirm: object = field(default_factory=lambda: SimpleNamespace(is_open=False))

    def __post_init__(self) -> None:
        self.search = attach_search_stub(self)
        self.debug_panels = EditorDebugPanelsController(self)

    def _autosave_workspace(self) -> None:
        return


def test_debug_focus_clears_on_tab_switch() -> None:
    controller = StubController()
    assert controller.search.focus_search_for_active_panel() is True
    assert controller.search.get_search_focus() == "debug"
    assert controller.debug_panels.get_active_filter_field() == "event_type"

    controller.dock.right_tab = "Inspector"
    controller.search.sync_search_focus()

    assert controller.search.get_search_focus() is None
    assert controller.debug_panels.get_active_filter_field() is None


def test_debug_focus_clears_on_command_palette_open() -> None:
    controller = StubController()
    assert controller.search.focus_search_for_active_panel() is True

    controller.search.toggle_command_palette()

    assert controller.panels.is_command_palette_open() is True
    assert controller.search.get_search_focus() is None
    assert controller.debug_panels.get_active_filter_field() is None


def test_debug_focus_clears_on_escape(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)

    controller = StubController()
    assert controller.search.focus_search_for_active_panel() is True

    editor_input.handle_input(controller, arcade_stub.key.ESCAPE, 0)

    assert controller.search.get_search_focus() is None
    assert controller.debug_panels.get_active_filter_field() is None


def test_debug_filters_only_update_when_focused() -> None:
    controller = StubController()
    assert controller.search.focus_search_for_active_panel() is True

    editor_input.handle_text_input(controller, "a")
    assert controller.workspace_data.debug_event_type_filter == "a"

    controller.search.clear_search_focus()
    editor_input.handle_text_input(controller, "b")
    assert controller.workspace_data.debug_event_type_filter == "a"
