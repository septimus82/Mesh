"""Live-GUI resize diagnostics (ENGINE-RESIZE-ROOT).

Enable with:
    set MESH_RESIZE_DIAG=1
    mesh edit   (or your usual launch command)

Then resize the OS window (drag corner, maximize, snap) and watch stderr/log for
lines prefixed with ``[Mesh][ResizeDiag]``.

This module is diagnostic-only — no layout or camera fixes.
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


def enabled() -> bool:
    value = os.environ.get("MESH_RESIZE_DIAG", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


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
    logger.warning(
        "%s frame tick site=%s post_resize_frames_left=%s event=%s seq=%s "
        "gui_camera.viewport=%sx%s | %s",
        _PREFIX,
        site,
        remaining,
        event,
        seq,
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
