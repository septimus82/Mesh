"""Pure module for cursor hint computation.

This module provides deterministic, headless-safe functions for building
cursor hint strings based on editor state. No arcade dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CursorHintResult:
    """Result of cursor hint computation.

    Attributes:
        text: Display text for the hint (e.g., "Cursor: Resize Dock"), or None.
        kind: Cursor kind string (e.g., "default", "pointer", "move", "resize_h",
            "resize_v", "crosshair"), or None if editor inactive.
    """

    text: str | None
    kind: str | None


def build_cursor_hint(
    *,
    editor_active: bool,
    mouse_x: float,
    mouse_y: float,
    window_w: int,
    window_h: int,
    # State flags
    ui_blocked: bool,
    marquee_active: bool,
    alt_dup_active: bool,
    gizmo_drag_active: bool,
    gizmo_mode: str | None,
    ui_hover: bool,
    # Hit test inputs
    shell_layout: Any,
    splitter_hit: str | None,
    entity_hit: bool,
) -> CursorHintResult:
    """Build cursor hint based on editor state and hit tests.

    Priority order (highest first):
    1. Marquee select active
    2. Alt-drag duplicate active
    3. Transform gizmo drag active
    4. Hovering dock splitter
    5. Hovering entity bounds
    6. Hovering UI chrome (menu/tab/top bar)
    7. Default

    Args:
        editor_active: Whether editor mode is active.
        mouse_x: Mouse X position in screen coordinates.
        mouse_y: Mouse Y position in screen coordinates.
        window_w: Window width.
        window_h: Window height.
        ui_blocked: Whether UI is blocked by text input/modal.
        marquee_active: Whether marquee selection is active.
        alt_dup_active: Whether alt-drag duplicate is active.
        gizmo_drag_active: Whether a transform gizmo drag is active.
        gizmo_mode: Current gizmo mode ("move", "rotate", "scale").
        ui_hover: Whether hovering UI chrome (menu/tab/top bar).
        shell_layout: EditorShellLayout instance (unused directly, reserved).
        splitter_hit: Result of hit_test_splitter ("left", "right", or None).
        entity_hit: Whether mouse is over any entity bounds.

    Returns:
        CursorHintResult with text and kind, or both None if no hint.
    """
    # No hint if editor is inactive
    if not editor_active:
        return CursorHintResult(text=None, kind=None)

    # Ignore unused params to satisfy linter
    _ = mouse_x, mouse_y, window_w, window_h, shell_layout

    if ui_blocked:
        return CursorHintResult(text=None, kind="default")

    # Priority 1: Marquee select active
    if marquee_active:
        return CursorHintResult(
            text="Cursor: Marquee (Esc cancel)",
            kind="crosshair",
        )

    # Priority 2: Alt-drag duplicate active
    if alt_dup_active:
        return CursorHintResult(
            text="Cursor: Alt-dup drag (RMB/Esc cancel)",
            kind="move",
        )

    # Priority 3: Transform gizmo drag active
    if gizmo_drag_active and gizmo_mode:
        mode_labels = {
            "move": "Move",
            "rotate": "Rotate",
            "scale": "Scale",
        }
        label = mode_labels.get(gizmo_mode.lower(), gizmo_mode.capitalize())
        return CursorHintResult(
            text=f"Cursor: {label}",
            kind="move",
        )

    # Priority 4: Hovering dock splitter
    if splitter_hit is not None:
        return CursorHintResult(
            text="Cursor: Resize Dock",
            kind="resize_h",
        )

    # Priority 5: Hovering entity bounds
    if entity_hit:
        return CursorHintResult(
            text="Cursor: Drag Entity",
            kind="move",
        )

    # Priority 6: Hovering UI chrome
    if ui_hover:
        return CursorHintResult(text=None, kind="pointer")

    # No hint
    return CursorHintResult(text=None, kind="default")
