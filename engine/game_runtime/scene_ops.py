from typing import Any


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)

def mark_scene_dirty(window: Any, reason: str) -> None:
    reason_text = str(reason or "").strip()
    window.scene_dirty = True
    window.scene_dirty_reason = reason_text
    window.scene_dirty_counter = int(getattr(window, "scene_dirty_counter", 0) or 0) + 1

def record_recent_scene(window: Any, scene_path: str) -> None:
    from engine.path_norm import normalize_scene_path

    p = normalize_scene_path(str(scene_path or "").strip())
    if not p or p == "-":
        return
    recent = getattr(window, "recent_scenes", None)
    if not isinstance(recent, list):
        recent = []
    try:
        while p in recent:
            recent.remove(p)
    except Exception:  # noqa: BLE001  # REASON: recent-scene list cleanup failures should not block recording the current scene path
        _log_swallow("SCEN-001", "engine/game_runtime/scene_ops.py pass-only blanket swallow")
        pass
    recent.insert(0, p)
    if len(recent) > 20:
        del recent[20:]
    window.recent_scenes = recent
    try:
        on_recent = getattr(window, "_on_recent_scene_recorded", None)
        if callable(on_recent):
            on_recent(p)
    except Exception:  # noqa: BLE001  # REASON: recent-scene callbacks are optional and should not break recent-scene bookkeeping
        _log_swallow("SCEN-002", "engine/game_runtime/scene_ops.py pass-only blanket swallow")
        pass

def get_recent_scenes(window: Any) -> list[str]:
    recent = getattr(window, "recent_scenes", None)
    if not isinstance(recent, list):
        return []
    return [str(v).strip() for v in recent if isinstance(v, str) and str(v).strip()]

def clear_scene_dirty(window: Any) -> None:
    window.scene_dirty = False
    window.scene_dirty_reason = ""

def reload_scene_from_disk(window: Any) -> bool:
    scene_path = str(getattr(window.scene_controller, "current_scene_path", "") or "").strip()
    window._undo_suppress_count = int(getattr(window, "_undo_suppress_count", 0) or 0) + 1
    try:
        ok = bool(window.reload_scene(scene_path or None))
    finally:
        window._undo_suppress_count = max(0, int(getattr(window, "_undo_suppress_count", 0) or 0) - 1)
    if ok:
        clear_scene_dirty(window)
        clearer = getattr(window, "clear_hot_reload_error", None)
        if callable(clearer):
            clearer()
        hud = getattr(window, "player_hud", None)
        enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
        if callable(enqueue):
            enqueue("Scene reloaded", seconds=2.0)
    else:
        message = str(getattr(window.scene_controller, "_last_hot_reload_error_message", "") or "").strip()
        if not message:
            message = "Scene reload failed"
        setter = getattr(window, "set_hot_reload_error", None)
        if callable(setter):
            setter(message, scene_path)
        else:
            window.hot_reload_error_message = message
            window.hot_reload_error_scene_path = scene_path
            window.hot_reload_error_visible = True
    return ok

def persist_scene_to_disk(window: Any) -> Any:
    from engine.tooling_runtime.entity_persist import persist_scene_payload

    scene_path = str(getattr(window.scene_controller, "current_scene_path", "") or "").strip()
    getter = getattr(window.scene_controller, "get_authored_scene_payload", None)
    payload = getter() if callable(getter) else None
    if not isinstance(payload, dict) or not scene_path:
        return persist_scene_payload(scene_path or "", {}, strict_no_overwrite=False)

    result = persist_scene_payload(scene_path, payload, strict_no_overwrite=False)
    window.last_persist_path = str(result.path)
    if result.ok:
        clear_scene_dirty(window)
    return result

def save_scene_as(window: Any, new_scene_path: str) -> Any:
    from pathlib import Path as _Path
    from engine.path_norm import normalize_scene_path
    from engine.tooling_runtime.entity_persist import PersistResult, persist_scene_payload

    if not bool(getattr(window, "scene_persist_armed", False)):
        path_display = normalize_scene_path(str(new_scene_path or "").strip() or "-")
        print(f"SCENE_SAVE_AS fail path={path_display} reason=not_armed")
        return PersistResult(ok=False, path=path_display, wrote=False, errors=["not_armed"])

    sc = getattr(window, "scene_controller", None)
    current_scene_path = str(getattr(sc, "current_scene_path", "") or "").strip() if sc is not None else ""
    getter = getattr(sc, "get_authored_scene_payload", None) if sc is not None else None
    payload = getter() if callable(getter) else None
    if not current_scene_path or not isinstance(payload, dict):
        print("SCENE_SAVE_AS fail path=- reason=no_scene")
        return PersistResult(ok=False, path="-", wrote=False, errors=["no_scene"])

    requested = str(new_scene_path or "").strip()
    if requested:
        result = persist_scene_payload(requested, payload, strict_no_overwrite=True)
        reason = ",".join(result.errors) if result.errors else "-"
        print(f"SCENE_SAVE_AS {'ok' if result.ok else 'fail'} path={result.path} reason={reason}")
        return result

    base = _Path(current_scene_path)
    base_dir = base.parent
    stem = base.stem
    suffix = "__v"
    for k in range(1, 1000):
        candidate = str(base_dir / f"{stem}{suffix}{k:03d}.json")
        result = persist_scene_payload(candidate, payload, strict_no_overwrite=True)
        if result.ok:
            reason = ",".join(result.errors) if result.errors else "-"
            print(f"SCENE_SAVE_AS ok path={result.path} reason={reason}")
            return result
        if "exists_different" in (result.errors or []):
            continue
        reason = ",".join(result.errors) if result.errors else "error"
        print(f"SCENE_SAVE_AS fail path={result.path} reason={reason}")
        return result

    path_display = normalize_scene_path(str(base_dir / f"{stem}{suffix}999.json"))
    print(f"SCENE_SAVE_AS fail path={path_display} reason=version_exhausted")
    return PersistResult(ok=False, path=path_display, wrote=False, errors=["version_exhausted"])
