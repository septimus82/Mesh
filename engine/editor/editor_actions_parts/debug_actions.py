"""Debug export, copy, select, and toast action handlers."""

from __future__ import annotations

from typing import Any

from engine.editor.editor_actions_parts._shared import _get_editor

__all__ = [
    "_action_debug_select_event_entity",
    "_action_debug_export_bundle",
    "_action_debug_copy_quest_diagnostic",
    "_action_debug_copy_filtered_events",
    "_action_debug_copy_cutscene_summary",
    "_action_debug_emit_feedback_info",
    "_action_debug_emit_feedback_warning",
    "_action_debug_emit_feedback_error_sticky",
    "_debug_toast",
]


def _action_debug_select_event_entity(window: Any) -> None:
    """Select an entity from the debug event monitor (EditorAction handler)."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    debug_panels = getattr(editor, "debug_panels", None)
    if debug_panels is None:
        return
    entity_id = debug_panels.consume_pending_select_entity_id()
    if not entity_id:
        return
    debug_panels.activate_event_entity(entity_id)


def _action_debug_export_bundle(window: Any) -> None:
    """Export the current debug bundle snapshot to artifacts/ (EditorAction handler)."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    from pathlib import Path  # noqa: PLC0415

    from engine.editor.debug_bundle import build_debug_bundle  # noqa: PLC0415
    from engine.persistence_io import write_json_atomic  # noqa: PLC0415
    from engine.repo_root import get_repo_root  # noqa: PLC0415

    try:
        repo_root = get_repo_root()
    except Exception:
        repo_root = Path.cwd()

    out_path = repo_root / "artifacts" / "debug_bundle.json"
    try:
        bundle = build_debug_bundle(window, editor, deterministic=False)
        payload = bundle.to_dict(deterministic=False)
        write_json_atomic(out_path, payload, indent=2, sort_keys=True, trailing_newline=True)
        _debug_toast(window, f"Debug bundle exported: {out_path.as_posix()}", severity="info")
    except Exception:
        _debug_toast(window, "Debug bundle export failed", severity="error")


def _action_debug_copy_quest_diagnostic(window: Any) -> None:
    """Copy the selected quest diagnostic line to clipboard (EditorAction handler)."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    debug_panels = getattr(editor, "debug_panels", None)
    if debug_panels is None:
        return
    text = str(debug_panels.get_selected_quest_diagnostic_text() or "")
    if not text:
        _debug_toast(window, "No quest diagnostic selected", severity="warning")
        return
    from engine.tooling_runtime.clipboard import try_copy_to_clipboard  # noqa: PLC0415

    if try_copy_to_clipboard(text):
        _debug_toast(window, "Quest diagnostic copied", severity="info")
    else:
        _debug_toast(window, "Clipboard unavailable (headless/web)", severity="warning")


def _action_debug_copy_filtered_events(window: Any) -> None:
    """Copy the last filtered events from the debug panel (EditorAction handler)."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    debug_panels = getattr(editor, "debug_panels", None)
    if debug_panels is None:
        return
    text = str(debug_panels.get_filtered_event_rows_text() or "")
    if not text:
        _debug_toast(window, "No events to copy", severity="warning")
        return
    from engine.tooling_runtime.clipboard import try_copy_to_clipboard  # noqa: PLC0415

    if try_copy_to_clipboard(text):
        _debug_toast(window, "Filtered events copied", severity="info")
    else:
        _debug_toast(window, "Clipboard unavailable (headless/web)", severity="warning")


def _action_debug_copy_cutscene_summary(window: Any) -> None:
    """Copy the cutscene summary line(s) from the debug panel (EditorAction handler)."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    debug_panels = getattr(editor, "debug_panels", None)
    if debug_panels is None:
        return
    text = str(debug_panels.get_cutscene_summary_text() or "")
    if not text:
        _debug_toast(window, "No cutscene summary available", severity="warning")
        return
    from engine.tooling_runtime.clipboard import try_copy_to_clipboard  # noqa: PLC0415

    if try_copy_to_clipboard(text):
        _debug_toast(window, "Cutscene summary copied", severity="info")
    else:
        _debug_toast(window, "Clipboard unavailable (headless/web)", severity="warning")


def _action_debug_emit_feedback_info(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or getattr(editor, "feedback", None) is None:
        return
    editor.feedback.info("Test info feedback")


def _action_debug_emit_feedback_warning(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or getattr(editor, "feedback", None) is None:
        return
    editor.feedback.warning("Test warning feedback")


def _action_debug_emit_feedback_error_sticky(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or getattr(editor, "feedback", None) is None:
        return
    editor.feedback.error("Test error feedback (sticky)", sticky=True)


def _debug_toast(window: Any, message: str, *, severity: str = "info", seconds: float | None = None) -> None:
    editor = _get_editor(window)
    feedback = getattr(editor, "feedback", None) if editor is not None else None
    method = getattr(feedback, severity, None) if feedback is not None else None
    if callable(method):
        if seconds is not None:
            method(message, ttl=seconds)
        else:
            method(message)

    hud = getattr(window, "player_hud", None)
    toaster = getattr(hud, "enqueue_" "toast", None) if hud is not None else None
    if callable(toaster):
        toaster(message, seconds=2.5 if seconds is None else seconds)
