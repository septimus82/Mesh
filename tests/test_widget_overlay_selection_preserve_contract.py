from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.asset_index import AssetRow
from engine.editor.editor_asset_browser_controller import EditorAssetBrowserController
from engine.editor.editor_keybinds_controller import EditorKeybindsController
from engine.editor.editor_ui_flow_controller import EditorUIFlowController
from engine.editor.find_everything_model import FindItem
from engine.editor.keybinds_ui_model import KeybindRow, KeybindsState
from engine.scene_index import SceneRow
from engine.ui_overlays import scene_browser_overlay as scene_overlay_module
from engine.ui_overlays.scene_browser_overlay import SceneBrowserOverlay
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


class _FindFlowHost:
    def __init__(self, items: list[FindItem]) -> None:
        self._items = list(items)
        self.window = None

    def ui_get_palette_items(self) -> list[Any]:
        return list(self._items)

    def ui_hd2d_cancel_preview(self) -> None:
        return None

    def ui_hd2d_preview(self, _preset_id: str) -> None:
        return None

    def ui_hd2d_commit(self, _preset_id: str) -> bool:
        return True

    def ui_activate_command(self, _item_id: str) -> bool:
        return True

    def ui_activate_asset(self, _item_id: str) -> bool:
        return True

    def ui_activate_scene(self, _item_id: str) -> bool:
        return True

    def ui_activate_entity(self, _item_id: str) -> bool:
        return True

    def ui_activate_problem(self, _item_id: str) -> bool:
        return True


def test_find_everything_query_update_preserves_selected_identity_when_possible() -> None:
    host = _FindFlowHost(
        [
            FindItem(kind="scene", item_id="scene.alpha", title="Scene Alpha", subtitle="", keywords=("scene",)),
            FindItem(kind="scene", item_id="scene.beta", title="Scene Beta", subtitle="", keywords=("scene",)),
            FindItem(kind="scene", item_id="scene.gamma", title="Scene Gamma", subtitle="", keywords=("scene",)),
        ]
    )
    flow = EditorUIFlowController(host)
    flow.open_palette("")
    flow.selection_index = 1

    flow.update_query("scene")
    assert flow.cached_results[flow.selection_index].item_id == "scene.beta"
    assert 0 <= flow.selection_index < len(flow.cached_results)

    flow.update_query("gamma")
    assert len(flow.cached_results) == 1
    assert flow.cached_results[0].item_id == "scene.gamma"
    assert flow.selection_index == 0


def test_find_everything_query_update_clamps_to_empty_deterministically() -> None:
    host = _FindFlowHost(
        [
            FindItem(kind="scene", item_id="scene.alpha", title="Scene Alpha", subtitle="", keywords=("scene",)),
            FindItem(kind="scene", item_id="scene.beta", title="Scene Beta", subtitle="", keywords=("scene",)),
        ]
    )
    flow = EditorUIFlowController(host)
    flow.open_palette("")
    flow.selection_index = 1

    flow.update_query("does-not-exist")
    assert flow.cached_results == []
    assert flow.selection_index == -1


class _SceneControllerStub:
    def __init__(self, rows: list[SceneRow], width: int = 1280, height: int = 720) -> None:
        self.active = True
        self.scene_browser_active = True
        self.scene_browser_query = ""
        self.scene_browser_index = 0
        self._all_rows = list(rows)
        self._rows = list(rows)
        self._open_calls: list[int] = []
        self.dock = SimpleNamespace(get_snapshot=lambda: SimpleNamespace(left_tab="Scene"))
        self.window = SimpleNamespace(width=width, height=height)

    def _refresh_scene_browser_rows(self) -> None:
        query = str(self.scene_browser_query or "").strip().lower()
        if not query:
            self._rows = list(self._all_rows)
            return
        self._rows = [row for row in self._all_rows if query in row.display_name.lower()]

    def _scene_browser_rows(self) -> list[SceneRow]:
        return list(self._rows)

    def _scene_browser_clamp_index(self, count: int) -> None:
        if count <= 0:
            self.scene_browser_index = -1
            return
        self.scene_browser_index = max(0, min(int(self.scene_browser_index), count - 1))

    def _scene_browser_layout(self, count: int) -> dict[str, float]:
        from engine.editor.scene_opening import compute_scene_browser_layout

        return compute_scene_browser_layout(float(self.window.width), float(self.window.height), int(count))

    def _scene_browser_open_selected(self) -> bool:
        self._open_calls.append(int(self.scene_browser_index))
        return True


def _stub_scene_draw(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)
    monkeypatch.setattr(scene_overlay_module, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(scene_overlay_module, "_draw_lrtb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(scene_overlay_module, "_draw_rectangle_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(scene_overlay_module, "draw_text_cached", lambda *args, **kwargs: None)


def test_scene_browser_filter_change_preserves_selection_and_keeps_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_scene_draw(monkeypatch)
    rows = [
        SceneRow(scene_id="scene/keep_a.json", display_name="Keep A", pack_name="core", is_recent=False),
        SceneRow(scene_id="scene/keep_b.json", display_name="Keep B", pack_name="core", is_recent=False),
        SceneRow(scene_id="scene/drop.json", display_name="Drop", pack_name="core", is_recent=False),
    ]
    controller = _SceneControllerStub(rows)
    controller.scene_browser_index = 1
    window = SimpleNamespace(width=1280, height=720, editor_controller=controller)
    overlay = SceneBrowserOverlay(as_any(window))

    overlay.draw()
    assert overlay.append_text("k") is True
    assert controller.scene_browser_index == 1

    overlay.draw()
    visible_indexes = [idx for idx, _text, _rect, _selected in overlay._results_scroll.visible_rows]
    assert 1 in visible_indexes

    assert overlay.append_text("z") is True
    assert controller.scene_browser_index == -1


def test_keybinds_query_change_preserves_selection_when_action_remains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actions = [
        SimpleNamespace(id="editor.move.alpha", title="Move Alpha", shortcut_scope="global", shortcut="Ctrl+1"),
        SimpleNamespace(id="editor.move.beta", title="Move Beta", shortcut_scope="global", shortcut="Ctrl+2"),
        SimpleNamespace(id="editor.gamma", title="Gamma", shortcut_scope="global", shortcut="Ctrl+3"),
    ]
    monkeypatch.setattr("engine.editor.editor_keybinds_controller.get_editor_actions", lambda *_args, **_kwargs: actions)

    editor = SimpleNamespace(window=SimpleNamespace(), _keymap_overrides={})
    controller = EditorKeybindsController(editor)
    controller.open()
    rows = controller.visible_rows
    beta_idx = next(i for i, row in enumerate(rows) if row.action_id == "editor.move.beta")
    controller.set_selected_index(beta_idx)

    controller.set_query("move")
    move_rows = controller.visible_rows
    assert move_rows[controller.state.selected_index].action_id == "editor.move.beta"
    assert 0 <= controller.state.selected_index < len(move_rows)

    controller.set_query("gamma")
    gamma_rows = controller.visible_rows
    assert len(gamma_rows) == 1
    assert controller.state.selected_index == 0


def test_asset_browser_filter_change_preserves_selection_by_rel_path() -> None:
    rows = [
        AssetRow(rel_path="assets/keep_a.png", kind="image", display_name="keep_a.png"),
        AssetRow(rel_path="assets/keep_b.png", kind="image", display_name="keep_b.png"),
        AssetRow(rel_path="assets/drop.png", kind="image", display_name="drop.png"),
    ]
    editor = SimpleNamespace(
        search=SimpleNamespace(get_assets_search=lambda: "", set_assets_search=lambda _text: None),
        asset_browser_filter="",
        asset_browser_kind="All",
        asset_browser_selection_index=1,
        _asset_browser_cached_rows=list(rows),
        _asset_browser_filtered_rows=list(rows),
        _autosave_workspace=lambda: None,
    )
    controller = EditorAssetBrowserController(editor)

    controller.set_asset_browser_filter("keep")
    kept_rows = list(editor._asset_browser_filtered_rows)
    assert kept_rows[editor.asset_browser_selection_index].rel_path == "assets/keep_b.png"
    assert 0 <= editor.asset_browser_selection_index < len(kept_rows)

    controller.set_asset_browser_filter("drop")
    dropped_rows = list(editor._asset_browser_filtered_rows)
    assert len(dropped_rows) == 1
    assert editor.asset_browser_selection_index == 0
