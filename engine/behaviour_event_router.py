"""
Runtime adapter for behaviour event routing.
"""
from __future__ import annotations

import logging
from typing import Any, Tuple, Dict, Set
from .behaviour_event_router_model import (
    BehaviourEvent,
    compute_dispatch_targets,
    should_fallback_to_primary,
)

logger = logging.getLogger(__name__)
_UNRESOLVED_WARNED: Set[Tuple[str, str]] = set()
_UNRESOLVED_WARNED_LIMIT = 1024

def _get_methods_from_entity(entity: Any) -> Tuple[str, ...]:
    """Return all handler-like methods available on an entity's behaviours."""
    methods = set()
    behaviours = getattr(entity, "mesh_behaviours_runtime", [])
    
    # Also check the entity itself if it's a Controller/Behaviour but usually behaviours are attached
    # Standard Mesh architecture: entity is a Sprite, has .mesh_behaviours_runtime list.
    
    # The model expects a Tuple[str] of *all* available handlers to match against.
    # To build that list, we iterate behaviours and dir().
    for beh in behaviours:
        for attr in dir(beh):
            if attr.startswith("on_sensor_"):
                methods.add(attr)
    return tuple(methods)

def _get_methods_from_scene(scene_controller: Any) -> Tuple[str, ...]:
    methods = set()
    for attr in dir(scene_controller):
        if attr.startswith("on_sensor_"):
            methods.add(attr)
    return tuple(methods)

def _warn_unresolved_once(event_kind: str, entity_id: str) -> None:
    key = (event_kind, entity_id)
    if key in _UNRESOLVED_WARNED:
        return
    if len(_UNRESOLVED_WARNED) >= _UNRESOLVED_WARNED_LIMIT:
        _UNRESOLVED_WARNED.clear()
    _UNRESOLVED_WARNED.add(key)
    logger.warning(
        "[Mesh][BehaviourRouter] Unresolved entity_id=%s for %s; falling back to scene/primary_player.",
        entity_id,
        event_kind,
    )

def _resolve_entity(scene_controller: Any, entity_id: str | None) -> Any | None:
    if not entity_id:
        return None
    scene_index = getattr(scene_controller, "_scene_index", None)
    if scene_index:
        lookup = getattr(scene_index, "lookup", None)
        if isinstance(lookup, dict):
            entity = lookup.get(entity_id)
            if entity is not None:
                return entity
    # Fallback to entity store/controller if present
    entities = getattr(scene_controller, "entities", None)
    if entities is not None:
        finder = getattr(entities, "find_entity", None)
        if callable(finder):
            entity = finder(scene_controller, entity_id)
            if entity is not None:
                return entity
    # Fallback to scene_controller.find_entity if available
    finder = getattr(scene_controller, "find_entity", None)
    if callable(finder):
        return finder(entity_id)
    return None

def _resolve_primary_player(scene_controller: Any) -> Any | None:
    entities = getattr(scene_controller, "entities", None)
    if entities is not None:
        finder = getattr(entities, "find_primary_player_sprite", None)
        if callable(finder):
            entity = finder(scene_controller)
            if entity is not None:
                return entity
    finder = getattr(scene_controller, "_find_player_sprite", None)
    if callable(finder):
        return finder()
    return None

def dispatch_events(
    scene_controller: Any, 
    events: Tuple[BehaviourEvent, ...]
) -> None:
    """
    Route events to their targets via the scene controller and entity system.
    """
    if not events:
        return

    # 1. Prepare Environment / Lookup
    # We need to find entities referenced in events.
    # SceneController usually has a way to look them up.
    # We'll rely on scene_controller having a lookup or looping layers if needed.
    # In V1, we assume we can resolve by ID. 
    # If SceneController doesn't have a fast lookup, we might rely on the caller providing context?
    # No, caller just passes events.
    
    # Optimization: Cache scene methods once per batch
    scene_methods = _get_methods_from_scene(scene_controller)
    
    entity_method_cache: Dict[int, Tuple[str, ...]] = {}

    # 2. Compute Plan + Execute
    for evt in events:
        target_id = evt.target_entity_id if evt.target_entity_id is not None else evt.entity_id
        resolved_entity = _resolve_entity(scene_controller, target_id)
        if resolved_entity is None and should_fallback_to_primary(evt):
            resolved_entity = _resolve_primary_player(scene_controller)
        if resolved_entity is None and isinstance(target_id, str) and target_id:
            _warn_unresolved_once(evt.kind, target_id)

        resolved_entity_id: str | None = None
        entity_methods: Tuple[str, ...] = ()
        if resolved_entity is not None:
            cache_key = id(resolved_entity)
            cached_methods = entity_method_cache.get(cache_key)
            if cached_methods is None:
                cached_methods = _get_methods_from_entity(resolved_entity)
                entity_method_cache[cache_key] = cached_methods
            entity_methods = cached_methods
            name = getattr(resolved_entity, "mesh_name", None)
            if isinstance(name, str) and name.strip():
                resolved_entity_id = name
            else:
                resolved_entity_id = target_id if isinstance(target_id, str) else None

        plan = compute_dispatch_targets(
            evt,
            {resolved_entity_id: entity_methods} if resolved_entity_id else {},
            scene_methods,
            resolved_entity_id=resolved_entity_id,
        )

        # Entity then scene
        if plan.entity_handler_enabled and resolved_entity is not None:
            try:
                behaviours = getattr(resolved_entity, "mesh_behaviours_runtime", [])
                for beh in behaviours:
                    handler = getattr(beh, plan.handler_name, None)
                    if callable(handler):
                        handler(evt.sensor_id)
            except Exception as e:
                logger.error(
                    "[Mesh][BehaviourRouter] Error dispatching %s: %s",
                    plan.handler_name,
                    e,
                )

        if plan.scene_target_enabled:
            try:
                handler = getattr(scene_controller, plan.handler_name, None)
                if callable(handler):
                    handler(evt.entity_id, evt.sensor_id)
            except Exception as e:
                logger.error(
                    "[Mesh][BehaviourRouter] Error dispatching %s: %s",
                    plan.handler_name,
                    e,
                )

