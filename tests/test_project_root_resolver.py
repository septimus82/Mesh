"""#623 (owner decision D5): a game's project files resolve against its project root (engine.paths.project_root),
never against the current folder.

``main.py`` and ``mesh edit`` change into the project folder, which hid it; ``run_game(project_root=)``, the main
menu's project switch, the checkout's project browser and the legacy editor don't. So a game started from another
folder saved into that folder's ``saves`` (another project's quicksave overwritten), and read that folder's
``cutscenes.json`` and item database. Here, every case runs in one process with the current folder left at another
project (a decoy holding its own cutscenes, items and saves). The save-folder rules one at a time, the older-save
fallback and its ambiguity rule: tests/test_save_storage.py.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.repo_root import engine_source_root
from tests._game_window_live import dispose_game_window
from tests._typing import as_any

pytestmark = pytest.mark.integration  # (files in temporary folders; one test opens hidden game windows)


def _project(root: Path, tag: str) -> Path:
    """A project whose cutscene, item and quicksave all carry ``tag``."""
    (root / "scenes").mkdir(parents=True)
    (root / "assets" / "data").mkdir(parents=True)
    config = {"title": f"Game {tag}", "game_id": f"game-{tag}-0000", "start_scene": "scenes/start.json",
              "width": 320, "height": 200, "vsync": False, "fullscreen": False, "main_menu_scene": None}
    (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (root / "scenes" / "start.json").write_text(json.dumps(
        {"name": "Start", "schema_version": 1, "version": 1, "layers": [], "entities": []}), encoding="utf-8")
    (root / "cutscenes.json").write_text(json.dumps(
        {"cutscenes": [{"id": f"intro_{tag}", "steps": [{"type": "wait", "duration": 0.1}]}]}), encoding="utf-8")
    (root / "assets" / "data" / "items.json").write_text(json.dumps(
        {"items": [{"id": f"gem_{tag}", "name": f"Gem {tag}"}]}), encoding="utf-8")
    return root


def _items() -> set[str]:
    from engine.inventory import load_item_database

    return set(load_item_database().items)


@pytest.fixture()
def projects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """Projects A and B; the current folder is A's (as after ``mesh edit A``), and stays there."""
    a, b = _project(tmp_path / "project_a", "a"), _project(tmp_path / "project_b", "b")
    monkeypatch.chdir(a)
    monkeypatch.delenv("MESH_SAVE_DIR", raising=False)
    return a.resolve(), b.resolve()


@pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")
def test_run_game_from_another_folder_uses_its_own_project(projects: tuple[Path, Path],
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    """The real entry point, ``run_game(project_root=)``, with a real (hidden) GameWindow: each project's quicksave
    stays its own and reloads its own; the game reads its own cutscenes.json and item database."""
    from engine.game import GameWindow
    from engine.public_api import run_game

    a, b = projects
    seen: dict[str, Any] = {}

    def play(window: Any, gold: int | None) -> None:  # (in place of window.run(): one "session" in the game)
        try:
            manager = window.save_manager
            tag = Path(window.engine_config._config_base_dir).name
            seen[tag] = {"save_dir": manager.save_dir, "legacy": manager.legacy_dir, "items": _items(),
                         "cutscenes": set(window.cutscene_controller.cutscenes)}
            if gold is None:
                assert manager.load_game("quicksave")
                seen[tag]["loaded_gold"] = window.game_state_controller.state.counters.get("gold")
            else:
                window.game_state_controller.set_counter("gold", gold)
                assert manager.save_game("quicksave")
        finally:
            dispose_game_window(window)

    for root, gold in ((a, 1), (b, 2)):  # (A first: B starts with A's saves in the current folder)
        monkeypatch.setattr(GameWindow, "run", lambda self, gold=gold: play(self, gold))
        run_game("scenes/start.json", project_root=root)
    assert seen["project_b"]["save_dir"] == b / "saves" and seen["project_b"]["legacy"] is None, \
        "the current folder is another project: its saves are never offered"
    assert seen["project_b"]["cutscenes"] == {"intro_b"} and seen["project_b"]["items"] == {"gem_b"}
    assert seen["project_a"]["cutscenes"] == {"intro_a"} and seen["project_a"]["items"] == {"gem_a"}
    for root, gold in ((b, 2), (a, 1)):
        assert (root / "saves" / "quicksave.json").is_file()
        monkeypatch.setattr(GameWindow, "run", lambda self: play(self, None))
        run_game("scenes/start.json", project_root=root)
        assert seen[root.name]["loaded_gold"] == gold, root.name


def test_the_main_menu_project_switch_moves_saves_cutscenes_and_items(projects: tuple[Path, Path]) -> None:
    """The legacy main menu's project switch changes the project but not the current folder."""
    from engine.config import load_config
    from engine.cutscene_controller import CutsceneController
    from engine.paths import pin_config
    from engine.save_manager import SaveManager
    from engine.ui_overlays.main_menu_overlay import MainMenuOverlay

    a, b = projects
    config = load_config(str(a / "config.json"))
    pin_config(config)
    window = SimpleNamespace(engine_config=config, editor_controller=SimpleNamespace(active=False),
                             world_controller=None, paused=False)
    window.save_manager = SaveManager(as_any(window))
    window.cutscene_controller = CutsceneController(window)
    window.cutscene_controller.load_project_cutscenes()
    assert (window.save_manager.save_dir, set(window.cutscene_controller.cutscenes), _items()) == \
        (a / "saves", {"intro_a"}, {"gem_a"})
    MainMenuOverlay(as_any(window))._apply_project_root(str(b))
    assert Path(window.engine_config._config_base_dir).resolve() == b
    assert window.save_manager.save_dir == b / "saves" and window.save_manager.legacy_dir is None
    assert set(window.cutscene_controller.cutscenes) == {"intro_b"} and _items() == {"gem_b"}


def test_the_older_save_format_s_file_is_the_project_s(projects: tuple[Path, Path], tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    """engine/savegame.py's ``saves/save_1.json`` (the legacy main menu's Continue): written in the project, read
    from the current folder only when the project has none and the current folder is no project."""
    from engine.config import load_config
    from engine.paths import pin_config
    from engine.savegame import resolve_savegame_path

    a, b = projects
    monkeypatch.delenv("MESH_SAVEGAME_PATH", raising=False)
    monkeypatch.delenv("MESH_SAVE_PATH", raising=False)
    (a / "saves").mkdir()
    (a / "saves" / "save_1.json").write_text("{}", encoding="utf-8")
    pin_config(load_config(str(b / "config.json")))
    assert resolve_savegame_path() == b / "saves" / "save_1.json"
    assert resolve_savegame_path(reading=True) == b / "saves" / "save_1.json", "A is another project: never offered"
    launch = tmp_path / "launch"
    (launch / "saves").mkdir(parents=True)
    (launch / "saves" / "save_1.json").write_text("{}", encoding="utf-8")
    monkeypatch.chdir(launch)  # (a plain folder: no config.json)
    assert resolve_savegame_path() == b / "saves" / "save_1.json", "written: always the project's"
    assert resolve_savegame_path(reading=True) == launch.resolve() / "saves" / "save_1.json", "read: the older one"


def test_an_exported_game_still_saves_per_player(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """H9 is unchanged: a real export saves in its player's folder, its older in-installation saves stay read-only,
    and a ``saves`` folder where it was started from is not offered."""
    from engine.save_manager import SaveManager
    from engine.save_runtime import storage
    from engine.tooling.export_bundle import build_bundle

    bundle = tmp_path / "bundle"
    exit_code, _manifest = build_bundle(Path(__file__).parent / "fixtures" / "export_bundle", bundle)
    assert exit_code == 0 and storage.is_exported_game(bundle)
    data = tmp_path / "player data"
    monkeypatch.setenv("APPDATA", str(data))
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    monkeypatch.delenv(storage.SAVE_DIR_ENV, raising=False)
    launch = tmp_path / "launch"
    (launch / "saves").mkdir(parents=True)
    monkeypatch.chdir(launch)
    config = SimpleNamespace(_config_base_dir=str(bundle), game_id="exported-0000", title="Exported",
                             start_scene="scenes/start.json", world_file=None)
    manager = SaveManager(as_any(SimpleNamespace(engine_config=config)))
    assert manager.save_dir == storage.user_data_home() / storage.PUBLISHER_DIR / "exported-0000" / "saves"
    assert manager.legacy_dir == bundle.resolve() / "saves"


def test_ai_history_is_kept_in_the_project(projects: tuple[Path, Path]) -> None:
    from engine import ai_history
    from engine.config import load_config
    from engine.paths import pin_config

    a, b = projects
    pin_config(load_config(str(b / "config.json")))
    ai_history.append_history_entry("plan.json", ["start"], goal="test")
    assert (b / ".mesh" / "ai_history.jsonl").is_file() and not (a / ".mesh").exists()
    assert [e["plan_path"] for e in ai_history.load_history()] == ["plan.json"]


def test_ai_scatter_reads_structure_models_from_the_room_s_project(tmp_path: Path,
                                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    """#391 (its wrong-root part): an authoring session started from another folder (``mesh author --project``,
    MCP) read a structure's model against that folder's project, missed a model only the room's project has, and
    scattered over the structure as if it were the 2 x 2 m fallback."""
    from engine import authoring
    from engine import project_ops as ops
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path / "game"
    create_project(root, "Game", template_id="hd2d_rpg")
    model = "assets/models/only_here.glb"
    (root / "assets" / "models").mkdir(parents=True, exist_ok=True)
    shutil.copy(engine_source_root() / "assets" / "hd2d_starter" / "models" / "cottage.glb", root / model)
    launch = tmp_path / "launch"
    launch.mkdir()
    monkeypatch.chdir(launch)
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    room = project.current
    hd2d = project.scene(room)["settings"]["hd2d"]
    lo, hi = hd2d["ground"]["from"], hd2d["ground"]["to"]
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    project.edit_scene(lambda s: {**s, "settings": {**s["settings"], "hd2d": {
        **s["settings"]["hd2d"], "structures": [{"id": "hut", "model": model, "x": cx, "y": cy}]}}}, room)
    with ops.in_project(root):
        ground, _spots, _routes = ops.scatter_context(project.scene(room))
    assert ground.structure(cx + 48, cy) and not ground.structure(cx + 400, cy), "the cottage is wider than 2 x 2 m"
    dabs = [[cx + dx, cy + dy] for dx in range(-160, 161, 32) for dy in range(-160, 161, 32)]
    authoring.apply(project, [{"op": "scatter_stroke", "room": room, "collection": {"grass_tuft": 1}, "dabs": dabs,
                               "radius": 48, "density": 4.0, "seed": 1}])
    rows = project.scene(room)["settings"]["hd2d"].get("scatter", {})
    assert rows, "the stroke scattered around the cottage"
    on_it = [r for items in rows.values() for r in items if ground.structure(r[0], r[1])]
    assert on_it == [], f"{len(on_it)} scattered onto the cottage's real footprint"
