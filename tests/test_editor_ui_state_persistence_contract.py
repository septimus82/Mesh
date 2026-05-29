from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.editor.editor_dock_controller import EditorDockController
from engine.editor.editor_scene_browse_controller import EditorSceneBrowseController
from engine.editor.editor_search_controller import EditorSearchController
from engine.editor.editor_ui_state import (
    EditorUiState,
    apply_editor_ui_state,
    dump_ui_state,
    load_editor_ui_state,
    load_ui_state,
    resolve_editor_ui_state_path,
    save_editor_ui_state,
)
from engine.editor.editor_workspace_controller import EditorWorkspaceController
from engine.workspace_settings import WorkspaceSettings, save_workspace
from tests.test_editor_workspace_controller_integration_contract import _StubEditor

pytestmark = pytest.mark.fast


class _FakePanels:
    def __init__(self) -> None:
        self._command_palette_open = False

    def is_command_palette_open(self) -> bool:
        return self._command_palette_open

    def open_command_palette(self) -> None:
        self._command_palette_open = True

    def close_command_palette(self) -> None:
        self._command_palette_open = False

    def toggle_command_palette(self) -> bool:
        self._command_palette_open = not self._command_palette_open
        return self._command_palette_open

    def close_context_menu(self) -> None:
        return None


def _make_editor(repo_root: Path) -> SimpleNamespace:
    editor = SimpleNamespace(
        active=True,
        _repo_root_override=repo_root,
        _autosave_workspace=lambda: None,
        _menu_active=None,
        panels=_FakePanels(),
        scene_switcher_active=False,
        scene_switcher_query="",
        scene_switcher_index=0,
        scene_switcher_recent=[],
        _scene_switcher_cached=[],
        scene_browser_active=False,
        scene_browser_query="",
        scene_browser_index=0,
        _scene_browser_cached_rows=[],
        asset_browser_active=False,
        entity_panels_filter_active=False,
        entity_panels_active=False,
        entity_panels_focus="outliner",
        _entity_panels_selected_id_value=lambda: "",
        _refresh_entity_panels_list=lambda **_kwargs: None,
        refresh_asset_browser=lambda: None,
        history=SimpleNamespace(on_open_tab=lambda: None),
        problems=SimpleNamespace(close_preview=lambda _host: None),
        scan_scene_problems=lambda: None,
    )
    editor.dock = EditorDockController(session=None)
    editor.search = EditorSearchController(editor, ui_flow=None)
    return editor


def test_editor_ui_state_dump_load_roundtrip() -> None:
    original = EditorUiState(
        command_palette_open=True,
        scene_switcher_open=True,
        scene_browser_open=False,
        asset_browser_open=True,
        left_dock_tab="Project",
        right_dock_tab="History",
        dock_left_collapsed=True,
        dock_right_collapsed=False,
        viewport_maximized=True,
    )
    payload = dump_ui_state(original)
    assert payload["schema_version"] == 1
    assert "problems_panel_open" in payload
    loaded = load_ui_state(payload)
    assert loaded == original


def test_editor_ui_state_missing_and_corrupt_returns_defaults(tmp_path: Path) -> None:
    state_path = tmp_path / ".mesh" / "editor_ui_state.json"
    assert load_editor_ui_state(path=state_path) == EditorUiState()

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{bad json", encoding="utf-8")
    assert load_editor_ui_state(path=state_path) == EditorUiState()


def test_editor_ui_state_save_is_deterministic(tmp_path: Path) -> None:
    state_path = tmp_path / ".mesh" / "editor_ui_state.json"
    state = EditorUiState(
        command_palette_open=True,
        scene_switcher_open=True,
        left_dock_tab="Scene",
        right_dock_tab="Debug",
    )
    save_editor_ui_state(state, path=state_path)
    first = state_path.read_text(encoding="utf-8")
    save_editor_ui_state(state, path=state_path)
    second = state_path.read_text(encoding="utf-8")
    assert first == second


def test_editor_ui_state_toggle_integration_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    editor = _make_editor(tmp_path)
    scene_browse = EditorSceneBrowseController(editor)
    monkeypatch.setattr(scene_browse, "refresh_scene_switcher_items", lambda: None)

    assert editor.search.toggle_command_palette() is True
    assert scene_browse.toggle_scene_switcher() is True
    editor.dock.set_right_tab("Problems", force=True)
    editor.dock.toggle_left_dock(editor)
    editor.dock.toggle_viewport_maximized(editor)

    state_path = resolve_editor_ui_state_path(repo_root=tmp_path)
    assert state_path.exists()
    loaded = load_editor_ui_state(path=state_path)

    editor2 = _make_editor(tmp_path)
    apply_editor_ui_state(editor2, loaded)
    assert editor2.panels.is_command_palette_open() is True
    assert editor2.scene_switcher_active is True
    assert editor2.scene_browser_active is False
    assert editor2.asset_browser_active is False
    assert loaded.problems_panel_open is True
    assert editor2.dock.right_tab == "Problems"
    assert editor2.dock.get_viewport_maximized() is True
    assert editor2.dock.get_left_collapsed() is True
    assert editor2.dock.get_right_collapsed() is False


def test_persisted_asset_browser_open_restores_closed(tmp_path: Path) -> None:
    save_workspace(tmp_path, WorkspaceSettings(asset_browser_open=True))

    workspace_editor = _StubEditor(tmp_path)
    EditorWorkspaceController(workspace_editor).load_workspace()
    assert workspace_editor.asset_browser_active is False
    assert workspace_editor.refresh_asset_browser_calls == 0

    ui_state_editor = _make_editor(tmp_path)
    apply_editor_ui_state(ui_state_editor, EditorUiState(asset_browser_open=True))
    assert ui_state_editor.asset_browser_active is False


def test_persisted_workspace_interaction_modes_restore_neutral(tmp_path: Path) -> None:
    save_workspace(tmp_path, WorkspaceSettings(asset_browser_open=True, light_occluder_tool="light"))

    editor = _StubEditor(tmp_path)
    EditorWorkspaceController(editor).load_workspace()

    assert editor.asset_browser_active is False
    assert editor.lights_tool_active is False
    assert editor.occluder_tool_active is False
