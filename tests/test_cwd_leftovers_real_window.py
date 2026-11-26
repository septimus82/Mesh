"""#675 items 1, 2 and 4: current-folder (CWD) sites left after the one project-root resolver (#623, #673), each in a
real (hidden) GameWindow whose current folder is not its project.

1. The console's ``ai_job`` took its project lock on, and wrote into, the current folder's project, not the window's.
2. The legacy main menu's Create New Project offered ``<current folder>/<name>``, which nests the new game inside
   whatever project the current folder is; it now offers Documents/Mesh Projects (as the launcher does) and refuses a
   folder inside another project.
4. The older ``saves`` in the current folder were offered (read-only) to the game also when the current folder is a
   folder inside another project, or the parent of other projects: another game's slot could be loaded into this one.
   Such ambiguous folders are not offered (owner decision D5: never guess, never write there).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from tests._game_window_live import dispose_game_window
from tests.test_dev_tools_gate_real_window import _console, _press, _type

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]


def _project(root: Path, tag: str) -> Path:
    (root / "scenes").mkdir(parents=True)
    config = {"title": f"Game {tag}", "game_id": f"game-{tag}-0000", "start_scene": "scenes/start.json",
              "width": 320, "height": 200, "vsync": False, "fullscreen": False, "main_menu_scene": None}
    (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (root / "scenes" / "start.json").write_text(json.dumps(
        {"name": "Start", "schema_version": 1, "version": 1, "layers": [],
         "entities": [{"id": "crate", "x": 32.0, "y": 32.0}]}), encoding="utf-8")
    return root.resolve()


def _window(project: Path, cwd: Path, monkeypatch: pytest.MonkeyPatch, *, mode: str | None = None) -> Any:
    """A game window on ``project`` (it pins its own config, as ``main.py`` and a main-menu switch do), started from
    ``cwd``."""
    from engine.config import load_config
    from engine.game import GameWindow

    monkeypatch.chdir(cwd)
    monkeypatch.delenv("MESH_SAVE_DIR", raising=False)
    monkeypatch.delenv("MESH_LEGACY_EDITOR", raising=False)
    config = load_config(str(project / "config.json"))
    if mode is not None:
        setattr(config, "_mesh_launch_mode", mode)
    window = GameWindow(width=320, height=200, title=config.title, vsync=False, config=config)
    window._allow_dispatch_event = True  # (pyglet queues a hidden window's events outside its own loop otherwise)
    window.load_scene(str(project / "scenes" / "start.json"))
    menu = getattr(window, "main_menu_overlay", None)
    if menu is not None and menu.visible:
        menu.close()
    return window


def _close(window: Any) -> None:
    from engine.editor.live_bridge_lifecycle import stop_live_bridge

    stop_live_bridge(window.editor_controller)
    dispose_game_window(window)


def _entities(project: Path) -> list[str]:
    scene = json.loads((project / "scenes" / "start.json").read_text(encoding="utf-8"))
    return [e["id"] for e in scene.get("entities", [])]


# --------------------------------------------------------------------- 1. console ai_job

def test_console_ai_job_writes_the_windows_project_not_the_current_folders(tmp_path: Path,
                                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    here, game = _project(tmp_path / "here", "here"), _project(tmp_path / "game", "game")
    job = tmp_path / "job.json"
    job.write_text(json.dumps({"operations": [
        {"type": "delete_entity", "scene_path": "scenes/start.json", "entity_id": "crate"}]}), encoding="utf-8")
    window = _window(game, here, monkeypatch, mode="play")  # (``mesh play``: the console is a developer's)
    try:
        _console(window, f"ai_job {job.as_posix()}")
        log = "\n".join(window.console_controller.lines)
        assert "[AI] Applied 1 operation(s)" in log, log
        assert _entities(game) == [], "the window's project was not changed"
        assert _entities(here) == ["crate"], "the current folder's project was changed"
        assert not (here / ".mesh").exists(), "the current folder's project was locked"
    finally:
        _close(window)


def test_console_ai_job_from_a_project_nested_in_the_windows_writes_the_windows(tmp_path: Path,
                                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    """#717 review: the current folder is inside the window's project A by path, but it is a nested project B (its
    own config.json), another project by Mesh's rule (project_ownership.project_root). A gets the change, B none."""
    game = _project(tmp_path / "game", "game")
    inner = _project(game / "inner", "inner")
    job = tmp_path / "job.json"
    job.write_text(json.dumps({"operations": [
        {"type": "delete_entity", "scene_path": "scenes/start.json", "entity_id": "crate"}]}), encoding="utf-8")
    window = _window(game, inner, monkeypatch, mode="play")
    try:
        _console(window, f"ai_job {job.as_posix()}")
        log = "\n".join(window.console_controller.lines)
        assert "[AI] Applied 1 operation(s)" in log, log
        assert _entities(game) == [], "the window's project was not changed"
        assert _entities(inner) == ["crate"], "the nested project was changed"
        assert not (inner / ".mesh").exists(), "the nested project was locked"
    finally:
        _close(window)


# --------------------------------------------------------------------- 2. Create New Project

def _create(window: Any, name: str, path: str | None = None) -> Any:
    key = optional_arcade.arcade.key
    menu = window.main_menu_overlay
    menu.open()
    menu.state = "create_project_name"  # (Create New Project..., then a template)
    _type(window, name)
    _press(window, key.ENTER)
    assert menu.state == "create_project_path"
    if path is not None:
        menu._create_path = ""
        _type(window, path)
    return menu


def test_create_new_project_offers_the_projects_folder_not_the_current_one(tmp_path: Path,
                                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.projects import default_projects_dir

    here, game = _project(tmp_path / "here", "here"), _project(tmp_path / "game", "game")
    monkeypatch.setenv("MESH_PROJECTS_DIR", str(tmp_path / "projects"))  # (never the real Documents folder)
    window = _window(game, here, monkeypatch)
    try:
        menu = _create(window, "New Game")
        assert Path(menu._create_path) == (default_projects_dir() / "new_game").resolve()
        assert not (here / "new_game").exists()
    finally:
        _close(window)


def test_create_new_project_refuses_a_folder_inside_another_project(tmp_path: Path,
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    here, game = _project(tmp_path / "here", "here"), _project(tmp_path / "game", "game")
    window = _window(game, here, monkeypatch)
    target = here / "levels" / "new_game"
    before = sorted(p.relative_to(here).as_posix() for p in here.rglob("*"))
    try:
        menu = _create(window, "New Game", str(target))
        _press(window, optional_arcade.arcade.key.ENTER)
        assert "inside the Mesh project" in menu._create_error and str(here) in menu._create_error
        assert menu.state == "create_project_path"
        assert sorted(p.relative_to(here).as_posix() for p in here.rglob("*")) == before, "files were written"
        assert Path(window.engine_config._config_base_dir).resolve() == game, "the project was switched"
    finally:
        _close(window)


# --------------------------------------------------------------------- 4. older saves in the current folder

@pytest.mark.parametrize("where,offered", [
    ("plain", True),  # (control: a plain folder's older saves are offered, read-only)
    ("subfolder of the game", True),
    ("parent of the game alone", True),
    ("parent of projects", False),
    ("subfolder of another project", False),
    ("another project", False),
])
def test_older_saves_in_an_ambiguous_current_folder_are_not_offered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                     where: str, offered: bool) -> None:
    parent = tmp_path / "parent"
    game = _project(parent / "game", "game")
    other = tmp_path / "other"
    cwd = {"plain": tmp_path / "plain",
           "subfolder of the game": game / "tools",
           "parent of the game alone": parent,
           "parent of projects": parent,
           "subfolder of another project": other / "tools",
           "another project": other}[where]
    if where in ("subfolder of another project", "another project"):
        _project(other, "other")
    if where == "parent of projects":
        _project(parent / "second", "second")
    (cwd / "saves").mkdir(parents=True)
    (cwd / "saves" / "quicksave.json").write_text("{}", encoding="utf-8")
    window = _window(game, cwd, monkeypatch)
    try:
        manager = window.save_manager
        assert manager.save_dir == game / "saves"
        assert manager.legacy_dir == ((cwd / "saves").resolve() if offered else None)
    finally:
        _close(window)


def test_older_saves_beside_an_unreadable_child_are_not_offered(tmp_path: Path,
                                                                monkeypatch: pytest.MonkeyPatch) -> None:
    """A child the scan can't read (PermissionError) might be another project: can't tell, so not offered."""
    from engine.save_runtime.storage import cwd_legacy_saves

    game = _project(tmp_path / "game", "game")
    cwd = tmp_path / "plain"
    (cwd / "saves").mkdir(parents=True)
    (cwd / "locked").mkdir()
    real_is_file = Path.is_file

    def is_file(self: Path, *args: Any, **kwargs: Any) -> bool:
        if self.parent.name == "locked":
            raise PermissionError(13, "Access is denied", str(self))
        return real_is_file(self, *args, **kwargs)

    monkeypatch.chdir(cwd)
    assert cwd_legacy_saves(game) == (cwd / "saves").resolve()  # (control: readable, offered)
    monkeypatch.setattr(Path, "is_file", is_file)
    assert cwd_legacy_saves(game) is None
