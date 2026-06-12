"""Integration tests for EditorWorkspaceController persistence wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine.editor.editor_history_controller import EditorHistoryController
from engine.editor.editor_workspace_controller import EditorWorkspaceController
from engine.workspace_settings import load_workspace
from tests._dock_stub import make_dock_stub
from tests._search_stub import attach_search_stub


class _StubPanels:
    def __init__(self, open_: bool = False) -> None:
        self._open = open_

    def is_command_palette_open(self) -> bool:
        return self._open

    def open_command_palette(self) -> None:
        self._open = True

    def close_command_palette(self) -> None:
        self._open = False


class _StubProblems:
    def __init__(self) -> None:
        self.query = ""

    def set_query(self, text: str) -> None:
        self.query = text


class _StubProjectExplorer:
    def __init__(self) -> None:
        self.search_query = ""
        self.recents_payload: list[dict[str, str]] = []

    def set_query(self, text: str) -> None:
        self.search_query = text

    def set_recents(self, recents: object) -> None:
        if isinstance(recents, list):
            self.recents_payload = list(recents)

    def get_recents_payload(self) -> list[dict[str, str]]:
        return list(self.recents_payload)


class _StubWindow:
    def __init__(self) -> None:
        self.current_scene_key = "scene_default"
        self.camera = MagicMock()
        self.camera.position = (0.0, 0.0)
        self.load_scene = MagicMock()


class _StubEditor:
    def __init__(self, repo_root: Path) -> None:
        self.window = _StubWindow()
        self._repo_root_override = repo_root
        self._get_repo_root = lambda: repo_root

        self.entity_panels_active = False
        self.scene_switcher_active = False
        self.scene_browser_active = False
        self.asset_browser_active = False
        self.asset_browser_filter = ""
        self.asset_browser_kind = "All"
        self.entity_panels_focus = "outliner"
        self.dock = make_dock_stub(left_tab="Outliner", right_tab="Inspector")
        self._ghost_originals_enabled = True
        self._ghost_originals_alpha = 90
        self._ghost_originals_dim_scale = 0.65
        self._hd2d_default_preset_id = None
        self._hd2d_batch_radius_px = 96
        self.lights_tool_active = False
        self.occluder_tool_active = False

        self.panels = _StubPanels()
        self.problems = _StubProblems()
        self.project_explorer = _StubProjectExplorer()
        self.refresh_asset_browser_calls = 0
        self.history = EditorHistoryController(self)
        self.search = attach_search_stub(self)

    def refresh_asset_browser(self) -> None:
        self.refresh_asset_browser_calls += 1

    def _refresh_entity_panels_list(self) -> None:
        return None

    def _project_explorer_recent_payloads(self) -> list[dict[str, str]]:
        return self.project_explorer.get_recents_payload()


def test_save_and_load_workspace_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYGBAG", raising=False)
    editor = _StubEditor(tmp_path)
    editor.entity_panels_active = True
    editor.scene_switcher_active = True
    editor.asset_browser_active = True
    editor.asset_browser_filter = "tree"
    editor.asset_browser_kind = "All"
    editor.search.set_outliner_search("player", autosave=False)
    editor.search.set_assets_search("rock")
    editor.history.set_search_text("undo")
    editor.problems.query = "light"
    editor.entity_panels_focus = "inspector"
    editor.dock.left_tab = "Project"
    editor.dock.right_tab = "Assets"
    editor.dock.set_left_width(280)
    editor.dock.set_right_width(360)
    editor.dock.set_left_collapsed(True)
    editor.dock.set_right_collapsed(False)
    editor.dock.set_viewport_maximized(True)
    editor._ghost_originals_enabled = False
    editor._ghost_originals_alpha = 120
    editor._ghost_originals_dim_scale = 0.5
    editor._hd2d_default_preset_id = "soft"
    editor.lights_tool_active = True
    editor.window.current_scene_key = "scene_saved"
    editor.window.camera.position = (12.0, 34.0)

    ctl = EditorWorkspaceController(editor)
    ctl.save_workspace()

    loaded = load_workspace(tmp_path)
    assert loaded.entity_panels_open is True
    assert loaded.scene_switcher_open is True
    assert loaded.asset_browser_filter == "tree"
    assert loaded.outliner_search == "player"
    assert loaded.assets_search == "rock"
    assert loaded.history_search == "undo"
    assert loaded.problems_search == "light"
    assert loaded.outliner_focus == "inspector"
    assert loaded.left_dock_tab == "Project"
    assert loaded.right_dock_tab == "Assets"
    assert loaded.dock_left_w == 280
    assert loaded.dock_right_w == 360
    assert loaded.dock_left_collapsed is True
    assert loaded.viewport_maximized is True
    assert loaded.ghost_originals_enabled is False
    assert loaded.ghost_originals_alpha == 120
    assert loaded.ghost_originals_dim_scale == 0.5
    assert loaded.light_occluder_tool == "light"
    assert loaded.last_scene_id == "scene_saved"
    assert loaded.last_camera_center == [12.0, 34.0]

    editor2 = _StubEditor(tmp_path)
    ctl2 = EditorWorkspaceController(editor2)
    ctl2.load_workspace()

    assert editor2.entity_panels_active is True
    assert editor2.scene_switcher_active is True
    assert editor2.asset_browser_filter == "tree"
    assert editor2.search.get_outliner_search() == "player"
    assert editor2.search.get_assets_search() == "rock"
    assert editor2.history.get_search_text() == "undo"
    assert editor2.problems.query == "light"
    assert editor2.entity_panels_focus == "inspector"
    assert editor2.dock.left_tab == "Project"
    assert editor2.dock.right_tab == "Assets"
    assert editor2.dock.get_left_width() == 280
    assert editor2.dock.get_right_width() == 360
    assert editor2.dock.get_left_collapsed() is True
    assert editor2.dock.get_viewport_maximized() is True
    assert editor2._ghost_originals_enabled is False
    assert editor2._ghost_originals_alpha == 120
    assert editor2._ghost_originals_dim_scale == 0.5
    assert editor2.lights_tool_active is False
    assert editor2.occluder_tool_active is False


def test_save_workspace_web_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYGBAG", "1")
    editor = _StubEditor(tmp_path)
    ctl = EditorWorkspaceController(editor)
    ctl.save_workspace()
    assert not (tmp_path / "workspace.json").exists()
