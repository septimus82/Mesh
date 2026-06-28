"""Encounter-clear detector for combat rooms."""

from __future__ import annotations

from typing import Any

from engine.combat_constants import EVENT_COMBAT_DEATH, EVENT_DIED_ALIAS
from engine.event_emit import emit_gameplay_event

from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "EncounterCleared",
    description="Emits an event once all live entities with the configured tag are gone.",
    config_fields=[
        {
            "name": "enemy_tag",
            "description": "Sprite tag counted as part of the encounter.",
            "type": "string",
            "default": "enemy",
        },
        {
            "name": "clear_event",
            "description": "Event emitted when the encounter clears.",
            "type": "string",
            "default": "encounter_cleared",
        },
    ],
)
class EncounterCleared(Behaviour):
    """Watch current-scene enemy count and emit exactly once on the last death."""

    PARAM_DEFS = {
        "enemy_tag": ParamDef(str, default="enemy", description="Sprite tag counted as an encounter enemy"),
        "clear_event": ParamDef(str, default="encounter_cleared", description="Event emitted when cleared"),
    }

    def __init__(self, entity: Any, window: Any, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self.enemy_tag = str(self.config.get("enemy_tag", "enemy") or "enemy").strip() or "enemy"
        self.clear_event = str(self.config.get("clear_event", "encounter_cleared") or "encounter_cleared").strip()
        self._saw_enemies = False
        self._fired = False

    def subscribed_event_types(self) -> frozenset[str] | None:
        return frozenset({EVENT_COMBAT_DEATH, EVENT_DIED_ALIAS})

    def update(self, dt: float) -> None:  # noqa: ARG002
        self._check_for_clear()

    def on_event(self, event: Any) -> None:
        if self._fired:
            return
        if getattr(event, "type", "") not in {EVENT_COMBAT_DEATH, EVENT_DIED_ALIAS}:
            return
        # If the watcher has not yet observed the populated scene, a death event
        # for a tagged actor still proves the encounter had at least one enemy.
        if self._event_actor_matches_tag(event):
            self._saw_enemies = True
        self._check_for_clear()

    def _check_for_clear(self) -> None:
        if self._fired:
            return
        live_count = self._live_enemy_count()
        if live_count > 0:
            self._saw_enemies = True
            return
        if not self._saw_enemies:
            return
        self._emit_cleared()

    def _live_enemy_count(self) -> int:
        scene_controller = getattr(self.window, "scene_controller", None)
        sprites = getattr(scene_controller, "all_sprites", []) if scene_controller is not None else []
        count = 0
        for sprite in list(sprites or []):
            if sprite is self.entity:
                continue
            if getattr(sprite, "mesh_tag", None) != self.enemy_tag:
                continue
            if self._sprite_is_dead(sprite):
                continue
            count += 1
        return count

    @staticmethod
    def _sprite_is_dead(sprite: Any) -> bool:
        for behaviour in getattr(sprite, "mesh_behaviours_runtime", []) or []:
            if getattr(behaviour, "_dead", False):
                return True
            if bool(getattr(behaviour, "is_dead", False)):
                return True
        return False

    def _event_actor_matches_tag(self, event: Any) -> bool:
        payload = getattr(event, "payload", {}) or {}
        actor = payload.get("actor")
        if actor is not None and getattr(actor, "mesh_tag", None) == self.enemy_tag:
            return True
        return False

    def _emit_cleared(self) -> None:
        self._fired = True
        scene_controller = getattr(self.window, "scene_controller", None)
        scene_path = getattr(scene_controller, "current_scene_path", None) if scene_controller is not None else None
        emit_gameplay_event(
            self.window,
            self.clear_event,
            {
                "enemy_tag": self.enemy_tag,
                "scene_path": scene_path,
                "entity": getattr(self.entity, "mesh_name", ""),
            },
            source_entity_id=str(getattr(self.entity, "mesh_id", "") or ""),
            source_behaviour="EncounterCleared",
        )
