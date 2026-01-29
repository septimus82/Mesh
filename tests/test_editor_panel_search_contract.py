"""Contract tests for editor panel search focus and filtering."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from engine import optional_arcade
from engine.asset_index import AssetRow
from engine.editor_entity_ops import EntitySummary
from engine.editor.asset_browser_panel import filter_assets_for_browser
from engine.editor.entity_panels import filter_entity_panels_items
from engine.editor.undo_history_model import (
    build_undo_history_entries,
    filter_undo_history_entries,
)
from engine.editor_runtime import input as editor_input
from engine.editor_controller import EditorModeController


@dataclass
class StubController:
    active: bool = True
    _left_dock_tab: str = "Outliner"
    _right_dock_tab: str = "Inspector"
    entity_panels_active: bool = True
    asset_browser_active: bool = False
    confirm_open: bool = False
    _menu_active: str | None = None
    _context_menu_open: bool = False
    scene_browser_active: bool = False
    scene_switcher_active: bool = False
    command_palette_active: bool = False
    dialogue_panel_active: bool = False
    dialogue_editing: bool = False
    animation_active: bool = False
    animation_editing: bool = False
    palette_active: bool = False
    palette_filter_active: bool = False
    hierarchy_active: bool = False
    hierarchy_rename_active: bool = False
    hierarchy_filter_active: bool = False
    _inspector_text_edit_active: bool = False
    _search_focus: str | None = None
    entity_panels_filter_active: bool = False
    _outliner_search: str = ""
    _assets_search: str = ""
    _history_search: str = ""
    _problems_search: str = ""
    _project_search: str = ""
    asset_browser_filter: str = ""
    _history_cursor_index: int = 0
    undo_stack: list[dict] = None  # type: ignore[assignment]
    redo_stack: list[dict] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.undo_stack is None:
            self.undo_stack = []
        if self.redo_stack is None:
            self.redo_stack = []

    def _autosave_workspace(self) -> None:
        return

    def _refresh_entity_panels_list(self, *, sync_selected: bool = False) -> None:  # noqa: ARG002
        return

    def set_asset_browser_filter(self, text: str) -> None:
        self._assets_search = text
        self.asset_browser_filter = text

    def focus_search_for_active_panel(self) -> bool:
        return EditorModeController.focus_search_for_active_panel(self)

    def clear_search_for_active_panel(self) -> bool:
        return EditorModeController.clear_search_for_active_panel(self)

    def clear_search_focus(self) -> None:
        EditorModeController.clear_search_focus(self)

    def is_search_focused(self) -> bool:
        return EditorModeController.is_search_focused(self)

    def append_search_text(self, text: str) -> bool:
        return EditorModeController.append_search_text(self, text)

    def backspace_search_text(self) -> bool:
        return EditorModeController.backspace_search_text(self)

    def _resolve_active_search_panel(self) -> str | None:
        return EditorModeController._resolve_active_search_panel(self)

    def _get_search_text_for_panel(self, panel: str) -> str:
        return EditorModeController._get_search_text_for_panel(self, panel)

    def _set_search_text_for_panel(self, panel: str, new_text: str) -> None:
        EditorModeController._set_search_text_for_panel(self, panel, new_text)

    def _clamp_history_cursor(self, cursor: int, count: int) -> int:
        return EditorModeController._clamp_history_cursor(self, cursor, count)

    def get_undo_history_entries(self):
        return EditorModeController.get_undo_history_entries(self)

    def get_filtered_undo_history_entries(self):
        return EditorModeController.get_filtered_undo_history_entries(self)

    def _history_display_index(self, entries):
        return EditorModeController._history_display_index(self, entries)

    def _history_input_blocked(self) -> bool:
        return False


def test_ctrl_f_focuses_active_panel(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)

    controller = StubController()

    editor_input.handle_input(controller, arcade_stub.key.F, arcade_stub.key.MOD_CTRL)
    assert controller._search_focus == "outliner"
    assert controller.entity_panels_filter_active is True

    controller._left_dock_tab = "Project"
    controller.entity_panels_active = False
    controller.clear_search_focus()

    editor_input.handle_input(controller, arcade_stub.key.F, arcade_stub.key.MOD_CTRL)
    assert controller._search_focus == "project"

    controller._left_dock_tab = "Scene"
    controller.entity_panels_active = False
    controller._right_dock_tab = "Assets"
    controller.asset_browser_active = True
    controller.clear_search_focus()

    editor_input.handle_input(controller, arcade_stub.key.F, arcade_stub.key.MOD_CTRL)
    assert controller._search_focus == "assets"

    controller._right_dock_tab = "History"
    controller.asset_browser_active = False
    controller.clear_search_focus()

    editor_input.handle_input(controller, arcade_stub.key.F, arcade_stub.key.MOD_CTRL)
    assert controller._search_focus == "history"

    controller._left_dock_tab = "Scene"
    controller.entity_panels_active = False
    controller._right_dock_tab = "Problems"
    controller.clear_search_focus()

    editor_input.handle_input(controller, arcade_stub.key.F, arcade_stub.key.MOD_CTRL)
    assert controller._search_focus == "problems"


def test_typing_updates_search_only_when_focused(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)

    controller = StubController()
    controller._search_focus = "outliner"

    editor_input.handle_text_input(controller, "a")
    assert controller._outliner_search == "a"

    controller._search_focus = None
    editor_input.handle_text_input(controller, "b")
    assert controller._outliner_search == "a"


def test_escape_clears_then_defocuses(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)

    controller = StubController()
    controller._search_focus = "outliner"
    controller._outliner_search = "alpha"

    editor_input.handle_input(controller, arcade_stub.key.ESCAPE, 0)
    assert controller._outliner_search == ""
    assert controller._search_focus == "outliner"

    editor_input.handle_input(controller, arcade_stub.key.ESCAPE, 0)
    assert controller._search_focus is None


def test_filtering_is_deterministic() -> None:
    outliner_items = [
        EntitySummary(id="chest_01", name="Chest", type="loot", x=0.0, y=0.0),
        EntitySummary(id="door_01", name="Door", type="prop", x=1.0, y=1.0),
        EntitySummary(id="chest_02", name="Chest B", type="loot", x=2.0, y=2.0),
    ]
    filtered_outliner = filter_entity_panels_items(outliner_items, "chest")
    assert [item.id for item in filtered_outliner] == ["chest_01", "chest_02"]

    asset_rows = [
        AssetRow(rel_path="assets/props/door.png", kind="image", display_name="door.png"),
        AssetRow(rel_path="assets/audio/chime.ogg", kind="audio", display_name="chime.ogg"),
        AssetRow(rel_path="assets/props/chest.png", kind="image", display_name="chest.png"),
    ]
    filtered_assets = filter_assets_for_browser(asset_rows, "chest", "All")
    assert [row.rel_path for row in filtered_assets] == ["assets/props/chest.png"]

    history_entries = build_undo_history_entries(
        [{"type": "MoveEntities"}, {"type": "RotateEntities"}],
        [{"type": "EditLight"}],
    )
    filtered_history = filter_undo_history_entries(history_entries, "rot")
    assert [entry.label for entry in filtered_history] == ["ROTATE"]


def test_enter_blocked_while_search_focused(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)

    controller = StubController()
    controller._search_focus = "assets"
    controller._right_dock_tab = "Assets"
    controller.asset_browser_active = True

    activated = {"called": False}

    def _activate_selected_asset() -> None:
        activated["called"] = True

    controller._activate_selected_asset = _activate_selected_asset  # type: ignore[attr-defined]

    editor_input.handle_input(controller, arcade_stub.key.ENTER, 0)
    assert activated["called"] is False

    controller._search_focus = "history"
    controller._right_dock_tab = "History"
    controller.undo_stack = [{"type": "MoveEntities"}]
    controller.redo_stack = []

    jumped = {"called": False}

    def _jump(_idx: int) -> bool:
        jumped["called"] = True
        return True

    controller.jump_undo_history_to = _jump  # type: ignore[attr-defined]
    EditorModeController._handle_history_input(controller, arcade_stub.key.ENTER, 0)
    assert jumped["called"] is False
