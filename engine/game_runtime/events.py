from typing import Any
import engine.optional_arcade as optional_arcade
from engine.events import MeshEvent
from engine.ui import (
    begin_boss_gold_reward_tracking,
    maybe_enqueue_boss_defeat_toast,
    maybe_enqueue_miniboss_defeat_toast,
    maybe_finish_boss_gold_reward_toast,
)

def on_entity_died(window: Any, event: MeshEvent) -> None:
    actor = event.payload.get("actor")
    name = event.payload.get("name", "<unknown>")

    scene_id = getattr(getattr(window, "scene_controller", None), "current_scene_path", None)

    if actor is not None:
        begin_boss_gold_reward_tracking(window, actor, scene_id)

    if actor is not None:
        maybe_enqueue_boss_defeat_toast(
            window,
            actor,
            scene_id,
            seconds=3.0,
        )
        maybe_enqueue_miniboss_defeat_toast(
            window,
            actor,
            scene_id,
            seconds=3.0,
        )

    # Spawn death particles
    if actor:
        window.particle_manager.emit_death_effect(actor.center_x, actor.center_y)

    window.console_log(f"Entity '{name}' died!")

    # Check if player
    if getattr(actor, "mesh_tag", "") == "player":
        window.console_log("PLAYER DIED!")
        window.game_over = True
        window.game_over_screen.visible = True
        window.paused = True

def on_any_event_boss_reward_clarity(window: Any, event: MeshEvent) -> None:
    if event.type != "died":
        return
    actor = event.payload.get("actor")
    if actor is None:
        return
    scene_id = getattr(getattr(window, "scene_controller", None), "current_scene_path", None)
    maybe_finish_boss_gold_reward_toast(window, actor, scene_id, seconds=3.0)

def on_damage_event(window: Any, event: MeshEvent) -> None:
    target = event.payload.get("target")
    if target:
        window.particle_manager.emit_hit_effect(target.center_x, target.center_y)

def on_collectible_event(window: Any, event: MeshEvent) -> None:
    collectible = event.payload.get("collectible")
    if collectible:
        window.particle_manager.emit_collect_effect(collectible.center_x, collectible.center_y)

def on_level_up(window: Any, event: MeshEvent) -> None:
    payload = event.payload or {}
    level = payload.get("level")
    console_log = getattr(window, "console_log", None)
    if callable(console_log):
        console_log(f"[XP] Level up! Reached level {level}")

def on_any_event(window: Any, event: MeshEvent) -> None:
    """Buffer all events for the main loop to consume."""
    window._mesh_event_queue.append(event)
    # Keep a simple list of recent event types for debug if needed,
    # though we now use the bus history.
    window.last_events.append(event.type)
    if len(window.last_events) > 10:
        window.last_events.pop(0)
