"""S1 5.6 (E8 contract 6): a game's project files resolve to its project (``engine.paths.project_root()``), never to
the current folder.

The current folder here is another project, a decoy with files of the same names (its own saves, item list,
cutscenes and pictures), as after ``run_game(project_root=)`` from another folder, the main menu's project switch or a
pinned launch (#623, #641). Each resource is checked through a real hidden window:

- ``saves``, ``items``, ``cutscenes``: the game, started by ``run_game(project_root=)`` from the decoy
  (tests/_real_game.py); a save lands in the project and loads back, the item list and the cutscenes are the project's;
- ``legacy file ops``: the legacy editor, launched as a pinned ``mesh edit`` does it (``MESH_REPO_ROOT``, the editor
  launch mode, F4), renames a picture: in the project, through its confirm dialog, with the scene reference rewritten.

The decoy's files are byte-identical afterwards. (One rule at a time: tests/test_project_root_resolver.py,
tests/test_legacy_file_ops_real_window.py.)
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from tests._game_window_live import dispose_game_window
from tests._real_game import RealGame, new_project, real_game

pytestmark = [pytest.mark.integration,  # (two generated projects in a temporary folder; hidden game windows)
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

MARKER = "assets/sprites/marker.png"


def _tag_project(root: Path, tag: str) -> None:
    """Same-named files, each carrying ``tag``: a cutscene, an item, a save and a picture a scene uses."""
    (root / "cutscenes.json").write_text(json.dumps(
        {"cutscenes": [{"id": f"intro_{tag}", "steps": [{"type": "set_flag", "flag": f"seen_{tag}"}]}]}),
        encoding="utf-8")
    (root / "assets" / "data" / "items.json").write_text(json.dumps(
        {"items": [{"id": f"gem_{tag}", "name": f"Gem {tag}"}]}), encoding="utf-8")
    (root / "saves").mkdir(exist_ok=True)
    (root / "saves" / f"only_{tag}.json").write_text("{}", encoding="utf-8")
    (root / MARKER).write_bytes(f"{tag}-MARKER".encode())
    (root / "scenes").mkdir(exist_ok=True)
    (root / "scenes" / "level.json").write_text(json.dumps({"entities": [{"id": "m", "x": 40, "y": 40, "sprite": MARKER}]}),
                                                encoding="utf-8")


def _files(root: Path) -> dict[str, bytes]:
    """Every file under ``root`` but the editor's own state (``.mesh/``)."""
    out = {}
    for dirpath, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".mesh"]
        for name in names:
            path = Path(dirpath) / name
            out[path.relative_to(root).as_posix()] = path.read_bytes()
    return out


@pytest.fixture(scope="module")
def projects(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Any, Path]]:
    """The game's project and the decoy (the current folder); the decoy is checked unchanged at the end."""
    base = tmp_path_factory.mktemp("roots")
    game = new_project(base / "game")
    decoy = new_project(base / "decoy")
    _tag_project(Path(game.root), "game")
    _tag_project(Path(decoy.root), "decoy")
    before = _files(Path(decoy.root))
    yield game, Path(decoy.root)
    assert _files(Path(decoy.root)) == before, "something was written to, or moved in, the current folder's project"


@pytest.fixture(scope="module")
def running(projects: tuple[Any, Path]) -> Iterator[RealGame]:
    project, decoy = projects
    with real_game(project, decoy) as started:
        yield started


@pytest.fixture()
def game(running: RealGame) -> RealGame:
    return running.resume()


def _saves(g: RealGame, root: Path, decoy: Path) -> None:
    manager = g.window.save_manager
    assert Path(manager.save_dir).resolve() == root / "saves"
    g.gs.set_counter("coins", 3)
    assert manager.save_game("contract6")
    assert (root / "saves" / "contract6.json").is_file() and not (decoy / "saves" / "contract6.json").exists()
    g.gs.set_counter("coins", 0)
    assert manager.load_game("contract6") and g.counter("coins") == 3
    g.frames(3)  # (the load's queued room change, a frame later)
    assert not manager.load_game("only_decoy"), "the current folder's save is never offered"


def _items(g: RealGame, root: Path, decoy: Path) -> None:
    from engine.inventory import load_item_database

    assert set(load_item_database().items) >= {"gem_game"}
    assert "gem_decoy" not in load_item_database().items


def _cutscenes(g: RealGame, root: Path, decoy: Path) -> None:
    controller = g.window.cutscene_controller
    assert set(controller.cutscenes) == {"intro_game"}
    assert controller.play_cutscene("intro_game")
    g.frames(3)
    assert g.flag("seen_game") and not g.flag("seen_decoy")


def _legacy_file_ops(root: Path, decoy: Path) -> None:
    """The legacy editor, launched pinned to the project from the decoy, renames a picture through its dialog."""
    from engine.config import load_config
    from engine.editor.live_bridge_lifecycle import stop_live_bridge
    from engine.game import GameWindow
    from engine.paths import reset_path_caches
    from engine.repo_root import clear_launched_project_root

    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(decoy)
        mp.setenv("MESH_REPO_ROOT", str(root))  # (as a pinned launch or a main-menu project switch sets it)
        mp.delenv("MESH_LEGACY_EDITOR", raising=False)
        reset_path_caches()
        room = root / "scenes" / "level.json"
        cfg = load_config(str(root / "config.json"))  # (the project's own config, as engine.game_launch reads it)
        setattr(cfg, "_mesh_launch_mode", "editor")  # (as engine.game_launch does for ``mesh edit``)
        window = GameWindow(width=320, height=200, title=cfg.title, vsync=False, config=cfg)
        editor = None
        try:
            window._allow_dispatch_event = True
            window.load_scene(str(room))
            menu = getattr(window, "main_menu_overlay", None)
            if menu is not None and menu.visible:
                menu.close()
            f4 = optional_arcade.arcade.key.F4
            window.dispatch_event("on_key_press", f4, 0)
            window.dispatch_event("on_key_release", f4, 0)
            editor = window.editor_controller
            assert editor.active and Path(editor.project_explorer.repo_root) == root
            assert editor.project_explorer_actions.reveal_path(MARKER)
            assert editor.file_ops.request_safe_rename_refactor("marker2.png") is True
            editor.confirm_modal.execute_confirm()
            assert not (root / MARKER).exists()
            assert (root / "assets/sprites/marker2.png").read_bytes() == b"game-MARKER"
            assert json.loads(room.read_text(encoding="utf-8"))["entities"][0]["sprite"] == "assets/sprites/marker2.png"
        finally:
            if editor is not None:
                stop_live_bridge(editor)
            dispose_game_window(window)
            clear_launched_project_root()
            reset_path_caches()


GAME_CHECKS = {"saves": _saves, "items": _items, "cutscenes": _cutscenes}


# (legacy file ops first: its own window opens and closes before the module's game window does)
@pytest.mark.parametrize("resource", ["legacy file ops", *GAME_CHECKS])
def test_project_files_resolve_to_the_project_not_the_current_folder(
        projects: tuple[Any, Path], request: pytest.FixtureRequest, resource: str) -> None:
    project, decoy = projects
    root = Path(project.root).resolve()
    if resource == "legacy file ops":
        _legacy_file_ops(root, decoy)
        return
    g: RealGame = request.getfixturevalue("game")
    assert Path.cwd().resolve() == decoy.resolve()
    GAME_CHECKS[resource](g, root, decoy)
