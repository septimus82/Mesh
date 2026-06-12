from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine.editor.editor_session_state import (
    EditorSessionState,
    load_editor_session_state,
    resolve_editor_session_state_path,
    save_editor_session_state,
    save_editor_session_state_for_editor,
)
from engine.editor.editor_workspace_controller import EditorWorkspaceController
from engine.game_runtime import scene_ops

pytestmark = pytest.mark.fast


def _make_editor(repo_root: Path) -> SimpleNamespace:
    window = SimpleNamespace(
        load_scene=MagicMock(),
        scene_controller=SimpleNamespace(current_scene_path=None),
    )
    return SimpleNamespace(
        window=window,
        _repo_root_override=repo_root,
        _get_repo_root=lambda: repo_root,
    )


def test_editor_session_state_roundtrip_and_deterministic_save(tmp_path: Path) -> None:
    state_path = resolve_editor_session_state_path(repo_root=tmp_path)
    state = EditorSessionState(last_scene_path="scenes/cellar.json")
    save_editor_session_state(state, path=state_path)
    loaded = load_editor_session_state(path=state_path)
    assert loaded == EditorSessionState(last_scene_path="scenes/cellar.json")

    first = state_path.read_text(encoding="utf-8")
    save_editor_session_state(state, path=state_path)
    second = state_path.read_text(encoding="utf-8")
    assert first == second


def test_editor_session_state_missing_and_corrupt_defaults(tmp_path: Path) -> None:
    state_path = resolve_editor_session_state_path(repo_root=tmp_path)
    assert load_editor_session_state(path=state_path) == EditorSessionState()

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{bad json", encoding="utf-8")
    assert load_editor_session_state(path=state_path) == EditorSessionState()


def test_scene_change_save_then_startup_restore_opens_last_scene(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene_path = tmp_path / "scenes" / "cellar.json"
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    scene_path.write_text("{}", encoding="utf-8")

    editor_save = SimpleNamespace(
        _repo_root_override=tmp_path,
        _get_repo_root=lambda: tmp_path,
    )
    window_save = SimpleNamespace(
        recent_scenes=[],
        _on_recent_scene_recorded=lambda path: save_editor_session_state_for_editor(editor_save, path),
    )
    scene_ops.record_recent_scene(window_save, "scenes/cellar.json")

    state_path = resolve_editor_session_state_path(repo_root=tmp_path)
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload.get("last_scene_path") == "scenes/cellar.json"

    editor_load = _make_editor(tmp_path)
    ctl = EditorWorkspaceController(editor_load)
    monkeypatch.setattr(ctl, "load_workspace", lambda: None)
    ctl.load_on_startup()
    editor_load.window.load_scene.assert_called_once_with("scenes/cellar.json")


def test_startup_restore_invalid_path_is_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_path = resolve_editor_session_state_path(repo_root=tmp_path)
    save_editor_session_state(
        EditorSessionState(last_scene_path="scenes/missing.json"),
        path=state_path,
    )

    editor = _make_editor(tmp_path)
    ctl = EditorWorkspaceController(editor)
    monkeypatch.setattr(ctl, "load_workspace", lambda: None)
    ctl.load_on_startup()
    editor.window.load_scene.assert_not_called()
