"""B-05: an entity that leaves the scene ends its behaviours, so its event callbacks stop.

Real runtime: a hidden GameWindow, real scene file, the production scene controller and behaviours (the harness of
tests/_b01_arena.py). The entity sprite's ``remove_from_sprite_lists`` (what ``kill()``, Health death, a collectible
pick-up and a projectile's expiry all call) runs each behaviour's ``on_destroy`` once; a layer move is not a removal.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest

from engine import optional_arcade
from tests._b01_arena import PIC, Arena, close_window, make_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

HERO = {"id": "hero", "name": "Hero", "tag": "player", "x": 50, "y": 50, "sprite": PIC,
        "behaviours": ["Health"], "behaviour_config": {"Health": {"max_hp": 10, "hp": 10}}}


def _entity(eid: str, *behaviours: tuple[str, dict[str, Any]], x: float = 200, y: float = 200) -> dict[str, Any]:
    return {"id": eid, "name": eid, "x": x, "y": y, "sprite": PIC, "layer": "entities",
            "behaviours": [name for name, _ in behaviours], "behaviour_config": {n: c for n, c in behaviours}}


XP = ("GrantExperience", {"event": "foe_died", "xp": 5})
QUEST = ("QuestGiver", {"quest_id": "q", "listen_event": "offer"})
CUTSCENE = ("CutsceneTrigger", {"listen_event": "go", "cutscene_id": "c"})
EXIT = ("SceneExit", {"listen_event": "leave", "target_scene": "b.json", "target_spawn": "s"})
HEALTH = ("Health", {"max_hp": 5, "hp": 5})


class Probe:
    """Counts what each callback does, without replacing it."""

    def __init__(self, arena: Arena) -> None:
        self.arena = arena
        window = arena.window
        gs = window.game_state_controller
        self.xp = 0
        self.quests = 0
        self.cutscenes = 0
        self.exits = 0
        orig_xp = gs.add_xp
        orig_start = gs.quests.start_quest

        def add_xp(amount: Any) -> Any:
            self.xp += 1
            return orig_xp(amount)

        def start_quest(*a: Any, **k: Any) -> Any:
            self.quests += 1
            return orig_start(*a, **k)

        gs.add_xp = add_xp
        gs.quests.start_quest = start_quest
        window.cutscene_controller.play_cutscene = lambda *_a, **_k: setattr(self, "cutscenes", self.cutscenes + 1)
        window.scene_controller.queue_scene_change = lambda *_a, **_k: setattr(self, "exits", self.exits + 1)

    def publish(self, sprite: Any) -> tuple[int, int, int, int]:
        bus = self.arena.window.event_bus
        bus.emit("foe_died", actor=sprite)
        bus.emit("offer")
        bus.emit("go")
        bus.emit("leave")
        return self.xp, self.quests, self.cutscenes, self.exits


def listeners(arena: Arena) -> int:
    bus = arena.window.event_bus
    return sum(len(v) for v in bus._subscribers.values())


@pytest.fixture()
def arena(tmp_path: Path) -> Iterator[Arena]:
    window = make_window()
    try:
        yield Arena(window, tmp_path)
    finally:
        close_window(window)


def _all_four(eid: str = "npc", *extra: tuple[str, dict[str, Any]], x: float = 200) -> dict[str, Any]:
    return _entity(eid, XP, QUEST, CUTSCENE, EXIT, *extra, x=x)


def _setup(arena: Arena, *entities: dict[str, Any]) -> tuple[Probe, int]:
    arena.write_room(HERO, *entities)
    baseline_room = listeners(arena)  # (empty room built below: measured after enter with only the hero)
    arena.enter()
    return Probe(arena), baseline_room


def _baseline_with_hero(arena: Arena) -> int:
    arena.write_room(HERO)
    arena.enter()
    return listeners(arena)


def test_kill_ends_behaviours_and_listeners_return_to_baseline(arena: Arena) -> None:
    base = _baseline_with_hero(arena)
    probe = Probe(arena)
    sprite = arena.spawn(_all_four("npc", HEALTH))
    assert listeners(arena) == base + 4
    sprite.kill()
    assert listeners(arena) == base
    assert probe.publish(sprite) == (0, 0, 0, 0)


def test_health_death_ends_behaviours(arena: Arena) -> None:
    base = _baseline_with_hero(arena)
    probe = Probe(arena)
    sprite = arena.spawn(_all_four("npc", HEALTH))
    health = next(b for b in sprite.mesh_behaviours_runtime if type(b).__name__ == "Health")
    health.apply_damage(999)
    assert sprite not in arena.sprites()
    assert listeners(arena) == base
    assert probe.publish(sprite) == (0, 0, 0, 0)  # no grant, offer, cutscene or exit from a dead entity


def test_death_still_pays_its_drop_before_the_behaviours_end(arena: Arena) -> None:
    """DropTable listens for the entity's own ``died``: the event is delivered before the removal, so the loot lands."""
    _baseline_with_hero(arena)
    drop = ("DropTable", {"listen_event": "died", "drops": [{"gold": 7}]})
    sprite = arena.spawn(_entity("beast", HEALTH, drop))
    gs = arena.window.game_state_controller
    before = gs.state.counters.get("gold", 0)
    next(b for b in sprite.mesh_behaviours_runtime if type(b).__name__ == "Health").apply_damage(999)
    assert sprite not in arena.sprites()
    assert gs.state.counters.get("gold", 0) == before + 7


def test_collectible_pickup_ends_behaviours(arena: Arena) -> None:
    base = _baseline_with_hero(arena)
    probe = Probe(arena)
    sprite = arena.spawn(_entity("gem", ("Collectible", {"collect_by_name": "Hero"}), QUEST, XP, x=50, y=50))
    assert listeners(arena) == base + 2
    collectible = next(b for b in sprite.mesh_behaviours_runtime if type(b).__name__ == "Collectible")
    if sprite in arena.sprites():
        collectible.update(1 / 60)
    assert sprite not in arena.sprites()
    assert listeners(arena) == base
    assert probe.publish(sprite) == (0, 0, 0, 0)


def test_projectile_expiry_ends_behaviours(arena: Arena) -> None:
    base = _baseline_with_hero(arena)
    probe = Probe(arena)
    sprite = arena.spawn(_entity("bolt", ("Projectile", {"lifetime": 0.5}), XP, QUEST))
    assert listeners(arena) == base + 2
    projectile = next(b for b in sprite.mesh_behaviours_runtime if type(b).__name__ == "Projectile")
    projectile.update(1.0)
    assert sprite not in arena.sprites()
    assert listeners(arena) == base
    assert probe.publish(sprite) == (0, 0, 0, 0)


def test_removal_ends_behaviours_once(arena: Arena) -> None:
    _baseline_with_hero(arena)
    sprite = arena.spawn(_all_four("npc"))
    calls: list[str] = []
    for behaviour in sprite.mesh_behaviours_runtime:
        orig = behaviour.on_destroy
        behaviour.on_destroy = lambda orig=orig, n=type(behaviour).__name__: (calls.append(n), orig())[1]
    sprite.remove_from_sprite_lists()
    sprite.remove_from_sprite_lists()
    sprite.kill()
    assert sorted(calls) == ["CutsceneTrigger", "GrantExperience", "QuestGiver", "SceneExit"]


def test_layer_move_is_not_a_removal(arena: Arena) -> None:
    base = _baseline_with_hero(arena)
    probe = Probe(arena)
    sprite = arena.spawn(_all_four("npc"))
    controller = arena.controller
    for layer in controller.layers.values():  # what the editor's layer move and delete_entity_internal do
        if sprite in layer:
            layer.remove(sprite)
    controller.add_sprite_to_layer(sprite, "entities")
    assert listeners(arena) == base + 4
    assert probe.publish(sprite) == (1, 1, 1, 1)


def test_scene_change_ends_listeners_and_a_later_room_works(arena: Arena) -> None:
    base = _baseline_with_hero(arena)
    probe = Probe(arena)
    arena.spawn(_all_four("npc"))
    arena.enter()  # entering a room again clears the scene's subscriptions (and builds the hero afresh)
    assert listeners(arena) == base
    arena.window.event_bus.emit("offer")
    assert probe.quests == 0
    again = arena.spawn(_all_four("npc2"))
    assert listeners(arena) == base + 4
    again.kill()
    assert listeners(arena) == base
