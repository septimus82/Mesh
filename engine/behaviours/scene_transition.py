"""Behaviour that loads a different scene when triggered."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from arcade import Sprite

import engine.optional_arcade as optional_arcade

from ..events import MeshEvent
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "SceneTransition",
    description="Requests a new scene when the player interacts or an event fires.",
    config_fields=[
        {
            "name": "target_scene",
            "description": "Path to the JSON scene that should load",
            "type": "string",
            "default": "",
        },
        {
            "name": "spawn_id",
            "description": "Optional spawn marker ID to use in the destination scene",
            "type": "string",
            "default": "",
        },
        {
            "name": "spawn_point",
            "description": "Alias for spawn_id",
            "type": "string",
            "default": "",
        },
        {
            "name": "allow_interact",
            "description": "If true, allow the player interact button to trigger the transition",
            "type": "bool",
            "default": True,
        },
        {
            "name": "event_type",
            "description": "Optional Mesh event name that triggers the transition",
            "type": "string",
            "default": "",
        },
        {
            "name": "event_field",
            "description": "Optional payload field to check before reacting to the event",
            "type": "string",
            "default": "",
        },
        {
            "name": "event_value",
            "description": "Optional value that event_field must equal",
            "type": "string",
            "default": "",
        },
        {
            "name": "once",
            "description": "Prevent the transition from firing more than once",
            "type": "bool",
            "default": False,
        },
    ],
)
class SceneTransition(Behaviour):
    """Allows scenes to change via player interaction or scripted events."""

    PARAM_DEFS = {
        "target_scene": ParamDef(str, default="", description="Path to the JSON scene that should load"),
        "spawn_id": ParamDef(str, default="", description="Optional spawn marker ID"),
        "allow_interact": ParamDef(bool, default=True, description="Allow player interact button to trigger"),
        "trigger_on_touch": ParamDef(bool, default=False, description="Trigger transition on collision"),
        "target_tag": ParamDef(str, default="player", description="Tag of entity that triggers collision"),
        "event_type": ParamDef(str, default="", description="Mesh event name that triggers the transition"),
        "event_field": ParamDef(str, default="", description="Payload field to check"),
        "event_value": ParamDef(str, default="", description="Optional value that event_field must equal"),
        "once": ParamDef(bool, default=False, description="Prevent the transition from firing more than once"),
    }

    def __init__(self, entity: Any, window: Any, **config: Any) -> None:
        merged = self._merge_entity_data(entity, config)
        super().__init__(entity, window, **merged)
        self.entity_name = getattr(entity, "mesh_name", "<unnamed>")
        self.target_scene = str(
            merged.get("target_scene")
            or merged.get("scene")
            or merged.get("target")
            or ""
        ).strip()
        self.spawn_id = str(
            merged.get("spawn_id")
            or merged.get("target_spawn")
            or merged.get("spawn_point")
            or ""
        ).strip()
        self.allow_interact = bool(merged.get("allow_interact", merged.get("interact", True)))
        self.trigger_on_touch = bool(merged.get("trigger_on_touch", False))
        self.target_tag = str(merged.get("target_tag", "player")).strip()
        self.event_type = str(merged.get("event_type", merged.get("trigger_event", ""))).strip()
        self.event_field = str(merged.get("event_field", merged.get("payload_field", ""))).strip()
        raw_value = merged.get("event_value", merged.get("payload_value"))
        self.event_value = str(raw_value).strip() if raw_value not in (None, "") else None
        self.once = bool(merged.get("once", False))
        self.config.update(
            {
                "target_scene": self.target_scene,
                "spawn_id": self.spawn_id,
                "allow_interact": self.allow_interact,
                "trigger_on_touch": self.trigger_on_touch,
                "target_tag": self.target_tag,
                "event_type": self.event_type,
                "event_field": self.event_field,
                "event_value": self.event_value,
                "once": self.once,
            },
        )
        self._triggered = False
        if not self.target_scene:
            self._log("SceneTransition has no target_scene configured")

    @staticmethod
    def _merge_entity_data(entity: Sprite, config: Dict[str, Any] | None) -> Dict[str, Any]:
        data = dict(getattr(entity, "mesh_entity_data", {}) or {})
        if config:
            data.update(config)
        return data

    def update(self, dt: float) -> None:
        if not self.trigger_on_touch or self._triggered:
            return

        # Find entities with target_tag
        scene_controller = getattr(self.window, "scene_controller", None)
        if not scene_controller:
            return

        candidates = []
        for sprite in scene_controller.all_sprites:
            if getattr(sprite, "mesh_tag", "") == self.target_tag:
                candidates.append(sprite)

        if not candidates:
            return
        sprite_list = optional_arcade.arcade.SpriteList()
        for candidate in candidates:
            sprite_list.append(candidate)
        hit_list = optional_arcade.arcade.check_for_collision_with_list(self.entity, sprite_list)
        if hit_list:
            self._trigger_transition(reason="collision", actor=hit_list[0])

    def on_interact(self, window: Any, actor: Any) -> None:  # noqa: D401
        if not self.allow_interact:
            return
        self._trigger_transition(reason="interact", actor=actor)

    def can_interact_with(self, _actor: Any) -> bool:
        if not self.allow_interact:
            return False
        if not self.target_scene:
            return False
        if self.once and self._triggered:
            return False
        getter = getattr(self.window, "get_flag", None)
        if callable(getter):
            from engine.scene_entity_gating import runtime_entity_passes_flag_gates  # noqa: PLC0415

            return bool(runtime_entity_passes_flag_gates(self.entity, get_flag=getter))
        return True

    def get_interact_label(self, _actor: Any | None = None) -> str | None:
        return str(getattr(self.entity, "mesh_name", "") or "Door").strip() or "Door"

    def subscribed_event_types(self) -> frozenset[str] | None:
        return frozenset({self.event_type}) if self.event_type else frozenset()

    def on_event(self, event: MeshEvent) -> None:  # noqa: D401
        if not self.event_type or event.type != self.event_type:
            return
        if self.event_field:
            payload = event.payload or {}
            candidate = payload.get(self.event_field)
            if self.event_value is not None:
                if str(candidate) != self.event_value:
                    return
            elif candidate is None:
                return
        self._trigger_transition(reason=f"event:{event.type}")

    def _trigger_transition(self, *, reason: str, actor: Sprite | None = None) -> None:
        if not self.target_scene:
            return
        from engine.scene_entity_gating import runtime_entity_passes_flag_gates  # noqa: PLC0415

        getter = getattr(self.window, "get_flag", None)
        if callable(getter) and not runtime_entity_passes_flag_gates(self.entity, get_flag=getter):
            return
        if self.once and self._triggered:
            return
        if self.once:
            self._triggered = True
        spawn_id = self.spawn_id or None
        if spawn_id:
            setter = getattr(self.window, "set_next_spawn_point", None)
            if callable(setter):
                setter(spawn_id)
        emitter = getattr(self.window, "emit_signal", None)
        if callable(emitter):
            payload = {
                "entity": self.entity_name,
                "reason": reason,
                "target_scene": self.target_scene,
                "spawn_id": spawn_id,
                "actor": getattr(actor, "mesh_name", None) if actor else None,
            }
            emitter("scene_transition", **payload)
        self._log(
            f"Transitioning to '{self.target_scene}'"
            + (f" via spawn '{spawn_id}'" if spawn_id else "")
        )
        requester = getattr(self.window, "request_scene_change", None)
        if callable(requester):
            requester(self.target_scene)

    def _log(self, message: str) -> None:
        logger = getattr(self.window, "console_log", None)
        if callable(logger):
            logger(message)
        else:
            print(f"[Mesh][SceneTransition] {message}")
