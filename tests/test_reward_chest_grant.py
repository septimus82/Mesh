"""#636 (owner decisions D6, D7): Studio's "Treasure chest" (RewardChest) gives its reward once, through the game.

It granted only through ``interactor.inventory`` (a player sprite has none) and ``add_gold`` (nothing has it), marked
itself looted first and emitted ``reward_collected`` anyway, so it gave nothing; and ``looted`` wasn't kept, so once it
gave something it could be opened again after leaving the room. Now the reward goes into the game-state inventory and
the ``gold`` counter, all or nothing: a chest whose item can't be carried (full stack, owned non-stackable, unknown id)
stays closed, gold included, with the pickup's "can't carry" / unknown toast. ``looted`` (and ``enabled``, unlocked)
are facts in room memory (#686), recorded only after the grant.

Each game is a new project (``create_project``: it has the starter items.json) with chests placed through Studio's
authoring (``engine.authoring.apply``: place, picture, Treasure chest, its settings) and a second room, played through
its own ``main.py`` in a hidden window and opened with ``engine.interaction.perform_interaction`` (the interact key).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine import authoring
from engine.project_scaffold import create_project
from engine.scene_runtime import room_memory
from engine.studio_project import Project
from tests.test_project_scaffolding_data import SIGN, START, _Game, _play

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

UNLOCK = "vault_open"  # (as the shipped core_regions dungeons: a door or lever's event unlocks the chest)
CHESTS = {  # name: (x offset from the player, item, gold); 128 px apart, beyond the interaction reach of the next
    "Chest": (64, "healing_potion", 10),
    "Sword chest": (192, "rusty_sword", 0),
    "Gem chest": (320, "mystery_gem", 5),
    "Gold chest": (448, "", 25),
}


@pytest.fixture(scope="module")
def made(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    """The game as its creator left it: the chests in the start room, and a Hall to walk to and back from."""
    root = tmp_path_factory.mktemp("chest") / "game"
    create_project(root, "Game", template_id="starter")
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    start = next(k for k in project.world["scenes"] if project.path(k) == START)
    hall = project.add_room("Hall")
    player = next(e for e in project.scene(start)["entities"] if e.get("prefab_id") == "player" or e.get("tag") == "player")
    changes: list[dict[str, Any]] = []
    for name, (dx, item, gold) in CHESTS.items():
        ref = f"@{len(changes)}"
        changes += [{"op": "place_blank", "room": start, "name": name, "x": float(player["x"]) + dx,
                     "y": float(player["y"]) - 32},
                    {"op": "set_picture", "room": start, "entity_id": ref, "sprite": SIGN},
                    {"op": "add_behaviour", "room": start, "entity_id": ref, "behaviour": "RewardChest"}]
        params = {"unlock_event": UNLOCK, "item_id": item, "gold": gold}
        changes += [{"op": "set_behaviour_param", "room": start, "entity_id": ref, "behaviour": "RewardChest",
                     "param": key, "value": value} for key, value in params.items() if value]
    authoring.apply(project, changes)
    project.save()
    return root, project.path(hall)


@pytest.fixture()
def game_root(made: tuple[Path, str], tmp_path: Path) -> Path:
    root = tmp_path / "game"
    shutil.copytree(made[0], root)
    return root


class _Chests:
    """The running game, with the player's view of the chests."""

    def __init__(self, game: _Game, hall: str) -> None:
        from engine.save_manager import SaveManager

        self.game, self.window, self.gs, self.hall = game, game.window, game.gs, hall
        self.window.save_manager = SaveManager(self.window, save_dir=Path("saves").resolve())  # (the game's folder)
        self.events: list[dict[str, Any]] = []
        self.window.event_bus.subscribe("reward_collected", self._seen)

    def _seen(self, event: Any) -> None:
        """What had happened by the time the event arrived."""
        item = event.payload["item_id"]
        chest = self.chest(next(n for n, (_dx, i, _g) in CHESTS.items() if i == item))
        self.events.append({"item": item, "count": self.count(item) if item else None, "gold": self.gold(),
                            "looted": chest.looted, "fact": self.facts().get(chest.entity.mesh_id)})

    def chest(self, name: str) -> Any:
        return self.game.behaviour(name, "RewardChest")

    def open(self, name: str) -> bool:
        """Stand just left of the chest and press interact."""
        from engine.interaction import perform_interaction

        target, hero = self.game.named(name), self.game.sc._find_player_sprite()
        hero.center_x, hero.center_y = target.center_x - 40, target.center_y
        self.game.step(1)
        handled = perform_interaction(self.window, actor=hero)
        self.game.step(2)
        return bool(handled)

    def unlock(self) -> None:
        self.window.event_bus.emit(UNLOCK)
        self.game.step(1)

    def refusals(self) -> list[str]:
        """The toasts showing, but the game's own key hints."""
        return [t for t in self.game.toasts() if "Can't" in t or "Unknown" in t]

    def inventory(self) -> Any:
        from engine.inventory import get_or_create_inventory

        return get_or_create_inventory(self.gs.state.values)

    def count(self, item: str) -> int:
        return int(self.inventory().get_count(item))

    def items(self) -> dict[str, int]:
        return dict(self.inventory().list_items())

    def gold(self) -> int:
        return int(self.gs.get_counter("gold", 0))

    def facts(self) -> dict[str, Any]:
        entry = (self.gs.get_var(room_memory.VAR) or {}).get(START) or {}
        return dict(entry.get("facts") or {})

    def visit(self, room: str) -> None:
        self.window.scene_controller.load_scene(room)
        self.game.step(2)

    def come_back(self) -> None:
        """Walk to the Hall and back."""
        self.visit(self.hall)
        self.visit(START)


def _strip_facts(node: Any) -> int:
    """Remove every room's facts from a save's room memory, wherever the save keeps a copy; how many copies."""
    found = 0
    if isinstance(node, dict):
        for key, value in node.items():
            if key == room_memory.VAR and isinstance(value, dict):
                found += sum(entry.pop(room_memory.FACTS, None) is not None for entry in value.values())
            else:
                found += _strip_facts(value)
    return found


def _run(root: Path, hall: str, monkeypatch: pytest.MonkeyPatch, drive: Any) -> None:
    _play(root, monkeypatch, lambda game: drive(_Chests(game, hall)))


# ------------------------------------------------------------------------------------------------ the grant

def test_an_empty_inventory_gets_the_item_and_gold_then_the_chest_is_looted_then_the_event(
        game_root: Path, made: tuple[Path, str], monkeypatch: pytest.MonkeyPatch) -> None:
    def drive(c: _Chests) -> None:
        assert not hasattr(c.game.sc._find_player_sprite(), "inventory")  # (the game keeps it in its state)
        assert not c.open("Chest") and c.items() == {} and c.gold() == 0  # (locked: nothing yet)
        c.unlock()
        assert c.open("Chest")
        assert (c.count("healing_potion"), c.gold(), c.chest("Chest").looted) == (1, 10, True)
        # When the event arrived the reward was in, the chest looted, and the fact in room memory (a save has it).
        assert c.events == [{"item": "healing_potion", "count": 1, "gold": 10, "looted": True,
                             "fact": {"RewardChest": {"enabled": True, "looted": True}}}]
        assert not c.open("Chest") and (c.count("healing_potion"), c.gold(), len(c.events)) == (1, 10, 1)
        assert not c.refusals()

    _run(game_root, made[1], monkeypatch, drive)


def test_a_gold_only_chest_pays_its_gold(game_root: Path, made: tuple[Path, str],
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    def drive(c: _Chests) -> None:
        c.unlock()
        assert c.open("Gold chest")
        assert (c.items(), c.gold(), c.chest("Gold chest").looted) == ({}, 25, True)
        assert [e["gold"] for e in c.events] == [25]

    _run(game_root, made[1], monkeypatch, drive)


@pytest.mark.parametrize(("case", "chest", "owned", "toast", "make_room"), [
    ("full stack", "Chest", {"healing_potion": 10}, "Can't carry any more Healing Potion", ("healing_potion", 1)),
    ("owned non-stackable", "Sword chest", {"rusty_sword": 1}, "Can't carry any more Rusty Sword", ("rusty_sword", 1)),
    ("unknown id", "Gem chest", {}, "Unknown item 'mystery_gem' (not in assets/data/items.json)", None),
])
def test_a_reward_the_inventory_cannot_take_leaves_the_chest_closed_and_says_why(
        game_root: Path, made: tuple[Path, str], monkeypatch: pytest.MonkeyPatch, case: str, chest: str,
        owned: dict[str, int], toast: str, make_room: tuple[str, int] | None) -> None:
    def drive(c: _Chests) -> None:
        for item, amount in owned.items():
            c.inventory().add_item(item, amount)
        c.unlock()
        before = (c.items(), c.gold())
        c.open(chest)
        assert (c.items(), c.gold()) == before, f"{case}: nothing taken, the gold included"
        assert not c.chest(chest).looted and c.events == [] and c.refusals() == [toast]
        assert c.facts()[c.chest(chest).entity.mesh_id] == {"RewardChest": {"enabled": True}}  # (not looted)
        c.come_back()  # (to make room, say): the chest is still unlocked and still holds its reward
        assert c.chest(chest).enabled and not c.chest(chest).looted
        if make_room is not None:
            c.inventory().remove_item(*make_room)
            assert c.open(chest) and c.chest(chest).looted and len(c.events) == 1

    _run(game_root, made[1], monkeypatch, drive)


# ------------------------------------------------------------------------------------------------ once only

def test_a_looted_chest_pays_once_across_re_entry_and_save_fresh_window_load(
        game_root: Path, made: tuple[Path, str], monkeypatch: pytest.MonkeyPatch) -> None:
    hall = made[1]

    def first(c: _Chests) -> None:
        c.unlock()
        assert c.open("Chest") and (c.count("healing_potion"), c.gold()) == (1, 10)
        c.come_back()
        assert c.chest("Chest").looted and not c.chest("Chest").can_interact_with(c.game.sc._find_player_sprite())
        assert not c.open("Chest") and (c.count("healing_potion"), c.gold()) == (1, 10)
        c.visit(hall)
        assert c.window.save_manager.save_game("slot")

    def second(c: _Chests) -> None:  # (the game quit: nothing of the first window is left)
        assert c.window.save_manager.load_game("slot")
        c.game.step(3)
        assert str(c.window.scene_controller.room_path) == hall and (c.count("healing_potion"), c.gold()) == (1, 10)
        c.visit(START)
        assert c.chest("Chest").looted and c.chest("Gold chest").enabled  # (still unlocked: no event this time)
        assert not c.open("Chest") and (c.count("healing_potion"), c.gold(), c.events) == (1, 10, [])

    _run(game_root, hall, monkeypatch, first)
    saved = json.loads((game_root / "saves" / "slot.json").read_text(encoding="utf-8"))
    chest_ids = saved["game_state"]["variables"][room_memory.VAR][START]["facts"]
    assert {"enabled": True, "looted": True} in [f["RewardChest"] for f in chest_ids.values()]
    _run(game_root, hall, monkeypatch, second)


def test_a_save_from_before_facts_loads_with_its_chests_not_yet_looted(
        game_root: Path, made: tuple[Path, str], monkeypatch: pytest.MonkeyPatch) -> None:
    """The engine before facts kept room memory without them, so a chest opened then is as authored (locked, full)
    when such a save loads: its reward can be taken once more. (Before #636 opening it gave nothing anyway.)"""
    hall = made[1]

    def first(c: _Chests) -> None:
        c.unlock()
        assert c.open("Chest")
        c.visit(hall)
        assert c.window.save_manager.save_game("old")

    def second(c: _Chests) -> None:
        assert c.window.save_manager.load_game("old")
        c.game.step(3)
        c.visit(START)
        assert not c.chest("Chest").looted and not c.chest("Chest").enabled
        c.unlock()
        assert c.open("Chest") and (c.count("healing_potion"), c.gold()) == (2, 20)
        c.come_back()  # (and from here it is kept as in any game)
        assert c.chest("Chest").looted and not c.open("Chest") and (c.count("healing_potion"), c.gold()) == (2, 20)

    _run(game_root, hall, monkeypatch, first)
    slot = game_root / "saves" / "old.json"
    saved = json.loads(slot.read_text(encoding="utf-8"))
    assert _strip_facts(saved)  # (to the old shape, what the engine before facts wrote; a save holds copies)
    slot.write_text(json.dumps(saved), encoding="utf-8")
    _run(game_root, hall, monkeypatch, second)
