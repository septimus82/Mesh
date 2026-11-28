"""S1-0 part B section 2: Studio's "Button" + "Locked until an event" puzzle, through the real runtime.

Studio's Interaction picker offers SwitchInteract ("Button": Event it sends, Only once, Picture once used) and DoorLock
("Locked until an event": Opens on event, Starts locked, Picture when open), and its inspector can make the door solid
(project_ops.set_solid). The shipped core_regions chapters use exactly this pair (e.g. Act1_Chapter2_Ambush:
Ch2AmbushSwitch -> Ch2AmbushDoor, solid, sprite door_locked.png).

Real hidden GameWindow, real scene loader, real interaction path (engine.interaction.perform_interaction, what the
interact key calls) and the real collision mover (scene_controller.move_entity_with_collision).

Checked:
 1. the button press unlocks the door (DoorLock.locked -> False, door_unlocked emitted);
 2. the unlocked door still BLOCKS the player: DoorLock._update_collision only writes entity.properties["solid"],
    which nothing reads; solidity is membership of scene_controller.solid_sprites. "Picture when open" (open_sprite)
    and the button's "Picture once used" (active_sprite) are never applied (no code swaps the texture);
 3. leaving and re-entering, and saving after the unlock then loading: the door is locked again and the "Only once"
    button can be pressed again (both keep their state only on the behaviour instance; neither is saved).

Exits 1 when the unlocked door still blocks (2) or the state is lost (3).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hidden_game import HERO, PICTURE, behaviour, hidden_game, scene, sprite_named  # noqa: E402

BUTTON = {"id": "button", "name": "Button", "x": 100, "y": 130, "sprite": PICTURE, "behaviours": ["SwitchInteract"],
          "behaviour_config": {"SwitchInteract": {"event_id": "gate_open", "one_shot": True,
                                                  "active_sprite": "assets/door_open.png"}}}
GATE = {"id": "gate", "name": "Gate", "x": 200, "y": 100, "sprite": PICTURE, "solid": True, "tag": "solid",
        "behaviours": ["DoorLock"],
        "behaviour_config": {"DoorLock": {"unlock_event": "gate_open", "starts_locked": True,
                                          "open_sprite": "assets/door_open.png"}}}
defects = []

with hidden_game({"yard": scene("Yard", HERO, BUTTON, GATE), "shed": scene("Shed", HERO)}) as (window, paths, _tmp):
    from engine.interaction import perform_interaction

    sc = window.scene_controller
    unlocked_events: list[str] = []
    window.event_bus.subscribe("door_unlocked", lambda e: unlocked_events.append(e.type))
    hero = sc._find_player_sprite()
    gate_sprite = sprite_named(window, "Gate")
    door = behaviour(gate_sprite, "DoorLock")
    texture_before = gate_sprite.texture
    print("gate is solid at load:", gate_sprite in sc.solid_sprites, "| locked:", door.locked)

    handled = perform_interaction(window, actor=hero)  # the interact key, next to the button
    print("button pressed (interaction handled):", handled, "| door locked:", door.locked,
          "| door_unlocked events:", len(unlocked_events))

    start_x = hero.center_x
    for _ in range(40):
        sc.move_entity_with_collision(hero, 4.0, 0.0)
    passed = hero.left > gate_sprite.right
    print(f"walked right from x={start_x:.0f} to x={hero.center_x:.0f}; gate spans x={gate_sprite.left:.0f}.."
          f"{gate_sprite.right:.0f} | passed through the unlocked gate: {passed} | gate still in solid_sprites: "
          f"{gate_sprite in sc.solid_sprites} | properties['solid']: {getattr(gate_sprite, 'properties', {}).get('solid')}")
    print("open picture applied:", gate_sprite.texture is not texture_before)
    if not door.locked and not passed:
        defects.append("the unlocked door still blocks the player")

    hero.center_x = start_x
    assert window.save_manager.save_game("after_unlock")
    sc.load_scene(paths["shed"])
    sc.load_scene(paths["yard"])
    door2 = behaviour(sprite_named(window, "Gate"), "DoorLock")
    button2 = behaviour(sprite_named(window, "Button"), "SwitchInteract")
    hero = sc._find_player_sprite()
    print("after leaving and re-entering: door locked:", door2.locked, "| 'Only once' button usable again:",
          button2.can_interact_with(hero))
    reentry_lost = door2.locked or button2.can_interact_with(hero)

    assert window.save_manager.load_game("after_unlock")
    sc.update(1 / 60)  # (a load is applied on the next frame's scene update)
    door3 = behaviour(sprite_named(window, "Gate"), "DoorLock")
    button3 = behaviour(sprite_named(window, "Button"), "SwitchInteract")
    print("after loading a save made after the unlock: door locked:", door3.locked, "| button usable again:",
          button3.can_interact_with(sc._find_player_sprite()))
    if reentry_lost or door3.locked:
        defects.append("the unlock and the 'Only once' press are forgotten on re-entry and on load")

if defects:
    print("DEFECT REPRODUCED:", "; ".join(defects))
    sys.exit(1)
print("not reproduced")
