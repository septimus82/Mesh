"""Integration tests for Find Everything controller wiring."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from pathlib import Path
from typing import Any

import pytest

from engine.editor.find_everything_model import FindItem, FindResult, filter_find_items, build_find_display_rows
from engine.editor.scene_lint_model import SceneLintIssue
from engine.editor_controller import EditorModeController
from tests._typing import as_any
from tests._session_stub import make_session_stub
from tests._dock_stub import make_dock_stub


@dataclass
class StubWindow:
    width: int = 1280
    height: int = 720
    editor_controller: object | None = None
    player_hud: object | None = None
    input: object | None = None


class StubController:
    def __init__(self, repo_root: Path) -> None:
        self.active = True
        self.window = StubWindow()
        self.session = make_session_stub()
        
        # UI Flow Controller
        from engine.editor.editor_ui_flow_controller import EditorUIFlowController
        self._ui_flow_ctl = EditorUIFlowController(self)
        from engine.editor.editor_search_controller import EditorSearchController
        self.search = EditorSearchController(self, self._ui_flow_ctl)
        
        # self._find_everything_open = False # Delegated
        # self._find_everything_query = "" # Delegated
        # self._find_everything_selection_index = 0 # Delegated
        # self._find_everything_cached_results: list[FindResult] = [] # Delegated
        
        self._find_items_override: list[FindItem] = []
        # self._find_asset_lookup: dict[str, object] = {} # Delegated
        self._asset_browser_cached_rows: list[Any] = []
        self.scene_switcher_recent: list[str] = []
        
        self._repo_root_override = repo_root
        self.dock = make_dock_stub(left_tab="Outliner", right_tab="Inspector")
        self.problems = SimpleNamespace(
            issues=[],
            selected_index=0,
            preview_open=False,
        )
        self.problems.set_issues = lambda items: setattr(self.problems, "issues", list(items))
        self.problems.set_selected_index = lambda idx: setattr(self.problems, "selected_index", idx)
        self.unsaved_confirm = SimpleNamespace(is_open=False)
        self.command_palette_active = False
        self.scene_browser_active = False
        self.asset_browser_active = False
        self.scene_switcher_active = False
        self.entity_panels_active = False
        self.palette_filter_active = False
        self.hierarchy_filter_active = False
        self.hierarchy_rename_active = False
        self.animation_edit_active = False
        self.inspector_edit_active = False
        self.entity_panels_filter_active = False
        self.window.editor_controller = self

        # HD2D preview state (stub - no actual scene to preview)
        self._hd2d_preview_active = False
        self._hd2d_preview_snapshot = None
        self._hd2d_preview_preset_id: str | None = None

        self.command_calls: list[str] = []
        self.scene_calls: list[str] = []
        self.entity_calls: list[str] = []
        self.asset_calls: list[str] = []

    def ui_get_palette_items(self) -> list[Any]:
        if self._find_items_override:
            return list(self._find_items_override)
        return []

    def ui_activate_command(self, cmd_id: str) -> bool:
        self.command_calls.append(cmd_id)
        return True

    def ui_activate_scene(self, scene_id: str) -> bool:
        self.scene_calls.append(scene_id)
        return True

    def ui_activate_entity(self, entity_id: str) -> bool:
        self.entity_calls.append(entity_id)
        return True

    def ui_activate_asset(self, asset_id: str) -> bool:
        self.asset_calls.append(asset_id)
        return True

    def ui_activate_problem(self, problem_id: str) -> bool:
        if self.problems.issues:
            # Logic from editor_controller.py: _activate_find_problem
            # It sets preview open and switches tab.
            self.problems.preview_open = True
            self.dock.right_tab = "Problems" 
            return True
        return False
    
    def ui_hd2d_preview(self, preset_id: str) -> None:
        self._hd2d_preview_active = True
        self._hd2d_preview_preset_id = preset_id

    def ui_hd2d_cancel_preview(self) -> None:
        self._hd2d_preview_active = False
        
    def ui_hd2d_commit(self, preset_id: str) -> bool:
        return True

    # Delegation Properties
    @property
    def _find_everything_open(self): return self._ui_flow_ctl.is_open
    @_find_everything_open.setter
    def _find_everything_open(self, v): self._ui_flow_ctl.is_open = v

    @property
    def _find_everything_query(self): return self._ui_flow_ctl.query
    @_find_everything_query.setter
    def _find_everything_query(self, v): self._ui_flow_ctl.query = v
    
    @property
    def _find_everything_selection_index(self): return self._ui_flow_ctl.selection_index
    @_find_everything_selection_index.setter
    def _find_everything_selection_index(self, v): self._ui_flow_ctl.selection_index = v
    
    @property
    def _find_everything_cached_results(self): return self._ui_flow_ctl.cached_results
    @_find_everything_cached_results.setter
    def _find_everything_cached_results(self, v): self._ui_flow_ctl.cached_results = v
    
    @property
    def _find_asset_lookup(self): return self._ui_flow_ctl.asset_lookup
    @_find_asset_lookup.setter
    def _find_asset_lookup(self, v): self._ui_flow_ctl.asset_lookup = v

    # Mock support for find_everything logic that expects these to exist if mocked
    @property
    def _find_everything_all_results(self): return self._ui_flow_ctl.all_results
    @_find_everything_all_results.setter
    def _find_everything_all_results(self, v): self._ui_flow_ctl.all_results = v
    
    @property
    def _find_everything_counts(self): return self._ui_flow_ctl.counts
    @_find_everything_counts.setter
    def _find_everything_counts(self, v): self._ui_flow_ctl.counts = v

    def _get_repo_root(self):
        return self._repo_root_override

    def _cancel_hd2d_preview(self) -> None:
        """Stub - cancel HD2D preview."""
        self._hd2d_preview_active = False
        self._hd2d_preview_snapshot = None
        self._hd2d_preview_preset_id = None

    def _maybe_preview_hd2d_from_selection(self) -> None:
        """Stub - no-op for tests without scene."""
        pass

    def toggle_find_everything(self) -> bool:
        return EditorModeController.toggle_find_everything(self)

    def close_find_everything(self) -> None:
        return EditorModeController.close_find_everything(self)

    def set_find_query(self, text: str) -> None:
        return EditorModeController.set_find_query(self, text)

    def move_find_selection(self, delta: int) -> None:
        return EditorModeController.move_find_selection(self, delta)

    def activate_find_selection(self) -> bool:
        return EditorModeController.activate_find_selection(self)

    def _refresh_find_everything_results(self) -> None:
        return EditorModeController._refresh_find_everything_results(self)

    def _build_find_everything_items(self) -> list[FindItem]:
        return EditorModeController._build_find_everything_items(self)

    def _get_find_everything_problems(self):
        return EditorModeController._get_find_everything_problems(self)

    def _handle_find_everything_input(self, key: int, modifiers: int) -> bool:
        return EditorModeController._handle_find_everything_input(self, key, modifiers)

    def get_filtered_problems(self):
        return list(self.problems.issues)

    def _clamp_problems_selection(self) -> None:
        return EditorModeController._clamp_problems_selection(self)

    def _open_problems_preview(self) -> bool:
        return EditorModeController._open_problems_preview(self)

    def _activate_find_command(self, command_id: str) -> bool:
        self.command_calls.append(command_id)
        return True

    def _activate_find_scene(self, scene_id: str) -> bool:
        self.scene_calls.append(scene_id)
        return True

    def _activate_find_entity(self, entity_id: str) -> bool:
        self.entity_calls.append(entity_id)
        return True

    def _activate_find_asset(self, asset_path: str) -> bool:
        self.asset_calls.append(asset_path)
        return True

    def _activate_find_problem(self, issue_id: str) -> bool:
        return EditorModeController._activate_find_problem(self, issue_id)


def test_toggle_and_query_updates_results(tmp_path: Path) -> None:
    ctrl = StubController(tmp_path)
    ctrl._find_items_override = [
        FindItem(kind="command", item_id="cmd.save", title="Save Scene", subtitle="", keywords=("save",)),
        FindItem(kind="scene", item_id="scn.1", title="Ridge Outpost", subtitle="", keywords=("ridge",)),
    ]

    assert ctrl.toggle_find_everything() is True
    assert ctrl._find_everything_open is True
    assert ctrl._find_everything_query == ""
    assert len(ctrl._find_everything_cached_results) == 2
    counts = getattr(ctrl, "_find_everything_counts", {})
    assert counts.get("total") == 2

    ctrl.set_find_query("ridge")
    assert len(ctrl._find_everything_cached_results) == 1
    assert ctrl._find_everything_cached_results[0].title.startswith("Scene:")

    display = build_find_display_rows(ctrl._find_everything_cached_results, ctrl._find_everything_counts)
    assert display
    assert display[-1].kind == "footer"


def test_activate_routes_to_correct_action(tmp_path: Path) -> None:
    ctrl = StubController(tmp_path)
    items = [
        FindItem(kind="command", item_id="cmd.save", title="Save Scene", subtitle="", keywords=()),
        FindItem(kind="scene", item_id="packs/demo.json", title="Demo", subtitle="", keywords=()),
        FindItem(kind="entity", item_id="player", title="player", subtitle="", keywords=()),
        FindItem(kind="asset", item_id="assets/props/tree.png", title="assets/props/tree.png", subtitle="", keywords=()),
    ]
    ctrl._find_items_override = items
    ctrl.toggle_find_everything()

    ctrl._find_everything_cached_results = filter_find_items(items, "", limit=10)

    ctrl._find_everything_selection_index = 0
    assert ctrl.activate_find_selection() is True
    assert ctrl.command_calls == ["cmd.save"]

    ctrl.toggle_find_everything()
    ctrl._find_everything_cached_results = filter_find_items(items, "", limit=10)
    ctrl._find_everything_selection_index = 1
    assert ctrl.activate_find_selection() is True
    assert ctrl.scene_calls == ["packs/demo.json"]

    ctrl.toggle_find_everything()
    ctrl._find_everything_cached_results = filter_find_items(items, "", limit=10)
    ctrl._find_everything_selection_index = 2
    assert ctrl.activate_find_selection() is True
    assert ctrl.entity_calls == ["player"]

    ctrl.toggle_find_everything()
    ctrl._find_everything_cached_results = filter_find_items(items, "", limit=10)
    ctrl._find_everything_selection_index = 3
    assert ctrl.activate_find_selection() is True
    assert ctrl.asset_calls == ["assets/props/tree.png"]


def test_activate_problem_opens_preview(tmp_path: Path) -> None:
    ctrl = StubController(tmp_path)
    issue = SceneLintIssue(
        issue_id="dup:1",
        kind="DUPLICATE_ID",
        message="Duplicate id",
        entity_id="dup",
        scene_id=None,
        severity="WARN",
        risk="safe",
        fix_kind="rename_id",
        fixable=True,
        meta={},
    )
    ctrl.problems.issues = [issue]
    item = FindItem(kind="problem", item_id="dup:1", title="Duplicate id", subtitle="DUPLICATE_ID", keywords=())
    ctrl._find_items_override = [item]
    ctrl.toggle_find_everything()
    ctrl._find_everything_cached_results = filter_find_items([item], "", limit=10)

    assert ctrl.activate_find_selection() is True
    assert ctrl.dock.right_tab == "Problems"
    assert ctrl.problems.selected_index == 0
    assert ctrl.problems.preview_open is True


def test_find_everything_ctrl_j_toggles(tmp_path: Path) -> None:
    from engine.editor_runtime import input as editor_input
    from engine import optional_arcade

    ctrl = StubController(tmp_path)
    assert ctrl._find_everything_open is False

    editor_input.handle_input(ctrl, optional_arcade.arcade.key.J, optional_arcade.arcade.key.MOD_CTRL)
    assert ctrl._find_everything_open is True

    editor_input.handle_input(ctrl, optional_arcade.arcade.key.J, optional_arcade.arcade.key.MOD_CTRL)
    assert ctrl._find_everything_open is False


def test_find_everything_hint_line_by_input_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from types import SimpleNamespace
    from engine.ui_overlays.find_everything_overlay import FindEverythingOverlay
    from engine import arcade_fallback as arcade_stub
    from engine import optional_arcade

    ctrl = StubController(tmp_path)
    ctrl._find_everything_open = True
    ctrl._find_everything_cached_results = [
        FindResult(kind="scene", item_id="s1", title="Scene: One", subtitle=""),
    ]
    ctrl._find_everything_counts = {"total": 1, "by_group": {"Scenes": 1, "Entities": 0, "Assets": 0, "Problems": 0, "Commands": 0}}

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)
    overlay = FindEverythingOverlay(as_any(ctrl.window))

    captured: list[str] = []

    def _capture(text: str, *_args, **_kwargs) -> None:
        captured.append(str(text))

    from engine.ui_overlays import find_everything_overlay as overlay_module
    monkeypatch.setattr(overlay_module, "draw_text_cached", _capture)
    ctrl.window.input = SimpleNamespace(input_source="keyboard_mouse")
    overlay.draw()
    assert "Enter: Open   Esc: Close   Up/Down: Navigate" in captured

    captured.clear()
    ctrl.window.input = SimpleNamespace(input_source="gamepad")
    overlay.draw()
    assert "A: Open   B: Close   D-pad: Navigate" in captured
