"""S1-0 part B section 2: picker behaviours driven through the real runtime (smoke matrix rows).

Real hidden GameWindow, real scene loader, real per-frame update (window.on_update) and the real interaction path
(engine.interaction.perform_interaction). One small room per row; the player starts next to the object.

Rows:
  zone     TriggerZone ("React when someone comes near"; Studio labels on_trigger "Event it sends"):
           does the configured event fire? (It is only printed; the behaviour always sends "entered_zone", and sends
           that twice: once through emit_gameplay_event, once through window.emit_signal.)
  lever    ToggleSwitch ("Lever or switch"): does pressing E flip it and send switch_toggled?
  door     SceneTransition with allow_interact (what Studio's doors are): does E take the player to the other room?
  timer    Timer ("Timer"): does it send its event after its duration?
  counter  IncrementCounterOnEvent: does an event add to the counter?

Exits 1 when the zone's configured event never fires (the confirmed defect); other rows are reported.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hidden_game import HERO, PICTURE, behaviour, hidden_game, scene, sprite_named  # noqa: E402


def obj(name: str, beh: str, cfg: dict, x: float = 110, y: float = 100) -> dict:
    return {"id": name.lower(), "name": name, "x": x, "y": y, "sprite": PICTURE, "behaviours": [beh],
            "behaviour_config": {beh: cfg}}


rooms = {
    "zone": scene("Zone", HERO, obj("Zone", "TriggerZone", {"trigger_radius": 60, "trigger_target": "Hero",
                                                            "on_trigger": "open_gate"})),
    "lever": scene("Lever", HERO, obj("Lever", "ToggleSwitch", {"label": "Lever"})),
    "door": scene("Door", HERO),  # filled in below (needs the target path)
    "shed": scene("Shed", HERO),
    "timer": scene("Timer", HERO, obj("Clock", "Timer", {"duration": 0.05, "timer_event": "ding"}, x=300)),
    "counter": scene("Counter", HERO, obj("Tally", "IncrementCounterOnEvent", {"event_type": "ping",
                                                                                "counter": "pings"}, x=300)),
}
results: dict[str, str] = {}
zone_ok = True

with hidden_game(rooms) as (window, paths, _tmp):
    import json

    from engine.interaction import perform_interaction

    sc = window.scene_controller
    seen: dict[str, int] = {}
    window.event_bus.subscribe_all(lambda e: seen.__setitem__(e.type, seen.get(e.type, 0) + 1))

    def enter(name: str) -> None:
        sc.load_scene(paths[name])
        seen.clear()

    def frames(n: int = 3) -> None:
        for _ in range(n):
            window.on_update(1 / 60)

    enter("zone")
    frames()
    results["zone"] = (f"configured event 'open_gate' fired {seen.get('open_gate', 0)}x | 'entered_zone' delivered "
                       f"{seen.get('entered_zone', 0)}x for one entry")
    zone_ok = seen.get("open_gate", 0) > 0

    enter("lever")
    lever = behaviour(sprite_named(window, "Lever"), "ToggleSwitch")
    try:
        handled = perform_interaction(window, actor=sc._find_player_sprite())
        results["lever"] = f"handled={handled} state={lever.state} switch_toggled={seen.get('switch_toggled', 0)}"
    except Exception as exc:  # noqa: BLE001
        results["lever"] = f"raised {type(exc).__name__}: {exc}"

    door_doc = scene("Door", HERO, obj("Exit", "SceneTransition", {"target_scene": paths["shed"],
                                                                   "allow_interact": True}))
    Path(paths["door"]).write_text(json.dumps(door_doc), encoding="utf-8")
    enter("door")
    handled = perform_interaction(window, actor=sc._find_player_sprite())
    frames(90)  # a fade, then the change
    results["door"] = f"handled={handled} now in: {Path(str(sc.current_scene_path)).stem}"

    enter("timer")
    frames(10)
    results["timer"] = f"'ding' after 10 frames: {seen.get('ding', 0)}x"

    enter("counter")
    window.event_bus.emit("ping")
    results["counter"] = f"pings counter after one ping: {window.game_state_controller.get_counter('pings', 0)}"

for row, outcome in results.items():
    print(f"{row:8} {outcome}")
if not zone_ok:
    print("DEFECT REPRODUCED: TriggerZone never sends the event the creator chose ('Event it sends')")
    sys.exit(1)
print("not reproduced")
