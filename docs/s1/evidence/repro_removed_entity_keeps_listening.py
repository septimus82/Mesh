"""S1-0 evidence: an entity removed during play keeps handling events until the room is left.

Real hidden GameWindow, real scene loader, real removal path: ``sprite.remove_from_sprite_lists()`` (what death,
pickups, projectiles and DamageOnTouch call; it reaches entity_factory._end_behaviours, the same funnel the editor
and authoring deletes use). _end_behaviours calls each behaviour's ``on_destroy`` only. DoorLock, RewardChest,
SetGameStateOnEvent and IncrementCounterOnEvent end their event-bus subscription in ``destroy()``, MessageOnZoneEnter
in ``dispose()``, and Vendor never: nothing in the runtime calls those, so their listeners outlive the entity.

Then checked: leaving and re-entering the room, and loading a save, end the stale listeners (the scene's
subscription record), so the leak is bounded by the room visit and does not multiply.

Exit 1 when the defect is present. Run: PYTHONPATH=<checkout> py -3.13 docs/s1/evidence/repro_removed_entity_keeps_listening.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hidden_game import HERO, PICTURE, behaviour, hidden_game, scene, sprite_named  # noqa: E402


def entity(name: str, x: int, behaviour_name: str, config: dict) -> dict:
    return {"id": name.lower(), "name": name, "x": x, "y": 160, "sprite": PICTURE, "behaviours": [behaviour_name],
            "behaviour_config": {behaviour_name: config}}


ENTITIES = [
    entity("Door", 140, "DoorLock", {"unlock_event": "lever_pulled"}),
    entity("Tally", 170, "SetGameStateOnEvent", {"event_type": "ping", "inc_counters": {"tally": 1}}),
    entity("Pinger", 200, "IncrementCounterOnEvent", {"event_type": "ping", "counter": "pings"}),
    entity("Chest", 230, "RewardChest", {"unlock_event": "vault_open", "gold": 5}),
    entity("Shop", 260, "Vendor", {"listen_event": "open_shop_evidence"}),
    entity("Greeter", 290, "MessageOnZoneEnter", {"zone_name": "gate"}),
]
EVENTS = ["lever_pulled", "ping", "vault_open", "open_shop_evidence", "entered_zone"]

with hidden_game({"yard": scene("Yard", HERO, *ENTITIES), "shed": scene("Shed", HERO)}) as (window, paths, _tmp):
    bus, gs, sc = window.event_bus, window.game_state_controller, window.scene_controller
    unlocked: list[str] = []
    bus.subscribe("door_unlocked", lambda e: unlocked.append(e.type))  # (a window-level listener, kept on purpose)

    def listeners() -> dict[str, int]:
        return {name: len(bus._subscribers.get(name, [])) for name in EVENTS}

    def counters() -> str:
        return f"tally={gs.get_counter('tally', 0):g} pings={gs.get_counter('pings', 0):g}"

    baseline = listeners()
    print("listeners with the room loaded:        ", baseline)
    bus.emit("ping")
    print("one ping while all are present:         ", counters())

    assert window.save_manager.save_game("before_removal")
    door = behaviour(sprite_named(window, "Door"), "DoorLock")
    for name in ("Door", "Tally", "Pinger", "Chest", "Shop", "Greeter"):
        sprite_named(window, name).remove_from_sprite_lists()  # killed / collected / deleted
    still_there = {s.mesh_name for s in sc.all_sprites}
    print("present after removal:                  ", sorted(still_there))
    after_removal = listeners()
    print("listeners after removing all six:       ", after_removal)

    bus.emit("ping")
    bus.emit("lever_pulled")
    print("ping + lever after removal:             ", counters(),
          f"| removed door unlocked={not door.locked} door_unlocked events={len(unlocked)}")
    stale = (gs.get_counter("tally", 0) > 1 or gs.get_counter("pings", 0) > 1 or bool(unlocked)
             or any(after_removal[k] for k in EVENTS))

    sc.load_scene(paths["shed"])
    print("listeners after leaving for the Shed:   ", listeners())
    sc.load_scene(paths["yard"])
    print("listeners after re-entering the Yard:   ", listeners(),
          "| removed ones stay removed (room memory):", sorted(s.mesh_name for s in sc.all_sprites))

    assert window.save_manager.load_game("before_removal")  # all six are back, with fresh behaviours
    sc.update(1 / 60)  # (a load is applied on the next frame's scene update)
    loaded = listeners()
    print("listeners after loading the save made before removal:", loaded, "| same as first visit:", loaded == baseline)
    before = gs.get_counter("tally", 0)
    bus.emit("ping")
    print("one ping after the load adds exactly one:", gs.get_counter("tally", 0) - before == 1)
    sc.load_scene(paths["shed"])
    sc.load_scene(paths["yard"])
    print("listeners after a further exit + re-entry:", listeners(), "| same as first visit:", listeners() == baseline)

print("DEFECT REPRODUCED: removed entities still react to their events" if stale else "not reproduced")
sys.exit(1 if stale else 0)
