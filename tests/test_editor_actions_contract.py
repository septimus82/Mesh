"""Contract tests for editor action registry."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from engine.editor import editor_actions
from engine.editor.editor_actions import get_editor_actions, run_editor_action
from tests._dock_stub import make_dock_stub
from engine.editor.menu_bar_model import build_menu_groups


def _stub_controller() -> MagicMock:
    controller = MagicMock()
    controller.selected_entity = None
    controller.undo_stack = []
    controller.redo_stack = []
    controller.scene_dirty = False
    from engine.editor.editor_undo_controller import EditorUndoController

    controller.undo = EditorUndoController(controller)
    return controller


def test_editor_actions_unique_ids() -> None:
    actions = get_editor_actions(None, None)
    ids = [action.id for action in actions]
    assert len(ids) == len(set(ids))


def test_editor_actions_deterministic_order() -> None:
    ids_a = [action.id for action in get_editor_actions(None, None)]
    ids_b = [action.id for action in get_editor_actions(None, None)]
    assert ids_a == ids_b


def test_menu_groups_include_expected_actions(monkeypatch) -> None:
    monkeypatch.delenv("PYGBAG", raising=False)
    controller = _stub_controller()
    window = MagicMock()
    groups = build_menu_groups(controller, window)
    group_map = {group.title: [item.id for item in group.items] for group in groups}

    assert "editor.scene.save" in group_map["File"]
    assert "editor.history.undo" in group_map["Edit"]
    assert "editor.entity_panels.toggle" in group_map["View"]
    assert "editor.panel.debug.toggle" in group_map["View"]
    assert "editor.light_tool.toggle" in group_map["Scene"]
    assert group_map["File"][:2] == ["editor.scene.save", "editor.scene_browser.open"]


def test_panel_toggle_actions_registered_in_order() -> None:
    expected = [
        "editor.panel.project_explorer.toggle",
        "editor.panel.outliner.toggle",
        "editor.panel.inspector.toggle",
        "editor.panel.history.toggle",
        "editor.panel.problems.toggle",
        "editor.panel.debug.toggle",
        "editor.panel.prefab_variant_editor.toggle",
    ]
    actions = get_editor_actions(None, None)
    panel_ids = [action.id for action in actions if action.id.startswith("editor.panel.")]
    assert panel_ids == expected


def test_panel_toggle_actions_toggle_collapsed_state() -> None:
    from types import SimpleNamespace
    from engine.editor.editor_actions import run_editor_action

    class _StubController:
        def __init__(self) -> None:
            self.active = True
            self.dock = make_dock_stub(left_tab="Outliner", right_tab="Inspector")

        def set_dock_tab(self, dock: str, tab: str) -> None:
            if dock == "left":
                self.dock.set_left_tab(tab, force=True)
                self.dock.set_left_collapsed(False)
            else:
                self.dock.set_right_tab(tab, force=True)
                self.dock.set_right_collapsed(False)

    controller = _StubController()
    window = SimpleNamespace(editor_controller=controller)

    assert run_editor_action("editor.panel.outliner.toggle", controller, window) is True
    assert controller.dock.get_left_collapsed() is True
    assert run_editor_action("editor.panel.outliner.toggle", controller, window) is True
    assert controller.dock.get_left_collapsed() is False

    assert run_editor_action("editor.panel.history.toggle", controller, window) is True
    assert controller.dock.right_tab == "History"
    assert run_editor_action("editor.panel.history.toggle", controller, window) is True
    assert controller.dock.get_right_collapsed() is True

    assert run_editor_action("editor.panel.debug.toggle", controller, window) is True
    assert controller.dock.right_tab == "Debug"


def test_undo_redo_actions_registered_and_enabled_correctly() -> None:
    controller = _stub_controller()
    window = MagicMock()
    actions = get_editor_actions(controller, window)
    by_id = {action.id: action for action in actions}

    assert "editor.history.undo" in by_id
    assert "editor.history.redo" in by_id
    assert by_id["editor.history.undo"].enabled(controller, window) is False
    assert by_id["editor.history.redo"].enabled(controller, window) is False

    controller.undo.push({"type": "test"})
    controller.undo.set_redo_stack([{"type": "test"}])
    assert by_id["editor.history.undo"].enabled(controller, window) is True
    assert by_id["editor.history.redo"].enabled(controller, window) is True


def test_ui_only_actions_do_not_push_history() -> None:
    class _StubController:
        def __init__(self) -> None:
            self.active = True
            self.dock = make_dock_stub(left_tab="Outliner", right_tab="Inspector")
            self.undo_stack: list[dict[str, object]] = []
            self.redo_stack: list[dict[str, object]] = []

        def set_dock_tab(self, dock: str, tab: str) -> None:
            if dock == "left":
                self.dock.set_left_tab(tab, force=True)
                self.dock.set_left_collapsed(False)
            else:
                self.dock.set_right_tab(tab, force=True)
                self.dock.set_right_collapsed(False)

        def _push_command(self, cmd: dict[str, object]) -> None:
            self.undo_stack.append(cmd)
            self.redo_stack.clear()

    controller = _StubController()
    window = MagicMock(editor_controller=controller)

    assert run_editor_action("editor.panel.inspector.toggle", controller, window) is True
    assert controller.undo_stack == []


@pytest.mark.fast
def test_selection_action_symbols_remain_callable() -> None:
    expected = [
        "_action_align_left",
        "_action_align_right",
        "_action_align_top",
        "_action_align_bottom",
        "_action_align_center_horizontal",
        "_action_align_center_vertical",
        "_action_distribute_horizontal",
        "_action_distribute_vertical",
        "_duplicate",
        "_delete",
    ]
    for name in expected:
        assert callable(getattr(editor_actions, name, None)), f"Missing or non-callable: {name}"


@pytest.mark.fast
def test_entity_prefab_action_symbols_remain_callable() -> None:
    expected = [
        "_enabled_entity_selected",
        "_enabled_entity_has_overrides",
        "_enabled_hd2d_clipboard_has_data",
        "_action_toggle_entity_shadow_enabled",
        "_action_toggle_entity_shadow_contact_enabled",
        "_action_toggle_entity_shadow_ao_enabled",
        "_action_toggle_entity_depth_tint_enabled",
        "_action_toggle_entity_outline_enabled",
        "_action_adjust_entity_depth_tint_strength_up",
        "_action_adjust_entity_depth_tint_strength_down",
        "_action_adjust_entity_outline_strength_up",
        "_action_adjust_entity_outline_strength_down",
        "_action_adjust_entity_outline_radius_up",
        "_action_adjust_entity_outline_radius_down",
        "_copy_entity_hd2d_overrides",
        "_paste_entity_hd2d_overrides",
        "_paste_replace_entity_hd2d_overrides",
        "_clear_all_entity_hd2d_overrides",
        "_batch_paste_hd2d_overrides_merge",
        "_batch_paste_hd2d_overrides_replace",
        "_action_adjust_hd2d_batch_radius_up",
        "_action_adjust_hd2d_batch_radius_down",
        "_reset_hd2d_batch_radius",
        "_toggle_entity_panels",
        "_toggle_prefab_palette",
    ]
    for name in expected:
        assert callable(getattr(editor_actions, name, None)), f"Missing or non-callable: {name}"


@pytest.mark.fast
def test_camera_view_action_symbols_remain_callable() -> None:
    expected = [
        "_set_dock_tab",
        "_toggle_dock_tab",
        "_toggle_inspector_panel",
        "_toggle_outliner_panel",
        "_toggle_history_panel",
        "_toggle_problems_panel",
        "_toggle_debug_panel",
        "_toggle_project_explorer_panel",
        "_toggle_left_dock",
        "_toggle_right_dock",
        "_toggle_viewport_maximized",
    ]
    for name in expected:
        assert callable(getattr(editor_actions, name, None)), f"Missing or non-callable: {name}"


@pytest.mark.fast
def test_planes_action_symbols_remain_callable() -> None:
    expected = [
        "_get_plane_state",
        "_get_selected_plane_id",
        "_enabled_plane_selected",
        "_get_sorted_plane_ids",
        "_enabled_scene_loaded",
        "_enabled_planes_exist",
        "_push_plane_command",
        "_apply_plane_update",
        "_action_planes_add",
        "_action_planes_duplicate",
        "_action_planes_remove",
        "_action_planes_move",
        "_action_planes_move_up",
        "_action_planes_move_down",
        "_action_planes_move_top",
        "_action_planes_move_bottom",
        "_action_planes_move_to_index",
        "_action_planes_toggle_repeat",
        "_action_planes_toggle_repeat_x",
        "_action_planes_toggle_repeat_y",
        "_action_planes_select",
        "_action_planes_select_prev",
        "_action_planes_select_next",
    ]
    for name in expected:
        assert callable(getattr(editor_actions, name, None)), f"Missing or non-callable: {name}"


@pytest.mark.fast
def test_history_action_symbols_remain_callable() -> None:
    expected = [
        "_enabled_can_undo",
        "_enabled_can_redo",
        "_undo",
        "_redo",
    ]
    for name in expected:
        assert callable(getattr(editor_actions, name, None)), f"Missing or non-callable: {name}"
