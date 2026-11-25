"""S1-0 part B section 3: how events reach behaviours (real hidden GameWindow; a probe, it documents behaviour).

The engine has two delivery paths for one MeshEventBus emit:
  * bus subscribers (event_bus.subscribe: DoorLock, RewardChest, SetGameStateOnEvent, Vendor, ...) run synchronously
    inside emit();
  * on_event behaviours (EmitEventOnEvent, QuestHook, QuestProgressOnEvent, Dialogue, ...) and the quest manager
    (GameStateController.handle_event) get the event from a queue (a wildcard subscriber appends to
    window._mesh_event_queue) on the NEXT on_update, after the scene update that applies a pending room change.

Measured here:
  1. latency: an on_event chain ping -> pong -> pang takes one frame per hop;
  2. room transfer: an event emitted in the same frame as a door's queue_scene_change is delivered to the NEW room's
     on_event behaviours (or dropped), not the room it happened in;
  3. load: the queue across save_manager.load_game.

Always exits 0 unless the probe itself fails; the findings are the printed lines.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hidden_game import HERO, PICTURE, hidden_game, scene  # noqa: E402


def relay(name: str, listen: str, emit: str) -> dict:
    return {"id": name.lower(), "name": name, "x": 300, "y": 300, "sprite": PICTURE,
            "behaviours": ["EmitEventOnEvent"],
            "behaviour_config": {"EmitEventOnEvent": {"listen_event": listen, "emit_event": emit}}}


rooms = {
    "yard": scene("Yard", HERO, relay("R1", "ping", "pong"), relay("R2", "pong", "pang"),
                  relay("YardEar", "knock", "heard_in_yard")),
    "shed": scene("Shed", HERO, relay("ShedEar", "knock", "heard_in_shed")),
}

with hidden_game(rooms) as (window, paths, _tmp):
    sc = window.scene_controller
    seen: list[str] = []
    window.event_bus.subscribe_all(lambda e: seen.append(e.type))

    window.event_bus.emit("ping")
    timeline = [list(seen)]
    for _ in range(3):
        window.on_update(1 / 60)
        timeline.append(list(seen))
    print("1) bus events seen after emit / after frame 1 / 2 / 3:", timeline)

    seen.clear()
    window.event_bus.emit("knock")  # e.g. the event of the interaction that opened the door
    sc.queue_scene_change(paths["shed"])  # the door, same frame
    for _ in range(90):
        window.on_update(1 / 60)
        if Path(str(sc.current_scene_path)).stem == "shed" and len(seen) > 1:
            break
    print("2) now in:", Path(str(sc.current_scene_path)).stem, "| events after the transition:", seen)

    sc.load_scene(paths["yard"])
    assert window.save_manager.save_game("probe")
    seen.clear()
    window.event_bus.emit("knock")
    assert window.save_manager.load_game("probe")
    for _ in range(3):
        window.on_update(1 / 60)
    print("3) knock emitted just before load_game; events after the load:", seen)
