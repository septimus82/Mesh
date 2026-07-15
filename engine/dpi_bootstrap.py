"""Win32 process DPI bootstrap.

Windows DPI awareness is set once per process. Pyglet forces per-monitor DPI
awareness at import time; calling ``set_process_dpi_unaware()`` before the
first ``import pyglet`` / ``import arcade`` keeps Mesh DPI-unaware so logical
window coordinates match the framebuffer on every monitor.
"""

from __future__ import annotations

import sys
from typing import Any, cast

_applied = False


def set_process_dpi_unaware() -> None:
    """Mark the Mesh process DPI-unaware on Windows; no-op elsewhere."""
    global _applied
    if _applied:
        return
    _applied = True
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes_module = cast(Any, ctypes)
        user32 = ctypes_module.windll.user32
        set_context = getattr(user32, "SetProcessDpiAwarenessContext", None)
        if set_context is not None:
            # DPI_AWARENESS_CONTEXT_UNAWARE == (DPI_AWARENESS_CONTEXT)-1
            unaware = ctypes.c_void_p(-1)
            if set_context(unaware):
                return

        shcore = ctypes_module.windll.shcore
        set_awareness = getattr(shcore, "SetProcessDpiAwareness", None)
        if set_awareness is not None:
            process_dpi_unaware = 0
            if set_awareness(process_dpi_unaware) == 0:
                return
    except Exception:
        return
