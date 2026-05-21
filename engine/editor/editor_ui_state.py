from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from engine import json_io
from engine.logging_tools import get_logger
from engine.repo_root import get_repo_root
from engine.swallowed_exceptions import _log_swallow


_LOG = get_logger(__name__)

_SCHEMA_VERSION = 1
_STATE_ENV = "MESH_EDITOR_UI_STATE_PATH"
_DEFAULT_STATE_DIR = ".mesh"
_DEFAULT_STATE_FILENAME = "editor_ui_state.json"
_LEFT_DOCK_TABS = {"Project", "Scene", "Outliner"}
_RIGHT_DOCK_TABS = {"Inspector", "Assets", "Items", "History", "Problems", "Debug"}


@dataclass(frozen=True, slots=True)
class EditorUiState:
    command_palette_open: bool = False
    scene_switcher_open: bool = False
    scene_browser_open: bool = False
    asset_browser_open: bool = False
    problems_panel_open: bool = False
    left_dock_tab: str = "Outliner"
    right_dock_tab: str = "Inspector"
    dock_left_collapsed: bool = False
    dock_right_collapsed: bool = False
    viewport_maximized: bool = False


def _coerce_left_tab(value: Any) -> str:
    text = str(value or "").strip()
    if text in _LEFT_DOCK_TABS:
        return text
    return EditorUiState().left_dock_tab


def _coerce_right_tab(value: Any) -> str:
    text = str(value or "").strip()
    if text in _RIGHT_DOCK_TABS:
        return text
    return EditorUiState().right_dock_tab


def resolve_editor_ui_state_path(
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


def dump_ui_state(state: EditorUiState) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "command_palette_open": bool(state.command_palette_open),
        "scene_switcher_open": bool(state.scene_switcher_open),
        "scene_browser_open": bool(state.scene_browser_open),
        "asset_browser_open": bool(state.asset_browser_open),
        "problems_panel_open": bool(state.problems_panel_open),
        "left_dock_tab": str(state.left_dock_tab),
        "right_dock_tab": str(state.right_dock_tab),
        "dock_left_collapsed": bool(state.dock_left_collapsed),
        "dock_right_collapsed": bool(state.dock_right_collapsed),
        "viewport_maximized": bool(state.viewport_maximized),
    }


def load_ui_state(payload: Any) -> EditorUiState:
    defaults = EditorUiState()
    if not isinstance(payload, dict):
        return defaults
    schema = _coerce_schema_version(payload.get("schema_version", 0))
    if schema is None:
        schema = 0
    if schema != _SCHEMA_VERSION:
        return defaults
    right_tab = _coerce_right_tab(payload.get("right_dock_tab", defaults.right_dock_tab))
    problems_open = bool(payload.get("problems_panel_open", right_tab == "Problems"))
    return EditorUiState(
        command_palette_open=bool(payload.get("command_palette_open", defaults.command_palette_open)),
        scene_switcher_open=bool(payload.get("scene_switcher_open", defaults.scene_switcher_open)),
        scene_browser_open=bool(payload.get("scene_browser_open", defaults.scene_browser_open)),
        asset_browser_open=bool(payload.get("asset_browser_open", defaults.asset_browser_open)),
        problems_panel_open=problems_open,
        left_dock_tab=_coerce_left_tab(payload.get("left_dock_tab", defaults.left_dock_tab)),
        right_dock_tab=right_tab,
        dock_left_collapsed=bool(payload.get("dock_left_collapsed", defaults.dock_left_collapsed)),
        dock_right_collapsed=bool(payload.get("dock_right_collapsed", defaults.dock_right_collapsed)),
        viewport_maximized=bool(payload.get("viewport_maximized", defaults.viewport_maximized)),
    )


def load_editor_ui_state(
    path: str | Path | None = None,
    *,
    repo_root: Path | None = None,
    self_heal_schema_mismatch: bool = True,
) -> EditorUiState:
    state_path = resolve_editor_ui_state_path(path=path, repo_root=repo_root)
    defaults = EditorUiState()
    try:
        payload = json_io.read_json(state_path)
    except FileNotFoundError:
        return defaults
    except Exception as exc:  # noqa: BLE001  # REASON: corrupt UI state files should log and fall back to default editor UI layout
        _LOG.warning("Failed to read editor UI state from %s: %s", state_path, exc)
        return defaults
    loaded = load_ui_state(payload)
    if loaded == defaults:
        schema = None
        if isinstance(payload, dict):
            schema = _coerce_schema_version(payload.get("schema_version", None))
        if schema != _SCHEMA_VERSION and bool(self_heal_schema_mismatch):
            save_editor_ui_state(defaults, path=state_path)
    return loaded


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


def save_editor_ui_state(
    state: EditorUiState,
    path: str | Path | None = None,
    *,
    repo_root: Path | None = None,
) -> None:
    state_path = resolve_editor_ui_state_path(path=path, repo_root=repo_root)
    payload = dump_ui_state(state)
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        json_io.write_json_atomic(state_path, payload)
    except Exception as exc:  # noqa: BLE001  # REASON: UI state persistence failures should log without breaking editor shutdown flows
        _LOG.warning("Failed to save editor UI state to %s: %s", state_path, exc)


def reset_editor_ui_state(
    path: str | Path | None = None,
    *,
    repo_root: Path | None = None,
) -> bool:
    state_path = resolve_editor_ui_state_path(path=path, repo_root=repo_root)
    try:
        if not state_path.exists():
            return False
        state_path.unlink()
        return True
    except Exception as exc:  # noqa: BLE001  # REASON: UI state reset failures should log without breaking editor recovery flows
        _LOG.warning("Failed to reset editor UI state at %s: %s", state_path, exc)
        return False


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
            _log_swallow("EDIT-001", "engine/editor/editor_ui_state.py pass-only blanket swallow")
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


def capture_editor_ui_state(editor: Any) -> EditorUiState:
    dock = getattr(editor, "dock", None)
    panels = getattr(editor, "panels", None)
    is_palette_open = getattr(panels, "is_command_palette_open", None)
    palette_open = bool(is_palette_open()) if callable(is_palette_open) else False
    left_tab = getattr(dock, "left_tab", EditorUiState().left_dock_tab) if dock is not None else EditorUiState().left_dock_tab
    right_tab = getattr(dock, "right_tab", EditorUiState().right_dock_tab) if dock is not None else EditorUiState().right_dock_tab
    get_left_collapsed = getattr(dock, "get_left_collapsed", None)
    get_right_collapsed = getattr(dock, "get_right_collapsed", None)
    get_viewport_maximized = getattr(dock, "get_viewport_maximized", None)
    return EditorUiState(
        command_palette_open=palette_open,
        scene_switcher_open=bool(getattr(editor, "scene_switcher_active", False)),
        scene_browser_open=bool(getattr(editor, "scene_browser_active", False)),
        asset_browser_open=bool(getattr(editor, "asset_browser_active", False)),
        problems_panel_open=_coerce_right_tab(right_tab) == "Problems",
        left_dock_tab=_coerce_left_tab(left_tab),
        right_dock_tab=_coerce_right_tab(right_tab),
        dock_left_collapsed=bool(get_left_collapsed()) if callable(get_left_collapsed) else False,
        dock_right_collapsed=bool(get_right_collapsed()) if callable(get_right_collapsed) else False,
        viewport_maximized=bool(get_viewport_maximized()) if callable(get_viewport_maximized) else False,
    )


def apply_editor_ui_state(editor: Any, state: EditorUiState) -> None:
    panels = getattr(editor, "panels", None)
    if panels is not None:
        open_palette = getattr(panels, "open_command_palette", None)
        close_palette = getattr(panels, "close_command_palette", None)
        if state.command_palette_open and callable(open_palette):
            open_palette()
        elif not state.command_palette_open and callable(close_palette):
            close_palette()

    setattr(editor, "scene_switcher_active", bool(state.scene_switcher_open))
    setattr(editor, "scene_browser_active", bool(state.scene_browser_open))
    setattr(editor, "asset_browser_active", bool(state.asset_browser_open))

    dock = getattr(editor, "dock", None)
    if dock is not None:
        set_left_tab = getattr(dock, "set_left_tab", None)
        set_right_tab = getattr(dock, "set_right_tab", None)
        set_left_collapsed = getattr(dock, "set_left_collapsed", None)
        set_right_collapsed = getattr(dock, "set_right_collapsed", None)
        set_viewport_maximized = getattr(dock, "set_viewport_maximized", None)
        if callable(set_left_tab):
            set_left_tab(state.left_dock_tab, force=True)
        if callable(set_right_tab):
            set_right_tab(state.right_dock_tab, force=True)
        if bool(state.problems_panel_open) and callable(set_right_tab):
            set_right_tab("Problems", force=True)
        if callable(set_left_collapsed):
            set_left_collapsed(state.dock_left_collapsed)
        if callable(set_right_collapsed):
            set_right_collapsed(state.dock_right_collapsed)
        if callable(set_viewport_maximized):
            set_viewport_maximized(state.viewport_maximized)


def save_editor_ui_state_for_editor(editor: Any) -> None:
    if editor is None:
        return
    state = capture_editor_ui_state(editor)
    save_editor_ui_state(state, repo_root=_resolve_editor_repo_root(editor))
