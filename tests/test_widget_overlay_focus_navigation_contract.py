from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor.find_everything_model import FindResult, compute_find_counts
from engine.ui_overlays import (
    asset_browser_overlay as asset_overlay_module,
    find_everything_overlay as find_overlay_module,
    keybinds_overlay as keybinds_overlay_module,
    scene_browser_overlay as scene_overlay_module,
)
from engine.ui_overlays.asset_browser_overlay import AssetBrowserOverlay
from engine.ui_overlays.find_everything_overlay import FindEverythingOverlay
from engine.ui_overlays.keybinds_overlay import KeybindsOverlay
from engine.ui_overlays.scene_browser_overlay import SceneBrowserOverlay
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


def _stub_overlay_drawing(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)

    monkeypatch.setattr(find_overlay_module, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(find_overlay_module, "_draw_tb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(find_overlay_module, "_draw_rectangle_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(find_overlay_module, "draw_text_cached", lambda *args, **kwargs: None)

    monkeypatch.setattr(scene_overlay_module, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(scene_overlay_module, "_draw_tb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(scene_overlay_module, "_draw_rectangle_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(scene_overlay_module, "draw_text_cached", lambda *args, **kwargs: None)

    monkeypatch.setattr(asset_overlay_module, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(asset_overlay_module, "_draw_tb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(asset_overlay_module, "_draw_rectangle_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(asset_overlay_module, "draw_text_cached", lambda *args, **kwargs: None)

    monkeypatch.setattr(keybinds_overlay_module, "draw_text", lambda *args, **kwargs: None)
    monkeypatch.setattr(keybinds_overlay_module, "_draw_tb_rectangle_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(keybinds_overlay_module, "_draw_tb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(keybinds_overlay_module, "_draw_rectangle_outline", lambda *args, **kwargs: None)


class _Case(SimpleNamespace):
    overlay: Any
    draw: Callable[[], None]
    get_query: Callable[[], str]
    get_selected_index: Callable[[], int]
    get_item_count: Callable[[], int]
    get_activation_count: Callable[[], int]


def _make_find_case() -> _Case:
    results = [
        FindResult(kind="command", item_id=f"editor.command_{index}", title=f"Command {index}", subtitle="")
        for index in range(4)
    ]
    counts = compute_find_counts(results)
    controller = SimpleNamespace(
        active=True,
        _find_everything_open=True,
        _find_everything_cached_results=results,
        _find_everything_counts=counts,
        _find_everything_query="",
        _find_everything_selection_index=0,
        _activation_count=0,
    )

    def _set_find_query(text: str) -> None:
        controller._find_everything_query = str(text or "")

    def _move_find_selection(delta: int) -> None:
        if not results:
            controller._find_everything_selection_index = -1
            return
        nxt = int(controller._find_everything_selection_index) + int(delta)
        controller._find_everything_selection_index = max(0, min(nxt, len(results) - 1))

    def _activate_find_selection() -> bool:
        controller._activation_count += 1
        return True

    controller.set_find_query = _set_find_query
    controller.move_find_selection = _move_find_selection
    controller.activate_find_selection = _activate_find_selection

    window = SimpleNamespace(width=1280, height=720, editor_controller=controller, input=None, input_controller=None)
    overlay = FindEverythingOverlay(as_any(window))

    return _Case(
        overlay=overlay,
        draw=overlay.draw,
        get_query=lambda: str(controller._find_everything_query),
        get_selected_index=lambda: int(controller._find_everything_selection_index),
        get_item_count=lambda: len(results),
        get_activation_count=lambda: int(controller._activation_count),
    )


def _make_scene_case() -> _Case:
    rows = [SimpleNamespace(scene_id=f"scenes/scene_{index}.json", display_name=f"Scene {index}", pack_name="core", is_recent=False) for index in range(4)]
    controller = SimpleNamespace(
        active=True,
        scene_browser_active=True,
        scene_browser_query="",
        scene_browser_index=0,
        dock=SimpleNamespace(get_snapshot=lambda: SimpleNamespace(left_tab="Scene")),
        _activation_count=0,
    )

    def _rows() -> list[Any]:
        return rows

    def _layout(_count: int) -> dict[str, float]:
        return {
            "left": 120.0,
            "right": 760.0,
            "top": 620.0,
            "bottom": 140.0,
            "start_x": 140.0,
            "start_y": 590.0,
            "row_start_y": 520.0,
        }

    def _clamp(_count: int) -> None:
        if not rows:
            controller.scene_browser_index = -1
            return
        controller.scene_browser_index = max(0, min(int(controller.scene_browser_index), len(rows) - 1))

    def _refresh() -> None:
        return

    def _open_selected() -> bool:
        controller._activation_count += 1
        return True

    controller._scene_browser_rows = _rows
    controller._scene_browser_layout = _layout
    controller._scene_browser_clamp_index = _clamp
    controller._refresh_scene_browser_rows = _refresh
    controller._scene_browser_open_selected = _open_selected

    window = SimpleNamespace(width=1280, height=720, editor_controller=controller)
    overlay = SceneBrowserOverlay(as_any(window))

    return _Case(
        overlay=overlay,
        draw=overlay.draw,
        get_query=lambda: str(controller.scene_browser_query),
        get_selected_index=lambda: int(controller.scene_browser_index),
        get_item_count=lambda: len(rows),
        get_activation_count=lambda: int(controller._activation_count),
    )


def _make_keybinds_case(monkeypatch: pytest.MonkeyPatch) -> _Case:
    rows = tuple(
        SimpleNamespace(
            title=f"Action {index}",
            action_id=f"editor.action_{index}",
            scope="global",
            shortcut_effective=f"Ctrl+{index}",
            shortcut_default=f"Ctrl+{index}",
            has_override=False,
            conflict_ids=(),
        )
        for index in range(4)
    )
    state = SimpleNamespace(query="", selected_index=0)
    controller = SimpleNamespace(state=state, visible_rows=rows, _activation_count=0)

    def _set_query(text: str) -> None:
        controller.state.query = str(text or "")
        controller.state.selected_index = 0

    def _set_selected_index(index: int) -> None:
        controller.state.selected_index = max(0, min(int(index), len(rows) - 1))

    def _start_recording_selected() -> None:
        controller._activation_count += 1

    controller.set_query = _set_query
    controller.set_selected_index = _set_selected_index
    controller.start_recording_selected = _start_recording_selected

    editor = SimpleNamespace(keybinds=controller)
    window = SimpleNamespace(width=1280, height=720, editor_controller=editor, text_cache=None)
    overlay = KeybindsOverlay(as_any(window))
    overlay.visible = True

    def _keybinds_data(_controller: Any, **_kwargs: Any) -> dict[str, Any]:
        selected_index = int(controller.state.selected_index)
        selected_item: dict[str, Any] | None = None
        if 0 <= selected_index < len(rows):
            row = rows[selected_index]
            selected_item = {
                "title": row.title,
                "action_id": row.action_id,
                "scope": row.scope,
                "effective": row.shortcut_effective,
                "default": row.shortcut_default,
                "conflicts": row.conflict_ids,
            }
        return {
            "query": str(controller.state.query),
            "recording": False,
            "pending_conflicts": (),
            "pending_record_shortcut": "",
            "recording_target": None,
            "selected_index": selected_index,
            "selected_item": selected_item,
            "scope_filter": "all",
            "show_conflicts_only": False,
            "hint_text": "Keybinds",
        }

    monkeypatch.setattr(keybinds_overlay_module, "get_keybinds_ui_data", _keybinds_data)

    return _Case(
        overlay=overlay,
        draw=overlay.draw,
        get_query=lambda: str(controller.state.query),
        get_selected_index=lambda: int(controller.state.selected_index),
        get_item_count=lambda: len(rows),
        get_activation_count=lambda: int(controller._activation_count),
    )


def _make_asset_case() -> _Case:
    all_rows = [
        SimpleNamespace(
            display_name=f"asset_{index}.png",
            kind="image",
            rel_path=f"assets/props/asset_{index}.png",
        )
        for index in range(4)
    ]
    search = SimpleNamespace(value="")

    def _get_assets_search() -> str:
        return str(search.value)

    search.get_assets_search = _get_assets_search

    controller = SimpleNamespace(
        active=True,
        asset_browser_active=True,
        asset_browser_kind="All",
        asset_browser_selection_index=0,
        asset_browser_filter="",
        _asset_browser_filtered_rows=list(all_rows),
        search=search,
        dock=SimpleNamespace(get_snapshot=lambda: SimpleNamespace(right_tab="Assets")),
        _activation_count=0,
    )

    def _set_asset_browser_filter(text: str) -> None:
        value = str(text or "")
        search.value = value
        controller.asset_browser_filter = value
        if not value:
            controller._asset_browser_filtered_rows = list(all_rows)
        else:
            controller._asset_browser_filtered_rows = [
                row for row in all_rows if value.lower() in str(row.display_name).lower()
            ]
        if controller._asset_browser_filtered_rows:
            controller.asset_browser_selection_index = max(
                0,
                min(
                    int(controller.asset_browser_selection_index),
                    len(controller._asset_browser_filtered_rows) - 1,
                ),
            )
        else:
            controller.asset_browser_selection_index = 0

    def _activate_selected_asset() -> None:
        controller._activation_count += 1

    controller.set_asset_browser_filter = _set_asset_browser_filter
    controller._activate_selected_asset = _activate_selected_asset

    window = SimpleNamespace(width=1280, height=720, editor_controller=controller)
    overlay = AssetBrowserOverlay(as_any(window))

    return _Case(
        overlay=overlay,
        draw=overlay.draw,
        get_query=lambda: str(search.value),
        get_selected_index=lambda: int(controller.asset_browser_selection_index),
        get_item_count=lambda: len(controller._asset_browser_filtered_rows),
        get_activation_count=lambda: int(controller._activation_count),
    )


@pytest.mark.parametrize(
    "case_factory",
    (
        lambda monkeypatch: _make_find_case(),
        lambda monkeypatch: _make_scene_case(),
        _make_keybinds_case,
        lambda monkeypatch: _make_asset_case(),
    ),
)
def test_widgetized_overlay_focus_navigation_behavior_contract(
    monkeypatch: pytest.MonkeyPatch,
    case_factory: Callable[[pytest.MonkeyPatch], _Case],
) -> None:
    _stub_overlay_drawing(monkeypatch)
    case = case_factory(monkeypatch)
    overlay = case.overlay

    overlay.reset_for_open()
    case.draw()
    assert overlay._focus_target == "input"

    initial_query = case.get_query()
    assert overlay.append_text("x") is True
    assert case.get_query() != initial_query
    assert overlay.backspace() is True
    assert case.get_query() == initial_query

    activation_before_input_enter = case.get_activation_count()
    assert overlay.on_key_enter() is True
    assert case.get_activation_count() == activation_before_input_enter

    assert overlay.toggle_focus() is True
    assert overlay._focus_target == "results"
    query_before_results_text = case.get_query()
    assert overlay.append_text("z") is False
    assert case.get_query() == query_before_results_text
    assert overlay.backspace() is False
    assert case.get_query() == query_before_results_text

    nav_result = overlay.handle_navigation_key(optional_arcade.arcade.key.DOWN)
    assert isinstance(nav_result, bool)
    assert nav_result is True
    selected = case.get_selected_index()
    count = case.get_item_count()
    assert count >= 1
    assert 0 <= selected < count

    activation_before_results_enter = case.get_activation_count()
    assert overlay.on_key_enter() is True
    assert case.get_activation_count() == activation_before_results_enter + 1

    overlay.reset_for_close()
    assert overlay._focus_target == "input"
    overlay.reset_for_open()
    assert overlay._focus_target == "input"
