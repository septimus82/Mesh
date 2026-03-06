from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.editor.editor_dock_controller import EditorDockController
from engine.editor.editor_ui_state import (
    EditorUiState,
    load_editor_ui_state,
    resolve_editor_ui_state_path,
    save_editor_ui_state,
)

pytestmark = pytest.mark.fast


class _FakePanels:
    def __init__(self) -> None:
        self._command_palette_open = False

    def open_command_palette(self) -> None:
        self._command_palette_open = True

    def close_command_palette(self) -> None:
        self._command_palette_open = False

    def is_command_palette_open(self) -> bool:
        return self._command_palette_open


def _make_editor() -> SimpleNamespace:
    editor = SimpleNamespace(
        active=True,
        panels=_FakePanels(),
        scene_switcher_active=True,
        scene_browser_active=True,
        asset_browser_active=True,
        _autosave_workspace=lambda: None,
        _menu_active=None,
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
    return editor


def test_palette_command_includes_reset_ui_layout() -> None:
    from engine.command_palette import build_default_commands

    ids = [c.id for c in build_default_commands(object())]
    assert "palette.reset_ui_layout" in ids


def test_reset_ui_layout_clears_persisted_file_and_applies_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from engine import command_palette_registry as registry

    state_path = resolve_editor_ui_state_path(repo_root=tmp_path)
    save_editor_ui_state(
        EditorUiState(
            command_palette_open=True,
            scene_switcher_open=True,
            scene_browser_open=True,
            asset_browser_open=True,
            left_dock_tab="Project",
            right_dock_tab="Debug",
            dock_left_collapsed=True,
            dock_right_collapsed=True,
            viewport_maximized=True,
        ),
        path=state_path,
    )
    assert state_path.exists()
    monkeypatch.setenv("MESH_EDITOR_UI_STATE_PATH", str(state_path))

    editor = _make_editor()
    editor.panels.open_command_palette()
    editor.scene_switcher_active = True
    editor.scene_browser_active = True
    editor.asset_browser_active = True
    editor.dock.set_left_tab("Project", force=True)
    editor.dock.set_right_tab("Debug", force=True)
    editor.dock.set_left_collapsed(True)
    editor.dock.set_right_collapsed(True)
    editor.dock.set_viewport_maximized(True)

    window = SimpleNamespace(editor_controller=editor)
    registry.action_palette_reset_ui_layout(window, None)

    assert not state_path.exists()
    assert editor.panels.is_command_palette_open() is False
    assert editor.scene_switcher_active is False
    assert editor.scene_browser_active is False
    assert editor.asset_browser_active is False
    assert editor.dock.left_tab == "Outliner"
    assert editor.dock.right_tab == "Inspector"
    assert editor.dock.get_left_collapsed() is False
    assert editor.dock.get_right_collapsed() is False
    assert editor.dock.get_viewport_maximized() is False


def test_schema_mismatch_falls_back_and_self_heals(tmp_path: Path) -> None:
    state_path = tmp_path / ".mesh" / "editor_ui_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps({"schema_version": 999, "command_palette_open": True}, indent=2) + "\n",
        encoding="utf-8",
    )

    loaded = load_editor_ui_state(path=state_path, self_heal_schema_mismatch=True)
    assert loaded == EditorUiState()

    healed = json.loads(state_path.read_text(encoding="utf-8"))
    assert healed.get("schema_version") == 1
    assert healed.get("command_palette_open") is False
