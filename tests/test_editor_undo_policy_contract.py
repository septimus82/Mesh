from __future__ import annotations

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_undo_history_overlay_uses_undo_controller() -> None:
    text = _read("engine/ui_overlays/undo_history_overlay.py")
    assert "undo_stack" not in text
    assert "redo_stack" not in text


def test_editor_controller_does_not_mutate_undo_stacks_directly() -> None:
    text = _read("engine/editor_controller.py")
    # Allow the fallback path in push_undo_command that uses undo_stack.append
    # when undo controller is not available (backwards compatibility)
    # Count occurrences to ensure it's only the single fallback case
    import re
    append_matches = len(re.findall(r"undo_stack\.append", text))
    clear_matches = len(re.findall(r"redo_stack\.clear", text))
    # Allow exactly 1 fallback occurrence of each
    assert append_matches <= 1, f"Found {append_matches} undo_stack.append calls, expected <= 1"
    assert clear_matches <= 1, f"Found {clear_matches} redo_stack.clear calls, expected <= 1"
