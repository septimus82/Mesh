from __future__ import annotations

from typing import Any

from ..events import MeshEventBus
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "TimeOfDayGate",
    description="Enables/disables an entity based on time-of-day windows.",
    config_fields=[
        {"name": "start_hour", "type": "float", "default": 6.0, "description": "Hour when gate becomes active."},
        {"name": "end_hour", "type": "float", "default": 20.0, "description": "Hour when gate becomes inactive."},
        {"name": "invert", "type": "bool", "default": False, "description": "If true, active outside the window."},
        {"name": "affect_visibility", "type": "bool", "default": True, "description": "Toggle entity visibility."},
        {"name": "open_event", "type": "string", "default": "", "description": "Event to emit when becoming active."},
        {"name": "close_event", "type": "string", "default": "", "description": "Event to emit when becoming inactive."},
    ],
)
class TimeOfDayGate(Behaviour):
    PARAM_DEFS = {
        "start_hour": ParamDef(float, default=6.0, description="Hour when gate becomes active."),
        "end_hour": ParamDef(float, default=20.0, description="Hour when gate becomes inactive."),
        "invert": ParamDef(bool, default=False, description="If true, active outside the window."),
        "affect_visibility": ParamDef(bool, default=True, description="Toggle entity visibility."),
        "open_event": ParamDef(str, default="", description="Event emitted when entering active window."),
        "close_event": ParamDef(str, default="", description="Event emitted when leaving active window."),
    }

    def __init__(self, entity, window, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self._start_hour = float(self.config.get("start_hour", 6.0)) % 24.0
        self._end_hour = float(self.config.get("end_hour", 20.0)) % 24.0
        self._invert = bool(self.config.get("invert", False))
        self._affect_visibility = bool(self.config.get("affect_visibility", True))
        self._open_event = str(self.config.get("open_event", "") or "")
        self._close_event = str(self.config.get("close_event", "") or "")
        self._bus = getattr(window, "event_bus", None)

        t = self._get_time_of_day_hours()
        self._active = self._compute_active(t)
        self._last_active = self._active
        self._apply_active_state(initial=True)

    # ------------------------------------------------------------------
    def _get_time_of_day_hours(self) -> float:
        dn = getattr(self.window, "day_night", None) or getattr(self.window, "day_night_controller", None)
        if dn is not None and hasattr(dn, "hour"):
            try:
                return float(dn.hour)
            except Exception as exc:  # noqa: BLE001
                if not getattr(self, "_mesh_day_night_hour_error_logged", False):
                    print(f"[Mesh][TimeOfDayGate] ERROR reading day/night hour: {exc}")
                    setattr(self, "_mesh_day_night_hour_error_logged", True)
        gs = getattr(self.window, "game_state_controller", None)
        if gs is not None:
            value = gs.get_var("time_of_day_hours", None)
            try:
                if value is not None:
                    return float(value)
            except (TypeError, ValueError):
                pass
        return 12.0

    def _compute_active(self, t: float) -> bool:
        start = self._start_hour
        end = self._end_hour
        within = False
        if start == end:
            within = False
        elif start < end:
            within = start <= t < end
        else:
            within = t >= start or t < end
        return within if not self._invert else not within

    def _emit(self, event_name: str) -> None:
        if not event_name:
            return
        if isinstance(self._bus, MeshEventBus):
            try:
                self._bus.emit(event_name, entity=getattr(self.entity, "mesh_name", None))
            except Exception as exc:  # noqa: BLE001
                if not getattr(self, "_mesh_emit_error_logged", False):
                    print(f"[Mesh][TimeOfDayGate] ERROR emitting '{event_name}': {exc}")
                    setattr(self, "_mesh_emit_error_logged", True)

    def _apply_active_state(self, *, initial: bool = False) -> None:
        if self._affect_visibility:
            try:
                self.entity.visible = bool(self._active)
            except Exception as exc:  # noqa: BLE001
                if not getattr(self, "_mesh_visible_error_logged", False):
                    print(f"[Mesh][TimeOfDayGate] ERROR setting entity visibility: {exc}")
                    setattr(self, "_mesh_visible_error_logged", True)
        if initial:
            return
        if self._active and self._open_event:
            self._emit(self._open_event)
        if (not self._active) and self._close_event:
            self._emit(self._close_event)

    # ------------------------------------------------------------------
    def update(self, delta_time: float) -> None:  # noqa: ARG002
        t = self._get_time_of_day_hours()
        self._active = self._compute_active(t)
        if self._active != self._last_active:
            self._apply_active_state(initial=False)
            self._last_active = self._active
