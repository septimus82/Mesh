"""S1 5.6 (a) (E8 contract 2): every behaviour that subscribes to the event bus lets go when its entity goes.

#637 was one instance: behaviours released their subscriptions only in a ``destroy()``/``dispose()`` nothing called,
so a removed door still unlocked and a removed counter still counted. Here every subscribing behaviour, found by
reading ``engine/behaviours`` (any class that calls ``subscribe``/``subscribe_all``), is built in one room of a real
hidden game (tests/_real_game.py) and then removed by each way the game removes an entity. After each removal the
bus has exactly the listeners it had before the room was entered, and the events they heard change nothing.

A new subscribing behaviour fails ``test_every_subscribing_behaviour_is_in_the_contract`` until it is added to
``SUBSCRIBERS`` (with the settings that make it subscribe) or to ``NOT_ON_THE_GAME_BUS`` with the reason.
"""
from __future__ import annotations

import ast
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from tests._real_game import PIC, RealGame, new_project, real_game

pytestmark = [pytest.mark.integration,  # (a generated project in a temporary folder; one hidden game window)
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

REPO = Path(__file__).resolve().parent.parent
WILDCARD = "*"
# behaviour -> (the settings that make it subscribe, the events it then listens to on the game's bus)
SUBSCRIBERS: dict[str, tuple[dict[str, Any], tuple[str, ...]]] = {
    "CutsceneTrigger": ({"listen_event": "cue", "cutscene_id": "none"}, ("cue",)),
    "DoorLock": ({"unlock_event": "lever_pulled"}, ("lever_pulled",)),
    "DropTable": ({"drops": [{"gold": 1}]}, ("died",)),
    "EventLogger": ({"events": "bell_rung"}, ("bell_rung",)),
    "GrantExperience": ({"xp": 1}, ("died",)),
    "IncrementCounterOnEvent": ({"event_type": "count_me", "counter": "pings"}, ("count_me",)),
    "MessageOnZoneEnter": ({"zone_name": "gate"}, ("entered_zone",)),
    "QuestGiver": ({"quest_id": "errand", "listen_event": "ask"}, ("ask",)),
    "RewardChest": ({"unlock_event": "vault_open", "gold": 5}, ("vault_open",)),
    "SceneExit": ({"listen_event": "leave_now", "target_scene": "nowhere"}, ("leave_now",)),
    "SetGameStateOnEvent": ({"event_type": "ping", "inc_counters": {"tally": 1}}, ("ping",)),
    "ToggleSceneLights": ({"listen_event": "lights_out", "mode": "off"}, ("lights_out",)),
}
# An EventLogger with no events named listens to everything (subscribe_all): a second entity.
WILDCARD_LOGGER = ("EventLogger", {}, (WILDCARD,))
NOT_ON_THE_GAME_BUS: dict[str, str] = {
    "QuestHook": "subscribes only to the episode harness's gameplay_event_bus, which a game window doesn't have; in a "
                 "game it hears events through on_event (the frame's delivery to the room's sprites), which ends with "
                 "the sprite",
}
# Every entity can also be removed by a hit (Health) and by being picked up (PickupCollectible).
REMOVABLE = {"Health": {"max_hp": 5, "hp": 5}, "PickupCollectible": {"collector_tag": "player"}}


def _entity(eid: str, behaviour: str, config: dict[str, Any], x: float) -> dict[str, Any]:
    behaviours = {behaviour: config, **REMOVABLE}
    return {"id": eid, "name": eid, "x": x, "y": 160 + 24 * (len(eid) % 4), "sprite": PIC, "layer": "entities",
            "behaviours": list(behaviours), "behaviour_config": behaviours}


def _entities() -> dict[str, tuple[str, tuple[str, ...]]]:
    """entity id -> (behaviour, its events)."""
    out = {name.lower(): (name, events) for name, (_cfg, events) in SUBSCRIBERS.items()}
    out["wildcard_logger"] = (WILDCARD_LOGGER[0], WILDCARD_LOGGER[2])
    return out


def _subscribing_classes() -> set[str]:
    """Names of the classes in engine/behaviours that call ``subscribe``/``subscribe_all`` on something."""
    found = set()
    for path in sorted((REPO / "engine" / "behaviours").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
            if any(isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                   and c.func.attr in ("subscribe", "subscribe_all") for c in ast.walk(cls)):
                found.add(cls.name)
    return found


def test_every_subscribing_behaviour_is_in_the_contract() -> None:
    from engine.behaviours import load_builtin_behaviours, registry

    load_builtin_behaviours()
    classes = _subscribing_classes()
    subscribing = {name for name, cls in registry.BEHAVIOUR_REGISTRY.items()
                   if any(base.__name__ in classes for base in getattr(cls, "__mro__", ()))}
    assert subscribing, "the scan found no subscriber at all: it is broken"
    assert not set(SUBSCRIBERS) & set(NOT_ON_THE_GAME_BUS)
    assert sorted(subscribing - set(SUBSCRIBERS) - set(NOT_ON_THE_GAME_BUS)) == [], \
        "a behaviour that subscribes is in neither SUBSCRIBERS nor NOT_ON_THE_GAME_BUS"
    assert sorted((set(SUBSCRIBERS) | set(NOT_ON_THE_GAME_BUS)) - subscribing) == []


# ---------------------------------------------------------------------------------------------------- the game
@pytest.fixture(scope="module")
def running(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RealGame]:
    base = tmp_path_factory.mktemp("removal")
    project = new_project(base / "game")
    made = [_entity(eid, behaviour, SUBSCRIBERS[behaviour][0] if eid != "wildcard_logger" else WILDCARD_LOGGER[1],
                    80 + 36 * i)
            for i, (eid, (behaviour, _events)) in enumerate(_entities().items())]
    # (written into the room document: #704 keeps Studio's add_behaviour from adding ToggleSceneLights)
    # One room per removal path (room memory keeps a removed entity removed, so each path needs a room of its own).
    for label in ROOMS:
        project.edit_scene(lambda scene: {**scene, "entities": [*scene.get("entities", []), *made]},
                           project.add_room(label))
    project.save()
    launch = base / "elsewhere"
    launch.mkdir()
    with real_game(project, launch) as started:
        yield started


@pytest.fixture()
def game(running: RealGame) -> RealGame:
    return running.resume()  # (one window for the module; its project pins put back for each test)


def _listeners(g: RealGame) -> dict[str, int]:
    bus = g.window.event_bus
    events = {e for _b, evs in _entities().values() for e in evs if e != WILDCARD}
    counts = {event: len(bus._subscribers.get(event, [])) for event in sorted(events)}
    counts[WILDCARD] = len(bus._wildcard_subscribers)
    return counts


def _ours(g: RealGame) -> dict[str, Any]:
    return {eid: g.named(eid) for eid in _entities()}


def _enter_with_baseline(g: RealGame, room: str) -> dict[str, int]:
    g.enter(g.room("Hall"))
    baseline = _listeners(g)
    g.enter(g.room(room))
    return baseline


def _what_they_did(g: RealGame) -> dict[str, Any]:
    gs, window = g.gs, g.window
    return {"tally": gs.get_counter("tally", 0), "pings": gs.get_counter("pings", 0), "gold": gs.get_counter("gold", 0),
            "xp": gs.get_xp(), "quest": window.quest_manager.is_quest_active("errand"), "room": str(g.sc.room_path),
            "cutscene": bool(window.cutscene_controller.is_running)}


def _send_everything(g: RealGame) -> None:
    bus = g.window.event_bus
    for event in ("lever_pulled", "vault_open", "ping", "count_me", "ask", "cue", "lights_out", "bell_rung",
                  "leave_now"):
        bus.emit(event)
    bus.emit("entered_zone", zone="gate", actor="Player")
    g.frames(2)


@pytest.mark.parametrize("eid", sorted(_entities()))
def test_each_subscriber_listens_while_present(game: RealGame, eid: str) -> None:
    """The control: built in the room, each one holds its subscriptions (so the removal checks below mean
    something)."""
    baseline = _enter_with_baseline(game, "control")
    sprite = game.named(eid)
    assert sprite is not None and sprite.mesh_behaviour_unsubscribes, f"{eid} made no subscription"
    behaviour, events = _entities()[eid]
    now = _listeners(game)
    for event in events:
        assert now[event] > baseline[event], f"{behaviour} isn't listening to {event!r}"


# ---- the ways the game removes an entity -----------------------------------------------------------------------
def _kill(g: RealGame, sprite: Any) -> None:
    sprite.kill()


def _death(g: RealGame, sprite: Any) -> None:
    g.behaviour(sprite.mesh_name, "Health").apply_damage(999)


def _pickup(g: RealGame, sprite: Any) -> None:
    g.behaviour(sprite.mesh_name, "PickupCollectible").on_interact(g.window, g.player())


def _despawn(g: RealGame, sprite: Any) -> None:
    store = g.sc.entities  # (what mesh_net's scene client does with an avatar or a drop that has gone)
    store.enqueue_despawn(sprite)
    store.apply_pending_ops(g.sc)


def _editor(g: RealGame, sprite: Any) -> None:
    from engine.editor.editor_entity_ops_controller import EditorEntityOpsController

    editor = SimpleNamespace(window=SimpleNamespace(scene_controller=g.sc), selected_entity=None)
    EditorEntityOpsController(editor).delete_entity_internal(sprite)  # type: ignore[arg-type]


def _authoring(g: RealGame, sprite: Any) -> None:
    from engine.scene_runtime.authoring.entity_ops_parts.delete_ops import debug_remove_entity_by_id
    from engine.scene_runtime.index_build import build_scene_index_from_sprites

    g.sc._scene_index = build_scene_index_from_sprites(g.sc.all_sprites)
    assert debug_remove_entity_by_id(g.sc, sprite.mesh_entity_data["id"])


PATHS: dict[str, Callable[[RealGame, Any], None]] = {"kill": _kill, "death": _death, "pickup": _pickup,
                                                     "despawn": _despawn, "editor": _editor, "authoring": _authoring}
LEAVING = "leaving the room"
ROOMS = ["control", *PATHS, LEAVING]


@pytest.mark.parametrize("path", [*PATHS, LEAVING])
def test_a_removed_subscriber_lets_go_and_hears_nothing(game: RealGame, path: str) -> None:
    baseline = _enter_with_baseline(game, path)
    ours = _ours(game)
    assert all(ours.values())
    if path == LEAVING:
        game.enter(game.room("Hall"))
    else:
        for sprite in ours.values():
            PATHS[path](game, sprite)
        assert not [eid for eid in _entities() if game.named(eid) is not None], "something wasn't removed"
        assert all(not s.mesh_behaviour_unsubscribes for s in ours.values()), "a removed entity kept its releases"
    assert _listeners(game) == baseline, "a removed entity is still listening"
    before = _what_they_did(game)
    _send_everything(game)
    assert _what_they_did(game) == before, "a removed entity still reacted"
    assert all(g is None or g not in game.sc.all_sprites for g in ours.values())

