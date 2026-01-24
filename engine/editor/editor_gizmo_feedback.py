"""Pure module for gizmo feedback formatting and layout.

This module provides deterministic, headless-safe functions for building
gizmo overlay strings and computing pivot marker geometry. No arcade dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True, slots=True)
class GizmoFeedbackState:
    """State snapshot for gizmo overlay rendering."""

    active: bool
    mode: str  # "move" | "rotate" | "scale"
    pivot_xy: Tuple[float, float] | None
    move_delta_xy: Tuple[float, float] | None
    rotate_delta_deg: float | None
    scale_factor: float | None
    snap_active: bool


@dataclass(frozen=True, slots=True)
class GizmoFeedbackLines:
    """Formatted lines for gizmo overlay display."""

    title: str
    line1: str
    line2: str | None


def format_move_delta(dx: float, dy: float) -> str:
    """Format move delta as string.

    Args:
        dx: X delta in world units.
        dy: Y delta in world units.

    Returns:
        Formatted string like "Δx +16.0  Δy -8.0"
    """
    sign_x = "+" if dx >= 0 else ""
    sign_y = "+" if dy >= 0 else ""
    return f"Δx {sign_x}{dx:.1f}  Δy {sign_y}{dy:.1f}"


def format_rotate_delta(deg: float) -> str:
    """Format rotation delta as string.

    Args:
        deg: Rotation delta in degrees.

    Returns:
        Formatted string like "Δθ +12.5°"
    """
    sign = "+" if deg >= 0 else ""
    return f"Δθ {sign}{deg:.1f}°"


def format_scale_factor(f: float) -> str:
    """Format scale factor as string.

    Args:
        f: Scale factor (1.0 = no change).

    Returns:
        Formatted string like "Scale x1.20"
    """
    return f"Scale x{f:.2f}"


def build_gizmo_feedback_lines(state: GizmoFeedbackState) -> GizmoFeedbackLines | None:
    """Build formatted feedback lines from state.

    Args:
        state: Current gizmo feedback state.

    Returns:
        GizmoFeedbackLines if active, None otherwise.
    """
    if not state.active:
        return None

    mode = state.mode.upper()
    title = f"TRANSFORM: {mode}"

    if state.mode == "move":
        if state.move_delta_xy is None:
            line1 = "Δx +0.0  Δy +0.0"
        else:
            line1 = format_move_delta(state.move_delta_xy[0], state.move_delta_xy[1])
        line2 = "Snap ON" if state.snap_active else None

    elif state.mode == "rotate":
        deg = state.rotate_delta_deg if state.rotate_delta_deg is not None else 0.0
        line1 = format_rotate_delta(deg)
        line2 = "Snap 15°" if state.snap_active else None

    elif state.mode == "scale":
        factor = state.scale_factor if state.scale_factor is not None else 1.0
        line1 = format_scale_factor(factor)
        line2 = "Snap 0.1" if state.snap_active else None

    else:
        # Unknown mode
        line1 = "..."
        line2 = None

    return GizmoFeedbackLines(title=title, line1=line1, line2=line2)


def compute_pivot_marker_segments(
    pivot_xy: Tuple[float, float],
    size_world: float,
) -> Tuple[Tuple[float, float, float, float], Tuple[float, float, float, float]]:
    """Compute crosshair line segments for pivot marker.

    Args:
        pivot_xy: Pivot position in world coordinates.
        size_world: Half-size of crosshair in world units.

    Returns:
        Tuple of two segments: (horizontal, vertical)
        Each segment is (x1, y1, x2, y2).
    """
    px, py = pivot_xy
    # Horizontal segment
    h_seg = (px - size_world, py, px + size_world, py)
    # Vertical segment
    v_seg = (px, py - size_world, px, py + size_world)
    return (h_seg, v_seg)


def compute_feedback_box_layout(
    screen_width: float,
    screen_height: float,
    lines: GizmoFeedbackLines,
    padding: float = 8.0,
    line_height: float = 18.0,
    char_width: float = 8.0,
) -> dict:
    """Compute layout for feedback text box.

    Args:
        screen_width: Screen width in pixels.
        screen_height: Screen height in pixels.
        lines: Feedback lines to display.
        padding: Box padding in pixels.
        line_height: Height per line in pixels.
        char_width: Approximate character width for sizing.

    Returns:
        Dict with box_x, box_y, box_width, box_height, text_positions.
    """
    # Calculate max text width
    max_chars = max(len(lines.title), len(lines.line1))
    if lines.line2:
        max_chars = max(max_chars, len(lines.line2))

    box_width = max_chars * char_width + padding * 2
    num_lines = 2 if lines.line2 is None else 3
    box_height = num_lines * line_height + padding * 2

    # Position: bottom-left corner, above status bar area
    margin = 10.0
    box_x = margin
    box_y = margin + 24.0  # Above status bar

    # Text positions (relative to box)
    text_positions = []
    text_y = box_y + box_height - padding - line_height * 0.5
    text_x = box_x + padding

    # Title
    text_positions.append({"text": lines.title, "x": text_x, "y": text_y})
    text_y -= line_height

    # Line 1
    text_positions.append({"text": lines.line1, "x": text_x, "y": text_y})
    text_y -= line_height

    # Line 2 (optional)
    if lines.line2:
        text_positions.append({"text": lines.line2, "x": text_x, "y": text_y})

    return {
        "box_x": box_x,
        "box_y": box_y,
        "box_width": box_width,
        "box_height": box_height,
        "text_positions": text_positions,
    }
