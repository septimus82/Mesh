from __future__ import annotations

from typing import Any, Iterable

from engine.logging_tools import get_logger

from engine.editor.editor_undo_model import (
    UndoEntry,
    UndoState,
    can_redo,
    can_undo,
    compute_visible_history,
    push_entry,
    redo_cursor,
    undo_cursor,
)

logger = get_logger(__name__)


class EditorUndoController:
    def __init__(self, controller: Any, max_history: int = 50) -> None:
        self._controller = controller
        self._max_history = int(max_history)
        self._undo_commands: list[dict[str, Any]] = []
        self._redo_commands: list[dict[str, Any]] = []
        self._state = UndoState(entries=tuple(), cursor=0, max_size=self._max_history)
        self._snapshot: UndoState | None = None
        self._rev = 0

    @property
    def undo_stack(self) -> list[dict[str, Any]]:
        return self._undo_commands

    @property
    def redo_stack(self) -> list[dict[str, Any]]:
        return self._redo_commands

    def set_undo_stack(self, values: Iterable[dict[str, Any]]) -> None:
        self._undo_commands = list(values)
        self._bump_rev()
        self._rebuild_state()

    def set_redo_stack(self, values: Iterable[dict[str, Any]]) -> None:
        self._redo_commands = list(values)
        self._bump_rev()
        self._rebuild_state()

    def push(self, cmd: dict[str, Any], *, label: str | None = None) -> None:
        if not isinstance(cmd, dict) or not cmd:
            return
        if self._state.cursor < len(self._state.entries):
            # Drop redo list when pushing new command.
            self._redo_commands = []
        self._undo_commands.append(cmd)
        if len(self._undo_commands) > self._max_history:
            overflow = len(self._undo_commands) - self._max_history
            del self._undo_commands[:overflow]
        self._bump_rev()
        entry_label = self._resolve_label(cmd, label)
        entry = UndoEntry(label=entry_label, rev=self._rev, meta=self._resolve_meta(cmd))
        self._state = push_entry(self._state, entry)
        self._snapshot = self._state
        self._mark_dirty()

    def can_undo(self) -> bool:
        return can_undo(self._state)

    def can_redo(self) -> bool:
        return can_redo(self._state)

    def undo(self) -> bool:
        editor = self._controller
        if not self._undo_commands:
            if getattr(editor, "feedback", None) is not None: editor.feedback.info("Nothing to undo")
            logger.info("[Editor] Nothing to undo.")
            return False
        cmd = self._undo_commands.pop()
        self._redo_commands.append(cmd)
        self._bump_rev()
        self._state = undo_cursor(self._state)
        self._snapshot = self._state
        self._revert_command(cmd)
        if getattr(editor, "feedback", None) is not None: editor.feedback.info(f"Undid: {self._resolve_label(cmd, None)}")
        logger.info("[Editor] Undid %s", cmd.get("type"))
        self._mark_dirty()
        return True

    def redo(self) -> bool:
        editor = self._controller
        if not self._redo_commands:
            if getattr(editor, "feedback", None) is not None: editor.feedback.info("Nothing to redo")
            logger.info("[Editor] Nothing to redo.")
            return False
        cmd = self._redo_commands.pop()
        self._undo_commands.append(cmd)
        self._bump_rev()
        self._state = redo_cursor(self._state)
        self._snapshot = self._state
        self._apply_command(cmd)
        if getattr(editor, "feedback", None) is not None: editor.feedback.info(f"Redid: {self._resolve_label(cmd, None)}")
        logger.info("[Editor] Redid %s", cmd.get("type"))
        self._mark_dirty()
        return True

    def clear(self) -> None:
        self._undo_commands = []
        self._redo_commands = []
        self._bump_rev()
        self._state = UndoState(entries=tuple(), cursor=0, max_size=self._max_history)
        self._snapshot = self._state

    def get_snapshot(self) -> UndoState:
        if self._snapshot is None:
            self._rebuild_state()
        return self._snapshot or self._state

    def get_history_rows(self, start: int, count: int) -> list[UndoEntry]:
        return compute_visible_history(self.get_snapshot(), start, count)

    def get_history_entries(self) -> list[Any]:
        from engine.editor.undo_history_model import build_undo_history_entries  # noqa: PLC0415

        return build_undo_history_entries(self._undo_commands, self._redo_commands)

    def _apply_command(self, cmd: dict[str, Any]) -> None:
        applier = getattr(self._controller, "_apply_command", None)
        if callable(applier):
            applier(cmd)

    def _revert_command(self, cmd: dict[str, Any]) -> None:
        revert = getattr(self._controller, "_revert_command", None)
        if callable(revert):
            revert(cmd)

    def _mark_dirty(self) -> None:
        marker = getattr(self._controller, "_mark_dirty", None)
        if callable(marker):
            marker()
            return
        setattr(self._controller, "scene_dirty", True)
        dirty_state = getattr(self._controller, "dirty_state", None)
        if dirty_state is not None and hasattr(dirty_state, "is_dirty"):
            dirty_state.is_dirty = True

    def _resolve_label(self, cmd: dict[str, Any], label: str | None) -> str:
        if isinstance(label, str) and label.strip():
            return label
        raw = cmd.get("label")
        if isinstance(raw, str) and raw.strip():
            return raw
        action_id = cmd.get("action_id")
        if isinstance(action_id, str) and action_id.strip():
            from engine.editor.history_label_model import format_history_entry  # noqa: PLC0415

            action_title = cmd.get("action_title") if isinstance(cmd.get("action_title"), str) else None
            detail = cmd.get("detail") if isinstance(cmd.get("detail"), dict) else None
            return format_history_entry(action_id, action_title, detail)
        cmd_type = cmd.get("type")
        if isinstance(cmd_type, str) and cmd_type.strip():
            return f"CMD:{cmd_type}"
        return "CMD:UNKNOWN"

    def _resolve_meta(self, cmd: dict[str, Any]) -> dict[str, object] | None:
        detail = cmd.get("detail")
        return detail if isinstance(detail, dict) else None

    def _bump_rev(self) -> None:
        self._rev += 1
        self._snapshot = None

    def _rebuild_state(self) -> None:
        entries: list[UndoEntry] = []
        chronological = list(self._undo_commands) + list(reversed(self._redo_commands))
        for cmd in chronological:
            entry = UndoEntry(
                label=self._resolve_label(cmd, None),
                rev=self._rev,
                meta=self._resolve_meta(cmd),
            )
            entries.append(entry)
        cursor = max(0, min(len(self._undo_commands), len(entries)))
        self._state = UndoState(entries=tuple(entries), cursor=cursor, max_size=self._max_history)
        self._snapshot = self._state
