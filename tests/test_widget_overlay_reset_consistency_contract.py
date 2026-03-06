from __future__ import annotations

from types import SimpleNamespace

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

pytestmark = [pytest.mark.fast]


def _stub_overlay_drawing(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)

    monkeypatch.setattr(find_overlay_module, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(find_overlay_module, "_draw_lrtb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(find_overlay_module, "_draw_rectangle_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(find_overlay_module, "draw_text_cached", lambda *args, **kwargs: None)

    monkeypatch.setattr(scene_overlay_module, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(scene_overlay_module, "_draw_lrtb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(scene_overlay_module, "_draw_rectangle_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(scene_overlay_module, "draw_text_cached", lambda *args, **kwargs: None)

    monkeypatch.setattr(asset_overlay_module, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(asset_overlay_module, "_draw_lrtb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(asset_overlay_module, "_draw_rectangle_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(asset_overlay_module, "draw_text_cached", lambda *args, **kwargs: None)

    monkeypatch.setattr(keybinds_overlay_module, "draw_text", lambda *args, **kwargs: None)
    monkeypatch.setattr(keybinds_overlay_module, "_draw_lrtb_rectangle_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(keybinds_overlay_module, "_draw_lrtb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(keybinds_overlay_module, "_draw_rectangle_outline", lambda *args, **kwargs: None)


def _make_find_results(count: int) -> list[FindResult]:
    return [
        FindResult(
            kind="command",
            item_id=f"editor.command_{index}",
            title=f"Command {index}",
            subtitle="",
        )
        for index in range(count)
    ]


def test_find_everything_overlay_reopen_resets_transient_state(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_overlay_drawing(monkeypatch)
    results = _make_find_results(24)
    counts = compute_find_counts(results)
    controller = SimpleNamespace(
        active=True,
        _find_everything_open=True,
        _find_everything_cached_results=results,
        _find_everything_counts=counts,
        _find_everything_query="",
        _find_everything_selection_index=0,
    )
    window = SimpleNamespace(width=1280, height=720, editor_controller=controller, input=None, input_controller=None)
    overlay = FindEverythingOverlay(window)  # type: ignore[arg-type]

    overlay._focus_target = "results"
    overlay._text_input.focused = False
    overlay._text_input.text = "stale"
    overlay._results_scroll.scroll_offset = 9.0
    overlay._results_scroll.selected_index = 7
    overlay._was_open = True

    controller._find_everything_open = False
    overlay.draw()
    assert overlay._was_open is False

    controller._find_everything_open = True
    controller._find_everything_query = ""
    controller._find_everything_selection_index = 0
    overlay.draw()
    assert overlay._focus_target == "input"
    assert overlay._text_input.focused is True
    assert overlay._text_input.text == ""
    expected_selected_display = overlay._resolve_selected_display_index(0)
    assert overlay._results_scroll.selected_index == expected_selected_display
    expected_scroll = float(max(0, expected_selected_display))
    assert overlay._results_scroll.scroll_offset == pytest.approx(expected_scroll)


def test_scene_browser_overlay_reopen_resets_transient_state(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_overlay_drawing(monkeypatch)
    rows = [SimpleNamespace(display_name=f"Scene {index}", pack_name="core", is_recent=False) for index in range(20)]
    dock = SimpleNamespace(get_snapshot=lambda: SimpleNamespace(left_tab="Scene"))
    controller = SimpleNamespace(
        active=True,
        scene_browser_active=True,
        scene_browser_query="",
        scene_browser_index=0,
        dock=dock,
        _scene_browser_rows=lambda: rows,
        _scene_browser_layout=lambda _count: {
            "left": 120.0,
            "right": 760.0,
            "top": 620.0,
            "bottom": 140.0,
            "start_x": 140.0,
            "start_y": 590.0,
            "row_start_y": 520.0,
        },
    )
    window = SimpleNamespace(width=1280, height=720, editor_controller=controller)
    overlay = SceneBrowserOverlay(window)  # type: ignore[arg-type]

    overlay._focus_target = "results"
    overlay._text_input.focused = False
    overlay._text_input.text = "stale"
    overlay._results_scroll.scroll_offset = 7.0
    overlay._results_scroll.selected_index = 9
    overlay._was_open = True

    controller.scene_browser_active = False
    overlay.draw()
    assert overlay._was_open is False

    controller.scene_browser_active = True
    controller.scene_browser_query = ""
    controller.scene_browser_index = 0
    overlay.draw()
    assert overlay._focus_target == "input"
    assert overlay._text_input.focused is True
    assert overlay._text_input.text == ""
    assert overlay._results_scroll.selected_index == 0
    assert overlay._results_scroll.scroll_offset == pytest.approx(0.0)


def test_keybinds_overlay_reset_hooks_reopen_clean_state(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_overlay_drawing(monkeypatch)

    rows = tuple(
        SimpleNamespace(
            title=f"Action {index}",
            action_id=f"editor.action_{index}",
            scope="global",
            shortcut_effective=f"Ctrl+{index % 10}",
            shortcut_default=f"Ctrl+{index % 10}",
            has_override=False,
            conflict_ids=(),
        )
        for index in range(20)
    )

    state = SimpleNamespace(query="", selected_index=0)
    controller = SimpleNamespace(state=state, visible_rows=rows)
    editor = SimpleNamespace(keybinds=controller)
    window = SimpleNamespace(width=1280, height=720, editor_controller=editor, text_cache=None)
    overlay = KeybindsOverlay(window)  # type: ignore[arg-type]
    overlay.visible = True

    def _data(_controller: object, **_kwargs: object) -> dict[str, object]:
        selected_index = int(controller.state.selected_index)
        selected_item: dict[str, object] | None = None
        if rows and 0 <= selected_index < len(rows):
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

    monkeypatch.setattr(keybinds_overlay_module, "get_keybinds_ui_data", _data)

    overlay._focus_target = "results"
    overlay._text_input.focused = False
    overlay._text_input.text = "stale"
    overlay._results_scroll.scroll_offset = 11.0
    overlay._results_scroll.selected_index = 6
    overlay._was_open = True

    overlay.reset_for_close()
    assert overlay._was_open is False

    controller.state.query = ""
    controller.state.selected_index = 0
    overlay.reset_for_open()
    overlay.draw()
    assert overlay._focus_target == "input"
    assert overlay._text_input.focused is True
    assert overlay._text_input.text == ""
    assert overlay._results_scroll.selected_index == 0
    assert overlay._results_scroll.scroll_offset == pytest.approx(0.0)


def test_asset_browser_overlay_reset_hooks_reopen_clean_state(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_overlay_drawing(monkeypatch)

    rows = [
        SimpleNamespace(
            display_name=f"asset_{index}.png",
            kind="image",
            rel_path=f"assets/props/asset_{index}.png",
        )
        for index in range(20)
    ]
    search = SimpleNamespace(
        _value="",
        get_assets_search=lambda: search._value,
    )
    dock = SimpleNamespace(get_snapshot=lambda: SimpleNamespace(right_tab="Assets"))
    controller = SimpleNamespace(
        active=True,
        asset_browser_active=True,
        asset_browser_kind="All",
        asset_browser_selection_index=0,
        _asset_browser_filtered_rows=rows,
        search=search,
        dock=dock,
    )
    window = SimpleNamespace(width=1280, height=720, editor_controller=controller)
    overlay = AssetBrowserOverlay(window)  # type: ignore[arg-type]

    overlay._focus_target = "results"
    overlay._text_input.focused = False
    overlay._text_input.text = "stale"
    overlay._results_scroll.scroll_offset = 8.0
    overlay._results_scroll.selected_index = 5
    overlay._was_open = True

    overlay.reset_for_close()
    assert overlay._was_open is False

    search._value = ""
    controller.asset_browser_selection_index = 0
    overlay.reset_for_open()
    overlay.draw()
    assert overlay._focus_target == "input"
    assert overlay._text_input.focused is True
    assert overlay._text_input.text == ""
    assert overlay._results_scroll.selected_index == 0
    assert overlay._results_scroll.scroll_offset == pytest.approx(0.0)
