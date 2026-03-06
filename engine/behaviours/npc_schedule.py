from __future__ import annotations

from typing import Any, Callable, List, cast

from ..event_emit import emit_gameplay_event
from .base import Behaviour, ParamDef
from .patrol import PatrolBehaviour
from .registry import register_behaviour

_SWALLOW_ONCE_TAGS: set[str] = set()


def _log_swallow(tag: str, context: str) -> None:
    if tag in _SWALLOW_ONCE_TAGS:
        return
    _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger
    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)


def _norm_hour(value: float) -> float:
    return float(value) % 24.0


@register_behaviour(
    "NpcSchedule",
    description="Switches NPC position or patrol route based on time-of-day windows.",
    config_fields=[
        {
            "name": "schedules",
            "type": "array",
            "default": [],
            "description": "List of schedule blocks with start/end hours and stand/patrol actions.",
        },
    ],
)
class NpcSchedule(Behaviour):
    PARAM_DEFS = {
        "schedules": ParamDef(
            list,
            default=[],
            description="List of schedule blocks with start/end hours and stand/patrol actions.",
        ),
    }

    def __init__(self, entity, window, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self._patrol_behaviour: PatrolBehaviour | None = self._find_patrol_behaviour()
        self._schedules: list[dict[str, Any]] = [self._normalize_schedule(block) for block in (self.config.get("schedules") or [])]
        self._active_index: int | None = None
        self._last_active_index: int | None = None

        t = self._get_time_of_day_hours()
        self._active_index = self._find_active_schedule_index(t)
        self._last_active_index = self._active_index
        if self._active_index is not None:
            self._apply_schedule(self._active_index, initial=True)

    def _log_exception_once(self, key: str, exc: Exception) -> None:
        logged = getattr(self, "_mesh_logged_exceptions", None)
        if not isinstance(logged, set):
            logged = set()
            setattr(self, "_mesh_logged_exceptions", logged)
        if key in logged:
            return
        logged.add(key)
        print(f"[Mesh][NpcSchedule] ERROR {key}: {exc}")

    # ------------------------------------------------------------------
    def _normalize_schedule(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            return {}
        sched = dict(raw)
        sched["start_hour"] = _norm_hour(float(sched.get("start_hour", 0.0)))
        sched["end_hour"] = _norm_hour(float(sched.get("end_hour", 0.0)))
        mode = str(sched.get("mode", "stand") or "stand").lower()
        if mode not in {"stand", "patrol"}:
            mode = "stand"
        sched["mode"] = mode
        return sched

    def _find_patrol_behaviour(self) -> PatrolBehaviour | None:
        runtime = getattr(self.entity, "mesh_behaviours_runtime", []) or []
        for beh in runtime:
            if isinstance(beh, PatrolBehaviour):
                return beh
            if hasattr(beh, "set_path_id") or hasattr(beh, "patrol_points"):
                return cast(PatrolBehaviour, beh)
        return None

    def _get_time_of_day_hours(self) -> float:
        dn = getattr(self.window, "day_night", None) or getattr(self.window, "day_night_controller", None)
        if dn is not None:
            getter = getattr(dn, "get_time_of_day_hours", None)
            if callable(getter):
                try:
                    return float(getter())
                except Exception as exc:  # noqa: BLE001  # REASON: npc schedule fallback isolation
                    _log_swallow("NPCS-001", "get_time_of_day_hours:getter")
                    self._log_exception_once("get_time_of_day_hours:getter", exc)
            if hasattr(dn, "hour"):
                try:
                    return float(getattr(dn, "hour"))
                except Exception as exc:  # noqa: BLE001  # REASON: npc schedule fallback isolation
                    _log_swallow("NPCS-002", "get_time_of_day_hours:hour")
                    self._log_exception_once("get_time_of_day_hours:hour", exc)
        gs = getattr(self.window, "game_state_controller", None)
        if gs is not None:
            val = gs.get_var("time_of_day_hours", None)
            if isinstance(val, (int, float)):
                return float(val)
        return 12.0

    def _is_time_in_range(self, t: float, start: float, end: float) -> bool:
        if start == end:
            return False
        if start < end:
            return start <= t < end
        return t >= start or t < end

    def _find_active_schedule_index(self, t: float) -> int | None:
        for idx, sched in enumerate(self._schedules):
            start = sched.get("start_hour", 0.0)
            end = sched.get("end_hour", 0.0)
            if self._is_time_in_range(t, start, end):
                return idx
        return None

    def _apply_schedule(self, index: int, *, initial: bool = False) -> None:
        if index < 0 or index >= len(self._schedules):
            return
        sched = self._schedules[index]
        mode = (sched.get("mode") or "stand").lower()
        if mode == "patrol":
            self._apply_patrol_schedule(sched)
        else:
            self._apply_stand_schedule(sched)

        enter_event = sched.get("enter_event") or ""
        if enter_event:
            if initial or self._last_active_index != index:
                try:
                    emit_gameplay_event(
                        self.window,
                        enter_event,
                        {
                            "entity": getattr(self.entity, "mesh_name", None),
                            "schedule_index": index,
                            "mode": mode,
                        },
                        source_entity_id=str(getattr(self.entity, "mesh_id", "") or ""),
                        source_behaviour="NpcSchedule",
                    )
                except Exception as exc:  # noqa: BLE001  # REASON: npc schedule fallback isolation
                    _log_swallow("NPCS-003", "emit_enter_event")
                    self._log_exception_once("emit_enter_event", exc)

    # Stand mode ------------------------------------------------------
    def _apply_stand_schedule(self, sched: dict[str, Any]) -> None:
        x = sched.get("x", None)
        y = sched.get("y", None)
        if x is not None:
            try:
                self.entity.center_x = float(x)
            except Exception as exc:  # noqa: BLE001  # REASON: npc schedule fallback isolation
                _log_swallow("NPCS-004", "set_center_x")
                self._log_exception_once("set_center_x", exc)
        if y is not None:
            try:
                self.entity.center_y = float(y)
            except Exception as exc:  # noqa: BLE001  # REASON: npc schedule fallback isolation
                _log_swallow("NPCS-005", "set_center_y")
                self._log_exception_once("set_center_y", exc)
        facing = sched.get("facing")
        if facing:
            controller = getattr(self.entity, "controller", None)
            if controller is not None and hasattr(controller, "set_facing"):
                try:
                    controller.set_facing(str(facing))
                except Exception as exc:  # noqa: BLE001  # REASON: npc schedule fallback isolation
                    _log_swallow("NPCS-006", "set_facing")
                    self._log_exception_once("set_facing", exc)
        self._disable_patrol()

    # Patrol mode -----------------------------------------------------
    def _apply_patrol_schedule(self, sched: dict[str, Any]) -> None:
        patrol_id = sched.get("patrol_id")
        patrol_points: list[Any] | None = sched.get("patrol_points")
        if patrol_points and self._patrol_behaviour is not None:
            points: List[tuple[float, float]] = []
            for p in patrol_points:
                try:
                    points.append((float(p["x"]), float(p["y"])))
                except Exception:
                    _log_swallow("NPCS-007", "_apply_patrol_schedule: parse patrol point")
                    continue
            self._patrol_behaviour.points = points
            self._patrol_behaviour.current_index = 0
            self._patrol_behaviour._disabled = len(points) < 2
        if patrol_id and self._patrol_behaviour is not None:
            set_path_id = getattr(self._patrol_behaviour, "set_path_id", None)
            if callable(set_path_id):
                try:
                    cast(Callable[[Any], None], set_path_id)(patrol_id)
                except Exception as exc:  # noqa: BLE001  # REASON: npc schedule fallback isolation
                    _log_swallow("NPCS-008", "set_path_id")
                    self._log_exception_once("set_path_id", exc)
            else:
                cfg = getattr(self._patrol_behaviour, "config", None)
                if isinstance(cfg, dict):
                    cfg["patrol_id"] = patrol_id
        self._enable_patrol()

    def _enable_patrol(self) -> None:
        if self._patrol_behaviour is None:
            return
        set_enabled = getattr(self._patrol_behaviour, "set_enabled", None)
        if callable(set_enabled):
            try:
                cast(Callable[[bool], None], set_enabled)(True)
                return
            except Exception as exc:  # noqa: BLE001  # REASON: npc schedule fallback isolation
                _log_swallow("NPCS-009", "enable_patrol")
                self._log_exception_once("enable_patrol", exc)
        self._patrol_behaviour._disabled = False

    def _disable_patrol(self) -> None:
        if self._patrol_behaviour is None:
            return
        set_enabled = getattr(self._patrol_behaviour, "set_enabled", None)
        if callable(set_enabled):
            try:
                cast(Callable[[bool], None], set_enabled)(False)
                return
            except Exception as exc:  # noqa: BLE001  # REASON: npc schedule fallback isolation
                _log_swallow("NPCS-010", "disable_patrol")
                self._log_exception_once("disable_patrol", exc)
        self._patrol_behaviour._disabled = True

    # ------------------------------------------------------------------
    def update(self, delta_time: float) -> None:  # noqa: ARG002
        t = self._get_time_of_day_hours()
        idx = self._find_active_schedule_index(t)
        if idx != self._active_index:
            self._active_index = idx
            if idx is not None:
                self._apply_schedule(idx, initial=False)
        self._last_active_index = self._active_index
