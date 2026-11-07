"""Behaviour that changes an object's picture when game flags change (a grave that's been dug)."""

from __future__ import annotations

from typing import Any

from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "PictureByFlags",
    description="Shows a different picture while flags allow it: the first matching rule wins, otherwise the object's own sprite.",
    config_fields=[
        {
            "name": "pictures",
            "description": "Rules: [{sprite, require_flags, forbid_flags}], checked in order",
            "type": "array",
            "default": [],
        },
    ],
)
class PictureByFlags(Behaviour):
    """Picks the entity's texture from flag rules every frame; cheap, and follows loads and edits."""

    PARAM_DEFS = {
        "pictures": ParamDef(list, default=[], description="Rules: [{sprite, require_flags, forbid_flags}]"),
    }

    def __init__(self, entity: Any, window: Any, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self.rules = [self._rule(raw) for raw in self.config.get("pictures") or [] if isinstance(raw, dict)]
        self.rules = [rule for rule in self.rules if rule["sprite"]]
        self._own_texture = getattr(entity, "texture", None)
        self._showing: str | None = None
        self.update(0.0)

    @staticmethod
    def _rule(raw: dict[str, Any]) -> dict[str, Any]:
        def names(value: Any) -> list[str]:
            items = value.split(",") if isinstance(value, str) else value if isinstance(value, list) else []
            return [str(item).strip() for item in items if str(item).strip()]

        return {"sprite": str(raw.get("sprite") or "").strip(),
                "require_flags": names(raw.get("require_flags")), "forbid_flags": names(raw.get("forbid_flags"))}

    def _allowed(self, rule: dict[str, Any]) -> bool:
        getter = getattr(self.window, "get_flag", None)
        if not callable(getter):
            return not rule["require_flags"]
        return all(getter(f) for f in rule["require_flags"]) and not any(getter(f) for f in rule["forbid_flags"])

    def update(self, dt: float) -> None:  # noqa: ARG002
        wanted = next((rule["sprite"] for rule in self.rules if self._allowed(rule)), None)
        if wanted == self._showing:
            return
        self._showing = wanted
        texture = self._own_texture
        if wanted is not None:
            assets = getattr(self.window, "assets", None)
            texture = assets.get_texture(wanted) if assets is not None else None
        if texture is not None:
            self.entity.texture = texture
