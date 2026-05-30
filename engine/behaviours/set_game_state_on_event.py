"""Behaviour that mutates global game_state when events fire."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, List

if TYPE_CHECKING:
    from arcade import Sprite

from ..events import MeshEvent
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "SetGameStateOnEvent",
    description="Listens for a Mesh event and toggles flags / increments counters when it fires.",
    config_fields=[
        {
            "name": "event_type",
            "description": "Mesh event name to react to (required)",
            "type": "string",
            "default": "",
        },
        {
            "name": "payload_field",
            "description": "Optional payload key that must exist",
            "type": "string",
            "default": "",
        },
        {
            "name": "payload_value",
            "description": "Optional value that payload_field must equal (string compare)",
            "type": "string",
            "default": "",
        },
        {
            "name": "set_flags",
            "description": "Object mapping flag names to booleans",
            "type": "object",
            "default": {},
        },
        {
            "name": "clear_flags",
            "description": "List of flags that should be forced to false",
            "type": "array",
            "default": [],
        },
        {
            "name": "inc_counters",
            "description": "Object mapping counter names to amounts to add",
            "type": "object",
            "default": {},
        },
        {
            "name": "require_flags",
            "description": "List of flags that must be true to apply the mutation",
            "type": "array",
            "default": [],
        },
        {
            "name": "forbid_flags",
            "description": "List of flags that must be false to apply the mutation",
            "type": "array",
            "default": [],
        },
        {
            "name": "once",
            "description": "Apply the mutation only the first time the event fires",
            "type": "bool",
            "default": False,
        },
        {
            "name": "message",
            "description": "Optional console message when the state update runs",
            "type": "string",
            "default": "",
        },
        {
            "name": "toast",
            "description": "Optional HUD toast message when the state update runs",
            "type": "string",
            "default": "",
        },
        {
            "name": "toast_seconds",
            "description": "Optional toast duration in seconds",
            "type": "float",
            "default": 0.0,
        },
    ],
)
class SetGameStateOnEvent(Behaviour):
    """Declarative hook that keeps quest/state flags in sync with runtime events."""

    PARAM_DEFS = {
        "event_type": ParamDef(str, default="", description="Mesh event name to react to"),
        "payload_field": ParamDef(str, default="", description="Optional payload key that must exist"),
        "payload_value": ParamDef(str, default="", description="Optional value that payload_field must equal"),
        "set_flags": ParamDef(dict, default={}, description="Object mapping flag names to booleans"),
        "clear_flags": ParamDef(list, default=[], description="List of flags that should be forced to false"),
        "inc_counters": ParamDef(dict, default={}, description="Object mapping counters to add amounts"),
        "require_flags": ParamDef(list, default=[], description="List of flags that must be true"),
        "forbid_flags": ParamDef(list, default=[], description="List of flags that must be false"),
        "once": ParamDef(bool, default=False, description="Apply the mutation only the first time"),
        "message": ParamDef(str, default="", description="Optional console message"),
        "toast": ParamDef(str, default="", description="Optional HUD toast message"),
        "toast_seconds": ParamDef(float, default=0.0, description="Optional toast duration in seconds"),
    }

    def __init__(self, entity: Sprite, window, **config) -> None:
        merged = self._merge_entity_data(entity, config)
        super().__init__(entity, window, **merged)
        self.event_type = str(merged.get("event_type", "")).strip()
        self.payload_field = str(merged.get("payload_field", "")).strip()
        raw_value = merged.get("payload_value")
        self.payload_value = str(raw_value).strip() if raw_value not in (None, "") else None
        self.once = bool(merged.get("once", False))
        self.message = str(merged.get("message", ""))
        self.toast = str(merged.get("toast", ""))
        self.toast_seconds = float(merged.get("toast_seconds", 0.0) or 0.0)
        self.flags_to_set = self._normalize_flag_map(merged.get("set_flags") or merged.get("flags"))
        self.flags_to_clear = self._normalize_name_list(merged.get("clear_flags"))
        self.counter_increments = self._normalize_counter_map(
            merged.get("inc_counters") or merged.get("add_counters")
        )
        self.require_flags = self._normalize_name_list(merged.get("require_flags"))
        self.forbid_flags = self._normalize_name_list(merged.get("forbid_flags") or merged.get("forbidden_flags"))
        self._consumed = False
        if not self.event_type:
            print("[Mesh][SetGameStateOnEvent] WARNING: event_type is required")
        if not (self.flags_to_set or self.flags_to_clear or self.counter_increments):
            print("[Mesh][SetGameStateOnEvent] WARNING: no flags/counters configured")

        self._unsubscribe: Callable[[], None] | None
        self._unsubscribe = None
        if self.event_type:
            self._unsubscribe = self.window.event_bus.subscribe(self.event_type, self.on_event)

    def destroy(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    @staticmethod
    def _merge_entity_data(entity: Sprite, config: Dict[str, Any] | None) -> Dict[str, Any]:
        data = dict(getattr(entity, "mesh_entity_data", {}) or {})
        if config:
            data.update(config)
        return data

    def subscribed_event_types(self) -> frozenset[str] | None:
        return frozenset({self.event_type}) if self.event_type else frozenset()

    def on_event(self, event: MeshEvent) -> None:  # noqa: D401
        if self._consumed:
            return
        if not self.event_type or event.type != self.event_type:
            return
        if self.payload_field:
            payload = event.payload or {}
            candidate = payload.get(self.payload_field)
            if self.payload_value is not None:
                if str(candidate) != self.payload_value:
                    return
            elif candidate is None:
                return
        if not self._requirements_met():
            return
        self._apply_mutations(event)
        if self.once:
            self._consumed = True

    def _requirements_met(self) -> bool:
        window = getattr(self, "window", None)
        getter = getattr(window, "get_flag", None) if window is not None else None
        if not callable(getter):
            return not self.require_flags and not self.forbid_flags
        for flag in self.require_flags:
            if not getter(flag, False):
                return False
        for flag in self.forbid_flags:
            if getter(flag, False):
                return False
        return True

    def _apply_mutations(self, event: MeshEvent) -> None:
        window = getattr(self, "window", None)
        if window is None:
            return
        setter = getattr(window, "set_flag", None)
        incrementer = getattr(window, "inc_counter", None)
        if callable(setter):
            for flag, value in self.flags_to_set.items():
                setter(flag, value)
        if callable(setter):
            for flag in self.flags_to_clear:
                setter(flag, False)
        if callable(incrementer):
            for counter, amount in self.counter_increments.items():
                incrementer(counter, amount)
        if self.message:
            payload = dict(event.payload or {})
            payload.setdefault("entity", getattr(self.entity, "mesh_name", "<unnamed>"))
            payload.setdefault("event", event.type)
            self._log(self.message.format_map(_SafeMap(payload)))
        if self.toast:
            hud = getattr(window, "player_hud", None)
            enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
            if callable(enqueue):
                payload = dict(event.payload or {})
                payload.setdefault("entity", getattr(self.entity, "mesh_name", "<unnamed>"))
                payload.setdefault("event", event.type)
                seconds = float(self.toast_seconds) if self.toast_seconds > 0.0 else 4.0
                enqueue(str(self.toast).format_map(_SafeMap(payload)), seconds=seconds)

    def _normalize_flag_map(self, payload: Any) -> Dict[str, bool]:
        result: Dict[str, bool] = {}
        if isinstance(payload, dict):
            for key, value in payload.items():
                name = str(key or "").strip()
                if not name:
                    continue
                result[name] = bool(value)
        elif isinstance(payload, (list, tuple)):
            for entry in payload:
                name = str(entry or "").strip()
                if name:
                    result[name] = True
        elif isinstance(payload, str):
            name = payload.strip()
            if name:
                result[name] = True
        return result

    def _normalize_name_list(self, payload: Any) -> List[str]:
        values: List[str] = []
        if isinstance(payload, (list, tuple)):
            source = payload
        elif isinstance(payload, str):
            source = [part.strip() for part in payload.replace(";", ",").split(",")]
        else:
            source = []
        for entry in source:
            name = str(entry or "").strip()
            if name:
                values.append(name)
        return values

    def _normalize_counter_map(self, payload: Any) -> Dict[str, float]:
        result: Dict[str, float] = {}
        if not isinstance(payload, dict):
            return result
        for key, value in payload.items():
            name = str(key or "").strip()
            if not name:
                continue
            amount = self._to_float(value)
            if amount is None:
                continue
            result[name] = amount
        return result

    def _to_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _log(self, message: str) -> None:
        logger = getattr(self.window, "console_log", None)
        if callable(logger):
            logger(message)
        else:
            print(f"[Mesh][SetGameStateOnEvent] {message}")


class _SafeMap(dict):
    def __missing__(self, key: str) -> str:  # pragma: no cover - formatting helper
        return "{" + key + "}"
