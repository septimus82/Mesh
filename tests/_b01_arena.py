"""B-01 test harness: a hidden GameWindow running a small "Arena" room through the production SaveManager.

Shared by tests/test_b01_save_identity.py and tests/test_b01_save_recovery.py. Real window, real scene files, real
save files: nothing here stubs the save path.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from engine.config import EngineConfig
from engine.save_manager import SaveManager
from engine.scene_lifecycle_controller import handle_pending_scene_load
from tests._game_window_live import dispose_game_window

PIC = "assets/placeholder.png"


def hero() -> dict[str, Any]:
    return {"id": "hero", "name": "Hero", "tag": "player", "x": 50, "y": 50, "sprite": PIC,
            "behaviours": ["Health"], "behaviour_config": {"Health": {"max_hp": 10, "hp": 10}}}


def goblin(eid: str | None, x: float, y: float, hp: float = 20, name: str = "Goblin") -> dict[str, Any]:
    out: dict[str, Any] = {"name": name, "x": x, "y": y, "sprite": PIC, "layer": "entities",
                           "behaviours": ["Health"], "behaviour_config": {"Health": {"max_hp": 20, "hp": hp}}}
    if eid is not None:
        out["id"] = eid
    return out


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hp_of(sprite: Any) -> float | None:
    for behaviour in getattr(sprite, "mesh_behaviours_runtime", []) or []:
        if type(behaviour).__name__ == "Health":
            return float(behaviour.hp)
    return None


def set_hp(sprite: Any, hp: float) -> None:
    for behaviour in sprite.mesh_behaviours_runtime:
        if type(behaviour).__name__ == "Health":
            behaviour.hp = float(hp)


class Arena:
    """A running game with an arena room; ``save``/``load`` are the player's save and Continue."""

    def __init__(self, window: Any, root: Path) -> None:
        self.window = window
        self.root = root
        self.saves = root / "saves"
        self.manager = SaveManager(window, save_dir=str(self.saves))
        window.save_manager = self.manager  # (room memory asks the window's manager where saves live)
        self.room = root / "arena.json"

    # ---- the room ------------------------------------------------------------------------------------------
    def write_room(self, *entities: dict[str, Any], name: str = "Arena") -> Path:
        self.room.write_text(json.dumps({"name": name, "schema_version": 1, "version": 1, "layers": [],
                                         "entities": list(entities)}), encoding="utf-8")
        return self.room

    def enter(self) -> None:
        """A pristine copy of the room (as a new game or a room change builds it)."""
        self.window.scene_controller.load_scene(str(self.room))

    @property
    def controller(self) -> Any:
        return self.window.scene_controller

    def sprites(self) -> list[Any]:
        return list(self.controller.all_sprites)

    def by_id(self, mesh_id: str) -> Any:
        found = [s for s in self.sprites() if getattr(s, "mesh_id", None) == mesh_id]
        assert len(found) == 1, (mesh_id, len(found))
        return found[0]

    def named(self, name: str) -> list[Any]:
        return sorted((s for s in self.sprites() if s.mesh_name == name), key=lambda s: (s.center_x, s.center_y))

    def spawn(self, data: dict[str, Any], hp: float | None = None) -> Any:
        """A runtime spawn exactly as combat/shooter/console do: _create_sprite + add_sprite_to_layer."""
        sprite = self.controller._create_sprite(dict(data))
        self.controller.add_sprite_to_layer(sprite, "entities")
        if hp is not None:
            set_hp(sprite, hp)
        return sprite

    def place(self, sprite: Any, x: float, y: float, hp: float | None = None) -> None:
        sprite.center_x, sprite.center_y = float(x), float(y)
        if hp is not None:
            set_hp(sprite, hp)

    def state(self) -> list[tuple[Any, Any, float, float, float | None]]:
        """(id, name, x, y, hp) of every sprite, sorted."""
        rows = [(getattr(s, "mesh_id", None), s.mesh_name, round(s.center_x, 3), round(s.center_y, 3), hp_of(s))
                for s in self.sprites()]
        return sorted(rows, key=lambda r: (str(r[0]), str(r[1]), r[2], r[3]))

    # ---- saving and loading --------------------------------------------------------------------------------
    def slot(self, name: str = "slot1") -> Path:
        return self.saves / f"{name}.json"

    def save(self, name: str = "slot1") -> dict[str, Any]:
        assert self.manager.save_game(name), "the save was refused"
        return self.read(name)

    def read(self, name: str = "slot1") -> dict[str, Any]:
        return json.loads(self.slot(name).read_text(encoding="utf-8"))

    def load(self, name: str = "slot1") -> bool:
        """Continue: the production load path, then the queued scene change a frame later."""
        if not self.manager.load_game(name):
            return False
        assert handle_pending_scene_load(self.controller) is True
        return True

    def toasts(self) -> list[str]:
        return list(self.window.player_hud.active_toasts())

    def records(self, name: str = "slot1") -> list[dict[str, Any]]:
        return self.read(name)["saved_entities"]["entities"]

    def unresolved(self, name: str = "slot1") -> list[dict[str, Any]]:
        return self.read(name)["saved_entities"]["unresolved"]

    def held(self) -> list[dict[str, Any]]:
        """The unresolved records the running game holds (what its next save writes)."""
        from engine.save_runtime.entity_state import held_unresolved

        return held_unresolved(self.controller)


def make_window() -> Any:
    """A hidden GameWindow that never activates, also in the worker processes (tests/_b09_worker.py,
    tests/_game1_worker.py), where tests/conftest.py's hiding doesn't run: they used to open a shown window."""
    from unittest.mock import patch

    import engine.optional_arcade as optional_arcade  # first: DPI-unaware, as the engine runs
    from engine.game import GameWindow
    from tooling.hidden_windows import no_activate

    no_activate()
    arcade = optional_arcade.arcade
    shown = arcade.Window.__init__

    def hidden(window: Any, *args: Any, **kwargs: Any) -> None:
        shown(window, *args, **{**kwargs, "visible": False})

    cfg = EngineConfig(width=320, height=200, title="B01", vsync=False, start_scene="", world_file=None,
                       main_menu_scene=None)
    with patch.object(arcade.Window, "__init__", hidden):
        return GameWindow(width=320, height=200, title=cfg.title, vsync=False, config=cfg)


def close_window(window: Any) -> None:
    dispose_game_window(window)
