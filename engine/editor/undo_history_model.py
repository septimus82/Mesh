"""Pure model for undo history list.

Provides deterministic, headless-safe helpers for building history entries
from undo/redo stacks and resolving jump deltas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


HISTORY_LINE_HEIGHT = 18.0
HISTORY_PADDING = 8.0


@dataclass(frozen=True, slots=True)
class UndoEntry:
    """Undo history list entry."""

    index: int
    real_index: int
    label: str
    is_current: bool


_LABEL_MAP = {
    "MoveEntity": "MOVE",
    "MoveEntities": "MOVE",
    "RotateEntities": "ROTATE",
    "ScaleEntities": "SCALE",
    "AltDragDuplicate": "ALT-DUP",
    "EditOccluder": "OCCLUDER",
    "AddLight": "LIGHT",
    "MoveLight": "LIGHT",
    "EditLight": "LIGHT",
    "DeleteLight": "LIGHT",
    "SaveScene": "SAVE",
    "SaveSceneJson": "SAVE",
    "ChangeProperty": "PARAM",
    "AddEntity": "ENTITY",
    "DeleteEntity": "ENTITY",
    "RenameEntity": "RENAME",
    "EditShape": "SHAPE",
    "EditShapes": "SHAPE",
    "ResetPrefabOverride": "OVERRIDE",
    "ResetPrefabOverrides": "OVERRIDE",
    "PromotePrefabShapes": "SHAPE",
    "ModifyPatrolPath": "PATH",
    "ResizeZone": "ZONE",
    "ResizeHitbox": "HITBOX",
    "EditAnimation": "ANIM",
    "EditDialogue": "DIALOGUE",
    "PaintTile": "PAINT",
    "FixSceneIssue": "FIX",
    "FixSceneIssues": "FIX",
    "EditBackgroundPlanes": "BG",
}


def build_undo_history_entries(
    undo_stack: Iterable[dict[str, Any]] | None,
    redo_stack: Iterable[dict[str, Any]] | None,
) -> list[UndoEntry]:
    """Build history entries from undo/redo stacks.

    Newest entry is first in the returned list.
    """
    undo_items = list(undo_stack or [])
    redo_items = list(redo_stack or [])

    chronological = undo_items + list(reversed(redo_items))
    if not chronological:
        return []

    entries: list[UndoEntry] = []
    current_index = _resolve_current_index(len(undo_items), len(redo_items))

    display_index = 1
    for idx, cmd in enumerate(reversed(chronological)):
        label = _label_for_cmd(cmd)
        is_current = (current_index is not None and idx == current_index)
        entries.append(UndoEntry(index=display_index, real_index=idx, label=label, is_current=is_current))
        display_index += 1

    return entries


def clamp_history_cursor(cursor: int, count: int) -> int:
    if count <= 0:
        return -1
    if cursor < 0:
        return 0
    return max(0, min(cursor, count - 1))


def compute_history_window(cursor: int, count: int, max_visible: int) -> tuple[int, int]:
    if count <= 0 or max_visible <= 0:
        return (0, 0)
    start_idx = 0
    if cursor > max_visible / 2:
        start_idx = max(0, int(cursor - max_visible / 2))
    visible = min(count - start_idx, max_visible)
    return (start_idx, visible)


def resolve_jump_delta(entries: list[UndoEntry], cursor: int) -> int:
    """Return signed delta to reach the selected cursor.

    Negative = undo steps, positive = redo steps.
    """
    current_index = _find_current_index(entries)
    if current_index is None:
        if not entries:
            return 0
        current_index = len(entries)
    return current_index - cursor


def filter_undo_history_entries(entries: list[UndoEntry], query: str) -> list[UndoEntry]:
    """Filter history entries by search text.

    Uses case-insensitive substring match on label text.
    """
    text = str(query or "").strip().casefold()
    if not text:
        return list(entries)
    return [entry for entry in entries if text in entry.label.casefold()]


def _resolve_current_index(undo_count: int, redo_count: int) -> int | None:
    if undo_count <= 0:
        return None
    return redo_count


def _find_current_index(entries: list[UndoEntry]) -> int | None:
    for i, entry in enumerate(entries):
        if entry.is_current:
            return i
    return None


def _label_for_cmd(cmd: Any) -> str:
    if not isinstance(cmd, dict):
        return "CMD:UNKNOWN"
    label = cmd.get("label")
    if isinstance(label, str) and label.strip():
        return label
    action_id = cmd.get("action_id")
    if isinstance(action_id, str) and action_id.strip():
        from engine.editor.history_label_model import format_history_entry  # noqa: PLC0415

        action_title = cmd.get("action_title") if isinstance(cmd.get("action_title"), str) else None
        detail = cmd.get("detail") if isinstance(cmd.get("detail"), dict) else None
        return format_history_entry(action_id, action_title, detail)
    ctype = cmd.get("type")
    if isinstance(ctype, str):
        mapped = _LABEL_MAP.get(ctype)
        if mapped:
            return mapped
        return f"CMD:{ctype}"
    return "CMD:UNKNOWN"
