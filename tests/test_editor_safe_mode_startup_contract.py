from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine.editor.editor_session_state import EditorSessionState, save_editor_session_state
from engine.editor.editor_workspace_controller import EditorWorkspaceController

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


def test_safe_mode_skips_session_last_scene_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene_path = tmp_path / "scenes" / "cellar.json"
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    scene_path.write_text("{}", encoding="utf-8")
    save_editor_session_state(
        EditorSessionState(last_scene_path="scenes/cellar.json"),
        repo_root=tmp_path,
    )

    monkeypatch.setenv("MESH_SAFE_MODE", "1")
    editor = _make_editor(tmp_path)
    ctl = EditorWorkspaceController(editor)
    monkeypatch.setattr(ctl, "load_workspace", lambda: None)
    ctl.load_on_startup()
    editor.window.load_scene.assert_not_called()


def test_normal_mode_restores_session_last_scene(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene_path = tmp_path / "scenes" / "cellar.json"
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    scene_path.write_text("{}", encoding="utf-8")
    save_editor_session_state(
        EditorSessionState(last_scene_path="scenes/cellar.json"),
        repo_root=tmp_path,
    )

    monkeypatch.delenv("MESH_SAFE_MODE", raising=False)
    editor = _make_editor(tmp_path)
    ctl = EditorWorkspaceController(editor)
    monkeypatch.setattr(ctl, "load_workspace", lambda: None)
    ctl.load_on_startup()
    editor.window.load_scene.assert_called_once_with("scenes/cellar.json")
