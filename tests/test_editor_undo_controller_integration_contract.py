from __future__ import annotations

from types import SimpleNamespace

from engine.editor.editor_undo_controller import EditorUndoController


class _StubController:
    def __init__(self) -> None:
        self.reverted: list[str] = []
        self.applied: list[str] = []
        self.scene_dirty = False
        self.dirty_state = SimpleNamespace(is_dirty=False)

    def _revert_command(self, cmd: dict[str, object]) -> None:
        self.reverted.append(str(cmd.get("type")))

    def _apply_command(self, cmd: dict[str, object]) -> None:
        self.applied.append(str(cmd.get("type")))

    def _mark_dirty(self) -> None:
        self.scene_dirty = True
        self.dirty_state.is_dirty = True


def test_push_undo_redo_round_trip() -> None:
    ctrl = _StubController()
    undo = EditorUndoController(ctrl, max_history=3)

    undo.push({"type": "A", "label": "A"})
    undo.push({"type": "B", "label": "B"})
    assert len(undo.undo_stack) == 2
    assert undo.can_undo() is True

    assert undo.undo() is True
    assert ctrl.reverted == ["B"]
    assert len(undo.redo_stack) == 1

    assert undo.redo() is True
    assert ctrl.applied == ["B"]
    assert len(undo.redo_stack) == 0
    assert len(undo.undo_stack) == 2


def test_push_clears_redo_stack() -> None:
    ctrl = _StubController()
    undo = EditorUndoController(ctrl, max_history=5)

    undo.push({"type": "A", "label": "A"})
    undo.push({"type": "B", "label": "B"})
    undo.undo()
    assert len(undo.redo_stack) == 1

    undo.push({"type": "C", "label": "C"})
    assert len(undo.redo_stack) == 0
    assert [cmd.get("type") for cmd in undo.undo_stack] == ["A", "C"]
