"""#639b (owner decision D6): an unlocked "Locked until an event" door and a spent "Only once" Button stay so.

``DoorLock.locked`` and ``SwitchInteract.activated`` lived only on the instance, and a room is rebuilt from its file on
every entry, so after leaving and coming back, or loading a save, the gate was locked and solid again and the button
could be pressed again. Both are now facts in room memory (#686): recorded when they change, applied as the room is
built, so the gate is out of the solid list (and shows its open picture) before the player's first movement, and the
button shows its used picture and refuses a second press.

Each game is a new project (``create_project``, blank template) authored through Studio's authoring
(``engine.authoring.apply``: place, picture, the picker's "Locked until an event" and "Button", their settings, solid)
with a second room, played through its own ``main.py`` in a hidden window: the interact key's ``perform_interaction``,
and the player walking through the game's own update (PlayerController's mover).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine import authoring
from engine.project_scaffold import create_project
from engine.scene_runtime import room_memory
from engine.studio_project import Project
from tests.test_project_scaffolding_data import START, _Game, _play
from tests.test_reward_chest_grant import _strip_facts

pytestmark = pytest.mark.integration  # (generated projects in temporary folders; hidden game windows)
needs_window = pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")

EVENT = "gate_open"
BUTTON, USED = "assets/sprites/starter_sign.png", "assets/sprites/starter_villager.png"
DOOR, OPEN = "assets/sprites/door.png", "assets/sprites/starter_sign.png"
SOUTH_ROW = 220.0  # (px below the player's row: the starts-unlocked door is off the gate's path)


@pytest.fixture(scope="module")
def made(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    """East of the player on its row: a solid gate locked until "gate_open", with the "Only once" Button that sends it
    just before the gate. On a row of its own further south: a solid door that starts unlocked. And a Hall."""
    root = tmp_path_factory.mktemp("gate") / "game"
    create_project(root, "Game", template_id="blank")
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    start = next(k for k in project.world["scenes"] if project.path(k) == START)
    hall = project.add_room("Hall")
    player = next(e for e in project.scene(start)["entities"]
                  if e.get("prefab_id") == "player" or e.get("tag") == "player" or "player" in str(e.get("id")))
    px, py = float(player["x"]), float(player["y"])
    changes: list[dict[str, Any]] = []

    def place(name: str, x: float, y: float, picture: str, behaviour: str, **params: Any) -> str:
        ref = f"@{len(changes)}"
        changes.extend([{"op": "place_blank", "room": start, "name": name, "x": x, "y": y},
                        {"op": "set_picture", "room": start, "entity_id": ref, "sprite": picture},
                        {"op": "add_behaviour", "room": start, "entity_id": ref, "behaviour": behaviour}])
        changes.extend({"op": "set_behaviour_param", "room": start, "entity_id": ref, "behaviour": behaviour,
                        "param": key, "value": value} for key, value in params.items())
        return ref

    for name, x, y, locked in (("Gate", px + 330, py, True), ("Open door", px + 130, py + SOUTH_ROW, False)):
        ref = place(name, x, y, DOOR, "DoorLock", unlock_event=EVENT, starts_locked=locked, open_sprite=OPEN)
        changes.append({"op": "set_solid", "room": start, "entity_id": ref, "solid": True})
    place("Button", px + 285, py + 30, BUTTON, "SwitchInteract", event_id=EVENT, one_shot=True, active_sprite=USED)
    authoring.apply(project, changes)
    project.save()
    return root, project.path(hall)


@pytest.fixture()
def game_root(made: tuple[Path, str], tmp_path: Path) -> Path:
    root = tmp_path / "game"
    shutil.copytree(made[0], root)
    return root


class _Puzzle:
    """The running game, with the player's view of the gate, the button and the open door."""

    def __init__(self, game: _Game, hall: str, monkeypatch: pytest.MonkeyPatch) -> None:
        from engine.behaviours.player_controller import PlayerController
        from engine.save_manager import SaveManager

        self.game, self.window, self.sc, self.hall = game, game.window, game.sc, hall
        self.window.save_manager = SaveManager(self.window, save_dir=Path("saves").resolve())  # (the game's folder)
        self.presses: list[str] = []
        self.window.event_bus.subscribe(EVENT, lambda event: self.presses.append(event.type))
        hero = self.hero()
        self.spawn = (hero.center_x, hero.center_y)  # (the player's authored spot: where a fresh room puts them)
        # Whether the gate was solid when the player's mover first ran after each room build (None: not yet).
        self.solid_at_first_move: bool | None = None
        update = PlayerController.update

        def watched(behaviour: Any, dt: float) -> None:
            if self.solid_at_first_move is None and self.gate() is not None:
                self.solid_at_first_move = self.gate() in self.sc.solid_sprites
            update(behaviour, dt)

        monkeypatch.setattr(PlayerController, "update", watched)

    def named(self, name: str) -> Any:
        return self.game.named(name)

    def gate(self) -> Any:
        return self.named("Gate")

    def hero(self) -> Any:
        return self.sc._find_player_sprite()

    def door(self, name: str = "Gate") -> Any:
        return self.game.behaviour(name, "DoorLock")

    def button(self) -> Any:
        return self.game.behaviour("Button", "SwitchInteract")

    def picture(self, name: str, path: str) -> bool:
        return self.named(name).texture is self.window.assets.get_texture(path)

    def press(self) -> bool:
        """Stand just left of the button and press interact."""
        from engine.interaction import perform_interaction

        target, hero = self.named("Button"), self.hero()
        hero.center_x, hero.center_y = target.center_x - 40, target.center_y
        self.game.step(1)
        handled = perform_interaction(self.window, actor=hero)
        self.game.step(2)
        return bool(handled)

    def walk_east(self, frames: int, *, row: float = 0.0) -> None:
        """From the room's start (the player's authored spot, ``row`` px south), hold the move key."""
        key = optional_arcade.arcade.key.D
        hero = self.hero()
        hero.center_x, hero.center_y = self.spawn[0], self.spawn[1] + row
        self.window.dispatch_event("on_key_press", key, 0)
        self.game.step(frames)
        self.window.dispatch_event("on_key_release", key, 0)
        self.game.step(1)

    def past(self, name: str = "Gate") -> bool:
        return bool(self.hero().left > self.named(name).right)

    def facts(self) -> dict[str, Any]:
        entry = (self.window.game_state_controller.get_var(room_memory.VAR) or {}).get(START) or {}
        return dict(entry.get("facts") or {})

    def visit(self, room: str) -> None:
        self.solid_at_first_move = None
        self.sc.load_scene(room)
        self.game.step(2)

    def come_back(self) -> None:
        """Walk to the Hall and back."""
        self.visit(self.hall)
        self.visit(START)

    def state(self) -> dict[str, Any]:
        """What the player sees of the gate and the button."""
        return {"gate solid": self.gate() in self.sc.solid_sprites, "gate locked": self.door().locked,
                "open picture": self.picture("Gate", OPEN), "button spent": not self.button().can_interact_with(
                    self.hero()), "used picture": self.picture("Button", USED)}



OPENED = {"gate solid": False, "gate locked": False, "open picture": True, "button spent": True, "used picture": True}
AS_AUTHORED = {"gate solid": True, "gate locked": True, "open picture": False, "button spent": False,
               "used picture": False}


def _run(root: Path, hall: str, monkeypatch: pytest.MonkeyPatch, drive: Any) -> None:
    _play(root, monkeypatch, lambda game: drive(_Puzzle(game, hall, monkeypatch)))


def _open_the_gate(p: _Puzzle) -> None:
    """Locked: the player stops at the gate. Press the button: the gate opens and the player walks through."""
    assert p.state() == AS_AUTHORED
    p.walk_east(220)
    assert not p.past(), "the locked gate stops the player"
    assert p.press() and p.presses == [EVENT]
    p.walk_east(220)
    assert p.past() and p.state() == OPENED


# ------------------------------------------------------------------------------------------------ re-entry, load
@needs_window
def test_an_opened_gate_and_a_spent_button_stay_so_across_re_entry_and_save_fresh_window_load(
        game_root: Path, made: tuple[Path, str], monkeypatch: pytest.MonkeyPatch) -> None:
    hall = made[1]

    def first(p: _Puzzle) -> None:
        _open_the_gate(p)
        gate_id, button_id, open_id = (p.named(n).mesh_id for n in ("Gate", "Button", "Open door"))
        assert p.facts() == {gate_id: {"DoorLock": {"locked": False}},
                             button_id: {"SwitchInteract": {"activated": True}}}  # (none for the open door)
        p.come_back()
        assert p.solid_at_first_move is False, "the gate was out of the solid list before the player first moved"
        assert p.state() == OPENED
        assert not p.press() and p.presses == [EVENT], "the spent button can't be pressed again"
        p.walk_east(220)
        assert p.past(), "the player walks through the gate after coming back"
        p.walk_east(90, row=SOUTH_ROW)  # (a door that starts unlocked: as before, never in the way)
        assert p.past("Open door") and not p.door("Open door").locked
        assert open_id not in p.facts()
        p.visit(START)  # (the save is made in the gate's own room)
        assert p.window.save_manager.save_game("slot")

    def second(p: _Puzzle) -> None:  # (the game quit: nothing of the first window is left)
        assert p.window.save_manager.load_game("slot")
        p.solid_at_first_move = None
        p.game.step(3)
        assert str(p.sc.room_path) == START
        assert p.solid_at_first_move is False and p.state() == OPENED, "loaded into the gate's room"
        p.come_back()
        assert p.solid_at_first_move is False and p.state() == OPENED, "and on revisiting it"
        assert not p.press() and p.presses == []
        p.walk_east(220)
        assert p.past()

    _run(game_root, hall, monkeypatch, first)
    saved = json.loads((game_root / "saves" / "slot.json").read_text(encoding="utf-8"))
    facts = saved["game_state"]["variables"][room_memory.VAR][START]["facts"]
    assert sorted(facts.values(), key=str) == [{"DoorLock": {"locked": False}},
                                                {"SwitchInteract": {"activated": True}}]
    _run(game_root, hall, monkeypatch, second)


@needs_window
def test_a_save_from_before_facts_loads_with_the_gate_locked_and_the_button_ready_to_press_once(
        game_root: Path, made: tuple[Path, str], monkeypatch: pytest.MonkeyPatch) -> None:
    """The engine before facts kept room memory without them, so a gate opened then is as authored (locked, solid)
    when such a save loads. Its event doesn't fire again by itself, but the button isn't spent either: one press
    opens the gate again, and from then on both are kept as in any game."""
    hall = made[1]

    def first(p: _Puzzle) -> None:
        _open_the_gate(p)
        p.visit(hall)
        assert p.window.save_manager.save_game("old")

    def second(p: _Puzzle) -> None:
        assert p.window.save_manager.load_game("old")
        p.game.step(3)
        p.visit(START)
        _open_the_gate(p)
        assert not p.press() and p.presses == [EVENT], "once"
        p.come_back()
        assert p.state() == OPENED and not p.press()

    _run(game_root, hall, monkeypatch, first)
    slot = game_root / "saves" / "old.json"
    saved = json.loads(slot.read_text(encoding="utf-8"))
    assert _strip_facts(saved)  # (to the old shape, what the engine before facts wrote; a save holds copies)
    slot.write_text(json.dumps(saved), encoding="utf-8")
    _run(game_root, hall, monkeypatch, second)


# ------------------------------------------------------------------------------------------------ shipped content
RIDGE_E = "packs/core_regions/scenes/Ridge Outpost_dungeon_variant_e.json"


def test_ridge_outpost_variant_e_s_chest_opens_and_gives_its_potion(monkeypatch: pytest.MonkeyPatch) -> None:
    """It named ``health_potion``, which isn't in the engine's items.json, so it stayed closed with the unknown-item
    toast. Headless: the shipped scene through the game's scene loader, its chest built from the scene and opened with
    the interact key's ``perform_interaction``."""
    from engine.behaviours.registry import create_behaviour
    from engine.events import MeshEventBus
    from engine.game_state_controller import GameStateController
    from engine.interaction import perform_interaction
    from engine.inventory import clear_item_database_cache, get_or_create_inventory
    from engine.paths import project_root, reset_path_caches
    from engine.repo_root import clear_launched_project_root
    from engine.scene_loader import SceneLoader

    repo = Path(__file__).resolve().parents[1]
    monkeypatch.delenv("MESH_REPO_ROOT", raising=False)  # (the engine's own project: its items.json)
    clear_launched_project_root()
    reset_path_caches()
    clear_item_database_cache()
    try:
        assert Path(project_root()).resolve() == repo
        assert not SceneLoader().validate_scene_file(str(repo / RIDGE_E)).errors
        entity = next(e for e in json.loads((repo / RIDGE_E).read_text(encoding="utf-8"))["entities"]
                      if "RewardChest" in e.get("behaviours", []))
        chest_sprite = SimpleNamespace(mesh_id=entity["id"], mesh_name=entity["name"], mesh_tag="interactable",
                                       mesh_tags=["interactable"], mesh_entity_data=entity, center_x=entity["x"],
                                       center_y=entity["y"], width=32.0, height=32.0, visible=True)
        hero = SimpleNamespace(mesh_id="player", mesh_name="player", mesh_tag="player", mesh_tags=["player"],
                               mesh_entity_data={"id": "player"}, mesh_behaviours_runtime=[], width=16.0, height=16.0,
                               center_x=entity["x"] - 40, center_y=entity["y"], visible=True)
        window: Any = SimpleNamespace(event_bus=MeshEventBus(), player_hud=None)
        window.game_state_controller = GameStateController(window)
        window.scene_controller = SimpleNamespace(_find_player_sprite=lambda: hero, all_sprites=[chest_sprite, hero],
                                                  solid_sprites=None)
        chest = create_behaviour("RewardChest", chest_sprite, window, config=entity["behaviour_config"]["RewardChest"])
        chest_sprite.mesh_behaviours_runtime = [chest]
        assert perform_interaction(window, actor=hero)
        assert chest.looted
        assert get_or_create_inventory(window.game_state_controller.state.values).get_count("healing_potion") == 1
    finally:
        clear_item_database_cache()
