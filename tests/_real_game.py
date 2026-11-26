"""The shared real-window contract fixture (S1 3.0 / 5.6): a game authored the way Mesh Studio authors it, played in
a real GameWindow.

``real_game(root)`` opens the project at ``root`` through the supported entry point ``run_game(project_root=)``, from
another folder (the current folder is never the project, so every project file has to resolve through
``engine.paths.project_root()``). The window is hidden, never activated and muted (``master_volume`` 0 in the project's
config, and the mixer set to 0). Keys and frames go through ``dispatch_event`` (``_allow_dispatch_event``: a hidden
window would queue them otherwise). One window serves a whole test module: open it in a module-scoped fixture.

``author(project, room, changes)`` writes through ``engine.authoring.apply``: the same ``project_ops`` operations
Studio's inspector, ``mesh author`` and the AI use.
"""
from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests._game_window_live import dispose_game_window

PIC = "assets/sprites/starter_sign.png"
HALL = "Hall"


def new_project(root: Path) -> Any:
    """A new project (``create_project``, blank template: a Start room with the shared player) with a small window and
    no sound, and its Studio model (``engine.studio_project.Project``)."""
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    create_project(root, "Contract", template_id="blank")
    config_path = root / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config.update(width=320, height=200, vsync=False, master_volume=0.0, tour_completed=True)
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    project = Project(root, config["world_file"])
    project.add_room(HALL)
    project.save()
    return project


def author(project: Any, room: str, changes: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply Studio authoring ``changes`` to ``room`` (each change gets ``room`` unless it names one) and save."""
    from engine import authoring

    result = authoring.apply(project, [{"room": room, **change} for change in changes])
    project.save()
    return result


def place(name: str, x: float, y: float, *behaviours: tuple[str, dict[str, Any]], picture: str = PIC,
          solid: bool = False, **fields: Any) -> list[dict[str, Any]]:
    """The changes that place one object with its picture and picker behaviours (``@0`` is the object made first in
    this list; ``place`` lists are concatenated with ``ref`` fixed up by ``batch``)."""
    changes: list[dict[str, Any]] = [{"op": "place_blank", "name": name, "x": x, "y": y},
                                     {"op": "set_picture", "entity_id": "@0", "sprite": picture}]
    for behaviour, params in behaviours:
        changes.append({"op": "add_behaviour", "entity_id": "@0", "behaviour": behaviour})
        changes += [{"op": "set_behaviour_param", "entity_id": "@0", "behaviour": behaviour, "param": key,
                     "value": value} for key, value in params.items()]
    if solid:
        changes.append({"op": "set_solid", "entity_id": "@0", "solid": True})
    if fields:
        changes.append({"op": "set_entity_fields", "entity_id": "@0", "fields": fields})
    return changes


def batch(*objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Concatenate ``place`` lists, pointing each one's ``@0`` at its own object."""
    out: list[dict[str, Any]] = []
    for changes in objects:
        ref = f"@{len(out)}"
        out += [{k: (ref if v == "@0" else v) for k, v in change.items()} for change in changes]
    return out


class RealGame:
    """The running game, driven as a player would: keys and frames through the window's own event dispatch."""

    def __init__(self, window: Any, project: Any) -> None:
        self.window = window
        self.project = project
        self.sc = window.scene_controller
        self.gs = window.game_state_controller
        self.heard: list[tuple[str, dict[str, Any]]] = []
        window.event_bus.subscribe_all(lambda event: self.heard.append((event.type, dict(event.payload or {}))))

    def resume(self) -> "RealGame":
        """Put back what holds while the game's window loop runs: run_game's ``MESH_REPO_ROOT`` and the window's
        pinned config. run_game's exit takes them away, and so does tests/conftest.py after every test; a module's
        shared game calls this at the start of each test (see ``game`` in the contract modules)."""
        from engine.paths import pin_config

        os.environ["MESH_REPO_ROOT"] = str(Path(self.project.root).resolve())
        pin_config(self.window.engine_config)
        return self

    # ---- time and keys --------------------------------------------------------------------------------------
    def frames(self, n: int = 1) -> None:
        for _ in range(n):
            self.window.dispatch_event("on_update", 1 / 60)

    def key(self, name: str, frames: int = 1) -> None:
        """Hold the key ``name`` (arcade.key.<name>) for ``frames`` frames."""
        import engine.optional_arcade as optional_arcade

        code = getattr(optional_arcade.arcade.key, name)
        self.window.dispatch_event("on_key_press", code, 0)
        self.frames(frames)
        self.window.dispatch_event("on_key_release", code, 0)
        self.frames(1)

    # ---- rooms ------------------------------------------------------------------------------------------------
    def room(self, label: str) -> str:
        """The key of the room called ``label``."""
        return next(key for key, name, _path in self.project.rooms() if name == label)

    def path(self, room: str) -> str:
        return str(self.project.path(room))

    def enter(self, room: str) -> None:
        """Enter ``room`` as a door does: a fresh build of its file (and its room memory)."""
        self.sc.load_scene(self.path(room))
        self.frames(2)
        self.heard.clear()

    def revisit(self, room: str) -> None:
        """Leave for the Hall and come back."""
        self.enter(self.room(HALL))
        self.enter(room)

    def save_load(self, slot: str = "contract") -> None:
        """Save in the current room, then Continue: the production load and the queued room change a frame later."""
        from engine.scene_lifecycle_controller import handle_pending_scene_load

        manager = self.window.save_manager
        assert manager.save_game(slot), "the save was refused"
        assert manager.load_game(slot), "the load was refused"
        handle_pending_scene_load(self.sc)
        self.frames(2)
        self.heard.clear()

    # ---- what the player sees ---------------------------------------------------------------------------------
    def player(self) -> Any:
        return self.sc._find_player_sprite()

    def named(self, name: str) -> Any:
        return next((s for s in self.sc.all_sprites if getattr(s, "mesh_name", "") == name), None)

    def behaviour(self, name: str, kind: str) -> Any:
        sprite = self.named(name)
        return next((b for b in (sprite.mesh_behaviours_runtime if sprite else []) if type(b).__name__ == kind), None)

    def events(self, kind: str) -> list[dict[str, Any]]:
        return [payload for event, payload in self.heard if event == kind]

    def stand_by(self, name: str, dx: float = -36.0, dy: float = 0.0) -> None:
        target, hero = self.named(name), self.player()
        hero.center_x, hero.center_y = target.center_x + dx, target.center_y + dy
        self.frames(1)

    def interact(self, name: str) -> None:
        """Stand beside ``name`` and press the interact key."""
        self.stand_by(name)
        self.key("E", 1)
        self.frames(2)

    def flag(self, name: str) -> bool:
        return bool(self.window.get_flag(name, False))

    def counter(self, name: str) -> float:
        return float(self.gs.get_counter(name, 0) or 0)

    def items(self, item: str) -> int:
        from engine.inventory import get_or_create_inventory

        return int(get_or_create_inventory(self.gs.state.values).get_count(item))


@contextlib.contextmanager
def real_game(project: Any, launch_from: Path) -> Iterator[RealGame]:
    """The project's game, started by ``run_game(project_root=)`` from ``launch_from`` (not the project)."""
    import engine.optional_arcade as optional_arcade  # first: DPI-unaware, as the engine runs
    from engine.game import GameWindow
    from engine.paths import reset_path_caches
    from engine.public_api import run_game
    from engine.repo_root import clear_launched_project_root
    from tooling.hidden_windows import no_activate

    root = Path(project.root).resolve()
    assert launch_from.resolve() != root
    no_activate()
    shown = optional_arcade.arcade.Window.__init__
    started: list[Any] = []
    with pytest.MonkeyPatch.context() as mp, pytest.MonkeyPatch.context() as starting:
        mp.chdir(launch_from)
        mp.delenv("MESH_REPO_ROOT", raising=False)
        mp.delenv("MESH_SAVE_DIR", raising=False)
        clear_launched_project_root()
        reset_path_caches()
        starting.setattr(optional_arcade.arcade.Window, "__init__",
                         lambda self, *a, **k: shown(self, *a, **{**k, "visible": False}))

        starting.setattr(GameWindow, "run", lambda self: started.append(self))  # (in place of the window loop)
        window = None
        try:
            run_game(project.path(project.start_key()), project_root=root)
            window = started[0]
            starting.undo()
            mp.setenv("MESH_REPO_ROOT", str(root))  # (restored when the game is done; ``resume`` re-sets it)
            window._allow_dispatch_event = True
            window.audio.set_master_volume(0.0)
            game = RealGame(window, project).resume()  # (the game goes on after run_game returns)
            game.frames(3)
            yield game
        finally:
            if window is not None:
                dispose_game_window(window)
            clear_launched_project_root()
            reset_path_caches()
