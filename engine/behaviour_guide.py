"""Behaviours as a creator meets them: plain names, a sentence each, categories, the settings that matter.

A presentation layer over the behaviour registry (``engine.behaviours.registry``): nothing here renames a
behaviour or changes stored data. A behaviour the guide doesn't know (a plugin's, a new one) still shows,
under Advanced, with its registry description; one marked advanced is out of the beginner's list but a
search finds it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CATEGORIES = ("Movement", "Interaction", "Dialogue and events", "Appearance", "Lighting", "Gameplay", "Advanced")


@dataclass(frozen=True)
class Guide:
    label: str
    summary: str
    category: str
    basics: tuple[str, ...] = ()  # the settings shown first; the rest under "More settings"
    labels: dict[str, str] = field(default_factory=dict)  # setting -> what to call it


_G = Guide
GUIDES: dict[str, Guide] = {
    # --- Movement
    "Patrol": _G("Walk between points", "Walks a route you click on the map, point after point, over and over.", "Movement",
                 ("patrol_points", "patrol_speed"), {"patrol_points": "Route", "patrol_speed": "Speed"}),
    "Wander": _G("Wander around", "Strolls to random nearby spots, pausing now and then.", "Movement",
                 ("wander_radius", "speed"), {"wander_radius": "How far (tiles)", "min_wander_distance": "Shortest walk (tiles)",
                                              "idle_time_min": "Pause at least (s)", "idle_time_max": "Pause at most (s)",
                                              "anchor_to_spawn": "Stay near where it starts"}),
    "FollowTarget": _G("Follow someone", "Walks after another object, by its name.", "Movement",
                       ("follow_target", "follow_speed"), {"follow_target": "Who (name)", "follow_speed": "Speed"}),
    "ChaseTarget": _G("Chase a target", "Spots someone nearby and runs after them, finding a way round walls.", "Movement",
                      ("target_tag", "acquire_radius_tiles", "speed"),
                      {"target_tag": "Chases (tag, e.g. player)", "target_entity_id": "Chases (object id)",
                       "acquire_radius_tiles": "Notices within (tiles)", "leash_radius_tiles": "Gives up beyond (tiles)",
                       "los_required": "Must see them"}),
    "FleeFromTarget": _G("Run away", "Keeps its distance from something it fears.", "Movement",
                         ("threat_tags", "detection_radius", "speed"),
                         {"threat_tags": "Afraid of (tags)", "detection_radius": "Notices within (tiles)",
                          "safe_distance": "Feels safe at (tiles)"}),
    "PatrolChase": _G("Patrol and chase intruders", "Walks a route, chases whoever comes close, then goes back to it.",
                      "Movement", ("patrol_points", "target_tag", "acquire_radius_tiles"),
                      {"patrol_points": "Route", "target_tag": "Chases (tag, e.g. player)",
                       "acquire_radius_tiles": "Notices within (tiles)", "patrol_speed": "Walking speed",
                       "chase_speed": "Running speed"}),
    "NpcSchedule": _G("Follow a daily schedule", "Is in different places at different times of day.", "Movement",
                      ("schedules",), {"schedules": "Schedule"}),
    "PatrolPath": _G("Walk a route (loop or back and forth)", "Walks waypoints, looping or turning back at the end.",
                     "Advanced", ("waypoints", "mode", "speed"), {"waypoints": "Route", "wait_time": "Wait at each (s)"}),
    "FollowPath": _G("Walk to a spot", "Finds its way to a point or a named object once.", "Advanced"),
    # --- Interaction
    "Interactable": _G("React when the player presses E", "Something happens when the player stands close and presses E.",
                       "Interaction", ("interact_label", "interact_event"), {"interact_label": "Prompt",
                                                                           "interact_event": "Event it sends"}),
    "ToggleSwitch": _G("Lever or switch", "Flips on and off when used.", "Interaction", ("label",),
                       {"label": "Name", "initial_state": "Starts on"}),
    "SwitchInteract": _G("Button", "Sends an event when the player uses it.", "Interaction", ("event_id",),
                         {"event_id": "Event it sends", "one_shot": "Only once", "active_sprite": "Picture once used"}),
    "PickupCollectible": _G("Can be picked up", "The player picks it up with E.", "Interaction", ("item_id", "item_amount"),
                            {"item_id": "Item", "item_amount": "How many"}),
    "Collectible": _G("Collected on touch", "Picked up the moment the player touches it.", "Interaction"),
    "TriggerVolume": _G("React when something enters an area", "Sends an event when someone walks into or out of an area.",
                        "Interaction", ("width", "height", "target_tags", "on_enter_event"),
                        {"target_tags": "Who (tags)", "on_enter_event": "Event on entering", "on_exit_event": "Event on leaving"}),
    "TriggerZone": _G("React when someone comes near", "Sends an event once when its target comes within reach.",
                      "Interaction", ("trigger_radius", "trigger_target", "on_trigger"),
                      {"trigger_radius": "Reach", "trigger_target": "Who (name)", "on_trigger": "Event it sends"}),
    "DoorLock": _G("Locked until an event", "Stays locked until a chosen event happens.", "Interaction", ("unlock_event",),
                   {"unlock_event": "Opens on event", "starts_locked": "Starts locked", "open_sprite": "Picture when open"}),
    "RewardChest": _G("Treasure chest", "Gives an item or gold once it is unlocked.", "Interaction",
                      ("unlock_event", "item_id", "gold"), {"unlock_event": "Opens on event", "item_id": "Item"}),
    "Vendor": _G("Shopkeeper", "Opens a shop with the items you list.", "Interaction", ("stock",), {"stock": "Items for sale"}),
    "SceneTransition": _G("Go to another room", "Takes the player to another room (Studio's doors use this).", "Interaction"),
    # --- Dialogue and events
    "Dialogue": _G("Talk", "Says lines, with choices, when the player talks to it (the Dialogue tab sets it up).",
                   "Dialogue and events"),
    "QuestGiver": _G("Give a quest", "Starts a quest when an event happens.", "Dialogue and events", ("quest_id",),
                     {"quest_id": "Quest", "listen_event": "Starts on event"}),
    "SetGameStateOnEvent": _G("Set a flag when something happens", "Sets or clears flags when an event happens.",
                              "Dialogue and events", ("event_type", "set_flags"),
                              {"event_type": "When event", "set_flags": "Sets flags", "clear_flags": "Clears flags"}),
    "Timer": _G("Timer", "Sends an event after some seconds, once or repeatedly.", "Dialogue and events",
                ("duration", "repeat"), {"duration": "Seconds", "timer_event": "Event it sends"}),
    "CutsceneTrigger": _G("Start a cutscene", "Plays a cutscene when an event happens.", "Dialogue and events"),
    "SequencePlayer": _G("Play a sequence", "Runs steps one after another: waits, moves, lines, events.", "Dialogue and events"),
    # --- Appearance
    "Animator": _G("Animate the picture", "Plays frames from a sheet (the Animation tab sets it up).", "Appearance"),
    "AutoAnimationByMovement": _G("Walk animation from movement", "Switches between idle and walking frames by itself.",
                                  "Appearance"),
    "PictureByFlags": _G("Change picture with the story", "Shows another picture while flags allow (the Conditions tab).",
                         "Appearance"),
    "ConditionalActivator": _G("Show only when flags allow", "Hidden (and not blocking) unless its flags allow (the "
                               "Conditions tab).", "Appearance"),
    "TimeOfDayGate": _G("Appear at certain hours", "Shows only between two times of day.", "Appearance",
                        ("start_hour", "end_hour"), {"start_hour": "From hour", "end_hour": "Until hour"}),
    "ParticleEmitter": _G("Particles", "Smoke, sparks, dust: little particles from the object.", "Appearance",
                          ("preset", "mode", "count")),
    # --- Lighting
    "LightSource": _G("Carry a light", "A light that moves with the object (a torch, a lantern carrier).", "Lighting",
                      ("radius", "color", "flicker_enabled"), {"radius": "Size", "color": "Colour", "flicker_enabled": "Flicker"}),
    "ToggleSceneLights": _G("Switch the room's lights", "Turns room lights on or off when an event happens.", "Lighting",
                            ("listen_event", "mode"), {"listen_event": "On event"}),
    # --- Gameplay
    "Health": _G("Has health", "Can be hurt, and is defeated at zero.", "Gameplay", ("max_hp",),
                 {"max_hp": "Health", "hp": "Starts with", "invulnerable": "Can't be hurt"}),
    "Combat": _G("Can attack", "Attacks what's in reach.", "Gameplay", ("damage", "target_tag"),
                 {"target_tag": "Attacks (tag)"}),
    "EnemyAI": _G("Enemy: chase and attack", "Hunts the player and attacks up close.", "Gameplay",
                  ("detect_radius", "speed"), {"detect_radius": "Notices within", "attack_radius": "Attacks within"}),
    "RangedEnemyAI": _G("Enemy: keep away and shoot", "Keeps its distance and shoots (add Shoot too).", "Gameplay",
                        ("detect_radius", "attack_radius")),
    "Shooter": _G("Shoot", "Fires projectiles at a target.", "Gameplay", ("damage", "cooldown", "target_tag")),
    "DamageOnTouch": _G("Hurts on touch", "Damages whoever touches it.", "Gameplay", ("damage",), {"target_name": "Hurts (name)"}),
    "DropTable": _G("Drops items when defeated", "Leaves items or gold behind.", "Gameplay", ("drops",)),
    "GrantExperience": _G("Gives experience when defeated", "The player gains experience for defeating it.", "Gameplay"),
    "InventoryHolder": _G("Carries items", "Holds items it can hand over.", "Gameplay"),
    "PlayerController": _G("Player controls", "Moves with WASD and talks with E: what makes the player the player.",
                           "Advanced"),
    "CameraFollow": _G("Camera follows it", "The camera keeps this object in view (the player has it).", "Advanced"),
}
# Engine plumbing, monster-game parts and debugging aids: found by searching, not listed for beginners.
ADVANCED = {"ActionListRunner", "BreedingShrineZone", "DialogueRunner", "EmitEventOnEvent", "EncounterCleared",
            "EventLogger", "Hitbox", "IncrementCounterOnEvent", "ListenForEvent", "MainMenuBehaviour", "MessageOnZoneEnter",
            "MonsterEncounterZone", "OfferPerkChoice", "Projectile", "QuestHook", "QuestProgressOnEvent", "RangedAttackAI",
            "SceneExit"}


def guide(name: str, description: str = "") -> Guide:
    """How to present a behaviour (its registry ``description`` for one the guide doesn't know)."""
    found = GUIDES.get(name)
    if found is not None:
        return found
    return Guide(humanize(name), description or "No description yet.", "Advanced")


def humanize(name: str) -> str:
    """``patrol_speed`` -> ``Patrol speed``; ``ChaseTarget`` -> ``Chase target``."""
    spaced = "".join(f" {c.lower()}" if c.isupper() and i else c for i, c in enumerate(name)) if "_" not in name else name
    words = spaced.replace("_", " ").split()
    return " ".join(words).capitalize() if words else name


def is_advanced(name: str) -> bool:
    return name in ADVANCED or guide(name).category == "Advanced"


def entries(catalog: list[dict[str, Any]], query: str = "", *, advanced: bool = False) -> list[dict[str, Any]]:
    """The picker's list: ``{name, label, summary, category}`` in category order, then by label. A search
    looks at labels, summaries and internal names, and always includes advanced behaviours."""
    query = query.strip().lower()
    out = []
    for item in catalog:
        name = item["name"]
        info = guide(name, item.get("description", ""))
        category = "Advanced" if is_advanced(name) else info.category
        text = f"{info.label} {info.summary} {name} {category}".lower()
        if query and query not in text:
            continue
        if not query and category == "Advanced" and not advanced:
            continue
        out.append({"name": name, "label": info.label, "summary": info.summary, "category": category})
    order = {c: i for i, c in enumerate(CATEGORIES)}
    return sorted(out, key=lambda e: (order.get(e["category"], len(order)), e["label"].lower()))


def visible_fields(name: str, fields: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """``(basics, more)``: the settings to show first and the rest, aliases left out."""
    real = [f for f in fields if not str(f.get("description") or "").startswith("Alias for")]
    basics = guide(name).basics
    if not basics:
        return real, []
    first = [next(f for f in real if f["name"] == b) for b in basics if any(f["name"] == b for f in real)]
    return first, [f for f in real if f["name"] not in basics]


def setting_label(name: str, setting: str) -> str:
    return guide(name).labels.get(setting) or humanize(setting)


def _points(value: Any) -> int:
    return len([p for p in value or [] if isinstance(p, dict) and "x" in p and "y" in p]) if isinstance(value, list) else 0


def problems(name: str, config: dict[str, Any]) -> list[str]:
    """What stops the behaviour working as set, in words the creator can act on (empty: nothing found)."""
    c = config or {}
    if name in ("Patrol", "PatrolChase") and _points(c.get("patrol_points")) < 2 and not c.get("patrol_tag"):
        return ["It needs at least two points to walk between: use Edit route, then click the map."]
    if name == "PatrolPath" and _points(c.get("waypoints")) < 2 and not c.get("waypoint_tag"):
        return ["It needs at least two waypoints."]
    if name in ("ChaseTarget", "PatrolChase") and not (c.get("target_tag") or c.get("target_entity_id")):
        return ["Choose what it chases: a tag such as player."]
    if name == "FollowTarget" and not c.get("follow_target"):
        return ["Choose who it follows: an object's name."]
    if name == "FleeFromTarget" and not (c.get("threat_tags") or c.get("threat_entity_id")):
        return ["Choose what it runs from: a tag such as player."]
    if name in ("DoorLock", "RewardChest") and not c.get("unlock_event"):
        return ["Choose the event that unlocks it."]
    if name == "QuestGiver" and not c.get("quest_id"):
        return ["Choose which quest it gives."]
    if name == "SetGameStateOnEvent" and not c.get("event_type"):
        return ["Choose the event it listens for."]
    if name == "Timer" and float(c.get("duration", 1.0) or 0) <= 0:
        return ["The time must be more than zero seconds."]
    return []
