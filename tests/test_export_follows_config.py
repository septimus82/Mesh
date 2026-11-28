"""#760 (programme finding 2): an export bundles what the game's configuration references, wherever it is in the
project, and refuses before publishing anything when that content is missing, broken or outside the project.

The exporter collected rooms and worlds only from fixed folders (``scenes/``, ``worlds/``, ``packs/``), so a game
keeping them in ``chapters/`` exported "OK" without them and its exported game crashed at start; a deleted start room,
a broken ``config.json`` or a missing ``main.py`` exported OK too. Each game here is made the supported way
(``engine.project_scaffold``, as ``mesh new``) and exported through ``mesh export build``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from engine import optional_arcade

pytestmark = [pytest.mark.integration]  # (projects and exports in tmp_path; subprocesses)

REPO = Path(__file__).resolve().parents[1]
HIDDEN = REPO / "tooling" / "hidden_windows.py"


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _chapters_game(root: Path) -> Path:
    """A starter game whose world, rooms and map live in ``chapters/`` (``packs/`` left empty): the start room
    "Chapter One" has a door to the world's room ``cellar``, written as Studio writes doors (by the room's key)."""
    from engine.project_scaffold import create_project

    create_project(root, "Chapters", "starter")
    pack, chapters = root / "packs" / "core_regions", root / "chapters"
    for name in ("scenes", "worlds", "maps"):
        shutil.move(str(pack / name), str(chapters / name))
    pack.rmdir()
    game_map = _json(chapters / "maps" / "start.json")
    game_map["tilesets"] = [{"firstgid": 1, "source": "../../assets/tilesets/starter.json"}]
    _write(chapters / "maps" / "start.json", game_map)
    start = _json(chapters / "scenes" / "start.json")
    cellar = {**start, "name": "Cellar", "entities": [e for e in start["entities"] if e.get("prefab_id") == "player"]}
    start["name"] = "Chapter One"
    start["entities"].append({"id": "start_door_to_cellar_400_300_0_0", "name": "Door to Cellar", "x": 400.0, "y": 300.0,
                              "sprite": "assets/sprites/door.png", "behaviours": ["SceneTransition"],
                              "behaviour_config": {"SceneTransition": {"target_scene": "cellar", "trigger_on_touch": True}}})
    _write(chapters / "scenes" / "start.json", start)
    _write(chapters / "scenes" / "cellar.json", cellar)
    world = _json(chapters / "worlds" / "main.json")
    world["scenes"] = {"start": {"label": "Chapter One", "path": "chapters/scenes/start.json", "tags": ["start"]},
                       "cellar": {"label": "Cellar", "path": "chapters/scenes/cellar.json", "tags": []}}
    _write(chapters / "worlds" / "main.json", world)
    config = _json(root / "config.json")
    config.update(start_scene="chapters/scenes/start.json", world_file="chapters/worlds/main.json")
    _write(root / "config.json", config)
    return root


def _export(game: Path, out: Path, capsys: pytest.CaptureFixture[str], command: str = "build") -> tuple[int, str]:
    import mesh_cli

    capsys.readouterr()
    code = mesh_cli.main(["export", command, "--repo-root", str(game), *(["--out", str(out)] if command == "build" else [])])
    return code, capsys.readouterr().out


def _tree(folder: Path) -> dict[str, str]:
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


def _env() -> dict[str, str]:
    """A player's environment: no Mesh variables, no PYTHONPATH (the game finds only its own engine)."""
    return {k: v for k, v in os.environ.items() if not k.startswith("MESH_") and k != "PYTHONPATH"}


def _link(link: Path, target: Path) -> None:
    """A link to the folder ``target``: a junction on Windows (no privilege needed), a symlink elsewhere."""
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


# The exported game's own engine, run from its folder: the room it starts in (as main.py picks it) and what that room
# holds, read by the engine's scene loader. No window.
OPENING = r'''
import json, sys
sys.path.insert(0, ".")
from engine.config import load_config
from engine.game_runtime.scene_flow import resolve_game_start_scene
from engine.migrations import migrate_payload
from engine.paths import pin_config, resolve_path
from engine.scene_loader import SceneLoader
from engine.world_controller import WorldController
config = load_config("config.json")
pin_config(config)
world = WorldController(migrate_payload("world", json.loads(resolve_path(config.world_file).read_text(encoding="utf-8"))))
start = config.main_menu_scene or resolve_game_start_scene(engine_config=config, world_controller=world) or config.start_scene
rooms = {key: SceneLoader().load_scene(world.get_scene_path(key)).get("name") for key in ("start", "cellar")}
print("MESH-OPENING " + json.dumps({"start": start, "rooms": rooms, "engine": __import__("engine").__file__}))
'''


def test_a_game_kept_in_chapters_exports_whole(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    game = _chapters_game(tmp_path / "game")
    code, said = _export(game, tmp_path / "bundle", capsys)
    assert code == 0, said
    listed = {f["path"] for f in _json(tmp_path / "bundle" / "bundle_manifest.json")["files"]}
    assert {"chapters/worlds/main.json", "chapters/scenes/start.json", "chapters/scenes/cellar.json",
            "chapters/maps/start.json", "assets/tilesets/starter.json", "assets/tilesets/starter.png"} <= listed

    bundle = Path(shutil.copytree(tmp_path / "bundle", tmp_path / "shipped"))  # (stands alone: no project behind it)
    shutil.rmtree(game)
    out = subprocess.run([sys.executable, "-c", OPENING], cwd=bundle, env=_env(), capture_output=True, text=True,
                         timeout=180)
    line = next((x for x in out.stdout.splitlines() if x.startswith("MESH-OPENING ")), None)
    assert line is not None, out.stdout + out.stderr
    opened = json.loads(line[len("MESH-OPENING "):])
    assert Path(opened["engine"]).resolve().is_relative_to(bundle.resolve()), "the bundle's own engine"
    assert opened["start"] == "chapters/scenes/start.json"
    assert opened["rooms"] == {"start": "Chapter One", "cellar": "Cellar"}


# The game's own main.py in a hidden, never-activated, silent window: the room it opened, then closed.
BOOT = r'''
import importlib.util, json, runpy, sys
from pathlib import Path
game, hidden = Path(sys.argv[1]), sys.argv[2]
sys.path.insert(0, str(game))
import pyglet
pyglet.options["audio"] = ("silent",)
spec = importlib.util.spec_from_file_location("hidden_windows", hidden)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.no_activate()
import pyglet.window
shown = pyglet.window.Window.__init__
def never_shown(self, *args, **kwargs):
    kwargs["visible"] = False
    shown(self, *args, **kwargs)
pyglet.window.Window.__init__ = never_shown
import engine
from engine.game import GameWindow
facts = {"engine": engine.__file__}
def drive(window):
    try:
        for _ in range(5):
            window.dispatch_event("on_update", 1 / 60)
        facts["room"] = window.scene_controller.current_scene_path
        facts["objects"] = sorted(str(getattr(s, "mesh_name", "")) for s in window.scene_controller.all_sprites)
    finally:
        window.close()
GameWindow.run = drive
runpy.run_path(str(game / "main.py"), run_name="__main__")
print("MESH-BOOT " + json.dumps(facts))
'''


def _boot(game: Path, env: dict[str, str], cwd: Path) -> dict[str, Any]:
    out = subprocess.run([sys.executable, "-c", BOOT, str(game), str(HIDDEN)], cwd=cwd, env=env, capture_output=True,
                         text=True, encoding="utf-8", errors="replace", timeout=300)
    line = next((x for x in out.stdout.splitlines() if x.startswith("MESH-BOOT ")), None)
    assert line is not None, f"the game didn't start (exit {out.returncode}):\n{(out.stdout + out.stderr)[-3000:]}"
    return dict(json.loads(line[len("MESH-BOOT "):]))


@pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                    reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)")
def test_a_game_kept_in_chapters_starts_in_its_opening_room_from_source_and_from_its_export(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    game = _chapters_game(tmp_path / "game")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    dev = {**_env(), "PYTHONPATH": str(REPO)}
    source = _boot(game, dev, elsewhere)
    assert source["room"] == "chapters/scenes/start.json"
    assert source["objects"] == ["Door to Cellar", "Guide", "Player"]

    assert _export(game, tmp_path / "bundle", capsys)[0] == 0
    bundle = Path(shutil.copytree(tmp_path / "bundle", tmp_path / "shipped"))
    shutil.rmtree(game)
    exported = _boot(bundle, _env(), elsewhere)
    assert Path(exported["engine"]).resolve().is_relative_to(bundle.resolve()), "the bundle's own engine"
    assert (exported["room"], exported["objects"]) == (source["room"], source["objects"])


# --------------------------------------------------------------------------------------------- refused exports

def _missing_room(game: Path, outside: Path) -> None:
    (game / "chapters" / "scenes" / "cellar.json").unlink()


def _broken_room(game: Path, outside: Path) -> None:
    (game / "chapters" / "scenes" / "cellar.json").write_text("{not json", encoding="utf-8")


def _door_to(target: Callable[[Path, Path], str]) -> Callable[[Path, Path], None]:
    def edit(game: Path, outside: Path) -> None:
        _write(outside / "room.json", {"name": "Elsewhere", "entities": []})  # (there, so only where it is is wrong)
        start = game / "chapters" / "scenes" / "start.json"
        scene = _json(start)
        scene["entities"][-1]["behaviour_config"]["SceneTransition"]["target_scene"] = target(game, outside)
        _write(start, scene)
    return edit


def _linked_room(game: Path, outside: Path) -> None:
    _write(outside / "room.json", {"name": "Elsewhere", "entities": []})
    _link(game / "chapters" / "linked", outside)
    world = _json(game / "chapters" / "worlds" / "main.json")
    world["scenes"]["cellar"]["path"] = "chapters/linked/room.json"
    _write(game / "chapters" / "worlds" / "main.json", world)


def _deleted_start(game: Path, outside: Path) -> None:
    (game / "chapters" / "scenes" / "start.json").unlink()


def _broken_config(game: Path, outside: Path) -> None:
    (game / "config.json").write_text('{"start_scene": "chapters/scenes/start.json",', encoding="utf-8")


def _no_main(game: Path, outside: Path) -> None:
    (game / "main.py").unlink()


REFUSED: dict[str, tuple[Callable[[Path, Path], None], str]] = {
    "missing room": (_missing_room, "room 'cellar' of the world ('chapters/scenes/cellar.json') is missing"),
    "invalid room": (_broken_room, "chapters/scenes/cellar.json) can't be read"),
    "door up out": (_door_to(lambda g, o: "../outside/room.json"), "is outside the project folder"),
    "door absolute": (_door_to(lambda g, o: str(o / "room.json")), "is an absolute path"),
    "linked out": (_linked_room, "is reached through a link pointing outside the project"),
    "deleted start": (_deleted_start, "the start room (config.json 'start_scene') ('chapters/scenes/start.json') is missing"),
    "invalid config": (_broken_config, "config.json can't be read by the game"),
    "no main.py": (_no_main, "main.py is missing"),
}


@pytest.fixture(scope="module")
def earlier(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path, dict[str, str]]:
    """The chapters game, and a good export of it with its exact contents (each test replaces a copy of it)."""
    from engine.tooling.export_bundle import build_bundle

    base = tmp_path_factory.mktemp("refused")
    game = _chapters_game(base / "game")
    out = base / "out" / "bundle"
    assert build_bundle(game, out)[0] == 0
    return game, out, _tree(out)


@pytest.mark.parametrize("case", list(REFUSED))
def test_an_export_with_content_missing_broken_or_outside_the_project_is_refused_before_publishing(
        case: str, earlier: tuple[Path, Path, dict[str, str]], tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source, good, before = earlier
    game = Path(shutil.copytree(source, tmp_path / "game"))
    out = Path(shutil.copytree(good, tmp_path / "out" / "bundle"))  # (this test's own earlier export)
    edit, message = REFUSED[case]
    edit(game, tmp_path / "outside")

    code, said = _export(game, out, capsys)
    assert code == 1 and message in said, said
    assert "OK" not in said
    assert _tree(out) == before, "the earlier export is exactly as it was"
    assert sorted(p.name for p in out.parent.iterdir()) == ["bundle"], "no working folder or journal left beside it"
    assert _export(game, out, capsys, "plan")[0] == 1


@pytest.mark.parametrize("template", ["blank", "adventure", "starter", "hd2d_rpg", "monster", "lighting_playground"])
def test_every_template_still_exports_from_its_own_folders(tmp_path: Path, template: str) -> None:
    """Nothing changes for the supported layouts: every file a template's game reaches is already in its ``packs/``
    or ``assets/``, so the plan is the one it was."""
    from engine.project_scaffold import create_project
    from engine.tooling.export_bundle import compute_export_plan

    create_project(tmp_path / "game", "Game", template)
    plan = compute_export_plan(tmp_path / "game")
    assert plan.ok, plan.summary()
    paths = [f.rel_path for f in plan.files]
    assert len(paths) == len(set(paths))
    assert not [p for p in paths if p.split("/")[0] not in ("engine", "share", "assets", "packs", "locales")
                and "/" in p], "nothing outside the folders a template's game keeps its files in"
