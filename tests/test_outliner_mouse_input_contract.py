from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor.dock_tab_registry import RIGHT_DOCK_TABS
from engine.editor.editor_outliner_input_controller import EditorOutlinerInputController
from engine.editor.editor_shell_layout import DOCK_WIDTH, TAB_HEADER_HEIGHT, compute_editor_shell_layout
from engine.editor_entity_ops import EntitySummary
from engine.editor_runtime import editor_input_click_handlers, editor_input_key_handlers
from tests._dock_stub import make_dock_stub

pytestmark = [pytest.mark.fast]


class _Window:
    width = 1280
    height = 720

    def __init__(self) -> None:
        self.scene_controller = SimpleNamespace(all_sprites=[])
        self.world_clicks: list[tuple[float, float]] = []

    def screen_to_world(self, x: float, y: float) -> tuple[float, float]:
        self.world_clicks.append((x, y))
        return (x + 1000.0, y + 1000.0)


class _SearchStub:
    def __init__(self, focused: bool = False) -> None:
        self.focused = focused

    def is_search_focused(self) -> bool:
        return self.focused

    def get_outliner_search(self) -> str:
        return ""

    def is_panel_search_focused(self, _panel: str) -> bool:
        return False


class _ItemEditorStub:
    def __init__(self, *, active: bool) -> None:
        self.active = active
        self.calls: list[str] = []

    def is_edit_mode_active(self) -> bool:
        return self.active

    def cycle_focus_forward(self) -> None:
        self.calls.append("forward")

    def cycle_focus_backward(self) -> None:
        self.calls.append("backward")


def _left_dock_point(*, item_line: int = 0) -> tuple[float, float]:
    dock = compute_editor_shell_layout(1280, 720, DOCK_WIDTH, DOCK_WIDTH).left_dock
    start_y = dock.top - TAB_HEADER_HEIGHT - 8.0
    first_item_line = 4
    y = start_y - ((first_item_line + item_line) * 18.0) - 9.0
    return (dock.left + 24.0, y)


def _outliner_editor(*, left_tab: str = "Outliner") -> SimpleNamespace:
    items = [
        EntitySummary(id="player", name="Player", type="actor", x=1.0, y=2.0),
        EntitySummary(id="crate", name="Crate", type="prop", x=3.0, y=4.0),
    ]
    editor = SimpleNamespace(
        active=True,
        dock=make_dock_stub(left_tab=left_tab),
        window=_Window(),
        entity_panels_active=True,
        entity_panels_selection_index=0,
        _cached_entity_panels_list=items,
        selected_ids=[],
    )

    def _select_current() -> bool:
        index = int(editor.entity_panels_selection_index)
        editor.selected_ids.append(editor._cached_entity_panels_list[index].id)
        return True

    editor._refresh_entity_panels_list = lambda: None
    editor._entity_panels_select_current = _select_current
    editor.outliner_input = EditorOutlinerInputController(editor)
    editor._outliner_handle_mouse_click = editor.outliner_input.handle_mouse_click
    return editor


def _click_dispatch_editor(*, left_tab: str = "Outliner") -> SimpleNamespace:
    window = _Window()
    return SimpleNamespace(
        active=True,
        dock=make_dock_stub(left_tab=left_tab),
        window=window,
        panels=SimpleNamespace(dispatch_input=lambda _key, _mods: False),
        search=_SearchStub(),
        _find_everything_open=False,
        asset_browser_active=False,
        asset_place_active=False,
        entity_panels_active=True,
        shape_edit_mode=False,
        tile_panel_active=False,
        occluder_tool_active=False,
        lights_tool_active=False,
        palette_active=False,
        tool_mode="SELECT",
        selected_entity=None,
        begin_marquee=lambda *_args: None,
    )


def _key_controller(*, right_tab: str = "Inspector", item_edit_mode: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        active=True,
        dock=make_dock_stub(right_tab=right_tab),
        panels=SimpleNamespace(dispatch_input=lambda _key, _mods: False),
        search=_SearchStub(),
        _find_everything_open=False,
        item_editor=_ItemEditorStub(active=item_edit_mode),
        prefab_editor=None,
        quest_editor=None,
        asset_place_active=False,
        _inspector_text_edit_active=False,
        entity_panels_text_edit_active=False,
        dialogue_panel_active=False,
        dialogue_editing=False,
        animation_active=False,
        animation_editing=False,
    )


def _disable_click_chrome(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("_handle_menu_bar_click", "_handle_top_bar_controls_click", "_handle_splitter_click", "_handle_dock_tab_click"):
        monkeypatch.setattr(editor_input_click_handlers, name, lambda *_args: None)


def test_click_inside_outliner_row_selects_that_entity() -> None:
    editor = _outliner_editor()
    x, y = _left_dock_point(item_line=1)

    assert editor.outliner_input.handle_mouse_click(x, y, optional_arcade.arcade.MOUSE_BUTTON_LEFT) is True

    assert editor.entity_panels_selection_index == 1
    assert editor.selected_ids == ["crate"]


def test_click_inside_outliner_rect_with_project_tab_does_not_select() -> None:
    editor = _outliner_editor(left_tab="Project")
    x, y = _left_dock_point()

    assert editor.outliner_input.handle_mouse_click(x, y, optional_arcade.arcade.MOUSE_BUTTON_LEFT) is False

    assert editor.selected_ids == []


def test_click_outside_left_dock_does_not_trigger_outliner_handler() -> None:
    editor = _outliner_editor()

    assert editor.outliner_input.handle_mouse_click(640.0, 360.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT) is False

    assert editor.selected_ids == []


def test_left_dock_content_guard_consumes_unclaimed_click(monkeypatch: pytest.MonkeyPatch) -> None:
    editor = _click_dispatch_editor(left_tab="Outliner")
    editor._project_explorer_handle_mouse_click = lambda *_args: False
    editor._outliner_handle_mouse_click = lambda *_args: False
    editor._scene_browser_handle_mouse_click = lambda *_args: False
    _disable_click_chrome(monkeypatch)
    x, y = _left_dock_point()

    assert editor_input_click_handlers.handle_mouse_click(editor, x, y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert editor.window.world_clicks == []


def test_tab_outside_edit_mode_cycles_right_dock_forward() -> None:
    controller = _key_controller(right_tab="Inspector", item_edit_mode=False)

    handled = editor_input_key_handlers.handle_pre_routed_keys(controller, optional_arcade.arcade.key.TAB, 0)

    assert handled is True
    assert controller.dock.right_tab == RIGHT_DOCK_TABS[1]


def test_shift_tab_outside_edit_mode_cycles_right_dock_backward() -> None:
    controller = _key_controller(right_tab="Inspector", item_edit_mode=False)

    handled = editor_input_key_handlers.handle_pre_routed_keys(
        controller,
        optional_arcade.arcade.key.TAB,
        optional_arcade.arcade.key.MOD_SHIFT,
    )

    assert handled is True
    assert controller.dock.right_tab == RIGHT_DOCK_TABS[-1]


def test_tab_inside_items_edit_mode_cycles_fields_not_dock_tabs() -> None:
    controller = _key_controller(right_tab="Items", item_edit_mode=True)

    handled = editor_input_key_handlers.handle_pre_routed_keys(controller, optional_arcade.arcade.key.TAB, 0)

    assert handled is True
    assert controller.dock.right_tab == "Items"
    assert controller.item_editor.calls == ["forward"]
