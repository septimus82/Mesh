"""S1 3.0 / 5.6 (E8 contracts 1 and 3): every behaviour Mesh Studio's picker offers does what it says in a real game,
and what it leaves behind is still there after leaving the room and after a save and a load.

``engine.behaviour_guide.GUIDES`` is the picker. Each row here:
1. authors the behaviour through Studio's operations (``engine.authoring.apply``: place, picture, the picker's
   behaviour, its settings) in a room of its own; quests and cutscenes are written through the MCP server's
   ``apply_ops``, as the AI writes them;
2. plays that room in one real hidden GameWindow (tests/_real_game.py: ``run_game(project_root=)`` from another
   folder), driven as a player would (keys, frames, the interact key) or as its trigger would (the event it waits
   for, the hour of the day, a flag the story sets);
3. asserts what the creator sees (the event sent, the flag, the item, the picture, the position, the room);
4. then leaves and comes back, and saves and loads, and asserts the row's persistence rule: ``KEPT`` (the outcome
   stays: a spent button, a looted chest, a defeated enemy) or ``AGAIN`` (a visit plays it afresh: it still works).

A behaviour that can't be checked this way has an entry in ``EXCLUDED`` with the reason. A new picker entry fails
``test_every_picker_behaviour_has_a_row_or_a_reasoned_exclusion`` until it gets one or the other.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.authoring import ChangeError
from engine.behaviour_guide import GUIDES
from tests._real_game import PIC, RealGame, author, batch, new_project, place, real_game

pytestmark = [pytest.mark.integration,  # (a generated project in a temporary folder; one hidden game window)
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

KEPT, AGAIN = "kept", "again"
X, Y = 320.0, 240.0  # (the middle of a new room: 20 x 15 tiles of floor inside a wall)
OTHER = "assets/sprites/starter_villager.png"
SHEET = "assets/sprites/starter_hero.png"  # (the template's hero sheet: 32 x 48 frames, four to a row)
ITEM = "healing_potion"


@dataclass(frozen=True)
class Row:
    objects: list[dict[str, Any]]
    play: Callable[[RealGame], None]  # drive it and assert the outcome
    rule: str = AGAIN
    kept: Callable[[RealGame], None] | None = None  # KEPT: what still shows after re-entry and after a load
    loaded: Callable[[RealGame], None] | None = None  # what a load shows, when it differs (a save keeps the moment)


def sheep(x: float) -> list[dict[str, Any]]:
    """A Sheep (tag ``sheep``) with health: what an attacker in a row goes for (the player is shared by every room)."""
    return place("Sheep", x, Y, ("Health", {"max_hp": 50}), tag="sheep")


# ---------------------------------------------------------------------------------------------------- helpers
def _at(g: RealGame, name: str, x: float, y: float) -> Any:
    sprite = g.named(name)
    sprite.center_x, sprite.center_y = x, y
    return sprite


def _distance(a: Any, b: Any) -> float:
    return math.hypot(a.center_x - b.center_x, a.center_y - b.center_y)


def _moves(name: str, frames: int = 40, least: float = 12.0) -> Callable[[RealGame], None]:
    def play(g: RealGame) -> None:
        sprite = g.named(name)
        start = (sprite.center_x, sprite.center_y)
        g.frames(frames)
        assert math.hypot(sprite.center_x - start[0], sprite.center_y - start[1]) >= least, f"{name} didn't move"
    return play


def _nears_player(name: str, frames: int = 40) -> Callable[[RealGame], None]:
    def play(g: RealGame) -> None:
        mover = _at(g, name, 480, 320)
        hero = g.player()
        hero.center_x, hero.center_y = 160, 160
        before = _distance(mover, hero)
        g.frames(frames)
        assert _distance(mover, hero) <= before - 20, f"{name} didn't come closer"
    return play


def _fires(event: str, drive: Callable[[RealGame], None]) -> Callable[[RealGame], None]:
    def play(g: RealGame) -> None:
        g.heard.clear()
        drive(g)
        assert g.events(event), f"no {event!r}"
    return play


def _quiet(event: str, frames: int) -> Callable[[RealGame], None]:
    def play(g: RealGame) -> None:
        g.heard.clear()
        g.frames(frames)
        assert not g.events(event), f"{event!r} again: the load should have kept the moment it was saved in"
    return play


def _emit(event: str, frames: int = 2) -> Callable[[RealGame], None]:
    def drive(g: RealGame) -> None:
        g.window.event_bus.emit(event)
        g.frames(frames)
    return drive


def _walk_in(name: str) -> Callable[[RealGame], None]:
    """From well outside ``name`` onto it."""
    def drive(g: RealGame) -> None:
        g.stand_by(name, dx=-160)
        g.frames(2)
        g.stand_by(name, dx=0)
        g.frames(3)
    return drive


def _flagged(flag: str) -> Callable[[RealGame], None]:
    def kept(g: RealGame) -> None:
        assert g.flag(flag)
    return kept


def _gone(name: str) -> Callable[[RealGame], None]:
    def kept(g: RealGame) -> None:
        assert g.named(name) is None, f"{name} is back"
    return kept


# ---------------------------------------------------------------------------------------------------- movement
def _schedule(g: RealGame) -> None:
    clock = g.window.day_night
    clock.set_hour(9)
    g.frames(2)
    npc = g.named("Baker")
    assert (npc.center_x, npc.center_y) == (400, 300), "at the bakery in the morning"
    clock.set_hour(21)
    g.frames(2)
    assert (npc.center_x, npc.center_y) == (200, 300), "at home in the evening"


def _flees(g: RealGame) -> None:
    mover = _at(g, "Deer", X, Y)
    hero = g.player()
    hero.center_x, hero.center_y = X - 60, Y
    g.frames(2)
    before = _distance(mover, hero)
    g.frames(40)
    assert _distance(mover, hero) >= before + 10, "it keeps its distance"


def _walks_to_spot(g: RealGame) -> None:
    mover = _at(g, "Courier", 200, 200)
    before = math.hypot(mover.center_x - 480, mover.center_y - 320)
    g.frames(40)
    assert math.hypot(mover.center_x - 480, mover.center_y - 320) <= before - 20


# ---------------------------------------------------------------------------------------------------- interaction
def _interactable(g: RealGame) -> None:
    g.frames(35)  # (its 0.5 s cooldown, which a save keeps, has passed)
    g.heard.clear()
    g.interact("Bell")
    assert g.events("bell_rung"), "pressing E beside it sends its event"


def _lever(g: RealGame) -> None:
    lever = g.behaviour("Lever", "ToggleSwitch")
    before = lever.state
    g.heard.clear()
    g.interact("Lever")
    assert lever.state is (not before) and [e["state"] for e in g.events("switch_toggled")] == [lever.state]


def _button(g: RealGame) -> None:
    g.interact("Button")
    assert g.events("button_pressed") and g.behaviour("Button", "SwitchInteract").activated
    assert g.named("Button").texture is g.window.assets.get_texture(OTHER), "its 'Picture once used'"


def _button_kept(g: RealGame) -> None:
    g.interact("Button")
    assert not g.events("button_pressed"), "'Only once': a spent button sends nothing"
    assert g.named("Button").texture is g.window.assets.get_texture(OTHER)


def _pickup(g: RealGame) -> None:
    before = g.items(ITEM)
    g.interact("Potion")
    assert g.named("Potion") is None and g.items(ITEM) == before + 1


def _pickup_kept(g: RealGame) -> None:
    assert g.named("Potion") is None and g.items(ITEM) >= 1


def _touched(g: RealGame) -> None:
    g.heard.clear()
    g.stand_by("Coin", dx=0)
    g.frames(3)
    assert g.events("collectible_picked") and g.named("Coin") is None


def _zone_once(g: RealGame) -> None:
    g.heard.clear()
    _walk_in("Shrine")(g)
    g.frames(10)
    assert len(g.events("zone_hit")) == 1, "its event, once"
    g.stand_by("Shrine", dx=-160)  # (and away again: the save that follows isn't made in the zone)


def _door(g: RealGame) -> None:
    door = g.named("Gate")
    assert door in g.sc.solid_sprites
    g.window.event_bus.emit("gate_open")
    g.frames(2)
    assert door not in g.sc.solid_sprites and not g.behaviour("Gate", "DoorLock").locked
    assert door.texture is g.window.assets.get_texture(OTHER), "its 'Picture when open'"


def _door_kept(g: RealGame) -> None:
    door = g.named("Gate")
    assert door not in g.sc.solid_sprites and not g.behaviour("Gate", "DoorLock").locked
    assert door.texture is g.window.assets.get_texture(OTHER)


def _chest(g: RealGame) -> None:
    gold = g.counter("gold")
    g.window.event_bus.emit("chest_open")
    g.frames(2)
    g.interact("Chest")
    assert g.counter("gold") == gold + 5 and g.behaviour("Chest", "RewardChest").looted


def _chest_kept(g: RealGame) -> None:
    gold = g.counter("gold")
    g.interact("Chest")
    assert g.counter("gold") == gold and g.behaviour("Chest", "RewardChest").looted, "looted: it pays once"


def _shop(g: RealGame) -> None:
    panel = g.window.ui_controller.shop_panel
    g.interact("Merchant")
    assert panel.visible and panel.vendor is g.behaviour("Merchant", "Vendor")
    g.key("ESCAPE")
    assert not panel.visible, "Esc closes the shop"


def _door_to_hall(g: RealGame) -> None:
    room = g.room("SceneTransition")
    g.interact("Exit")
    g.frames(3)
    assert str(g.sc.room_path) == g.path(g.room("Hall")), "it takes the player to the Hall"
    g.enter(room)


# ---------------------------------------------------------------------------------------------------- dialogue, events
def _talk(g: RealGame) -> None:
    box = g.window.ui_controller.dialogue_box
    g.interact("Sage")
    assert box.is_active() and box.get_current_entry()["text"] == "Hello, traveller."
    g.key("E")
    g.frames(2)
    assert not box.is_active()


def _talk_kept(g: RealGame) -> None:
    g.interact("Sage")
    assert not g.window.ui_controller.dialogue_box.is_active(), "'Only once': it has been had"


def _quest(g: RealGame) -> None:
    g.window.event_bus.emit("ask_for_help")
    g.frames(2)
    assert g.window.quest_manager.is_quest_active("find_bell"), "the quest log has it"


def _quest_kept(g: RealGame) -> None:
    assert g.window.quest_manager.is_quest_active("find_bell")


def _set_flag(g: RealGame) -> None:
    g.window.event_bus.emit("lamp_lit")
    g.frames(2)
    assert g.flag("lamp_flag")


def _cutscene(g: RealGame) -> None:
    before = g.counter("intro_seen")
    g.window.event_bus.emit("play_intro")
    g.frames(10)
    assert g.counter("intro_seen") == before + 1, "the cutscene ran its steps"


def _picture_flag(g: RealGame) -> None:
    sign = g.named("Banner")
    assert sign.texture is g.window.assets.get_texture(PIC)
    g.window.set_flag("festival", True)
    g.frames(2)
    assert sign.texture is g.window.assets.get_texture(OTHER)


def _picture_flag_kept(g: RealGame) -> None:
    assert g.named("Banner").texture is g.window.assets.get_texture(OTHER)


def _shown_by_flag(g: RealGame) -> None:
    ghost = g.named("Ghost")
    assert not ghost.visible
    g.window.set_flag("haunted", True)
    g.frames(2)
    assert ghost.visible


def _shown_by_flag_kept(g: RealGame) -> None:
    assert g.named("Ghost").visible


def _hours(g: RealGame) -> None:
    owl, clock = g.named("Owl"), g.window.day_night
    clock.set_hour(12)
    g.frames(2)
    assert not owl.visible, "not at noon"
    clock.set_hour(23)
    g.frames(2)
    assert owl.visible, "at night"


def _particles(g: RealGame) -> None:
    g.frames(2)
    system = g.window.particle_manager.system
    assert system.count_alive(g.named("Chimney").mesh_id) > 0


def _animates(g: RealGame) -> None:
    flag = g.named("Flag")
    seen = set()
    for _ in range(30):
        g.frames(1)
        seen.add(id(flag.texture))
    assert len(seen) > 1, "its frames play"


def _walk_animation(g: RealGame) -> None:
    walker = g.named("Strider")
    g.frames(20)
    assert walker.mesh_animator.current_state == "walk", "walking shows the walk frames"


def _carried_light(g: RealGame) -> None:
    g.frames(2)
    assert g.behaviour("Lantern", "LightSource")._light_handle is not None


def _room_lights(g: RealGame) -> None:
    lights = g.sc._loaded_scene_data["lights"]
    assert lights[0].get("enabled", True)
    g.window.event_bus.emit("lights_out")
    g.frames(2)
    assert lights[0]["enabled"] is False


# ---------------------------------------------------------------------------------------------------- gameplay
def _hp(g: RealGame, name: str) -> float:
    return float(g.behaviour(name, "Health").hp)


def _health(g: RealGame) -> None:
    assert _hp(g, "Slime") == 3
    g.behaviour("Slime", "Health").apply_damage(1, source_entity="player")
    assert _hp(g, "Slime") == 2
    g.behaviour("Slime", "Health").apply_damage(5, source_entity="player")
    g.frames(3)
    assert g.named("Slime") is None, "defeated at zero"


def _hurts_sheep(g: RealGame, drive: Callable[[RealGame], None]) -> None:
    health = g.behaviour("Sheep", "Health")
    health.hp = health.max_hp
    drive(g)
    assert health.hp < health.max_hp, "the sheep was hurt"


def _brawl(g: RealGame) -> None:
    _at(g, "Sheep", g.named("Brawler").center_x + 32, Y)
    _hurts_sheep(g, lambda g: g.frames(90))


def _enemy(g: RealGame) -> None:
    wolf, flock = _at(g, "Wolf", 200, Y), _at(g, "Sheep", 420, Y)
    before = _distance(wolf, flock)
    _hurts_sheep(g, lambda g: g.frames(150))
    assert _distance(wolf, flock) < before, "it went after the sheep"


def _shoots(name: str) -> Callable[[RealGame], None]:
    def play(g: RealGame) -> None:
        g.heard.clear()
        g.stand_by(name, dx=-200)
        g.frames(90)
        assert g.events("projectile_fired"), f"{name} shoots"
    return play


def _spikes(g: RealGame) -> None:
    def touch(g: RealGame) -> None:
        spikes = g.named("Spikes")
        _at(g, "Sheep", spikes.center_x, spikes.center_y)
        g.frames(3)
    _hurts_sheep(g, touch)


def _drops(g: RealGame) -> None:
    gold = g.counter("gold")
    g.behaviour("Bandit", "Health").apply_damage(99, source_entity="player")
    g.frames(3)
    assert g.named("Bandit") is None and g.counter("gold") == gold + 7


def _drops_kept(g: RealGame) -> None:
    assert g.named("Bandit") is None


def _xp(g: RealGame) -> None:
    xp = g.gs.get_xp()
    g.behaviour("Rat", "Health").apply_damage(99, source_entity="player")
    g.frames(3)
    assert g.named("Rat") is None and g.gs.get_xp() == xp + 10


def _hands_over(g: RealGame) -> None:
    before = g.items(ITEM)
    g.interact("Satchel")
    assert g.items(ITEM) == before + 2, "what it carries is handed over"


def _player_moves(g: RealGame) -> None:
    hero = g.player()
    hero.center_x, hero.center_y = 200, 240
    g.key("D", 20)
    assert hero.center_x >= 230, "D walks right"


def _camera(g: RealGame) -> None:
    hero = g.player()
    hero.center_x, hero.center_y = 100, 100
    g.frames(60)
    before = g.window.get_camera_center()
    hero.center_x, hero.center_y = 540, 380
    g.frames(60)
    after = g.window.get_camera_center()
    assert after[0] > before[0] + 40 and after[1] > before[1] + 40, "the camera keeps the player in view"


ROWS: dict[str, Row] = {
    # --- Movement
    "Patrol": Row(place("Guard", 200, Y, ("Patrol", {"patrol_points": [{"x": 460, "y": Y}, {"x": 200, "y": Y}],
                                                     "patrol_speed": 120})), _moves("Guard")),
    "Wander": Row(place("Goat", X, Y, ("Wander", {"wander_radius": 3, "speed": 80, "idle_time_min": 0,
                                                  "idle_time_max": 0})), _moves("Goat", 90, 8)),
    "FollowTarget": Row(place("Dog", 480, 320, ("FollowTarget", {"follow_target": "Player", "follow_speed": 120})),
                        _nears_player("Dog")),
    "ChaseTarget": Row(place("Hound", 480, 320, ("ChaseTarget", {"target_tag": "player", "acquire_radius_tiles": 15,
                                                                 "speed": 120})), _nears_player("Hound", 90)),
    "FleeFromTarget": Row(place("Deer", X, Y, ("FleeFromTarget", {"threat_tags": ["player"], "detection_radius": 6,
                                                                  "speed": 120})), _flees),
    "PatrolChase": Row(place("Sentry", 480, 320, ("PatrolChase", {
        "patrol_points": [{"x": 480, "y": 320}, {"x": 520, "y": 320}], "target_tag": "player",
        "acquire_radius_tiles": 15, "chase_speed": 120})), _nears_player("Sentry", 90)),
    "NpcSchedule": Row(place("Baker", X, Y, ("NpcSchedule", {"schedules": [
        {"start_hour": 6, "end_hour": 18, "mode": "stand", "x": 400, "y": 300},
        {"start_hour": 18, "end_hour": 6, "mode": "stand", "x": 200, "y": 300}]})), _schedule),
    "PatrolPath": Row(place("Ferry", 200, Y, ("PatrolPath", {"waypoints": [{"x": 460, "y": Y}, {"x": 200, "y": Y}],
                                                             "speed": 120})), _moves("Ferry")),
    "FollowPath": Row(place("Courier", 200, 200, ("FollowPath", {"goal_x": 480, "goal_y": 320, "speed": 120})),
                      _walks_to_spot),
    # --- Interaction
    "Interactable": Row(place("Bell", X, Y, ("Interactable", {"interact_event": "bell_rung"})), _interactable),
    "ToggleSwitch": Row(place("Lever", X, Y, ("ToggleSwitch", {"label": "Lever"})), _lever),
    "SwitchInteract": Row(place("Button", X, Y, ("SwitchInteract", {"event_id": "button_pressed", "one_shot": True,
                                                                    "active_sprite": OTHER})),
                          _fires("button_pressed", _button), KEPT, _button_kept),
    "PickupCollectible": Row(place("Potion", X, Y, ("PickupCollectible", {"item_id": ITEM, "item_amount": 1})),
                             _pickup, KEPT, _pickup_kept),
    "Collectible": Row(place("Coin", X, Y, ("Collectible", {"collect_by_name": "Player"})), _touched, KEPT,
                       _gone("Coin")),
    "TriggerVolume": Row(place("Doormat", X, Y, ("TriggerVolume", {"width": 64, "height": 64,
                                                                   "target_tags": ["player"],
                                                                   "on_enter_event": "stepped_in"})),
                         _fires("stepped_in", _walk_in("Doormat"))),
    "TriggerZone": Row(place("Shrine", X, Y, ("TriggerZone", {"trigger_radius": 48, "trigger_target": "Player",
                                                              "on_trigger": "zone_hit"})), _zone_once),
    "DoorLock": Row(place("Gate", X, Y, ("DoorLock", {"unlock_event": "gate_open", "open_sprite": OTHER}),
                          solid=True), _door, KEPT, _door_kept),
    "RewardChest": Row(place("Chest", X, Y, ("RewardChest", {"unlock_event": "chest_open", "gold": 5})), _chest, KEPT,
                       _chest_kept),
    "Vendor": Row(place("Merchant", X, Y, ("Vendor", {"stock": [{"item_id": ITEM, "price": 5, "quantity": 3}]})),
                  _shop),
    "SceneTransition": Row(place("Exit", X, Y, ("SceneTransition", {"target_scene": "hall"})), _door_to_hall),
    # --- Dialogue and events
    "Dialogue": Row(place("Sage", X, Y) + [
        {"op": "add_line", "entity_id": "@0", "text": "Hello, traveller."},
        {"op": "set_conversation", "entity_id": "@0", "once": True}], _talk, KEPT, _talk_kept),
    "QuestGiver": Row(place("Elder", X, Y, ("QuestGiver", {"quest_id": "find_bell", "listen_event": "ask_for_help"})),
                      _quest, KEPT, _quest_kept),
    "SetGameStateOnEvent": Row(place("Lamp", X, Y, ("SetGameStateOnEvent", {"event_type": "lamp_lit",
                                                                            "set_flags": {"lamp_flag": True}})),
                               _set_flag, KEPT, _flagged("lamp_flag")),
    "Timer": Row(place("Clock", X, Y, ("Timer", {"duration": 0.2, "timer_event": "ding"})),
                 _fires("ding", lambda g: g.frames(20)), loaded=_quiet("ding", 20)),
    "CutsceneTrigger": Row(place("Stage", X, Y, ("CutsceneTrigger", {"cutscene_id": "intro",
                                                                     "listen_event": "play_intro"})), _cutscene),
    "SequencePlayer": Row(place("Herald", X, Y, ("SequencePlayer", {
        "steps": [{"type": "wait", "duration": 0.05}, {"type": "signal", "event": "fanfare"}],
        "auto_start": True})), _fires("fanfare", lambda g: g.frames(20))),
    # --- Appearance
    "Animator": Row(place("Flag", X, Y, ("Animator", {
        "animations": {"wave": {"sheet": SHEET, "frame_width": 32, "frame_height": 48, "frames": 4, "fps": 12,
                                "start": 0}}, "animation_state": "wave"}), picture=SHEET), _animates),
    "AutoAnimationByMovement": Row(place(
        "Strider", 200, Y, ("Patrol", {"patrol_points": [{"x": 460, "y": Y}, {"x": 200, "y": Y}], "patrol_speed": 120}),
        ("AutoAnimationByMovement", {}), picture=SHEET,  # (with the frame-list animation it switches between)
        sprite_sheet={"frame_width": 32, "frame_height": 48},
        animations={"idle": {"frames": [0], "fps": 8, "loop": True}, "walk": {"frames": [0, 1, 2, 3], "fps": 8, "loop": True}}), _walk_animation),
    "PictureByFlags": Row(place("Banner", X, Y, ("PictureByFlags", {"pictures": [{"sprite": OTHER,
                                                                                  "require_flags": ["festival"]}]})),
                          _picture_flag, KEPT, _picture_flag_kept),
    "ConditionalActivator": Row(place("Ghost", X, Y, ("ConditionalActivator", {"require_flags": ["haunted"]})),
                                _shown_by_flag, KEPT, _shown_by_flag_kept),
    "TimeOfDayGate": Row(place("Owl", X, Y, ("TimeOfDayGate", {"start_hour": 20, "end_hour": 5})), _hours),
    "ParticleEmitter": Row(place("Chimney", X, Y, ("ParticleEmitter", {"mode": "burst", "count": 8})), _particles),
    # --- Lighting
    "LightSource": Row(place("Lantern", X, Y, ("LightSource", {"radius": 96}))
                       + [{"op": "set_room_lighting", "enabled": True}], _carried_light),
    "ToggleSceneLights": Row(place("Switchboard", X, Y, ("ToggleSceneLights", {"listen_event": "lights_out",
                                                                              "indices": [0], "mode": "off"}))
                             + [{"op": "add_light", "x": 200, "y": 200}, {"op": "set_room_lighting", "enabled": True}],
                             _room_lights),
    # --- Gameplay
    "Health": Row(place("Slime", X, Y, ("Health", {"max_hp": 3})), _health, KEPT, _gone("Slime")),
    "Combat": Row(batch(place("Brawler", X, Y, ("Combat", {"target_tag": "sheep", "damage": 1, "cooldown": 0.3}),
                              ("EnemyAI", {"target_tag": "sheep", "detect_radius": 300, "attack_radius": 48})),
                        sheep(X + 32)), _brawl),
    "EnemyAI": Row(batch(place("Wolf", 200, Y, ("EnemyAI", {"target_tag": "sheep", "detect_radius": 400,
                                                             "attack_radius": 40, "speed": 120}),
                               ("Combat", {"target_tag": "sheep", "damage": 1, "cooldown": 0.3})), sheep(420)),
                   _enemy),
    "RangedEnemyAI": Row(place("Archer", X, Y, ("RangedEnemyAI", {"detect_radius": 400, "attack_radius": 300}),
                               ("Shooter", {"target_tag": "player", "cooldown": 0.5})), _shoots("Archer")),
    "Shooter": Row(place("Turret", X, Y, ("Shooter", {"target_tag": "player", "cooldown": 0.5}),
                         ("RangedEnemyAI", {"detect_radius": 400, "attack_radius": 300})), _shoots("Turret")),
    "DamageOnTouch": Row(batch(place("Spikes", X, Y, ("DamageOnTouch", {"target_name": "Sheep", "damage": 1})),
                               sheep(X + 150)), _spikes),
    "DropTable": Row(place("Bandit", X, Y, ("Health", {"max_hp": 3}), ("DropTable", {"drops": [{"gold": 7}]})),
                     _drops, KEPT, _drops_kept),
    "GrantExperience": Row(place("Rat", X, Y, ("Health", {"max_hp": 3}), ("GrantExperience", {"xp": 10})), _xp, KEPT,
                           _gone("Rat")),
    "InventoryHolder": Row(place("Satchel", X, Y, ("InventoryHolder", {"items": [{"id": ITEM, "amount": 2}]}),
                                 ("PickupCollectible", {})), _hands_over, KEPT, _gone("Satchel")),
    "PlayerController": Row([], _player_moves),
    "CameraFollow": Row([], _camera),
}

EXCLUDED: dict[str, str] = {
    "FloorRoute": "HD-2D rooms only: it walks between floors over stairs and bridges, which only an HD-2D room (a GL "
                  "3D scene) has; a 2D room has no floors to route across.",
}

QUESTS = {"find_bell": {"id": "find_bell", "title": "Find the bell",
                        "stages": [{"id": "look", "description": "Look for the bell", "complete_on": "bell_found"}]}}
REFUSED: dict[str, str] = {}  # row -> why authoring it was refused (filled by the module's game)
CUTSCENES = {"intro": [{"type": "add_counter", "name": "intro_seen", "delta": 1}, {"type": "wait", "duration": 0.05}]}


# ---------------------------------------------------------------------------------------------------- the game
@pytest.fixture(scope="module")
def running(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RealGame]:
    from engine.mcp_server import tools

    base = tmp_path_factory.mktemp("picker")
    project = new_project(base / "game")
    for name, row in ROWS.items():
        room = project.add_room(name)
        try:
            if row.objects:
                author(project, room, batch(row.objects))
        except ChangeError as err:  # (that row fails: Studio refused to author it)
            REFUSED[name] = str(err)
    project.save()  # (the rooms with nothing authored too)
    ops = [{"type": "add_quest_definition", "quest_id": qid, "quest": quest} for qid, quest in QUESTS.items()]
    ops += [{"type": "add_cutscene", "id": cid, "steps": steps} for cid, steps in CUTSCENES.items()]
    result = tools.apply_ops(ops, root=str(project.root))
    assert result.get("ok"), result
    launch = base / "elsewhere"
    launch.mkdir()
    with real_game(project, launch) as started:
        yield started


@pytest.fixture()
def game(running: RealGame) -> RealGame:
    return running.resume()  # (one window for the module; its project pins put back for each test)


def test_every_picker_behaviour_has_a_row_or_a_reasoned_exclusion() -> None:
    assert not set(ROWS) & set(EXCLUDED)
    assert sorted(set(GUIDES) - set(ROWS) - set(EXCLUDED)) == []
    assert sorted((set(ROWS) | set(EXCLUDED)) - set(GUIDES)) == []
    assert all(reason.strip() for reason in EXCLUDED.values())


# Rows a production defect fails today: strict, so the fix flips its own row (an unexpected pass fails CI).
BROKEN: dict[str, str] = {
    "AutoAnimationByMovement": "#703: never switches to walk for anything that moves by position "
                               "(it trusts Sprite.change_x/change_y, which every arcade sprite has as 0.0)",
}


@pytest.mark.parametrize("name", [pytest.param(name, marks=pytest.mark.xfail(strict=True, reason=BROKEN[name]))
                                  if name in BROKEN else name for name in sorted(ROWS)])
def test_picker_behaviour_contract(game: RealGame, name: str) -> None:
    row = ROWS[name]
    assert name not in REFUSED, f"Studio refuses to author it: {REFUSED.get(name)}"
    room = game.room(name)
    game.enter(room)
    row.play(game)
    for phase, leave in (("leaving and coming back", game.revisit), ("a save and a load", lambda _r: game.save_load())):
        leave(room)
        try:
            if row.loaded is not None and phase == "a save and a load":
                row.loaded(game)
            elif row.rule == KEPT:
                assert row.kept is not None
                row.kept(game)
            else:
                row.play(game)
        except AssertionError as err:
            raise AssertionError(f"after {phase}: {err}") from err
