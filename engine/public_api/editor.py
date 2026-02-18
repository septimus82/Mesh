"""Editor-facing entrypoints for Mesh Engine consumers.

This module re-exports editor symbols that are intentionally supported for
consumers building tools or extensions on top of the Mesh editor.

.. warning::

   Everything in this module requires a display back-end (``arcade``) and is
   **not headless-safe**.  Import only in contexts where a window is available.

Symbols exported here are covered by the engine's semver promise.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# ---------------------------------------------------------------------------
# Lazy imports — editor modules are heavy; defer until actually used.
# ---------------------------------------------------------------------------

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController


def get_editor_controller_class() -> type:
    """Return the :class:`EditorModeController` class (lazy import).

    This avoids pulling in the full editor stack at import time.
    """
    from engine.editor_controller import EditorModeController
    return EditorModeController


# ---------------------------------------------------------------------------
# Export list
# ---------------------------------------------------------------------------

__all__ = [
    "get_editor_controller_class",
]
