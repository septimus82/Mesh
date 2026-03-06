from __future__ import annotations

from pathlib import Path
from typing import Any
from engine.logging_tools import get_logger

_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)


HINT_LABEL = "Ctrl+P Palette  Ctrl+O Scenes  Ctrl+S Save"


# -----------------------------------------------------------------------------
# Operation Banner Formatting
# -----------------------------------------------------------------------------


def _format_move_banner(dx: float, dy: float) -> str:
    """Format move banner with delta values."""
    sign_x = "+" if dx >= 0 else ""
    sign_y = "+" if dy >= 0 else ""
    return f"MOVE: Dx {sign_x}{dx:.1f} Dy {sign_y}{dy:.1f} (Shift snap)"


def _format_rotate_banner(deg: float) -> str:
    """Format rotate banner with delta angle."""
    sign = "+" if deg >= 0 else ""
    return f"ROTATE: Dth {sign}{deg:.1f}deg (Shift 15deg snap)"


def _format_scale_banner(factor: float) -> str:
    """Format scale banner with factor."""
    return f"SCALE: x{factor:.2f} (Shift 0.1 snap)"


def build_editor_operation_banner(controller: Any) -> str | None:
    """Build operation banner for status bar center section.

    Checks transient editor operations in precedence order:
    1. Marquee select active
    2. Alt-drag duplicate active
    3. Transform gizmo drag active (move/rotate/scale)

    Args:
        controller: Editor controller instance.

    Returns:
        Banner string if an operation is active, None otherwise.
    """
    # Precedence 1: Marquee select
    if getattr(controller, "_marquee_active", False):
        return "MARQUEE: box selecting (Esc cancel)"

    # Precedence 2: Alt-drag duplicate
    if getattr(controller, "_alt_dup_active", False):
        return "ALT-DUP: dragging copies (RMB/Esc cancel)"

    # Precedence 3: Transform gizmo drag
    # Check for active transform drags
    move_drag = (
        getattr(controller, "entity_dragging", False)
        and getattr(controller, "selected_entity", None) is not None
    )
    rotate_drag = getattr(controller, "_rotate_drag_active", False)
    scale_drag = getattr(controller, "_scale_drag_active", False)

    if rotate_drag:
        deg = getattr(controller, "_rotate_preview_delta_deg", None)
        if deg is None:
            deg = 0.0
        return _format_rotate_banner(deg)

    if scale_drag:
        factor = getattr(controller, "_scale_preview_factor", None)
        if factor is None:
            factor = 1.0
        return _format_scale_banner(factor)

    if move_drag:
        delta_xy = getattr(controller, "_move_preview_delta_xy", None)
        if delta_xy is None:
            dx, dy = 0.0, 0.0
        else:
            dx, dy = delta_xy
        return _format_move_banner(dx, dy)

    return None


# -----------------------------------------------------------------------------
# Status Bar Helpers
# -----------------------------------------------------------------------------


def _scene_label(editor_state: Any) -> str:
    window = getattr(editor_state, "window", None)
    controller = getattr(window, "scene_controller", None) if window is not None else None
    scene_name = ""
    if controller is not None:
        data = getattr(controller, "current_scene_data", None)
        if isinstance(data, dict):
            name = data.get("name")
            if isinstance(name, str) and name.strip():
                scene_name = name.strip()
        if not scene_name:
            path_value = getattr(controller, "current_scene_path", None)
            if isinstance(path_value, str) and path_value.strip():
                scene_name = Path(path_value).stem or path_value.strip()

    if not scene_name:
        return "Scene: Unsaved"
    return f"Scene: {scene_name}"


def _dirty_label(editor_state: Any) -> str:
    dirty_state = getattr(editor_state, "dirty_state", None)
    is_dirty = bool(getattr(dirty_state, "is_dirty", False))
    if not is_dirty:
        is_dirty = bool(getattr(editor_state, "scene_dirty", False))
    return "Unsaved" if is_dirty else "Saved"


def _entity_display_name(editor_state: Any, sprite: Any) -> str:
    getter = getattr(editor_state, "_get_display_name_for_sprite", None)
    if callable(getter):
        try:
            name = getter(sprite)
        except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
            _log_swallow("ESTA-001", "engine/editor_status.py blanket swallow", once=True)
            name = ""
        if isinstance(name, str) and name.strip():
            return name.strip()

    entity_data = getattr(sprite, "mesh_entity_data", None)
    if isinstance(entity_data, dict):
        for key in ("mesh_name", "name", "id", "tag"):
            raw = entity_data.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()

    for attr in ("mesh_name", "name", "mesh_tag"):
        raw = getattr(sprite, attr, None)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return "<unnamed>"


def _light_selection_label(editor_state: Any, index: int) -> str:
    getter = getattr(editor_state, "_get_scene_lights", None)
    if callable(getter):
        try:
            lights = getter()
        except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
            _log_swallow("ESTA-002", "engine/editor_status.py blanket swallow", once=True)
            lights = None
        if isinstance(lights, list) and 0 <= index < len(lights):
            light = lights[index]
            if isinstance(light, dict):
                for key in ("name", "id", "tag"):
                    raw = light.get(key)
                    if isinstance(raw, str) and raw.strip():
                        return raw.strip()
    return f"light_{index + 1}"


def _occluder_selection_label(editor_state: Any, index: int) -> str:
    getter = getattr(editor_state, "_get_scene_occluders", None)
    if callable(getter):
        try:
            occluders = getter()
        except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
            _log_swallow("ESTA-003", "engine/editor_status.py blanket swallow", once=True)
            occluders = None
        if isinstance(occluders, list) and 0 <= index < len(occluders):
            occluder = occluders[index]
            if isinstance(occluder, dict):
                for key in ("name", "id"):
                    raw = occluder.get(key)
                    if isinstance(raw, str) and raw.strip():
                        return raw.strip()
    return f"poly_{index + 1}"


def _selection_label(editor_state: Any) -> str:
    if bool(getattr(editor_state, "lights_tool_active", False)):
        index = getattr(editor_state, "lights_selection", None)
        if isinstance(index, int) and index >= 0:
            return f"Light: {_light_selection_label(editor_state, index)}"
        return ""

    if bool(getattr(editor_state, "occluder_tool_active", False)):
        index = getattr(editor_state, "occluder_selection", None)
        if isinstance(index, int) and index >= 0:
            return f"Occluder: {_occluder_selection_label(editor_state, index)}"
        return ""

    sprite = getattr(editor_state, "selected_entity", None)
    if sprite is None:
        return ""
    return f"Entity: {_entity_display_name(editor_state, sprite)}"


def _problems_indicator(editor_state: Any) -> str | None:
    problems = getattr(editor_state, "problems", None)
    if problems is None:
        return None
    refresher = getattr(problems, "refresh_structured_diagnostics", None)
    if callable(refresher):
        try:
            refresher()
        except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
            _log_swallow("ESTA-004", "engine/editor_status.py blanket swallow", once=True)
            return None
    has_new = bool(getattr(problems, "has_new_error_indicator", lambda: False)())
    if not has_new:
        return None
    counts_getter = getattr(problems, "get_severity_counts", None)
    if not callable(counts_getter):
        return "Problems: new errors"
    try:
        counts = counts_getter()
    except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
        _log_swallow("ESTA-005", "engine/editor_status.py blanket swallow", once=True)
        return "Problems: new errors"
    errors = int(counts.get("error", 0)) if isinstance(counts, dict) else 0
    return f"Problems: {errors} new error(s)"


def build_editor_status(editor_state: Any, window_w: int = 800, window_h: int = 600) -> dict[str, str | None]:
    """Build editor status bar data.

    Args:
        editor_state: Editor controller instance.
        window_w: Window width for cursor hint computation.
        window_h: Window height for cursor hint computation.

    Returns:
        Dictionary with status bar sections:
        - scene_label: Scene name
        - dirty_label: Saved/Unsaved state
        - selection_label: Current selection info
        - hint_label: Keyboard shortcuts hint
        - operation_banner: Active operation banner or None
        - cursor_hint: Cursor affordance hint or None
    """
    # Get cursor hint from controller if available
    cursor_hint: str | None = None
    get_hint = getattr(editor_state, "get_cursor_hint_text", None)
    if callable(get_hint):
        try:
            cursor_hint = get_hint(window_w, window_h)
        except Exception:  # noqa: BLE001  # REASON: editor fallback isolation
            _log_swallow("ESTA-006", "engine/editor_status.py blanket swallow", once=True)
            cursor_hint = None

    return {
        "scene_label": _scene_label(editor_state),
        "dirty_label": _dirty_label(editor_state),
        "selection_label": _selection_label(editor_state),
        "hint_label": HINT_LABEL,
        "operation_banner": build_editor_operation_banner(editor_state),
        "cursor_hint": cursor_hint,
        "problems_indicator": _problems_indicator(editor_state),
    }
