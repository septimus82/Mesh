"""Contract tests for editor action registry."""

from __future__ import annotations

from unittest.mock import MagicMock

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
