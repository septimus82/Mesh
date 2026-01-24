"""Behaviour that hides/disables sprites until state flags are satisfied."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from .base import Behaviour, ParamDef
from .registry import register_behaviour
import engine.optional_arcade as optional_arcade

if TYPE_CHECKING:  # pragma: no cover - typing only
    import optional_arcade.arcade


@register_behaviour(
    "ConditionalActivator",
    description="Enables a sprite only when required flags are set and forbidden flags remain false.",
    config_fields=[
        {
            "name": "require_flags",
            "description": "List of flag names that must be true",
            "type": "array",
            "default": [],
        },
        {
            "name": "forbid_flags",
            "description": "List of flag names that must remain false",
            "type": "array",
            "default": [],
        },
        {
            "name": "refresh_rate",
            "description": "Seconds between requirement checks (0 = every frame)",
            "type": "float",
            "default": 0.0,
        },
    ],
)
class ConditionalActivator(Behaviour):
    """Toggles sprite visibility + collision membership based on quest flags."""

    PARAM_DEFS = {
        "require_flags": ParamDef(list, default=[], description="List of flag names that must be true"),
        "forbid_flags": ParamDef(list, default=[], description="List of flag names that must remain false"),
        "refresh_rate": ParamDef(float, default=0.0, description="Seconds between requirement checks (0 = every frame)"),
    }

    def __init__(self, entity: "optional_arcade.arcade.Sprite", window, **config) -> None:  # type: ignore[override]
        merged = self._merge_entity_data(entity, config)
        super().__init__(entity, window, **merged)

        require_source = merged.get("require_flags") or merged.get("flags")
        forbid_source = merged.get("forbid_flags") or merged.get("forbidden_flags")
        self.require_flags = self._normalize_flag_list(require_source)
        self.forbid_flags = self._normalize_flag_list(forbid_source)
        self.refresh_rate = max(0.0, float(self.config.get("refresh_rate", 0.0) or 0.0))
        self.config["require_flags"] = list(self.require_flags)
        self.config["forbid_flags"] = list(self.forbid_flags)
        self._time_until_check = 0.0
        self._was_solid = bool(getattr(entity, "mesh_is_solid", False))
        self._visible_when_active = bool(getattr(entity, "visible", True))
        self._active: bool | None = None
        self._apply_state(self._requirements_met())

    @staticmethod
    def _merge_entity_data(entity: "optional_arcade.arcade.Sprite", config: Dict[str, Any] | None) -> Dict[str, Any]:
        data = dict(getattr(entity, "mesh_entity_data", {}) or {})
        if config:
            data.update(config)
        return data

    def update(self, dt: float) -> None:  # noqa: D401
        if self.refresh_rate > 0.0:
            self._time_until_check -= dt
            if self._time_until_check > 0.0:
                return
            self._time_until_check = self.refresh_rate
        desired = self._requirements_met()
        self._apply_state(desired)

    def _requirements_met(self) -> bool:
        window = getattr(self, "window", None)
        getter = getattr(window, "get_flag", None)
        if not callable(getter):
            return not self.require_flags and not self.forbid_flags
        for flag in self.require_flags:
            if not getter(flag):
                return False
        for flag in self.forbid_flags:
            if getter(flag):
                return False
        return True

    def _apply_state(self, enabled: bool) -> None:
        if self._active is not None and self._active == enabled:
            return
        self._active = enabled
        sprite = self.entity
        sprite.visible = bool(self._visible_when_active and enabled)
        sprite.alpha = 255 if sprite.visible else 0
        if self._was_solid:
            if enabled:
                self._ensure_in_solids()
            else:
                self._remove_from_solids()

    def _ensure_in_solids(self) -> None:

        solids = getattr(self.window, "solid_sprites", None)
        if not isinstance(solids, optional_arcade.arcade.SpriteList):
            return
        if self.entity not in solids:
            solids.append(self.entity)

    def _remove_from_solids(self) -> None:

        solids = getattr(self.window, "solid_sprites", None)
        if not isinstance(solids, optional_arcade.arcade.SpriteList):
            return
        try:
            solids.remove(self.entity)
        except ValueError:
            pass

    def _normalize_flag_list(self, payload: Any) -> List[str]:
        values: List[str] = []
        if isinstance(payload, (list, tuple)):
            iterable = payload
        elif isinstance(payload, str):
            iterable = [part.strip() for part in payload.replace(";", ",").split(",")]
        else:
            iterable = []
        for entry in iterable:
            name = str(entry or "").strip()
            if name:
                values.append(name)
        return values
