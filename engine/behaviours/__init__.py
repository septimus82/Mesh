"""Behaviour package exposing registry helpers and default behaviours."""

from __future__ import annotations

import importlib
from typing import Iterable

from .registry import (
    BEHAVIOUR_REGISTRY,
    BehaviourInfo,
    create_behaviour,
    get_behaviour_info,
    get_behaviour_param_defs,
    list_behaviours,
    normalize_config,
    register,
    register_behaviour,
    reload_behaviour_modules,
    reset_behaviour_registry,
)

_BUILTIN_MODULES: tuple[str, ...] = (
    "engine.behaviours.action_list_runner",
    "engine.behaviours.auto_animation_by_movement",
    "engine.behaviours.animator",
    "engine.behaviours.breeding_shrine_zone",
    "engine.behaviours.camera_follow",
    "engine.behaviours.patrol_chase",
    "engine.behaviours.collectible",
    "engine.behaviours.combat",
    "engine.behaviours.chase_target",
    "engine.behaviours.conditional_activator",
    "engine.behaviours.cutscene_trigger",
    "engine.behaviours.damage_on_touch",
    "engine.behaviours.dialogue",
    "engine.behaviours.dialogue_runner",
    "engine.behaviours.drop_table",
    "engine.behaviours.encounter_cleared",
    "engine.behaviours.emit_event_on_event",
    "engine.behaviours.enemy_ai",
    "engine.behaviours.event_logger",
    "engine.behaviours.flee_from_target",
    "engine.behaviours.follow",
    "engine.behaviours.follow_path",
    "engine.behaviours.grant_experience",
    "engine.behaviours.health",
    "engine.behaviours.hitbox",
    "engine.behaviours.increment_counter_on_event",
    "engine.behaviours.interactable",
    "engine.behaviours.inventory_holder",
    "engine.behaviours.light_source",
    "engine.behaviours.listen_for_event",
    "engine.behaviours.main_menu",
    "engine.behaviours.message_on_zone_enter",
    "engine.behaviours.monster_encounter_zone",
    "engine.behaviours.npc_schedule",
    "engine.behaviours.offer_perk_choice",
    "engine.behaviours.particle_emitter",
    "engine.behaviours.patrol",
    "engine.behaviours.patrol_path",
    "engine.behaviours.pickup_collectible",
    "engine.behaviours.player_controller",
    "engine.behaviours.projectile",
    "engine.behaviours.puzzle_behaviours",
    "engine.behaviours.quest_giver",
    "engine.behaviours.quest_hook",
    "engine.behaviours.quest_progress",
    "engine.behaviours.ranged_attack_ai",
    "engine.behaviours.ranged_enemy_ai",
    "engine.behaviours.scene_exit",
    "engine.behaviours.scene_transition",
    "engine.behaviours.sequence_player",
    "engine.behaviours.set_game_state_on_event",
    "engine.behaviours.shooter",
    "engine.behaviours.time_of_day_gate",
    "engine.behaviours.timer",
    "engine.behaviours.toggle_scene_lights",
    "engine.behaviours.toggle_switch",
    "engine.behaviours.trigger_volume",
    "engine.behaviours.trigger_zone",
    "engine.behaviours.vendor",
    "engine.behaviours.wander",
)

_BUILTINS_LOADED = False


def load_builtin_behaviours(*, modules: Iterable[str] | None = None, force: bool = False) -> None:
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED and not force:
        return
    for module_name in modules or _BUILTIN_MODULES:
        importlib.import_module(module_name)
    _BUILTINS_LOADED = True

__all__ = [
    "BEHAVIOUR_REGISTRY",
    "BehaviourInfo",
    "create_behaviour",
    "get_behaviour_param_defs",
    "get_behaviour_info",
    "normalize_config",
    "list_behaviours",
    "register",
    "register_behaviour",
    "reset_behaviour_registry",
    "reload_behaviour_modules",
    "load_builtin_behaviours",
]
