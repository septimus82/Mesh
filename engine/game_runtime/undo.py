from dataclasses import dataclass
from typing import Any
import copy

@dataclass(slots=True)
class UndoFrame:
    scene_path: str
    authored_scene_payload: dict[str, Any]
    dirty_counter: int
    reason: str
    ts_counter: int

def undo_enabled(window: Any) -> bool:
    return bool(getattr(window, "show_debug", False)) and int(getattr(window, "_undo_suppress_count", 0) or 0) <= 0

def snapshot_current_authored_scene_payload(window: Any) -> UndoFrame | None:
    sc = getattr(window, "scene_controller", None)
    scene_path = str(getattr(sc, "current_scene_path", "") or "").strip() if sc is not None else ""
    getter = getattr(sc, "get_authored_scene_payload", None) if sc is not None else None
    payload = getter() if callable(getter) else None
    if not scene_path or not isinstance(payload, dict):
        return None

    ts = int(getattr(window, "_undo_ts_counter", 0) or 0) + 1
    window._undo_ts_counter = ts
    return UndoFrame(
        scene_path=scene_path,
        authored_scene_payload=copy.deepcopy(payload),
        dirty_counter=int(getattr(window, "scene_dirty_counter", 0) or 0),
        reason="",
        ts_counter=ts,
    )

def push_undo_frame(window: Any, reason: str) -> bool:
    if not undo_enabled(window):
        return False

    frame = snapshot_current_authored_scene_payload(window)
    if frame is None:
        return False
    frame.reason = str(reason or "").strip()

    undo_stack = getattr(window, "undo_stack", None)
    if not isinstance(undo_stack, list):
        undo_stack = []
        window.undo_stack = undo_stack
    redo_stack = getattr(window, "redo_stack", None)
    if not isinstance(redo_stack, list):
        redo_stack = []
        window.redo_stack = redo_stack

    if undo_stack and isinstance(undo_stack[-1], UndoFrame):
        if undo_stack[-1].scene_path == frame.scene_path and undo_stack[-1].authored_scene_payload == frame.authored_scene_payload:
            return False

    undo_stack.append(frame)
    if len(undo_stack) > 50:
        del undo_stack[: len(undo_stack) - 50]
    redo_stack.clear()
    return True

def undo(window: Any) -> bool:
    if not bool(getattr(window, "show_debug", False)):
        print("UNDO noop reason=empty")
        return False

    undo_stack = getattr(window, "undo_stack", None)
    redo_stack = getattr(window, "redo_stack", None)
    if not (isinstance(undo_stack, list) and isinstance(redo_stack, list)) or not undo_stack:
        print("UNDO noop reason=empty")
        return False

    sc = getattr(window, "scene_controller", None)
    current_scene_path = str(getattr(sc, "current_scene_path", "") or "").strip() if sc is not None else ""
    top = undo_stack[-1]
    if not isinstance(top, UndoFrame) or not current_scene_path or top.scene_path != current_scene_path:
        print("UNDO noop reason=scene_mismatch")
        return False

    current = snapshot_current_authored_scene_payload(window)
    if current is None:
        print("UNDO noop reason=empty")
        return False
    current.reason = "undo"

    frame = undo_stack.pop()
    redo_stack.append(current)
    if len(redo_stack) > 50:
        del redo_stack[: len(redo_stack) - 50]

    applier = getattr(sc, "debug_apply_authored_scene_payload", None) if sc is not None else None
    if not callable(applier):
        print("UNDO noop reason=empty")
        undo_stack.append(frame)
        redo_stack.pop()
        return False

    window._undo_suppress_count = int(getattr(window, "_undo_suppress_count", 0) or 0) + 1
    try:
        ok = bool(applier(frame.authored_scene_payload))
    finally:
        window._undo_suppress_count = max(0, int(getattr(window, "_undo_suppress_count", 0) or 0) - 1)
    if not ok:
        undo_stack.append(frame)
        redo_stack.pop()
        print("UNDO noop reason=empty")
        return False

    marker = getattr(window, "mark_scene_dirty", None)
    if callable(marker):
        marker("undo")
    print(f"UNDO ok depth={len(undo_stack)} redo={len(redo_stack)}")
    return True

def redo(window: Any) -> bool:
    if not bool(getattr(window, "show_debug", False)):
        print("REDO noop reason=empty")
        return False

    undo_stack = getattr(window, "undo_stack", None)
    redo_stack = getattr(window, "redo_stack", None)
    if not (isinstance(undo_stack, list) and isinstance(redo_stack, list)) or not redo_stack:
        print("REDO noop reason=empty")
        return False

    sc = getattr(window, "scene_controller", None)
    current_scene_path = str(getattr(sc, "current_scene_path", "") or "").strip() if sc is not None else ""
    top = redo_stack[-1]
    if not isinstance(top, UndoFrame) or not current_scene_path or top.scene_path != current_scene_path:
        print("REDO noop reason=scene_mismatch")
        return False

    current = snapshot_current_authored_scene_payload(window)
    if current is None:
        print("REDO noop reason=empty")
        return False
    current.reason = "redo"

    frame = redo_stack.pop()
    undo_stack.append(current)
    if len(undo_stack) > 50:
        del undo_stack[: len(undo_stack) - 50]

    applier = getattr(sc, "debug_apply_authored_scene_payload", None) if sc is not None else None
    if not callable(applier):
        print("REDO noop reason=empty")
        redo_stack.append(frame)
        undo_stack.pop()
        return False

    window._undo_suppress_count = int(getattr(window, "_undo_suppress_count", 0) or 0) + 1
    try:
        ok = bool(applier(frame.authored_scene_payload))
    finally:
        window._undo_suppress_count = max(0, int(getattr(window, "_undo_suppress_count", 0) or 0) - 1)
    if not ok:
        redo_stack.append(frame)
        undo_stack.pop()
        print("REDO noop reason=empty")
        return False

    marker = getattr(window, "mark_scene_dirty", None)
    if callable(marker):
        marker("redo")
    print(f"REDO ok depth={len(undo_stack)} redo={len(redo_stack)}")
    return True
