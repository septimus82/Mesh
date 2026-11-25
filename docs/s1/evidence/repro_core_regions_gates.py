"""S1-0 part D: are the shipped core_regions chapters with a switch-gated door impassable (#639)?

    py -3.13 docs/s1/evidence/repro_core_regions_gates.py        (PYTHONPATH = this checkout)

Real hidden, muted, never-activated GameWindow (docs/s1/evidence/_hidden_game.py), the shipped scene files loaded from
this checkout by their own paths, the game's own key input and update loop (on_key_press / on_update dispatched to the
window, as pyglet's loop does). The player is made invulnerable (only so the raiders can't end the walk; nothing else
is changed).

1. Act1_Chapter2_Ambush end to end: walk to Ch2AmbushSwitch, press E, then walk east along the lane through
   Ch2AmbushDoor to ToRuinedGateFromAmbush (920, 300): does the next room load?
2. If the straight walk is blocked: walk around the gate (up, east, down), with the gate still there.
3. Every other shipped scene with a solid DoorLock (static list below): from beside the door on the player's side,
   (a) straight through while LOCKED, (b) around it while locked, (c) straight through after its unlock event.

Also: the Ambush exit (ToRuinedGateFromAmbush, require_flags act1_ch2_ambush_cleared) after the clear zone sets that
flag; if it is absent, the workaround (leave by the way in, come back) is walked.

Exits 1 when an unlocked gate still blocks the straight way (#639), a locked gate can be walked round (the puzzle is
skippable), or the Ambush exit does not appear when its flag is set. Prints whether the Ambush is impassable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hidden_game import HERO, REPO, hidden_game, scene  # noqa: E402

SCENES = sorted(p.relative_to(REPO).as_posix() for p in (REPO / "packs").rglob("*.json")
                if p.parent.name == "scenes" and '"DoorLock"' in p.read_text(encoding="utf-8", errors="ignore"))
AMBUSH = "packs/core_regions/scenes/Act1_Chapter2_Ambush.json"


def main() -> int:
    defects: list[str] = []
    with hidden_game({"blank": scene("Blank", HERO)}) as (window, _paths, _tmp):
        import engine.optional_arcade as optional_arcade

        K = optional_arcade.arcade.key
        sc = window.scene_controller
        window._allow_dispatch_event = True
        held: set[int] = set()

        def step(n: int = 1) -> None:
            for _ in range(n):
                window.dispatch_event("on_update", 1 / 60)

        def hold(keys: set[int]) -> None:
            for k in held - keys:
                window.dispatch_event("on_key_release", k, 0)
            for k in keys - held:
                window.dispatch_event("on_key_press", k, 0)
            held.clear()
            held.update(keys)

        def hero():
            return sc._find_player_sprite()

        def room() -> str:
            return Path(str(sc.current_scene_path or "")).name

        def walk_to(x: float, y: float, tol: float = 8, frames: int = 900) -> str:
            start, last, still = room(), None, 0
            for _ in range(frames):
                h = hero()
                if h is None or room() != start:
                    hold(set())
                    step(2)
                    return f"left the room -> {room()}"
                dx, dy = x - h.center_x, y - h.center_y
                if abs(dx) <= tol and abs(dy) <= tol:
                    hold(set())
                    return "arrived"
                keys = {k for k, on in ((K.RIGHT, dx > tol), (K.LEFT, dx < -tol), (K.UP, dy > tol),
                                        (K.DOWN, dy < -tol)) if on}
                hold(keys)
                step()
                pos = (round(h.center_x), round(h.center_y))
                still = still + 1 if pos == last else 0
                last = pos
                if still > 40:
                    hold(set())
                    return f"blocked at {pos}"
            hold(set())
            return "timeout"

        def enter(path: str):
            window.load_scene(path)
            window.main_menu_overlay.close()  # (a checkout boots into the project browser: closed, as Play does)
            step(3)
            h = hero()
            for b in getattr(h, "mesh_behaviours_runtime", []):
                if type(b).__name__ == "Health":
                    b.invulnerable = True
            return h

        def gate_of(name: str | None = None):
            for s in sc.all_sprites:
                for b in getattr(s, "mesh_behaviours_runtime", []):
                    if type(b).__name__ == "DoorLock" and (name is None or s.mesh_name == name):
                        return s, b
            return None, None

        # 1-2. Act 1 Chapter 2 Ambush, end to end.
        enter(AMBUSH)
        switch = next(s for s in sc.all_sprites if s.mesh_name == "Ch2AmbushSwitch")
        door, lock = gate_of("Ch2AmbushDoor")
        print(f"Ambush: player at {hero().position}, switch at {switch.position}, door at {door.position} "
              f"({door.width:.0f}x{door.height:.0f}, solid={door in sc.solid_sprites}, locked={lock.locked})")
        r = walk_to(switch.center_x - 36, switch.center_y)
        window.dispatch_event("on_key_press", K.E, 0)
        step()
        window.dispatch_event("on_key_release", K.E, 0)
        step(3)
        print(f"  walked to the switch: {r}; pressed E -> door locked: {lock.locked}")
        straight = walk_to(920, 300, frames=1500)
        print(f"  straight east along the lane to ToRuinedGateFromAmbush: {straight}")
        if not lock.locked and straight.startswith("blocked"):
            defects.append("Ambush: the unlocked gate blocks the lane (#639)")
            around = [walk_to(hero().center_x, door.top + 60), walk_to(door.right + 60, door.top + 60),
                      walk_to(900, 300, frames=1500)]
            print(f"  around the gate (up, east, back to the lane and on to the exit): {around}")
        window.dispatch_event("on_key_press", K.E, 0)  # the exit door is used with E (allow_interact)
        step()
        window.dispatch_event("on_key_release", K.E, 0)
        step(5)
        cleared = window.game_state_controller.get_flag("act1_ch2_ambush_cleared")
        exit_built = any(s.mesh_name == "ToRuinedGateFromAmbush" for s in sc.all_sprites)
        print(f"  pressed E where the exit should be: still in {room()} | act1_ch2_ambush_cleared={cleared} | "
              f"exit door built: {exit_built}")
        if cleared and not exit_built:
            defects.append("Ambush: the exit gated on act1_ch2_ambush_cleared stays absent after the flag is set in the "
                           "room (entity require_flags are applied only when the room is built)")

        def use_door_at(x: float, y: float) -> str:
            r = walk_to(x, y, frames=1500)
            window.dispatch_event("on_key_press", K.E, 0)
            step()
            window.dispatch_event("on_key_release", K.E, 0)
            step(5)
            return f"{r}, then E -> {room()}"

        if room() == "Act1_Chapter2_Ambush.json":  # leave by the way in (round the gate again) and come back
            back = [walk_to(door.right + 60, door.top + 60), walk_to(door.left - 60, door.top + 60),
                    use_door_at(60, 300)]
            print(f"  workaround: back round the gate to ReturnToChapter2Camp: {back}")
            if room() == "Act1_Chapter2_Camp.json":
                print(f"  from the Camp, ToChapter2Ambush: {use_door_at(720, 300)}")
                exit_now = any(s.mesh_name == "ToRuinedGateFromAmbush" for s in sc.all_sprites)
                door, lock = gate_of("Ch2AmbushDoor")
                print(f"  re-entered the Ambush: exit built now: {exit_now} | gate locked again: {lock.locked}")
                route = [walk_to(hero().center_x, door.top + 60), walk_to(door.right + 60, door.top + 60)]
                print(f"  round the gate once more and use the exit: {route} {use_door_at(900, 300)}")
        impassable = room() == "Act1_Chapter2_Ambush.json"
        print(f"  => Act1_Chapter2_Ambush impassable: {impassable} (now in {room()})")

        # 3. Every shipped scene with a DoorLock.
        print(f"\nshipped scenes with a DoorLock: {len(SCENES)}")
        for path in SCENES:
            h = enter(path)
            door, lock = gate_of()
            if door is None or h is None:
                print(f"  {path}: no player or no gate built")
                continue
            side = 1 if door.center_x >= h.center_x else -1
            near = (door.center_x - side * (door.width / 2 + 40), door.center_y)
            far = (door.center_x + side * (door.width / 2 + 40), door.center_y)
            solid = door in sc.solid_sprites
            walk_to(*near)
            locked_straight = walk_to(*far)
            walk_to(*near)
            locked_around = [walk_to(near[0], door.top + 50), walk_to(far[0], door.top + 50), walk_to(*far)][-1]
            walk_to(far[0], door.top + 50)
            walk_to(near[0], door.top + 50)
            walk_to(*near)
            window.emit_signal(lock.unlock_event)
            step(2)
            unlocked_straight = walk_to(*far)
            print(f"  {Path(path).name}: solid={solid} | locked: straight={locked_straight}, around={locked_around} | "
                  f"unlocked={not lock.locked}: straight={unlocked_straight}")
            if solid and not lock.locked and unlocked_straight.startswith("blocked"):
                defects.append(f"{Path(path).name}: unlocked gate still blocks (#639)")
            if solid and locked_around == "arrived":
                defects.append(f"{Path(path).name}: the locked gate can be walked round")
    if defects:
        print("\nDEFECTS:")
        for d in defects:
            print("  -", d)
        return 1
    print("no gate defects")
    return 0


if __name__ == "__main__":
    sys.exit(main())
