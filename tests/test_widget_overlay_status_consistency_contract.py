from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor.find_everything_model import FindResult, compute_find_counts
from engine.editor.keybinds_ui_model import KeybindRow, KeybindsState
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


def _stub_overlay_draw(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)
    monkeypatch.setattr(find_overlay_module, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(find_overlay_module, "_draw_lrtb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(find_overlay_module, "_draw_rectangle_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(scene_overlay_module, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(scene_overlay_module, "_draw_lrtb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(scene_overlay_module, "_draw_rectangle_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(asset_overlay_module, "draw_panel_bg", lambda *args, **kwargs: None)
    monkeypatch.setattr(asset_overlay_module, "_draw_lrtb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(asset_overlay_module, "_draw_rectangle_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(keybinds_overlay_module, "_draw_lrtb_rectangle_filled", lambda *args, **kwargs: None)
    monkeypatch.setattr(keybinds_overlay_module, "_draw_lrtb_rectangle_outline", lambda *args, **kwargs: None)
    monkeypatch.setattr(keybinds_overlay_module, "_draw_rectangle_outline", lambda *args, **kwargs: None)


class _OverlayCase:
    def __init__(self, overlay: Any, text_sink: list[str]) -> None:
        self.overlay = overlay
        self.text_sink = text_sink

    def draw(self) -> None:
        self.text_sink.clear()
        self.overlay.draw()

    def set_nonempty(self, selected_index: int = 0) -> None:  # pragma: no cover - implemented per case
        raise NotImplementedError

    def set_empty(self) -> None:  # pragma: no cover - implemented per case
        raise NotImplementedError

    def get_count(self) -> int:  # pragma: no cover - implemented per case
        raise NotImplementedError

    def get_selected(self) -> int:  # pragma: no cover - implemented per case
        raise NotImplementedError

    def get_activation_count(self) -> int:  # pragma: no cover - implemented per case
        raise NotImplementedError

    @property
    def empty_text(self) -> str:  # pragma: no cover - implemented per case
        raise NotImplementedError


class _FindCase(_OverlayCase):
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._all_results = [
            FindResult(kind="command", item_id=f"editor.command_{index}", title=f"Command {index}", subtitle="")
            for index in range(3)
        ]
        self._activation_count = 0
        self._query = ""
        self._filtered_results = list(self._all_results)
        self._selection = 0
        self._counts = compute_find_counts(self._filtered_results)
        self._texts: list[str] = []

        monkeypatch.setattr(find_overlay_module, "draw_text_cached", lambda text, *args, **kwargs: self._texts.append(str(text)))

        controller = SimpleNamespace(active=True, _find_everything_open=True)

        def _set_query(text: str) -> None:
            self._query = str(text or "")
            q = self._query.lower().strip()
            if not q:
                self._filtered_results = list(self._all_results)
            else:
                self._filtered_results = [row for row in self._all_results if q in row.title.lower() or q in row.item_id.lower()]
            self._counts = compute_find_counts(self._filtered_results)
            if self._filtered_results:
                self._selection = max(0, min(self._selection, len(self._filtered_results) - 1))
            else:
                self._selection = 0
            controller._find_everything_cached_results = list(self._filtered_results)
            controller._find_everything_counts = self._counts
            controller._find_everything_query = self._query
            controller._find_everything_selection_index = self._selection

        def _move(delta: int) -> None:
            if not self._filtered_results:
                self._selection = 0
            else:
                self._selection = max(0, min(self._selection + int(delta), len(self._filtered_results) - 1))
            controller._find_everything_selection_index = self._selection

        def _activate() -> bool:
            self._activation_count += 1
            return True

        controller._find_everything_cached_results = list(self._filtered_results)
        controller._find_everything_counts = self._counts
        controller._find_everything_query = self._query
        controller._find_everything_selection_index = self._selection
        controller.set_find_query = _set_query
        controller.move_find_selection = _move
        controller.activate_find_selection = _activate

        window = SimpleNamespace(width=1280, height=720, editor_controller=controller, input=None, input_controller=None)
        overlay = FindEverythingOverlay(window)  # type: ignore[arg-type]
        super().__init__(overlay=overlay, text_sink=self._texts)
        controller.set_find_query("")

    @property
    def empty_text(self) -> str:
        return "(No matches)"

    def set_nonempty(self, selected_index: int = 0) -> None:
        self.overlay.window.editor_controller.set_find_query("")
        self._selection = max(0, min(int(selected_index), max(0, len(self._filtered_results) - 1)))
        self.overlay.window.editor_controller._find_everything_selection_index = self._selection

    def set_empty(self) -> None:
        self.overlay.window.editor_controller.set_find_query("___none___")

    def get_count(self) -> int:
        return len(self._filtered_results)

    def get_selected(self) -> int:
        return int(self.overlay.window.editor_controller._find_everything_selection_index)

    def get_activation_count(self) -> int:
        return int(self._activation_count)


class _SceneCase(_OverlayCase):
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._all_rows = [
            SimpleNamespace(scene_id=f"scenes/scene_{index}.json", display_name=f"Scene {index}", pack_name="core", is_recent=False)
            for index in range(3)
        ]
        self._filtered_rows = list(self._all_rows)
        self._query = ""
        self._selection = 0
        self._activation_count = 0
        self._texts: list[str] = []

        monkeypatch.setattr(scene_overlay_module, "draw_text_cached", lambda text, *args, **kwargs: self._texts.append(str(text)))

        controller = SimpleNamespace(
            active=True,
            scene_browser_active=True,
            scene_browser_query="",
            scene_browser_index=0,
            dock=SimpleNamespace(get_snapshot=lambda: SimpleNamespace(left_tab="Scene")),
        )

        def _refresh() -> None:
            q = str(controller.scene_browser_query or "").lower().strip()
            if not q:
                self._filtered_rows = list(self._all_rows)
            else:
                self._filtered_rows = [row for row in self._all_rows if q in row.display_name.lower() or q in row.scene_id.lower()]
            if self._filtered_rows:
                controller.scene_browser_index = max(0, min(int(controller.scene_browser_index), len(self._filtered_rows) - 1))
            else:
                controller.scene_browser_index = 0

        def _rows() -> list[Any]:
            return list(self._filtered_rows)

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
            _refresh()

        def _open_selected() -> bool:
            self._activation_count += 1
            return True

        controller._refresh_scene_browser_rows = _refresh
        controller._scene_browser_rows = _rows
        controller._scene_browser_layout = _layout
        controller._scene_browser_clamp_index = _clamp
        controller._scene_browser_open_selected = _open_selected

        window = SimpleNamespace(width=1280, height=720, editor_controller=controller)
        overlay = SceneBrowserOverlay(window)  # type: ignore[arg-type]
        super().__init__(overlay=overlay, text_sink=self._texts)
        _refresh()

    @property
    def empty_text(self) -> str:
        return "(No scenes)"

    def set_nonempty(self, selected_index: int = 0) -> None:
        controller = self.overlay.window.editor_controller
        controller.scene_browser_query = ""
        controller._refresh_scene_browser_rows()
        controller.scene_browser_index = max(0, min(int(selected_index), max(0, len(self._filtered_rows) - 1)))

    def set_empty(self) -> None:
        controller = self.overlay.window.editor_controller
        controller.scene_browser_query = "___none___"
        controller._refresh_scene_browser_rows()

    def get_count(self) -> int:
        return len(self._filtered_rows)

    def get_selected(self) -> int:
        return int(self.overlay.window.editor_controller.scene_browser_index)

    def get_activation_count(self) -> int:
        return int(self._activation_count)


class _KeybindsCase(_OverlayCase):
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._all_rows = tuple(
            KeybindRow(
                scope="global",
                action_id=f"editor.action_{index}",
                title=f"Action {index}",
                shortcut_effective=f"Ctrl+{index}",
                shortcut_default=f"Ctrl+{index}",
                has_override=False,
                conflict_ids=(),
            )
            for index in range(3)
        )
        self._activation_count = 0
        self._texts: list[str] = []

        def _draw_text(_cache: Any, *args: Any, **kwargs: Any) -> None:
            text = kwargs.get("text")
            if text is None and args:
                text = args[0]
            self._texts.append(str(text or ""))

        monkeypatch.setattr(keybinds_overlay_module, "draw_text", _draw_text)

        state = KeybindsState(visible=True, query="", selected_index=0, staged_overrides={})
        controller = SimpleNamespace(state=state)

        def _visible_rows() -> tuple[KeybindRow, ...]:
            q = str(controller.state.query or "").lower().strip()
            if not q:
                return self._all_rows
            return tuple(row for row in self._all_rows if q in row.title.lower() or q in row.action_id.lower())

        def _set_query(text: str) -> None:
            controller.state = replace(controller.state, query=str(text or ""), selected_index=0)

        def _set_selected(index: int) -> None:
            rows = _visible_rows()
            if not rows:
                controller.state = replace(controller.state, selected_index=-1)
                return
            clamped = max(0, min(int(index), len(rows) - 1))
            controller.state = replace(controller.state, selected_index=clamped)

        def _start_recording() -> None:
            self._activation_count += 1

        controller.set_query = _set_query
        controller.set_selected_index = _set_selected
        controller.start_recording_selected = _start_recording
        controller.visible_rows = _visible_rows()

        def _get_data(_controller: Any, **_kwargs: Any) -> dict[str, Any]:
            rows = _visible_rows()
            controller.visible_rows = rows
            idx = int(controller.state.selected_index)
            selected_item = None
            if rows and 0 <= idx < len(rows):
                row = rows[idx]
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
                "selected_index": int(controller.state.selected_index),
                "selected_item": selected_item,
                "scope_filter": "all",
                "show_conflicts_only": False,
                "hint_text": "Keybinds",
            }

        monkeypatch.setattr(keybinds_overlay_module, "get_keybinds_ui_data", _get_data)

        editor = SimpleNamespace(keybinds=controller)
        window = SimpleNamespace(width=1280, height=720, editor_controller=editor, text_cache=None)
        overlay = KeybindsOverlay(window)  # type: ignore[arg-type]
        overlay.visible = True
        super().__init__(overlay=overlay, text_sink=self._texts)

    @property
    def empty_text(self) -> str:
        return "(No keybindings)"

    def set_nonempty(self, selected_index: int = 0) -> None:
        controller = self.overlay.window.editor_controller.keybinds
        controller.set_query("")
        controller.set_selected_index(selected_index)

    def set_empty(self) -> None:
        controller = self.overlay.window.editor_controller.keybinds
        controller.set_query("___none___")

    def get_count(self) -> int:
        controller = self.overlay.window.editor_controller.keybinds
        return len(tuple(controller.visible_rows))

    def get_selected(self) -> int:
        controller = self.overlay.window.editor_controller.keybinds
        return int(controller.state.selected_index)

    def get_activation_count(self) -> int:
        return int(self._activation_count)


class _AssetCase(_OverlayCase):
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._all_rows = [
            SimpleNamespace(display_name=f"asset_{index}.png", kind="image", rel_path=f"assets/a_{index}.png")
            for index in range(3)
        ]
        self._filtered_rows = list(self._all_rows)
        self._activation_count = 0
        self._query = ""
        self._texts: list[str] = []

        monkeypatch.setattr(asset_overlay_module, "draw_text_cached", lambda text, *args, **kwargs: self._texts.append(str(text)))

        search = SimpleNamespace()
        search.get_assets_search = lambda: str(self._query)

        controller = SimpleNamespace(
            active=True,
            asset_browser_active=True,
            asset_browser_kind="All",
            asset_browser_selection_index=0,
            _asset_browser_filtered_rows=list(self._filtered_rows),
            search=search,
            dock=SimpleNamespace(get_snapshot=lambda: SimpleNamespace(right_tab="Assets")),
        )

        def _set_filter(text: str) -> None:
            self._query = str(text or "")
            q = self._query.lower().strip()
            if not q:
                self._filtered_rows = list(self._all_rows)
            else:
                self._filtered_rows = [row for row in self._all_rows if q in row.display_name.lower() or q in row.rel_path.lower()]
            controller._asset_browser_filtered_rows = list(self._filtered_rows)
            if self._filtered_rows:
                controller.asset_browser_selection_index = max(0, min(int(controller.asset_browser_selection_index), len(self._filtered_rows) - 1))
            else:
                controller.asset_browser_selection_index = 0

        def _activate() -> None:
            self._activation_count += 1

        controller.set_asset_browser_filter = _set_filter
        controller._activate_selected_asset = _activate

        window = SimpleNamespace(width=1280, height=720, editor_controller=controller)
        overlay = AssetBrowserOverlay(window)  # type: ignore[arg-type]
        super().__init__(overlay=overlay, text_sink=self._texts)
        _set_filter("")

    @property
    def empty_text(self) -> str:
        return "(No assets)"

    def set_nonempty(self, selected_index: int = 0) -> None:
        controller = self.overlay.window.editor_controller
        controller.set_asset_browser_filter("")
        controller.asset_browser_selection_index = max(0, min(int(selected_index), max(0, len(self._filtered_rows) - 1)))

    def set_empty(self) -> None:
        self.overlay.window.editor_controller.set_asset_browser_filter("___none___")

    def get_count(self) -> int:
        return len(self._filtered_rows)

    def get_selected(self) -> int:
        return int(self.overlay.window.editor_controller.asset_browser_selection_index)

    def get_activation_count(self) -> int:
        return int(self._activation_count)


@pytest.mark.parametrize(
    "case_factory",
    (
        _FindCase,
        _SceneCase,
        _KeybindsCase,
        _AssetCase,
    ),
)
def test_widgetized_overlay_empty_and_status_rows_are_deterministic(
    monkeypatch: pytest.MonkeyPatch,
    case_factory: type[_OverlayCase],
) -> None:
    _stub_overlay_draw(monkeypatch)
    case = case_factory(monkeypatch)
    overlay = case.overlay

    overlay.reset_for_open()
    case.set_empty()
    case.draw()
    assert case.empty_text in case.text_sink
    assert "Results: 0" in case.text_sink

    case.set_nonempty(selected_index=1)
    case.draw()
    total = case.get_count()
    selected = max(0, min(case.get_selected(), max(0, total - 1))) + 1
    assert f"Results: {total}  Selected: {selected}/{total}" in case.text_sink


def test_find_everything_includes_deterministic_shortcuts_hint_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_overlay_draw(monkeypatch)
    case = _FindCase(monkeypatch)
    case.overlay.reset_for_open()
    case.set_nonempty(selected_index=1)
    case.draw()
    assert "Hints: Tab focus | Ctrl+N/P nav | Ctrl+Enter activate | Enter activates in results" in case.text_sink


@pytest.mark.parametrize(
    "case_factory",
    (
        _SceneCase,
        _KeybindsCase,
        _AssetCase,
    ),
)
def test_remaining_widgetized_overlays_include_deterministic_shortcuts_hint_row(
    monkeypatch: pytest.MonkeyPatch,
    case_factory: type[_OverlayCase],
) -> None:
    _stub_overlay_draw(monkeypatch)
    case = case_factory(monkeypatch)
    case.overlay.reset_for_open()
    case.set_nonempty(selected_index=1)
    case.draw()
    hint_row = "Hints: Tab focus | Ctrl+N/P nav | Ctrl+Enter activate | Enter activates in results"
    assert case.text_sink.count(hint_row) == 1


@pytest.mark.parametrize(
    "case_factory",
    (
        _FindCase,
        _SceneCase,
        _KeybindsCase,
        _AssetCase,
    ),
)
def test_widgetized_overlay_bounds_and_enter_gating_smoke(
    monkeypatch: pytest.MonkeyPatch,
    case_factory: type[_OverlayCase],
) -> None:
    _stub_overlay_draw(monkeypatch)
    case = case_factory(monkeypatch)
    overlay = case.overlay

    overlay.reset_for_open()
    case.set_nonempty(selected_index=0)
    case.draw()

    activation_before_input = case.get_activation_count()
    assert overlay.on_key_enter() is True
    assert case.get_activation_count() == activation_before_input

    assert overlay.toggle_focus() is True
    for _ in range(12):
        assert overlay.handle_navigation_key(optional_arcade.arcade.key.DOWN) is True

    count = case.get_count()
    selected = case.get_selected()
    assert count >= 1
    assert 0 <= selected < count

    activation_before_results = case.get_activation_count()
    assert overlay.on_key_enter() is True
    assert case.get_activation_count() == activation_before_results + 1
