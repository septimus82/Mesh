from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine.editor.editor_session_state import (
    EditorSessionState,
    get_camera_for_scene,
    load_editor_session_state,
    load_editor_session_state_payload,
    record_camera_for_scene,
    resolve_editor_session_state_path,
    save_editor_session_state,
)
from engine.editor.editor_workspace_controller import EditorWorkspaceController
from engine.game_runtime import scene_ops

pytestmark = pytest.mark.fast


def _make_editor(repo_root: Path, *, center: tuple[float, float], zoom: float) -> SimpleNamespace:
    camera = SimpleNamespace(position=center, move_to=MagicMock())
    window = SimpleNamespace(
        recent_scenes=[],
        load_scene=MagicMock(),
        scene_controller=SimpleNamespace(current_scene_path=None),
        camera=camera,
        camera_controller=SimpleNamespace(zoom_state=SimpleNamespace(current=float(zoom))),
        get_camera_center=lambda: center,
        set_camera_zoom_target=MagicMock(),
    )
    return SimpleNamespace(
        window=window,
        _repo_root_override=repo_root,
        _get_repo_root=lambda: repo_root,
    )


def test_camera_by_scene_roundtrip_and_lookup(tmp_path: Path) -> None:
    state_path = resolve_editor_session_state_path(repo_root=tmp_path)
    state = EditorSessionState(
        last_scene_path="scenes/cellar.json",
        camera_by_scene={"scenes/cellar.json": {"x": 10.0, "y": 20.0, "zoom": 1.5}},
        camera_scene_order=("scenes/cellar.json",),
    )
    save_editor_session_state(state, path=state_path)
    loaded = load_editor_session_state(path=state_path)
    assert get_camera_for_scene(loaded, "scenes/cellar.json") == {"x": 10.0, "y": 20.0, "zoom": 1.5}


def test_invalid_camera_entries_are_ignored() -> None:
    payload = {
        "schema_version": 1,
        "last_scene_path": "scenes/cellar.json",
        "camera_by_scene": {
            "scenes/good.json": {"x": 1, "y": "2", "zoom": 1.25},
            "scenes/bad1.json": {"x": "nope", "y": 2, "zoom": 1.0},
            "scenes/bad2.json": {"x": 1, "y": 2},
            123: {"x": 1, "y": 2, "zoom": 1.0},
        },
        "camera_scene_order": ["scenes/good.json", "scenes/bad1.json"],
    }
    loaded = load_editor_session_state_payload(payload)
    assert loaded.camera_by_scene == {"scenes/good.json": {"x": 1.0, "y": 2.0, "zoom": 1.25}}
    assert loaded.camera_scene_order == ("scenes/good.json",)


def test_camera_by_scene_cap_enforced() -> None:
    state = EditorSessionState(last_scene_path="scenes/s0.json")
    for index in range(30):
        state = record_camera_for_scene(
            state,
            f"scenes/s{index}.json",
            {"x": float(index), "y": float(index + 1), "zoom": 1.0},
        )
    assert len(state.camera_by_scene) == 25
    assert len(state.camera_scene_order) == 25
    assert state.camera_scene_order[0] == "scenes/s29.json"
    assert "scenes/s4.json" not in state.camera_by_scene


def test_startup_restore_applies_camera_for_last_scene(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene_path = tmp_path / "scenes" / "cellar.json"
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    scene_path.write_text("{}", encoding="utf-8")

    editor_save = _make_editor(tmp_path, center=(12.0, 34.0), zoom=2.5)
    _ = EditorWorkspaceController(editor_save)
    scene_ops.record_recent_scene(editor_save.window, "scenes/cellar.json")

    editor_load = _make_editor(tmp_path, center=(0.0, 0.0), zoom=1.0)
    ctl = EditorWorkspaceController(editor_load)
    monkeypatch.setattr(ctl, "load_workspace", lambda: None)
    ctl.load_on_startup()

    editor_load.window.load_scene.assert_called_once_with("scenes/cellar.json")
    editor_load.window.set_camera_zoom_target.assert_called_once_with(2.5, speed=999.0)
    editor_load.window.camera.move_to.assert_called_once_with((12.0, 34.0), 1.0)


def test_safe_mode_skips_scene_and_camera_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scene_path = tmp_path / "scenes" / "cellar.json"
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    scene_path.write_text("{}", encoding="utf-8")
    save_editor_session_state(
        EditorSessionState(
            last_scene_path="scenes/cellar.json",
            camera_by_scene={"scenes/cellar.json": {"x": 3.0, "y": 4.0, "zoom": 1.8}},
            camera_scene_order=("scenes/cellar.json",),
        ),
        repo_root=tmp_path,
    )

    monkeypatch.setenv("MESH_SAFE_MODE", "1")
    editor = _make_editor(tmp_path, center=(0.0, 0.0), zoom=1.0)
    ctl = EditorWorkspaceController(editor)
    monkeypatch.setattr(ctl, "load_workspace", lambda: None)
    ctl.load_on_startup()

    editor.window.load_scene.assert_not_called()
    editor.window.set_camera_zoom_target.assert_not_called()
    editor.window.camera.move_to.assert_not_called()
