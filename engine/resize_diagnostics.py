"""Live-GUI resize diagnostics (ENGINE-RESIZE-ROOT).

Enable with:
    set MESH_RESIZE_DIAG=1
    mesh edit   (or your usual launch command)

Then resize the OS window (drag corner, maximize, snap) and watch stderr/log for
lines prefixed with ``[Mesh][ResizeDiag]``.

This module is diagnostic-only — no layout or camera fixes.

Visual confirmation (step 1 of ENGINE-RESIZE-DPI):
    set MESH_RESIZE_DPI_VIS=1
    Draws a red border at the logical window rect (window.width x window.height).
    If content stops inside the OS window with empty margin beyond the red border,
    the DPI viewport hypothesis is confirmed.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from engine.logging_tools import get_logger

if TYPE_CHECKING:
    from engine.camera_controller import CameraController
    from engine.game import GameWindow

logger = get_logger(__name__)

_PREFIX = "[Mesh][ResizeDiag]"
_POST_RESIZE_FRAME_BUDGET = 8
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def enabled() -> bool:
    value = os.environ.get("MESH_RESIZE_DIAG", "").strip().lower()
    return value in _TRUTHY


def visual_enabled() -> bool:
    value = os.environ.get("MESH_RESIZE_DPI_VIS", "").strip().lower()
    return value in _TRUTHY


def _read_ctx_viewport(window: "GameWindow") -> tuple[int | None, int | None, int | None, int | None]:
    ctx = getattr(window, "ctx", None)
    if ctx is None:
        return None, None, None, None
    viewport = getattr(ctx, "viewport", None)
    if viewport is None:
        return None, None, None, None
    try:
        if isinstance(viewport, tuple) and len(viewport) == 4:
            x, y, w, h = viewport
            return int(x), int(y), int(w), int(h)
    except (TypeError, ValueError):
        pass
    return None, None, None, None


def _read_window_viewport(window: "GameWindow") -> tuple[int | None, int | None, int | None, int | None]:
    viewport = getattr(window, "viewport", None)
    if viewport is None:
        return None, None, None, None
    try:
        if isinstance(viewport, tuple) and len(viewport) == 4:
            x, y, w, h = viewport
            return int(x), int(y), int(w), int(h)
    except (TypeError, ValueError):
        pass
    return None, None, None, None


def _viewport_wh(camera: Any) -> tuple[int | None, int | None]:
    viewport = getattr(camera, "viewport", None)
    if viewport is None:
        return None, None
    try:
        return int(viewport.width), int(viewport.height)
    except (AttributeError, TypeError, ValueError):
        return None, None


def _read_os_size(window: "GameWindow") -> tuple[int | None, int | None]:
    get_size = getattr(window, "get_size", None)
    if not callable(get_size):
        return None, None
    try:
        width, height = get_size()
        return int(width), int(height)
    except Exception as exc:
        logger.warning("%s get_size() failed: %s", _PREFIX, exc, exc_info=True)
        return None, None


def _read_framebuffer_size(window: "GameWindow") -> tuple[int | None, int | None]:
    get_fb = getattr(window, "get_framebuffer_size", None)
    if not callable(get_fb):
        return None, None
    try:
        width, height = get_fb()
        return int(width), int(height)
    except Exception as exc:
        logger.warning("%s get_framebuffer_size() failed: %s", _PREFIX, exc, exc_info=True)
        return None, None


def _format_sizes(window: "GameWindow") -> str:
    width_attr = int(getattr(window, "width", 0) or 0)
    height_attr = int(getattr(window, "height", 0) or 0)
    os_w, os_h = _read_os_size(window)
    fb_w, fb_h = _read_framebuffer_size(window)
    scale = getattr(window, "scale", None)
    return (
        f"window.width/height={width_attr}x{height_attr} "
        f"get_size={os_w}x{os_h} framebuffer={fb_w}x{fb_h} scale={scale!r}"
    )


def log_viewport_pipeline(
    window: "GameWindow",
    *,
    site: str,
    camera_controller: "CameraController | None" = None,
) -> None:
    """Log GL viewport state vs logical/framebuffer sizes (ENGINE-RESIZE-DPI step 2)."""
    if not enabled():
        return
    ctx_vp = _read_ctx_viewport(window)
    win_vp = _read_window_viewport(window)
    gui_vp = (None, None)
    if camera_controller is not None:
        gui_vp = gui_camera_viewport(camera_controller)
    seq = getattr(window, "_resize_diag_seq", "?")
    logger.warning(
        "%s viewport_pipeline site=%s seq=%s "
        "ctx.viewport=%s window.viewport=%s gui_camera.viewport=%sx%s | %s",
        _PREFIX,
        site,
        seq,
        ctx_vp,
        win_vp,
        gui_vp[0],
        gui_vp[1],
        _format_sizes(window),
    )


def maybe_draw_dpi_visual_markers(window: "GameWindow") -> None:
    """Draw logical-size border overlay for live screenshot confirmation."""
    if not visual_enabled():
        return
    import engine.optional_arcade as optional_arcade

    arcade = optional_arcade.arcade
    if arcade is None:
        return

    width = float(getattr(window, "width", 0) or 0)
    height = float(getattr(window, "height", 0) or 0)
    if width <= 0 or height <= 0:
        return

    border = 4.0
    red = (255, 40, 40, 255)
    # Logical rect edges — content should reach these if viewport matches framebuffer.
    arcade.draw_lrbt_rectangle_outline(0, width, 0, height, red, border)
    # Emphasize right and bottom edges where DPI gap would appear.
    arcade.draw_lrbt_rectangle_filled(width - border, width, 0, height, (255, 40, 40, 180))
    arcade.draw_lrbt_rectangle_filled(0, width, 0, border, (255, 40, 40, 180))

    fb_w, fb_h = _read_framebuffer_size(window)
    scale = getattr(window, "scale", None)
    label = f"logical {int(width)}x{int(height)}  fb {fb_w}x{fb_h}  scale={scale}"
    draw_text = getattr(arcade, "draw_text", None)
    if callable(draw_text):
        draw_text(label, 8, height - 24, red, 14, anchor_x="left", anchor_y="top")


def note_window_resize(window: "GameWindow", event_width: int, event_height: int) -> None:
    """Call from GameWindow.on_resize — starts post-resize frame logging."""
    if not enabled():
        return
    seq = int(getattr(window, "_resize_diag_seq", 0) or 0) + 1
    window._resize_diag_seq = seq
    window._resize_diag_frames_left = _POST_RESIZE_FRAME_BUDGET
    window._resize_diag_last_event = (int(event_width), int(event_height))
    logger.warning(
        "%s on_resize event #%s params=%sx%s | immediately after super: %s",
        _PREFIX,
        seq,
        int(event_width),
        int(event_height),
        _format_sizes(window),
    )


def _post_resize_active(window: "GameWindow") -> bool:
    return int(getattr(window, "_resize_diag_frames_left", 0) or 0) > 0


def _consume_post_resize_frame(window: "GameWindow") -> int:
    remaining = int(getattr(window, "_resize_diag_frames_left", 0) or 0)
    if remaining <= 0:
        return 0
    window._resize_diag_frames_left = remaining - 1
    return remaining


def gui_camera_viewport(camera_controller: "CameraController") -> tuple[int | None, int | None]:
    return _viewport_wh(camera_controller.gui_camera)


def log_gui_camera_sync(
    camera_controller: "CameraController",
    *,
    synced: bool,
    pre_viewport: tuple[int | None, int | None],
    post_viewport: tuple[int | None, int | None],
) -> None:
    if not enabled():
        return
    window = camera_controller.window
    if not _post_resize_active(window):
        return
    event = getattr(window, "_resize_diag_last_event", None)
    seq = getattr(window, "_resize_diag_seq", "?")
    logger.warning(
        "%s sync_gui_camera_to_window #%s event=%s synced=%s "
        "pre_viewport=%sx%s post_viewport=%sx%s | %s",
        _PREFIX,
        seq,
        event,
        synced,
        pre_viewport[0],
        pre_viewport[1],
        post_viewport[0],
        post_viewport[1],
        _format_sizes(window),
    )


def maybe_log_draw_frame_sizes(
    window: "GameWindow",
    camera_controller: "CameraController | None",
    *,
    site: str,
) -> None:
    """Call once per frame near UI draw (e.g. tick.py after use_gui_camera)."""
    if not enabled():
        return
    remaining = int(getattr(window, "_resize_diag_frames_left", 0) or 0)
    if remaining <= 0:
        return
    event = getattr(window, "_resize_diag_last_event", None)
    seq = getattr(window, "_resize_diag_seq", "?")
    gui_vp = (None, None)
    if camera_controller is not None:
        gui_vp = _viewport_wh(camera_controller.gui_camera)
    ctx_vp = _read_ctx_viewport(window)
    win_vp = _read_window_viewport(window)
    logger.warning(
        "%s frame tick site=%s post_resize_frames_left=%s event=%s seq=%s "
        "ctx.viewport=%s window.viewport=%s gui_camera.viewport=%sx%s | %s",
        _PREFIX,
        site,
        remaining,
        event,
        seq,
        ctx_vp,
        win_vp,
        gui_vp[0],
        gui_vp[1],
        _format_sizes(window),
    )
    _consume_post_resize_frame(window)


def maybe_log_menu_draw_sizes(window: "GameWindow", *, panel_width: float, panel_height: float) -> None:
    """Call from MainMenuOverlay.draw when visible during post-resize window."""
    if not enabled():
        return
    if not _post_resize_active(window):
        return
    seq = getattr(window, "_resize_diag_seq", "?")
    event = getattr(window, "_resize_diag_last_event", None)
    logger.warning(
        "%s MainMenuOverlay.draw seq=%s event=%s layout_panel=%sx%s (from window %sx%s) | %s",
        _PREFIX,
        seq,
        event,
        int(panel_width),
        int(panel_height),
        int(getattr(window, "width", 0) or 0),
        int(getattr(window, "height", 0) or 0),
        _format_sizes(window),
    )
