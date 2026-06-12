"""Integration tests for Project Explorer recents wiring."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from engine.editor.editor_project_explorer_actions_controller import (
    EditorProjectExplorerActionsController,
)
from engine.editor.project_explorer_model import ProjectExplorerRecentItem, ProjectRow
from engine.editor_controller import EditorModeController
from engine.workspace_settings import WorkspaceSettings
from tests._dock_stub import make_dock_stub
from tests._search_stub import attach_search_stub


@dataclass
class StubWindow:
    player_hud: object | None = None


class StubHud:
    def __init__(self) -> None:
        self.toasts: list[str] = []

    def enqueue_toast(self, text: str, seconds: float = 2.5) -> None:  # noqa: ARG002
        self.toasts.append(text)


from pathlib import Path

from engine.editor.editor_project_explorer_controller import ProjectExplorerController


class StubController:
    def __init__(self) -> None:
        self.window = StubWindow(player_hud=StubHud())
        self.project_explorer = ProjectExplorerController(Path("."))
        self.project_explorer.recents = []
        self.project_explorer_actions = EditorProjectExplorerActionsController(self)

        self.active = True
        self.dock = make_dock_stub(left_tab="Project")
        self._project_search = ""
        self.search = attach_search_stub(self)

        self.scene_calls: list[str] = []
        self.asset_calls: list[str] = []
        self.path_calls: list[str] = []
        self.autosave_calls: int = 0 # If this exists, need to verify
        # Ah, autosave_calls might be missing in the read block?
        # Let's check if autosave_calls is in the file.

    # Sync recents
    @property
    def _project_explorer_recents(self):
        return self.project_explorer.recents

    @_project_explorer_recents.setter
    def _project_explorer_recents(self, value):
        self.project_explorer.recents = value

    @property
    def _project_rows(self):
         return self.project_explorer.project_rows

    @_project_rows.setter
    def _project_rows(self, value):
         self.project_explorer.project_rows = value
         self.project_explorer.tree_rev += 1

    @property
    def _project_selected_index(self):
        return self.project_explorer.selected_index

    @_project_selected_index.setter
    def _project_selected_index(self, value):
        self.project_explorer.selected_index = value

    def _filter_project_explorer_rows(self) -> None:
        self.project_explorer.set_query(self._project_search)

    def _project_explorer_display_rows(self):
        self.project_explorer.set_query(self._project_search)
        self.project_explorer.ensure_rows()
        return list(self.project_explorer.cached_rows)

    def _project_explorer_selectable_rows(self):
        self.project_explorer.set_query(self._project_search)
        self.project_explorer.ensure_rows()
        return list(self.project_explorer.selectable_rows)

    def _activate_project_explorer_selected(self) -> bool:
        return EditorModeController._activate_project_explorer_selected(self)

    def _activate_project_recent(self, recent: ProjectExplorerRecentItem) -> bool:
        return EditorModeController._activate_project_recent(self, recent)

    def _clear_project_recents(self) -> bool:
        return EditorModeController._clear_project_recents(self)

    def _push_project_recent(self, kind: str, rel_path: str, label: str) -> None:
        return EditorModeController._push_project_recent(self, kind, rel_path, label)

    def _open_scene_by_id(self, scene_id: str) -> bool:
        self.scene_calls.append(scene_id)
        return True

    def _spawn_find_asset(self, asset_path: str) -> bool:
        self.asset_calls.append(asset_path)
        return True

    def _copy_find_asset_path(self, asset_path: str) -> bool:
        self.path_calls.append(asset_path)
        return True

    def _autosave_workspace(self) -> None:
        return

    def _refresh_project_explorer_rows(self) -> None:
        return EditorModeController._refresh_project_explorer_rows(self)


def test_push_recent_dedupes_and_bumps() -> None:
    ctrl = StubController()
    ctrl._push_project_recent("scene", "scenes/a.json", "a.json")
    ctrl._push_project_recent("scene", "scenes/b.json", "b.json")
    ctrl._push_project_recent("scene", "scenes/a.json", "a.json")
    recents = ctrl._project_explorer_recents
    assert [item.rel_path for item in recents] == ["scenes/a.json", "scenes/b.json"]


def test_recent_activation_routes_actions() -> None:
    ctrl = StubController()
    ctrl._project_explorer_recents = [
        ProjectExplorerRecentItem(kind="scene", rel_path="scenes/demo.json", label="demo.json"),
    ]
    ctrl._project_rows = [
        ProjectRow(rel_path="assets/a.png", name="a.png", depth=0, is_dir=False),
    ]
    ctrl._filter_project_explorer_rows()
    ctrl._project_selected_index = 0

    assert ctrl._activate_project_explorer_selected() is True
    assert ctrl.scene_calls == ["scenes/demo.json"]


def test_workspace_recents_roundtrip() -> None:
    settings = WorkspaceSettings(
        project_explorer_recents=[
            {"kind": "scene", "rel_path": "scenes/demo.json", "label": "demo.json"},
            {"kind": "asset", "rel_path": "assets/a.png", "label": "a.png"},
        ]
    )
    data = asdict(settings)
    loaded = WorkspaceSettings.from_dict(data)
    assert loaded.project_explorer_recents == settings.project_explorer_recents


def test_clear_recents_action_toasts_and_clears() -> None:
    ctrl = StubController()
    ctrl._project_explorer_recents = [
        ProjectExplorerRecentItem(kind="scene", rel_path="scenes/demo.json", label="demo.json"),
    ]
    ctrl._project_rows = [
        ProjectRow(rel_path="assets/a.png", name="a.png", depth=0, is_dir=False),
    ]
    ctrl._filter_project_explorer_rows()
    ctrl.project_explorer.ensure_rows()
    ctrl.project_explorer.handle_click(1)  # clear recents action after one recent

    assert ctrl._activate_project_explorer_selected() is True
    assert ctrl._project_explorer_recents == []
    assert ctrl.window.player_hud is not None
    assert any("Recents cleared" in toast for toast in ctrl.window.player_hud.toasts)


def test_clear_recents_no_recents_toast() -> None:
    ctrl = StubController()
    ctrl._project_rows = [
        ProjectRow(rel_path="assets/a.png", name="a.png", depth=0, is_dir=False),
    ]
    ctrl._filter_project_explorer_rows()
    ctrl.project_explorer.ensure_rows()
    ctrl.project_explorer.handle_click(0)  # clear recents action when no recents

    assert ctrl._activate_project_explorer_selected() is True
    assert ctrl.window.player_hud is not None
    assert any("No recents to clear" in toast for toast in ctrl.window.player_hud.toasts)
