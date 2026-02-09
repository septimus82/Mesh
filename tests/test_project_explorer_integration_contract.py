"""Integration tests for Project Explorer controller wiring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from engine.editor.project_explorer_model import ProjectRow
from engine.editor_controller import EditorModeController
from engine.editor.editor_project_explorer_actions_controller import (
    EditorProjectExplorerActionsController,
)
from tests._dock_stub import make_dock_stub
from tests._search_stub import attach_search_stub


class StubHud:
    def __init__(self) -> None:
        self.toasts: list[str] = []

    def enqueue_toast(self, text: str, seconds: float = 2.5) -> None:  # noqa: ARG002
        self.toasts.append(text)


@dataclass
class StubWindow:
    player_hud: StubHud | None = None
    width: int = 1280
    height: int = 720



from engine.editor.editor_project_explorer_controller import ProjectExplorerController
from pathlib import Path

class StubController:
    def __init__(self, rows: list[ProjectRow]) -> None:
        self.window = StubWindow(player_hud=StubHud())
        self.active = True
        self.dock = make_dock_stub(left_tab="Project")
        
        self.project_explorer = ProjectExplorerController(Path("."))
        self.project_explorer.project_rows = list(rows)
        self.project_explorer.tree_rev = 1
        
        self.project_explorer.ensure_rows()
        self.project_explorer_actions = EditorProjectExplorerActionsController(self)

        # Legacy fields redirection (if tests access them directly)
        # But tests seem to access _project_selected_index.
        # I should probably use properties or update tests.
        # But for now, let's see if StubController usages can just be updated or if I can sync state.
        
        self._project_search = ""
        self.search = attach_search_stub(self)
        
        # Mocks
        self.scene_calls: list[str] = []
        self.asset_calls: list[str] = []

    @property
    def _project_selected_index(self):
        return self.project_explorer.selected_index
    
    @_project_selected_index.setter
    def _project_selected_index(self, value):
        self.project_explorer.selected_index = value
        
    @property
    def _project_rows(self):
        return self.project_explorer.project_rows
    
    @_project_rows.setter
    def _project_rows(self, value):
        self.project_explorer.project_rows = value
        

    def _filter_project_explorer_rows(self) -> None:
        self.project_explorer.set_query(self._project_search)

    def _project_explorer_display_rows(self) -> list:
        self.project_explorer.set_query(self._project_search)
        self.project_explorer.ensure_rows()
        return list(self.project_explorer.cached_rows)

    def _project_explorer_selectable_rows(self) -> list:
        self.project_explorer.set_query(self._project_search)
        self.project_explorer.ensure_rows()
        return list(self.project_explorer.selectable_rows)

    def _activate_project_explorer_selected(self) -> bool:
        return EditorModeController._activate_project_explorer_selected(self)

    def _clear_project_recents(self) -> bool:
        return EditorModeController._clear_project_recents(self)

    def _push_project_recent(self, kind: str, rel_path: str, label: str) -> None:
        return EditorModeController._push_project_recent(self, kind, rel_path, label)

    def _project_explorer_recent_payloads(self) -> list[dict[str, str]]:
        return []

    def _autosave_workspace(self) -> None:
        return

    def _refresh_project_explorer_rows(self) -> None:
        return EditorModeController._refresh_project_explorer_rows(self)

    def _open_scene_by_id(self, scene_id: str) -> bool:
        self.scene_calls.append(scene_id)
        return True

    def _spawn_find_asset(self, asset_path: str) -> bool:
        self.asset_calls.append(asset_path)
        return True

    def _copy_find_asset_path(self, asset_path: str) -> bool:
        hud = self.window.player_hud
        if hud is not None:
            hud.enqueue_toast(f"Copied path: {asset_path}")
        return True


def test_project_explorer_scene_activation() -> None:
    rows = [
        ProjectRow(rel_path="packs/core/scenes/demo.json", name="demo.json", depth=2, is_dir=False),
        ProjectRow(rel_path="assets/props/tree.png", name="tree.png", depth=2, is_dir=False),
        ProjectRow(rel_path="config.json", name="config.json", depth=0, is_dir=False),
    ]
    ctrl = StubController(rows)
    ctrl._project_selected_index = 1
    ctrl._filter_project_explorer_rows()
    assert ctrl._activate_project_explorer_selected() is True
    assert ctrl.scene_calls == ["packs/core/scenes/demo.json"]


def test_project_explorer_asset_activation() -> None:
    rows = [
        ProjectRow(rel_path="packs/core/scenes/demo.json", name="demo.json", depth=2, is_dir=False),
        ProjectRow(rel_path="assets/props/tree.png", name="tree.png", depth=2, is_dir=False),
    ]
    ctrl = StubController(rows)
    ctrl._project_selected_index = 2
    ctrl._filter_project_explorer_rows()
    assert ctrl._activate_project_explorer_selected() is True
    assert ctrl.asset_calls == ["assets/props/tree.png"]


def test_project_explorer_copy_path_toast() -> None:
    rows = [
        ProjectRow(rel_path="config.json", name="config.json", depth=0, is_dir=False),
    ]
    ctrl = StubController(rows)
    ctrl._project_selected_index = 1
    ctrl._filter_project_explorer_rows()
    assert ctrl._activate_project_explorer_selected() is True
    assert ctrl.window.player_hud is not None
    assert any("Copied path: config.json" == toast for toast in ctrl.window.player_hud.toasts)
