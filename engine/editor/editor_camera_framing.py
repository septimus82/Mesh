"""Keep scene content on the visible canvas when the editor owns the camera.

In play mode CameraFollow positions the camera every frame. The editor pauses
behaviours, so a scene opened with ``mesh edit`` (or switched to inside the
editor) keeps arcade's default camera, which maps world (x, y) straight to
screen (x, y). Content near the origin then sits under the left dock and the
bottom panels. Framing only moves the camera when *nothing* is visible, so a
restored workspace view or a play-mode follow position is never disturbed.
"""

from __future__ import annotations

from typing import Any

from engine.editor.editor_dock_query import get_effective_dock_widths
from engine.editor.editor_shell_layout import Rect, compute_editor_shell_layout
from engine.swallowed_exceptions import _log_swallow


def frame_editor_camera_if_offscreen(editor: Any) -> bool:
    """Frame the scene in the Advanced editor canvas (or Creator canvas when it is open)."""
    try:
        creator = getattr(editor, "creator_mode", None)
        if creator is not None and getattr(creator, "active", False):
            from engine.editor.creator_mode.creator_overlay_renderer import creator_canvas_rect  # noqa: PLC0415

            viewport = creator_canvas_rect(editor.window.width, editor.window.height)
        else:
            viewport = editor_viewport_rect(editor)
        return frame_content_if_offscreen(editor.window, viewport)
    except Exception:  # noqa: BLE001  # REASON: camera framing is cosmetic; never block editor entry or scene load
        _log_swallow("EDCF-001", "engine/editor/editor_camera_framing.py framing failed", once=True)
        return False


def editor_viewport_rect(editor: Any) -> Rect:
    window = editor.window
    width, height = int(window.width), int(window.height)
    left_w, right_w = get_effective_dock_widths(editor, width)
    return compute_editor_shell_layout(width, height, left_w, right_w).viewport


def frame_content_if_offscreen(window: Any, viewport: Rect) -> bool:
    """Centre the camera on the scene's sprites if none is inside ``viewport`` (screen rect).

    Returns True when the camera was moved.
    """
    camera = getattr(window, "camera", None)
    scene = getattr(window, "scene_controller", None)
    sprites = list(getattr(scene, "all_sprites", None) or [])
    position = getattr(camera, "position", None)
    if not sprites or position is None:
        return False

    cam_x, cam_y = float(position[0]), float(position[1])
    zoom = float(getattr(camera, "zoom", 1.0) or 1.0)
    half_w, half_h = float(window.width) / 2.0, float(window.height) / 2.0
    points = [(float(s.center_x), float(s.center_y)) for s in sprites]

    def on_canvas(x: float, y: float) -> bool:
        return viewport.contains_point((x - cam_x) * zoom + half_w, (y - cam_y) * zoom + half_h)

    if any(on_canvas(x, y) for x, y in points):
        return False

    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    content_x = (min(xs) + max(xs)) / 2.0
    content_y = (min(ys) + max(ys)) / 2.0
    # Solve screen(content) == viewport centre for the camera position.
    camera.position = (
        content_x - (viewport.center_x - half_w) / zoom,
        content_y - (viewport.center_y - half_h) / zoom,
    )
    return True
