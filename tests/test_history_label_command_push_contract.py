"""Contract tests for history label injection on command push."""

from __future__ import annotations

from types import SimpleNamespace

from engine.editor_controller import EditorModeController
from tests._typing import as_any


def _stub_controller() -> EditorModeController:
    controller = EditorModeController.__new__(EditorModeController)

    from engine.editor.editor_undo_controller import EditorUndoController
    controller.undo = EditorUndoController(controller)
    controller.undo_stack = []
    controller.redo_stack = []
    controller.window = SimpleNamespace()

    def _mark_dirty() -> None:
        return None

    as_any(controller)._mark_dirty = _mark_dirty
    return controller


def test_entity_command_pushes_labeled_history_entry() -> None:
    controller = _stub_controller()
    controller._push_command({"type": "AddEntity", "entity_name": "crate_01"})
    cmd = controller.undo_stack[0]
    assert cmd.get("action_id") == "editor.entity.add"
    assert cmd.get("label") == "Add Entity (entity:crate_01)"


def test_prefab_variant_command_pushes_labeled_history_entry() -> None:
    controller = _stub_controller()
    controller._push_command({"type": "EditPrefabOverride", "entity_id": "e1", "key": "x"})
    cmd = controller.undo_stack[0]
    assert cmd.get("action_id") == "editor.prefab.override.set"
    assert cmd.get("label") == "Edit Prefab Override (entity:e1, field:x)"


def test_field_edit_command_pushes_labeled_history_entry() -> None:
    controller = _stub_controller()
    controller._push_command(
        {
            "type": "InspectorEdit",
            "entity_id": "crate_01",
            "field_key": "x",
            "before": 1.0,
            "after": 2.0,
        }
    )
    cmd = controller.undo_stack[0]
    assert cmd.get("action_id") == "editor.entity.field"
    assert cmd.get("label") == "Set x - crate_01 (1 -> 2)"


def test_light_edit_command_pushes_labeled_history_entry() -> None:
    controller = _stub_controller()
    controller._push_command({"type": "EditLight", "index": 1, "field": "radius", "before": 120, "after": 140})
    cmd = controller.undo_stack[0]
    assert cmd.get("action_id") == "editor.light.edit"
    assert cmd.get("label") == "Set Light radius - light:1 (120 -> 140)"
