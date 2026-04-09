from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
from pathlib import Path
from typing import Any

from engine import json_io
from engine.logging_tools import get_logger
from engine.path_norm import normalize_scene_path
from engine.repo_root import get_repo_root


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)

_LOG = get_logger(__name__)

_SCHEMA_VERSION = 1
_STATE_ENV = "MESH_EDITOR_SESSION_STATE_PATH"
_DEFAULT_STATE_DIR = ".mesh"
_DEFAULT_STATE_FILENAME = "editor_session_state.json"
_MAX_CAMERA_SCENES = 25


@dataclass(frozen=True, slots=True)
class EditorSessionState:
    last_scene_path: str | None = None
    camera_by_scene: dict[str, dict[str, float]] = field(default_factory=dict)
    camera_scene_order: tuple[str, ...] = ()


def resolve_editor_session_state_path(
    path: str | Path | None = None,
    *,
    repo_root: Path | None = None,
) -> Path:
    if path is not None:
        return Path(path)
    env = str(os.environ.get(_STATE_ENV, "") or "").strip()
    if env:
        return Path(env)
    root = repo_root if repo_root is not None else get_repo_root()
    return root / _DEFAULT_STATE_DIR / _DEFAULT_STATE_FILENAME


def dump_editor_session_state(state: EditorSessionState) -> dict[str, Any]:
    scene_path = state.last_scene_path
    normalized = normalize_scene_path(scene_path) if scene_path is not None else ""
    camera_by_scene = dict(state.camera_by_scene or {})
    pruned_by_scene, pruned_order = _prune_camera_entries(camera_by_scene, list(state.camera_scene_order))
    return {
        "schema_version": _SCHEMA_VERSION,
        "last_scene_path": normalized if normalized else None,
        "camera_by_scene": pruned_by_scene,
        "camera_scene_order": list(pruned_order),
    }


def load_editor_session_state_payload(payload: Any) -> EditorSessionState:
    defaults = EditorSessionState()
    if not isinstance(payload, dict):
        return defaults
    schema = _coerce_schema_version(payload.get("schema_version", 0))
    if schema != _SCHEMA_VERSION:
        return defaults
    raw_last_scene = payload.get("last_scene_path")
    last_scene = normalize_scene_path(raw_last_scene) if isinstance(raw_last_scene, str) else ""
    parsed_camera_by_scene: dict[str, dict[str, float]] = {}
    raw_camera_by_scene = payload.get("camera_by_scene")
    if isinstance(raw_camera_by_scene, dict):
        for raw_scene_path, raw_camera in raw_camera_by_scene.items():
            if not isinstance(raw_scene_path, str):
                continue
            scene_path = normalize_scene_path(raw_scene_path)
            if not scene_path:
                continue
            camera_state = _coerce_camera_state(raw_camera)
            if camera_state is None:
                continue
            parsed_camera_by_scene[scene_path] = camera_state
    order = _coerce_camera_scene_order(payload.get("camera_scene_order"), parsed_camera_by_scene)
    if not order:
        if last_scene and last_scene in parsed_camera_by_scene:
            order.append(last_scene)
        for scene_path in sorted(parsed_camera_by_scene):
            if scene_path != last_scene:
                order.append(scene_path)
    pruned_by_scene, pruned_order = _prune_camera_entries(parsed_camera_by_scene, order)
    return EditorSessionState(
        last_scene_path=last_scene or None,
        camera_by_scene=pruned_by_scene,
        camera_scene_order=tuple(pruned_order),
    )


def load_editor_session_state(
    path: str | Path | None = None,
    *,
    repo_root: Path | None = None,
) -> EditorSessionState:
    state_path = resolve_editor_session_state_path(path=path, repo_root=repo_root)
    try:
        payload = json_io.read_json(state_path)
    except FileNotFoundError:
        return EditorSessionState()
    except Exception as exc:  # noqa: BLE001  # REASON: corrupt session state files should log and fall back to a clean editor session
        _LOG.warning("Failed to read editor session state from %s: %s", state_path, exc)
        return EditorSessionState()
    return load_editor_session_state_payload(payload)


def save_editor_session_state(
    state: EditorSessionState,
    path: str | Path | None = None,
    *,
    repo_root: Path | None = None,
) -> None:
    state_path = resolve_editor_session_state_path(path=path, repo_root=repo_root)
    payload = dump_editor_session_state(state)
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        json_io.write_json_atomic(state_path, payload)
    except Exception as exc:  # noqa: BLE001  # REASON: session state persistence failures should log without breaking editor shutdown flows
        _LOG.warning("Failed to save editor session state to %s: %s", state_path, exc)


def save_editor_session_state_for_editor(editor: Any, scene_path: str) -> None:
    normalized = normalize_scene_path(scene_path)
    if not normalized:
        return
    repo_root = _resolve_editor_repo_root(editor)
    state = load_editor_session_state(repo_root=repo_root)
    updated = EditorSessionState(
        last_scene_path=normalized,
        camera_by_scene=dict(state.camera_by_scene or {}),
        camera_scene_order=tuple(state.camera_scene_order),
    )
    camera_state = capture_camera_state_for_editor(editor)
    if camera_state is not None:
        updated = record_camera_for_scene(updated, normalized, camera_state)
        updated = EditorSessionState(
            last_scene_path=normalized,
            camera_by_scene=dict(updated.camera_by_scene or {}),
            camera_scene_order=tuple(updated.camera_scene_order),
        )
    save_editor_session_state(
        updated,
        repo_root=repo_root,
    )


def record_camera_for_scene(
    state: EditorSessionState,
    scene_path: str,
    camera_state: Any,
) -> EditorSessionState:
    normalized = normalize_scene_path(scene_path)
    if not normalized:
        return state
    parsed_camera = _coerce_camera_state(camera_state)
    if parsed_camera is None:
        return state
    camera_by_scene = dict(state.camera_by_scene or {})
    camera_by_scene[normalized] = parsed_camera
    order = [path for path in state.camera_scene_order if path != normalized]
    order.insert(0, normalized)
    pruned_by_scene, pruned_order = _prune_camera_entries(camera_by_scene, order)
    return EditorSessionState(
        last_scene_path=state.last_scene_path,
        camera_by_scene=pruned_by_scene,
        camera_scene_order=tuple(pruned_order),
    )


def get_camera_for_scene(
    state: EditorSessionState,
    scene_path: str,
) -> dict[str, float] | None:
    normalized = normalize_scene_path(scene_path)
    if not normalized:
        return None
    camera_by_scene = dict(state.camera_by_scene or {})
    camera_state = camera_by_scene.get(normalized)
    if camera_state is None:
        return None
    parsed = _coerce_camera_state(camera_state)
    if parsed is None:
        return None
    return parsed


def capture_camera_state_for_editor(editor: Any) -> dict[str, float] | None:
    window = getattr(editor, "window", None)
    if window is None:
        return None
    return capture_camera_state_for_window(window)


def capture_camera_state_for_window(window: Any) -> dict[str, float] | None:
    center = _read_camera_center(window)
    zoom = _read_camera_zoom(window)
    if center is None or zoom is None:
        return None
    x, y = center
    return {"x": x, "y": y, "zoom": zoom}


def apply_camera_state_for_editor(editor: Any, camera_state: Any) -> bool:
    window = getattr(editor, "window", None)
    if window is None:
        return False
    return apply_camera_state_for_window(window, camera_state)


def apply_camera_state_for_window(window: Any, camera_state: Any) -> bool:
    parsed = _coerce_camera_state(camera_state)
    if parsed is None:
        return False
    x = parsed["x"]
    y = parsed["y"]
    zoom = parsed["zoom"]
    applied = False
    setter = getattr(window, "set_camera_zoom_target", None)
    if callable(setter):
        try:
            setter(zoom, speed=999.0)
            applied = True
        except Exception:
            _log_swallow("EDIT-001", "engine/editor/editor_session_state.py pass-only blanket swallow")
            pass
    if not applied:
        zoom_state = getattr(getattr(window, "camera_controller", None), "zoom_state", None)
        if zoom_state is not None:
            try:
                setattr(zoom_state, "current", zoom)
                applied = True
            except Exception:
                _log_swallow("EDIT-002", "engine/editor/editor_session_state.py pass-only blanket swallow")
                pass
    camera = getattr(window, "camera", None)
    if camera is not None:
        move_to = getattr(camera, "move_to", None)
        if callable(move_to):
            try:
                move_to((x, y), 1.0)
                applied = True
            except Exception:
                _log_swallow("EDIT-003", "engine/editor/editor_session_state.py pass-only blanket swallow")
                pass
        else:
            try:
                setattr(camera, "position", (x, y))
                applied = True
            except Exception:
                _log_swallow("EDIT-004", "engine/editor/editor_session_state.py pass-only blanket swallow")
                pass
    return applied


def _resolve_editor_repo_root(editor: Any) -> Path | None:
    getter = getattr(editor, "_get_repo_root", None)
    if callable(getter):
        try:
            root = getter()
            if isinstance(root, Path):
                return root
            if root is not None:
                return Path(root)
        except Exception:
            _log_swallow("EDIT-005", "engine/editor/editor_session_state.py pass-only blanket swallow")
            pass
    root = getattr(editor, "_repo_root_override", None)
    if isinstance(root, Path):
        return root
    if root is not None:
        try:
            return Path(root)
        except Exception:
            return None
    return None


def _coerce_schema_version(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _coerce_camera_state(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    x = _coerce_float(value.get("x"))
    y = _coerce_float(value.get("y"))
    zoom = _coerce_float(value.get("zoom"))
    if x is None or y is None or zoom is None:
        return None
    return {"x": x, "y": y, "zoom": zoom}


def _coerce_camera_scene_order(
    value: Any,
    camera_by_scene: dict[str, dict[str, float]],
) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    order: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        scene_path = normalize_scene_path(item)
        if not scene_path or scene_path in seen or scene_path not in camera_by_scene:
            continue
        seen.add(scene_path)
        order.append(scene_path)
    return order


def _prune_camera_entries(
    camera_by_scene: dict[str, dict[str, float]],
    order: list[str],
) -> tuple[dict[str, dict[str, float]], tuple[str, ...]]:
    seen: set[str] = set()
    normalized_order: list[str] = []
    for scene_path in order:
        normalized = normalize_scene_path(scene_path)
        if not normalized or normalized in seen or normalized not in camera_by_scene:
            continue
        seen.add(normalized)
        normalized_order.append(normalized)
    extras = sorted(scene_path for scene_path in camera_by_scene if scene_path not in seen)
    merged = normalized_order + extras
    pruned_order = tuple(merged[:_MAX_CAMERA_SCENES])
    pruned_map = {scene_path: dict(camera_by_scene[scene_path]) for scene_path in pruned_order}
    return pruned_map, pruned_order


def _read_camera_center(window: Any) -> tuple[float, float] | None:
    getter = getattr(window, "get_camera_center", None)
    if callable(getter):
        try:
            raw = getter()
            if isinstance(raw, (list, tuple)) and len(raw) >= 2:
                x = _coerce_float(raw[0])
                y = _coerce_float(raw[1])
                if x is not None and y is not None:
                    return (x, y)
        except Exception:
            _log_swallow("EDIT-006", "engine/editor/editor_session_state.py pass-only blanket swallow")
            pass
    camera = getattr(window, "camera", None)
    raw_pos = getattr(camera, "position", None) if camera is not None else None
    if isinstance(raw_pos, (list, tuple)) and len(raw_pos) >= 2:
        x = _coerce_float(raw_pos[0])
        y = _coerce_float(raw_pos[1])
        if x is not None and y is not None:
            return (x, y)
    return None


def _read_camera_zoom(window: Any) -> float | None:
    try:
        zoom_state = getattr(getattr(window, "camera_controller", None), "zoom_state", None)
        if zoom_state is not None:
            zoom = _coerce_float(getattr(zoom_state, "current", None))
            if zoom is not None:
                return zoom
    except Exception:
        _log_swallow("EDIT-007", "engine/editor/editor_session_state.py pass-only blanket swallow")
        pass
    camera = getattr(window, "camera", None)
    zoom = _coerce_float(getattr(camera, "zoom", None)) if camera is not None else None
    return zoom


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, (str, bytes, bytearray)):
        try:
            numeric = float(value)
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(numeric):
        return None
    return numeric
