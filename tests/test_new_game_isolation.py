"""Watchfire R1: a new game never takes progress from the editor's remembered scene.

Every game window builds the editor's workspace controller, and its start-up reopened the editor's remembered scene
(``.mesh/editor_session_state.json`` ``last_scene_path``, ``workspace.json`` ``last_scene_id``). The runtime records
the save slot it loads there, so the next game start loaded that save and a new game began with its flags. The
remembered scene now reopens in an editor launch only, and never a save slot; a main-menu New Game clears all of
the game state. (The real two-process check: ``tests/test_new_game_isolation_gpu.py``.)
"""

from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from engine.editor.editor_session_state import EditorSessionState, save_editor_session_state
from engine.editor.editor_workspace_controller import EditorWorkspaceController
from engine.editor_controller import EditorModeController
from engine.game_state_controller import GameStateController
from engine.ui_overlays.main_menu_overlay import MainMenuOverlay
from engine.workspace_settings import WorkspaceSettings, save_workspace

pytestmark = pytest.mark.fast

ROOM = "scenes/cellar.json"
SLOT = "saves/slot_a.json"


def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for rel in (ROOM, SLOT):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("{}", encoding="utf-8")
    monkeypatch.chdir(tmp_path)  # (a game and the editor both run in the project folder)
    monkeypatch.delenv("MESH_SAFE_MODE", raising=False)
    return tmp_path


def _editor(root: Path, launch_mode: str | None) -> SimpleNamespace:
    window = SimpleNamespace(
        load_scene=MagicMock(),
        scene_controller=SimpleNamespace(current_scene_path=None),
        engine_config=SimpleNamespace(_mesh_launch_mode=launch_mode),
        save_manager=SimpleNamespace(save_dir=root / "saves"),
    )
    return SimpleNamespace(window=window, _repo_root_override=root, _get_repo_root=lambda: root)


@pytest.mark.parametrize("remembered", [ROOM, SLOT])
def test_a_game_start_never_reopens_the_session_scene(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                      remembered: str) -> None:
    root = _project(tmp_path, monkeypatch)
    save_editor_session_state(EditorSessionState(last_scene_path=remembered), repo_root=root)
    editor = _editor(root, launch_mode=None)  # main.py and exported games: no launch mode
    ctl = EditorWorkspaceController(editor)
    monkeypatch.setattr(ctl, "load_workspace", lambda: None)
    ctl.load_on_startup()
    editor.window.load_scene.assert_not_called()


@pytest.mark.parametrize(("remembered", "reopened"), [(ROOM, True), (SLOT, False)])
def test_the_editor_reopens_its_room_but_never_a_save(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                      remembered: str, reopened: bool) -> None:
    root = _project(tmp_path, monkeypatch)
    save_editor_session_state(EditorSessionState(last_scene_path=remembered), repo_root=root)
    editor = _editor(root, launch_mode="editor")
    ctl = EditorWorkspaceController(editor)
    monkeypatch.setattr(ctl, "load_workspace", lambda: None)
    ctl.load_on_startup()
    assert editor.window.load_scene.call_count == (1 if reopened else 0)


@pytest.mark.parametrize(("launch_mode", "remembered", "reopened"),
                         [(None, ROOM, False), (None, SLOT, False), ("editor", ROOM, True), ("editor", SLOT, False)])
def test_workspace_scene_and_camera_reopen_only_in_the_editor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                              launch_mode: str | None, remembered: str,
                                                              reopened: bool) -> None:
    save_workspace(tmp_path, WorkspaceSettings(last_scene_id=remembered, last_camera_center=[50.0, 50.0]))
    monkeypatch.setenv("PYGBAG", "0")
    window = MagicMock()
    window.current_scene_key = "default"
    window.camera.position = (0.0, 0.0)
    window.engine_config._mesh_launch_mode = launch_mode
    window.save_manager.save_dir = Path("saves")  # (as the game's: relative to the folder it runs in)
    editor = EditorModeController(window)
    editor._repo_root_override = tmp_path
    editor.load_workspace()
    assert window.load_scene.call_count == (1 if reopened else 0)
    assert window.camera.position == ((50.0, 50.0) if reopened else (0.0, 0.0))


@pytest.mark.parametrize(("launch_mode", "remembered"), [(None, False), ("editor", True)])
def test_only_the_editor_remembers_the_room_it_loads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                     launch_mode: str | None, remembered: bool) -> None:
    """#422 H7: a game (main.py, an exported game) wrote .mesh/editor_session_state.json into its own folder on every
    room it loaded, though only the editor reads it; the exported game then no longer matched its manifest."""
    root = _project(tmp_path, monkeypatch)
    editor = _editor(root, launch_mode=launch_mode)
    EditorWorkspaceController(editor)
    editor.window._on_recent_scene_recorded(ROOM)
    assert (root / ".mesh" / "editor_session_state.json").is_file() == remembered


def test_main_menu_new_game_clears_all_game_state() -> None:
    window = SimpleNamespace(
        engine_config=SimpleNamespace(start_scene="scenes/start.json"),
        world_controller=None,
        editor_controller=SimpleNamespace(active=False),
    )
    controller = GameStateController(window)
    window.game_state_controller = controller
    state = controller.state
    state.flags["task_accepted"] = True
    state.counters["embers"] = 3.0
    state.values["coins"] = 12
    state.values["quests"] = {"watchfire": {"status": "completed", "completed_stages": ["light"]}}
    requested: list[str] = []
    window.request_scene_change = requested.append

    overlay = MainMenuOverlay.__new__(MainMenuOverlay)
    overlay.window = window
    MainMenuOverlay._handle_start_game_impl(overlay)

    fresh = controller.state
    assert fresh.flags == {} and fresh.counters == {}
    assert "coins" not in fresh.values and not fresh.values.get("quests")
    assert requested == ["scenes/start.json"]


class _GameWindow(SimpleNamespace):
    """What the quest manager needs of a game window: its game state, as GameWindow gives it."""

    @property
    def game_state(self) -> object:
        return self.game_state_controller.state


def test_main_menu_new_game_starts_quests_as_a_fresh_game_does() -> None:
    from engine.quests import QuestManager

    window = _GameWindow(engine_config=SimpleNamespace(start_scene="scenes/start.json"), world_controller=None,
                         editor_controller=SimpleNamespace(active=False), request_scene_change=lambda _path: None,
                         emit_signal=lambda *_args, **_kwargs: None)
    window.game_state_controller = GameStateController(window)
    window.game_state_controller.quests = QuestManager(window)  # one shared manager, as GameWindow sets it up
    fresh = copy.deepcopy(window.game_state_controller.state.values["quests"])
    started = next(qid for qid, q in fresh.items() if q["status"] == "active")  # (a quest that starts by itself)
    window.game_state_controller.state.values["quests"][started] = {  # (the last game finished it)
        "status": "completed", "current_stage": None, "awaiting_stage": None, "completed_stages": []}

    overlay = MainMenuOverlay.__new__(MainMenuOverlay)
    overlay.window = window
    MainMenuOverlay._handle_start_game_impl(overlay)

    assert window.game_state_controller.state.values["quests"] == fresh
