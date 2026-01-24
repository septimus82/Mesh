"""Base behaviour definitions for Mesh Engine."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Mapping

if TYPE_CHECKING:  # pragma: no cover - import guard for typing only
    from arcade import Sprite

    from engine.game import GameWindow

    from ..events import MeshEvent


@dataclass(slots=True)
class ParamDef:
    """Describes a typed behaviour parameter."""

    type: type | str
    default: Any = None
    description: str = ""


class Behaviour:
    """Base behaviour class; overrides implement update logic."""

    PARAM_DEFS: Dict[str, ParamDef] = {}

    def __init__(self, entity: "Sprite", window: "GameWindow", **config: Any) -> None:
        self.entity = entity
        self.window = window
        self._explicit_params: set[str] = set()
        self.config: dict[str, Any] = self._merge_param_config(config)

    # ------------------------------------------------------------------
    # Parameter helpers
    # ------------------------------------------------------------------
    @classmethod
    def param_defs(cls) -> dict[str, ParamDef]:
        """Return normalized parameter definitions declared on the class."""

        raw_defs = getattr(cls, "PARAM_DEFS", {}) or {}
        normalized: dict[str, ParamDef] = {}
        for name, definition in raw_defs.items():
            param = cls._coerce_param_def(definition)
            normalized[str(name)] = param
        return normalized

    @staticmethod
    def _coerce_param_def(definition: Any) -> ParamDef:
        if isinstance(definition, ParamDef):
            return definition
        if isinstance(definition, Mapping):
            return ParamDef(
                type=definition.get("type", str),
                default=definition.get("default"),
                description=definition.get("description", ""),
            )
        if isinstance(definition, tuple):
            length = len(definition)
            param_type = definition[0] if length >= 1 else str
            default = definition[1] if length >= 2 else None
            description = definition[2] if length >= 3 else ""
            return ParamDef(type=param_type, default=default, description=description)
        return ParamDef(type=str, default=definition)

    def _merge_param_config(self, overrides: Mapping[str, Any] | None) -> dict[str, Any]:
        incoming = dict(overrides or {})
        merged: dict[str, Any] = {}
        for name, definition in self.param_defs().items():
            raw_value = incoming.pop(name, _PARAM_SENTINEL)
            value = self._coerce_param_value(raw_value, definition)
            if raw_value is not _PARAM_SENTINEL:
                self._explicit_params.add(name)
            merged[name] = value
            setattr(self, name, value)
        for key, value in incoming.items():
            merged[key] = value
        return merged

    def _coerce_param_value(self, raw_value: Any, definition: ParamDef) -> Any:
        if raw_value is _PARAM_SENTINEL:
            return self._clone_default(definition.default)
        expected = definition.type
        kind = self._resolve_param_type(expected)
        try:
            if kind == "float":
                return float(raw_value)
            if kind == "int":
                return int(raw_value)
            if kind == "bool":
                if isinstance(raw_value, str):
                    lowered = raw_value.strip().lower()
                    if lowered in {"1", "true", "yes", "on"}:
                        return True
                    if lowered in {"0", "false", "no", "off"}:
                        return False
                return bool(raw_value)
            if kind == "array":
                if isinstance(raw_value, list):
                    return list(raw_value)
                if isinstance(raw_value, tuple):
                    return list(raw_value)
                if isinstance(raw_value, str):
                    return [chunk.strip() for chunk in raw_value.split(",") if chunk.strip()]
                return self._clone_default(definition.default or [])
            if kind == "object":
                if isinstance(raw_value, dict):
                    return dict(raw_value)
                return self._clone_default(definition.default or {})
            if kind == "string":
                if raw_value is None:
                    return ""
                return str(raw_value)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return self._clone_default(definition.default)
        return raw_value

    @staticmethod
    def _clone_default(value: Any) -> Any:
        if isinstance(value, (dict, list, set)):  # pragma: no cover - trivial
            return copy.deepcopy(value)
        return value

    @staticmethod
    def _resolve_param_type(expected: type | str | None) -> str:
        if expected in {int, "int"}:
            return "int"
        if expected in {float, "float"}:
            return "float"
        if expected in {bool, "bool"}:
            return "bool"
        if expected in {list, tuple, "array"}:
            return "array"
        if expected in {dict, "object"}:
            return "object"
        return "string"

    def pre_update(self, dt: float) -> None:  # pragma: no cover - default no-op
        """Run before movement and core update; subclasses override."""
        return

    def update(self, dt: float) -> None:  # pragma: no cover - default no-op
        """Advance behaviour state; subclasses override."""
        return

    def late_update(self, dt: float) -> None:  # pragma: no cover - default no-op
        """Run after movement and collisions; subclasses override."""
        return

    def on_event(self, event: "MeshEvent") -> None:  # pragma: no cover - default no-op
        """Handle Mesh events emitted during the frame."""
        return


_PARAM_SENTINEL = object()
