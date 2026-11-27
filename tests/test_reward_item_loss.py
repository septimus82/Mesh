"""#627 (owner decision D7): an item the player's inventory can't take is never consumed for nothing.

Every way the game grants an item, played in a real hidden game (tests/_real_game.py) with a full stack of the item:
a defeated enemy's drop ("Drops items when defeated"), a pickup ("Can be picked up"), a pickup that carries items
("Carries items"), a treasure chest and a shopkeeper. What the inventory refuses stays to be had once there is room.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from tests._real_game import PIC, RealGame, new_project, real_game

pytestmark = [
    pytest.mark.integration,  # (a generated project in a temporary folder; one hidden game window)
    pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)"),
]

POTION, FULL = "healing_potion", 10  # (the starter item list's potion stacks to 10)
ROOM, DEN = "Loot", "Den"
HIGH = 64.0  # px: the wolf stands 2 m up (an HD-2D elevation; a 2D room ignores it, but the loot must keep it)


def _entity(eid: str, x: float, behaviours: dict[str, dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {
        "id": eid,
        "name": eid,
        "x": x,
        "y": 120,
        "sprite": PIC,
        "layer": "entities",
        "behaviours": list(behaviours),
        "behaviour_config": behaviours,
        **extra,
    }


WOLF = {"Health": {"max_hp": 5, "hp": 5}, "DropTable": {"drops": [{"item_id": POTION, "quantity": 3, "gold": 2}]}}


ENTITIES = [  # 128 px apart: beyond the interaction reach of the next
    _entity("Wolf", 80, WOLF, elevation=HIGH),
    _entity("Potion", 208, {"PickupCollectible": {"item_id": POTION, "item_amount": 2}}),
    _entity("Bag", 336, {"PickupCollectible": {}, "InventoryHolder": {"items": [{"id": POTION, "amount": 2}]}}),
    _entity("Satchel", 464, {"PickupCollectible": {}, "InventoryHolder": {"items": [{"id": POTION, "amount": 2}], "consume_on_transfer": False}}),
    _entity("Chest", 592, {"RewardChest": {"item_id": POTION, "gold": 4}}),
    _entity("Merchant", 720, {"Vendor": {"stock": [{"item_id": POTION, "price": 5}]}}),
    _entity("Urn", 848, {"DropTable": {"listen_event": "smash", "drops": [{"item_id": POTION, "quantity": 3}]}}),
]


@pytest.fixture(scope="module")
def running(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RealGame]:
    base = tmp_path_factory.mktemp("loot")
    project = new_project(base / "game")
    project.edit_scene(lambda scene: {**scene, "entities": [*scene.get("entities", []), *ENTITIES]}, project.add_room(ROOM))
    project.edit_scene(lambda scene: {**scene, "entities": [*scene.get("entities", []), _entity("DenWolf", 80, WOLF)]}, project.add_room(DEN))
    project.save()
    launch = base / "elsewhere"
    launch.mkdir()
    with real_game(project, launch) as started:
        yield started


@pytest.fixture()
def game(running: RealGame) -> RealGame:
    """A new game in the loot room (nothing taken, nothing remembered), with the potion stack at ``FULL``."""
    from engine.inventory import get_or_create_inventory

    g = running.resume()
    g.enter(g.room("Hall"))  # (leaving records what was taken; then it is forgotten)
    g.gs.set_var("room_memory", {})
    g.gs.set_counter("gold", 0)
    g.enter(g.room(ROOM))
    inventory = get_or_create_inventory(g.gs.state.values)
    inventory.clear()
    inventory.add_item(POTION, FULL)
    g.window.player_hud.clear_toasts()
    return g


def _make_room(g: RealGame) -> None:
    from engine.inventory import get_or_create_inventory

    get_or_create_inventory(g.gs.state.values).remove_item(POTION, FULL)


def _toasts(g: RealGame) -> list[str]:
    return list(g.window.player_hud.active_toasts())


def _pickups_at(g: RealGame, x: float) -> list[Any]:
    """Pickups lying within a step of ``x`` (what a defeated enemy left behind)."""
    return [s for s in g.sc.all_sprites if abs(s.center_x - x) < 32 and any(type(b).__name__ == "PickupCollectible" for b in s.mesh_behaviours_runtime)]


def _take(g: RealGame, sprite: Any) -> None:
    g.player().center_x, g.player().center_y = sprite.center_x - 36, sprite.center_y
    g.frames(1)
    g.key("E", 1)
    g.frames(2)


# --------------------------------------------------------------------------------------------- drops
def test_a_refused_drop_stays_on_the_ground_until_there_is_room(game: RealGame) -> None:
    game.behaviour("Wolf", "Health").apply_damage(99.0, source_entity="player")
    game.frames(4)
    assert game.named("Wolf") is None
    assert (game.items(POTION), game.counter("gold")) == (FULL, 6), "the gold arrives; the potions can't"
    assert "Can't carry any more Healing Potion" in _toasts(game)
    left = _pickups_at(game, 80)
    assert len(left) == 1, "the potions stay where the wolf fell"
    assert left[0].mesh_entity_data["elevation"] == HIGH, "on the level it fell on (HD-2D: same_level)"
    _take(game, left[0])
    assert game.items(POTION) == FULL and _pickups_at(game, 80), "still no room: still there"
    _make_room(game)
    _take(game, _pickups_at(game, 80)[0])
    assert game.items(POTION) == 3 and not _pickups_at(game, 80)


def test_a_refused_drop_is_still_there_after_leaving_and_after_a_save(game: RealGame) -> None:
    game.behaviour("Wolf", "Health").apply_damage(99.0, source_entity="player")
    game.frames(4)
    game.revisit(game.room(ROOM))
    assert game.named("Wolf") is None and len(_pickups_at(game, 80)) == 1
    assert _pickups_at(game, 80)[0].mesh_entity_data["elevation"] == HIGH
    game.save_load()
    assert game.named("Wolf") is None and len(_pickups_at(game, 80)) == 1
    assert _pickups_at(game, 80)[0].mesh_entity_data["elevation"] == HIGH
    _make_room(game)
    _take(game, _pickups_at(game, 80)[0])
    assert game.items(POTION) == 3
    game.revisit(game.room(ROOM))
    assert not _pickups_at(game, 80), "taken once: gone for good"
    game.save_load()
    assert not _pickups_at(game, 80) and game.items(POTION) == 3


def test_a_drop_that_partly_fits_grants_what_fits_and_leaves_the_rest(game: RealGame) -> None:
    from engine.inventory import get_or_create_inventory

    get_or_create_inventory(game.gs.state.values).remove_item(POTION, 2)
    game.behaviour("Wolf", "Health").apply_damage(99.0, source_entity="player")
    game.frames(4)
    assert game.items(POTION) == FULL
    left = _pickups_at(game, 80)
    assert [b.item_amount for s in left for b in s.mesh_behaviours_runtime] == [1]
    _make_room(game)
    _take(game, left[0])
    assert game.items(POTION) == 1 and not _pickups_at(game, 80)


def test_two_refusals_by_one_table_are_both_remembered(game: RealGame) -> None:
    game.window.event_bus.emit("smash")
    game.window.event_bus.emit("smash")
    game.frames(2)
    assert len(_pickups_at(game, 848)) == 2
    game.revisit(game.room(ROOM))
    assert sum(b.item_amount for s in _pickups_at(game, 848) for b in s.mesh_behaviours_runtime) == 6
    _make_room(game)
    for pile in _pickups_at(game, 848):
        _take(game, pile)
    assert game.items(POTION) == 6
    game.revisit(game.room(ROOM))
    assert not _pickups_at(game, 848)


def test_loot_outlives_its_enemy_being_renamed_or_deleted(game: RealGame) -> None:
    den = game.room(DEN)
    game.enter(den)
    game.behaviour("DenWolf", "Health").apply_damage(99.0, source_entity="player")
    game.frames(4)
    game.project.edit_scene(lambda scene: {**scene, "entities": [e for e in scene["entities"] if e.get("id") != "DenWolf"]}, den)
    game.project.save()  # (the creator deletes the wolf; its loot is still the player's)
    game.revisit(den)
    assert len(_pickups_at(game, 80)) == 1
    _make_room(game)
    _take(game, _pickups_at(game, 80)[0])
    assert game.items(POTION) == 3
    game.revisit(den)
    assert not _pickups_at(game, 80), "taken once: gone for good"


def test_a_drop_with_room_is_granted_once_and_leaves_nothing(game: RealGame) -> None:
    _make_room(game)
    game.behaviour("Wolf", "Health").apply_damage(99.0, source_entity="player")
    game.frames(4)
    assert (game.items(POTION), game.counter("gold")) == (3, 6)
    assert not _pickups_at(game, 80)
    game.revisit(game.room(ROOM))
    assert not _pickups_at(game, 80) and game.items(POTION) == 3


# --------------------------------------------------------------------------------------------- pickups
def test_a_refused_pickup_stays(game: RealGame) -> None:
    game.interact("Potion")
    assert game.items(POTION) == FULL and game.named("Potion") is not None
    _make_room(game)
    game.interact("Potion")
    assert game.items(POTION) == 2 and game.named("Potion") is None


@pytest.mark.parametrize("name", ["Bag", "Satchel"])
def test_a_carrier_whose_items_are_refused_stays_and_says_so(game: RealGame, name: str) -> None:
    game.interact(name)
    assert game.items(POTION) == FULL and game.named(name) is not None, "what it carries is still there"
    assert "Can't carry any more Healing Potion" in _toasts(game)
    assert not game.events("collected"), "nothing was collected"
    _make_room(game)
    game.interact(name)
    assert game.items(POTION) == 2 and game.named(name) is None


# --------------------------------------------------------------------------------------------- chest, shop
def test_a_refused_chest_stays_closed(game: RealGame) -> None:
    game.interact("Chest")
    assert (game.items(POTION), game.counter("gold")) == (FULL, 0)
    _make_room(game)
    game.interact("Chest")
    game.interact("Chest")
    assert (game.items(POTION), game.counter("gold")) == (1, 4)


def test_a_refused_purchase_costs_nothing(game: RealGame) -> None:
    vendor = game.behaviour("Merchant", "Vendor")
    game.gs.set_counter("gold", 20)
    assert not vendor.handle_buy_request(vendor.stock[0]).ok
    assert (game.items(POTION), game.counter("gold")) == (FULL, 20)
    _make_room(game)
    assert vendor.handle_buy_request(vendor.stock[0]).ok
    assert (game.items(POTION), game.counter("gold")) == (1, 15)
