"""Clipboard utilities for the tooling runtime.

This module provides safe clipboard operations that never hang in
CI, test, web, or headless environments.
"""
from __future__ import annotations

import os

from engine.editor.clipboard_capabilities_model import should_attempt_clipboard


def try_copy_to_clipboard(text: str, *, is_web: bool = False, is_headless: bool = False) -> bool:
    """
    Best-effort clipboard copy.

    Must be safe in headless/test environments: all errors are swallowed.
    Returns False immediately in CI, test, web, or headless environments
    to avoid tkinter hangs.

    Args:
        text: The text to copy to the clipboard.
        is_web: True if running in web/pygbag context.
        is_headless: True if running without a display.

    Returns:
        True if the copy succeeded, False otherwise.
    """
    value = str(text or "")
    if not value:
        return False

    # Check if clipboard operations are safe before importing tkinter
    if not should_attempt_clipboard(os.environ, is_web=is_web, is_headless=is_headless):
        return False

    # Only import tkinter when we're actually going to use it
    try:
        import warnings  # noqa: PLC0415
        import tkinter  # noqa: PLC0415

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            root = tkinter.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(value)
        root.update()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001  # REASON: clipboard access depends on host GUI state and should degrade to a simple unavailable result across platform-specific failures
        return False
