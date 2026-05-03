from __future__ import annotations

from dataclasses import dataclass, replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from engine.editor.editor_undo_controller import EditorUndoController


pytestmark = [pytest.mark.fast]


@dataclass(frozen=True, slots=True)
class _Emission:
    message: str
    ttl: float
    created_at: float
    count: int = 1


class _Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = float(value)

    def __call__(self) -> float:
        return self.value


class _StubFeedback:
    def __init__(self, clock: _Clock | None = None) -> None:
        self._clock = clock or _Clock()
        self._entries: tuple[_Emission, ...] = tuple()

    def info(self, message: str, *, ttl: float = 4.0) -> None:
        now = float(self._clock())
        if self._entries:
            last = self._entries[-1]
            if last.message == message and now - last.created_at <= 1.0:
                self._entries = self._entries[:-1] + (
                    replace(last, ttl=float(ttl), created_at=now, count=last.count + 1),
                )
                return
        self._entries = self._entries + (_Emission(str(message), float(ttl), now),)

    def pending(self) -> tuple[_Emission, ...]:
        return self._entries


class _StubController:
    def __init__(self, feedback: _StubFeedback | None = None) -> None:
        self.feedback = feedback or _StubFeedback()
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


def test_undo_non_empty_emits_feedback_and_logs() -> None:
    ctrl = _StubController()
    undo = EditorUndoController(ctrl, max_history=5)
    undo.push({"type": "Paint", "label": "Brush Stroke"})

    with patch("engine.editor.editor_undo_controller.logger.info") as log_info:
        assert undo.undo() is True

    pending = ctrl.feedback.pending()
    assert len(pending) == 1
    assert pending[0].message == "Undid: Brush Stroke"
    assert pending[0].ttl == 4.0
    log_info.assert_called_once_with("[Editor] Undid %s", "Paint")


def test_redo_non_empty_emits_feedback_and_logs() -> None:
    ctrl = _StubController()
    undo = EditorUndoController(ctrl, max_history=5)
    undo.push({"type": "Paint", "label": "Brush Stroke"})
    undo.undo()

    with patch("engine.editor.editor_undo_controller.logger.info") as log_info:
        assert undo.redo() is True

    pending = ctrl.feedback.pending()
    assert pending[-1].message == "Redid: Brush Stroke"
    assert pending[-1].ttl == 4.0
    log_info.assert_called_once_with("[Editor] Redid %s", "Paint")


def test_undo_empty_emits_feedback_and_returns_false() -> None:
    ctrl = _StubController()
    undo = EditorUndoController(ctrl, max_history=5)

    with patch("engine.editor.editor_undo_controller.logger.info") as log_info:
        assert undo.undo() is False

    pending = ctrl.feedback.pending()
    assert len(pending) == 1
    assert pending[0].message == "Nothing to undo"
    assert pending[0].ttl == 4.0
    log_info.assert_called_once_with("[Editor] Nothing to undo.")


def test_redo_empty_emits_feedback_and_returns_false() -> None:
    ctrl = _StubController()
    undo = EditorUndoController(ctrl, max_history=5)

    with patch("engine.editor.editor_undo_controller.logger.info") as log_info:
        assert undo.redo() is False

    pending = ctrl.feedback.pending()
    assert len(pending) == 1
    assert pending[0].message == "Nothing to redo"
    assert pending[0].ttl == 4.0
    log_info.assert_called_once_with("[Editor] Nothing to redo.")


def test_empty_undo_duplicate_feedback_collapses_within_one_second() -> None:
    clock = _Clock()
    feedback = _StubFeedback(clock)
    ctrl = _StubController(feedback)
    undo = EditorUndoController(ctrl, max_history=5)

    undo.undo()
    first = ctrl.feedback.pending()[0]
    clock.value += 0.5
    undo.undo()

    pending = ctrl.feedback.pending()
    assert len(pending) == 1
    assert pending[0].message == "Nothing to undo"
    assert pending[0].count == 2
    assert pending[0].created_at > first.created_at