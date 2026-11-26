"""#637 / #638: a removed entity stops reacting to events; an EventLogger logs in a live game.

Real runtime: a hidden GameWindow, real room files, the production scene controller, behaviours, save manager and
frame (tests/_b01_arena.py). Each removal path the game has (kill, Health death, a pickup, the entity store's despawn
that mesh_net's client uses, the editor's and the authoring delete, leaving the room) is followed by every event the
six behaviours used to hear, delivered through the bus and the next frame: nothing they did before happens.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterator

import pytest

from engine import optional_arcade
from engine.editor.editor_entity_ops_controller import EditorEntityOpsController
from engine.game_runtime import scene_ops
from engine.scene_runtime.authoring.entity_ops_parts.delete_ops import debug_remove_entity_by_id
from engine.scene_runtime.index_build import build_scene_index_from_sprites
from tests._b01_arena import PIC, Arena, close_window, hero, make_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

REPO = Path(__file__).resolve().parent.parent
REMOVABLE = [("Health", {"max_hp": 5, "hp": 5}), ("PickupCollectible", {"collector_tag": "player"})]
# id -> (behaviour, its config, the event it subscribes to). Vendor listens through the frame's on_event (#682).
SIX = {
    "door": ("DoorLock", {"unlock_event": "lever_pulled"}, "lever_pulled"),
    "chest": ("RewardChest", {"unlock_event": "vault_open", "gold": 5}, "vault_open"),
    "tally": ("SetGameStateOnEvent", {"event_type": "ping", "inc_counters": {"tally": 1}}, "ping"),
    "pinger": ("IncrementCounterOnEvent", {"event_type": "count_me", "counter": "pings"}, "count_me"),
    "greeter": ("MessageOnZoneEnter", {"zone_name": "gate"}, "entered_zone"),
    "shop": ("Vendor", {"listen_event": "open_shop", "open_on": "event"}, None),
}
BUS_EVENTS = [event for _name, _cfg, event in SIX.values() if event]


def _entity(eid: str, x: float) -> dict[str, Any]:
    name, cfg, _event = SIX[eid]
    behaviours = [(name, cfg), *REMOVABLE]
    return {"id": eid, "name": eid, "x": x, "y": 160, "sprite": PIC, "layer": "entities",
            "behaviours": [b for b, _ in behaviours], "behaviour_config": dict(behaviours)}


ROOM = [hero(), *(_entity(eid, 100 + 30 * i) for i, eid in enumerate(SIX))]


@pytest.fixture()
def arena(tmp_path: Path) -> Iterator[Arena]:
    window = make_window()
    try:
        arena = Arena(window, tmp_path)
        arena.logs = []  # type: ignore[attr-defined]
        log = window.console_log
        window.console_log = lambda text, *a, **k: (arena.logs.append(str(text)), log(text, *a, **k))[1]  # type: ignore[attr-defined]
        arena.write_room(*ROOM)
        arena.enter()
        yield arena
    finally:
        close_window(window)


def _behaviour(sprite: Any, name: str) -> Any:
    return next(b for b in sprite.mesh_behaviours_runtime if type(b).__name__ == name)


def _six(arena: Arena) -> dict[str, Any]:
    return {eid: arena.by_id(eid) for eid in SIX}


def _observed(arena: Arena, sprites: dict[str, Any]) -> dict[str, Any]:
    gs, window = arena.window.game_state_controller, arena.window
    return {"door locked": _behaviour(sprites["door"], "DoorLock").locked,
            "chest enabled": _behaviour(sprites["chest"], "RewardChest").enabled,
            "tally": gs.get_counter("tally", 0), "pings": gs.get_counter("pings", 0),
            "zone messages": sum("entered zone gate" in line for line in arena.logs),  # type: ignore[attr-defined]
            "shop open": bool(window.ui_controller.shop_panel.visible)}


def _send_all(arena: Arena) -> None:
    bus = arena.window.event_bus
    for event in ("lever_pulled", "vault_open", "ping", "count_me"):
        bus.emit(event)
    bus.emit("entered_zone", zone="gate", actor="Hero")
    bus.emit("open_shop")
    arena.window.on_update(1 / 60)  # (the frame delivers them to each entity's on_event too)


def _listeners(arena: Arena) -> dict[str, int]:
    subscribers = arena.window.event_bus._subscribers
    return {event: len(subscribers.get(event, [])) for event in BUS_EVENTS}


# ---- the removal paths ----------------------------------------------------------------------------------------
def _kill(arena: Arena, sprite: Any) -> None:
    sprite.kill()


def _death(arena: Arena, sprite: Any) -> None:
    _behaviour(sprite, "Health").apply_damage(999)


def _pickup(arena: Arena, sprite: Any) -> None:
    _behaviour(sprite, "PickupCollectible").on_interact(arena.window, arena.by_id("hero"))


def _despawn(arena: Arena, sprite: Any) -> None:
    store = arena.controller.entities  # what mesh_net's scene client does with an avatar or a drop that has gone
    store.enqueue_despawn(sprite)
    store.apply_pending_ops(arena.controller)


def _editor(arena: Arena, sprite: Any) -> None:
    editor = SimpleNamespace(window=SimpleNamespace(scene_controller=arena.controller), selected_entity=None)
    EditorEntityOpsController(editor).delete_entity_internal(sprite)  # type: ignore[arg-type]


def _authoring(arena: Arena, sprite: Any) -> None:
    arena.controller._scene_index = build_scene_index_from_sprites(arena.controller.all_sprites)
    assert debug_remove_entity_by_id(arena.controller, sprite.mesh_entity_data["id"])


PATHS: dict[str, Callable[[Arena, Any], None]] = {"kill": _kill, "death": _death, "pickup": _pickup,
                                                  "despawn": _despawn, "editor": _editor, "authoring": _authoring}


def test_present_entities_each_react_once(arena: Arena) -> None:
    """The control: the room as built hears every event once."""
    sprites = _six(arena)
    assert _listeners(arena) == dict.fromkeys(BUS_EVENTS, 1)
    _send_all(arena)
    assert _observed(arena, sprites) == {"door locked": False, "chest enabled": True, "tally": 1, "pings": 1,
                                         "zone messages": 1, "shop open": True}


@pytest.mark.parametrize("remove", list(PATHS.values()), ids=list(PATHS))
def test_a_removed_entity_reacts_to_nothing(arena: Arena, remove: Callable[[Arena, Any], None]) -> None:
    sprites = _six(arena)
    before = _observed(arena, sprites)
    for sprite in sprites.values():
        remove(arena, sprite)
    assert [s.mesh_id for s in arena.sprites()] == ["hero"]
    assert _listeners(arena) == dict.fromkeys(BUS_EVENTS, 0)
    _send_all(arena)
    assert _observed(arena, sprites) == before


def test_leaving_the_room_ends_them_too(arena: Arena) -> None:
    sprites = _six(arena)
    before = _observed(arena, sprites)
    shed = arena.root / "shed.json"
    shed.write_text(json.dumps({"name": "Shed", "schema_version": 1, "version": 1, "layers": [], "entities": [hero()]}),
                    encoding="utf-8")
    arena.window.scene_controller.load_scene(str(shed))
    assert _listeners(arena) == dict.fromkeys(BUS_EVENTS, 0)
    _send_all(arena)
    assert _observed(arena, sprites) == before


def test_ending_twice_is_harmless_to_a_twin(arena: Arena) -> None:
    """The scene's record runs the same unsubscribes again on leaving: a removed entity's never takes a twin's."""
    twin = arena.spawn({**_entity("tally", 400), "id": "tally2"})
    gone = arena.by_id("tally")
    made = list(gone.mesh_behaviour_unsubscribes)
    assert made and _listeners(arena)["ping"] == 2
    gone.kill()
    assert gone.mesh_behaviour_unsubscribes == []  # (released: nothing of the removed entity is kept to run again)
    for unsubscribe in made:
        unsubscribe()
    assert _listeners(arena)["ping"] == 1
    arena.window.event_bus.emit("ping")
    assert arena.window.game_state_controller.get_counter("tally", 0) == 1
    assert twin in arena.sprites()


def test_reentry_reload_and_a_loaded_save_give_one_listener_each(arena: Arena) -> None:
    one_each = dict.fromkeys(BUS_EVENTS, 1)
    assert scene_ops.reload_scene_from_disk(arena.window) is True  # Ctrl+R
    assert _listeners(arena) == one_each
    arena.save("before")
    for sprite in _six(arena).values():
        sprite.kill()
    arena.enter()  # re-entry: what was removed stays removed (room memory), nothing listens for it
    assert _listeners(arena) == dict.fromkeys(BUS_EVENTS, 0)
    assert arena.load("before")
    assert _listeners(arena) == one_each
    sprites = _six(arena)
    _send_all(arena)
    assert _observed(arena, sprites) == {"door locked": False, "chest enabled": True, "tally": 1, "pings": 1,
                                         "zone messages": 1, "shop open": True}


def _rusted_key() -> dict[str, Any]:
    scene = json.loads((REPO / "packs/core_regions/scenes/Ridge Outpost_interior.json").read_text(encoding="utf-8"))
    return next(e for e in scene["entities"] if e.get("id") == "ridge_outpost_interior_rusted_key_450_300_0_0")


def test_the_ridge_outpost_rusted_key_still_sets_its_flag(arena: Arena) -> None:
    """The shipped key emits ``collected`` and removes itself in one call: its SetGameStateOnEvent hears it on the bus
    before the removal ends the subscription. Its QuestProgressOnEvent waits for the next frame and so never hears it
    (#638 NEW-3, by design; the quest's own ``complete_on`` completes that stage from the same event)."""
    arena.write_room({**hero(), "x": 450, "y": 300}, _rusted_key())
    arena.enter()
    key = next(s for s in arena.sprites() if s.mesh_name == "RustedKey")
    quest_step = _behaviour(key, "QuestProgressOnEvent")
    heard: list[str] = []
    original = quest_step.on_event
    quest_step.on_event = lambda event: (heard.append(event.type), original(event))[1]
    window = arena.window
    listening = sum(len(v) for v in window.event_bus._subscribers.values())

    _behaviour(key, "PickupCollectible").on_interact(window, arena.by_id("hero"))

    assert window.get_flag("demo_ridge_found_key", False) is True
    assert key not in arena.sprites()
    assert sum(len(v) for v in window.event_bus._subscribers.values()) == listening - 1  # its SetGameStateOnEvent
    window.on_update(1 / 60)
    assert heard == []


def test_an_event_logger_logs_in_a_live_game_until_removed(arena: Arena, capsys: pytest.CaptureFixture[str]) -> None:
    """#638 NEW-4: it subscribed in an ``on_added`` nothing calls, so it logged nothing."""
    bus = arena.window.event_bus
    wildcard = len(bus._wildcard_subscribers)
    named = arena.spawn({"id": "bell", "name": "Bell", "x": 300, "y": 60, "sprite": PIC, "behaviours": ["EventLogger"],
                         "behaviour_config": {"EventLogger": {"events": "bell_rung"}}})
    everything = arena.spawn({"id": "ear", "name": "Ear", "x": 330, "y": 60, "sprite": PIC,
                              "behaviours": ["EventLogger"]})
    assert len(bus._wildcard_subscribers) == wildcard + 1
    capsys.readouterr()
    bus.emit("bell_rung", times=2)
    out = capsys.readouterr().out
    assert out.count("[Mesh][EventLogger] Received 'bell_rung'") == 2  # the named and the '*' logger, once each
    named.kill()
    everything.kill()
    assert len(bus._wildcard_subscribers) == wildcard
    bus.emit("bell_rung")
    assert "[Mesh][EventLogger]" not in capsys.readouterr().out
