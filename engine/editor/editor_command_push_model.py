"""Pure helpers for command push plumbing.

Provides pure functions for:
- Backfilling command dicts with action_id, detail, label
- Detecting no-op commands (if payloads are identical)
- Formatting default undo labels from command dicts

Import-safe and headless-safe. Does not depend on runtime state.
"""

from __future__ import annotations

from typing import Any


def compute_command_backfill(
    cmd: dict[str, Any],
    *,
    action_id_lookup: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Backfill a command dict with action_id, detail, label if missing.

    This function delegates to history_label_model for actual label building,
    but extracts the pure backfill logic from the controller.

    Args:
        cmd: The command dict (will be mutated).
        action_id_lookup: Optional mapping from command type to action_id.
            If None, uses history_label_model.action_id_for_command_type.

    Returns:
        The same cmd dict, mutated with backfilled fields.
    """
    if not isinstance(cmd, dict):
        return cmd

    from engine.editor.history_label_model import (  # noqa: PLC0415
        action_id_for_command_type,
        build_history_detail_for_command,
        build_history_label_for_command,
    )

    # Backfill action_id
    if "action_id" not in cmd:
        if action_id_lookup is not None:
            cmd_type = cmd.get("type")
            if isinstance(cmd_type, str):
                action_id = action_id_lookup.get(cmd_type)
                if action_id:
                    cmd["action_id"] = action_id
        else:
            action_id = action_id_for_command_type(cmd.get("type"))
            if action_id:
                cmd["action_id"] = action_id

    # Backfill detail
    if "detail" not in cmd:
        detail = build_history_detail_for_command(cmd)
        if detail:
            cmd["detail"] = detail

    # Backfill label (first attempt from command type)
    if "label" not in cmd:
        label = build_history_label_for_command(cmd)
        if label:
            cmd["label"] = label

    return cmd


def should_push_command(prev_payload: Any, next_payload: Any) -> bool:
    """Determine if a command should be pushed based on payload comparison.

    Returns False if payloads are identical (no-op detection).
    This is a pure comparison - does not modify any state.

    Args:
        prev_payload: The "before" state payload.
        next_payload: The "after" state payload.

    Returns:
        True if the command should be pushed (payloads differ),
        False if it's a no-op (payloads are identical).
    """
    return bool(prev_payload != next_payload)


def format_default_undo_label(
    cmd: dict[str, Any],
    action_title: str | None = None,
) -> str:
    """Format a default undo label for a command.

    Delegates to history_label_model.format_history_entry for consistency.

    Args:
        cmd: The command dict with at least 'action_id' and optionally 'detail'.
        action_title: Optional title to use (e.g., from EditorAction.title).

    Returns:
        A formatted label string, or "Unknown Action" if no info available.
    """
    from engine.editor.history_label_model import format_history_entry  # noqa: PLC0415

    action_id = cmd.get("action_id") if isinstance(cmd, dict) else None
    if not isinstance(action_id, str):
        action_id = ""
    detail = cmd.get("detail") if isinstance(cmd, dict) else None
    if not isinstance(detail, dict):
        detail = None

    return format_history_entry(action_id, action_title, detail)


def backfill_label_from_action(
    cmd: dict[str, Any],
    action_id: str,
    action_title: str,
) -> dict[str, Any]:
    """Backfill command label from action metadata.

    This handles the second-pass label generation when the first pass
    (from command type) didn't produce a label.

    Args:
        cmd: The command dict to update.
        action_id: The action ID string.
        action_title: The action title from EditorAction.

    Returns:
        The same cmd dict, mutated with label if it was missing.
    """
    if not isinstance(cmd, dict):
        return cmd

    if "label" in cmd:
        return cmd

    from engine.editor.history_label_model import format_history_entry  # noqa: PLC0415

    detail = cmd.get("detail") if isinstance(cmd.get("detail"), dict) else None
    cmd["label"] = format_history_entry(action_id, action_title, detail)
    return cmd
