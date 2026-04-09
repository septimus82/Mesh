"""SequencePlayer behaviour that runs simple scripted cutscenes."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from arcade import Sprite

from ..events import MeshEvent
from .base import Behaviour, ParamDef
from .registry import register_behaviour


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)


@register_behaviour(
    "SequencePlayer",
    description="Runs declarative cutscene steps such as waits, movement, dialogue, and events.",
    config_fields=[
        {
            "name": "steps",
            "description": "Ordered list of step dictionaries (type+fields)",
            "type": "array",
            "default": [],
        },
        {
            "name": "auto_start",
            "description": "Automatically begin once after the scene loads",
            "type": "bool",
            "default": False,
        },
        {
            "name": "start_event",
            "description": "Mesh event that triggers the sequence",
            "type": "string",
            "default": "",
        },
        {
            "name": "event_field",
            "description": "Optional payload field that must exist for start_event",
            "type": "string",
            "default": "",
        },
        {
            "name": "event_value",
            "description": "Optional value that event_field must equal before starting",
            "type": "string",
            "default": "",
        },
        {
            "name": "lock_player_input",
            "description": "Lock PlayerController input while the sequence is active",
            "type": "bool",
            "default": True,
        },
        {
            "name": "lock_owner",
            "description": "Custom owner label for the input lock (defaults to entity name)",
            "type": "string",
            "default": "",
        },
        {
            "name": "once",
            "description": "Prevent re-triggering after the sequence finishes",
            "type": "bool",
            "default": True,
        },
        {
            "name": "default_move_speed",
            "description": "Fallback speed (units/sec) for move steps",
            "type": "float",
            "default": 120.0,
        },
        {
            "name": "move_tolerance",
            "description": "Distance threshold (px) treated as reaching the target",
            "type": "float",
            "default": 2.0,
        },
    ],
)
class SequencePlayer(Behaviour):
    """Executes a list of declarative steps to build lightweight cutscenes."""

    _MIN_LINE_DURATION = 0.2

    PARAM_DEFS = {
        "steps": ParamDef(list, default=[], description="Ordered list of step dictionaries"),
        "auto_start": ParamDef(bool, default=False, description="Automatically begin once after the scene loads"),
        "start_event": ParamDef(str, default="", description="Mesh event that triggers the sequence"),
        "event_field": ParamDef(str, default="", description="Optional payload field that must exist"),
        "event_value": ParamDef(str, default="", description="Optional value to match"),
        "lock_player_input": ParamDef(bool, default=True, description="Lock PlayerController input while active"),
        "lock_owner": ParamDef(str, default="", description="Custom owner label for the input lock"),
        "once": ParamDef(bool, default=True, description="Prevent re-triggering after the sequence finishes"),
        "default_move_speed": ParamDef(float, default=120.0, description="Fallback speed for move steps"),
        "move_tolerance": ParamDef(float, default=2.0, description="Distance threshold treated as reaching the target"),
    }

    def __init__(self, entity: Sprite, window, **config) -> None:
        merged = dict(getattr(entity, "mesh_entity_data", {}) or {})
        if config:
            merged.update(config)
        super().__init__(entity, window, **merged)

        self.entity_name = getattr(entity, "mesh_name", "<unnamed>")
        steps_source = merged.get("steps") or merged.get("sequence") or []
        self.steps = self._normalize_steps(steps_source)
        self.auto_start = bool(merged.get("auto_start", False))
        self.start_event = str(merged.get("start_event", "")).strip()
        self.event_field = str(merged.get("event_field", "")).strip()
        raw_event_value = merged.get("event_value")
        self.event_value = (
            str(raw_event_value).strip()
            if raw_event_value not in (None, "")
            else None
        )
        self.lock_player_input = bool(merged.get("lock_player_input", True))
        owner_hint = str(merged.get("lock_owner", self.entity_name)).strip() or self.entity_name
        self._lock_owner = f"sequence::{owner_hint}"
        self.once = bool(merged.get("once", True))
        raw_default_move_speed = merged.get("default_move_speed", merged.get("move_speed", 120.0))
        if raw_default_move_speed is None:
            raw_default_move_speed = 120.0
        self.default_move_speed = float(raw_default_move_speed)
        self.move_tolerance = max(0.5, float(merged.get("move_tolerance", 2.0)))
        self.config.update(
            {
                "steps": self.steps,
                "auto_start": self.auto_start,
                "start_event": self.start_event,
                "event_field": self.event_field,
                "event_value": self.event_value,
                "lock_player_input": self.lock_player_input,
                "lock_owner": owner_hint,
                "once": self.once,
                "default_move_speed": self.default_move_speed,
                "move_tolerance": self.move_tolerance,
            },
        )
        self._active = False
        self._has_started = False
        self._step_index = 0
        self._step_state: dict[str, Any] = {}
        self._pending_auto = self.auto_start
        self._dialogue_owner = f"sequence.dialogue::{self.entity_name}"
        self._lock_applied = False

        if not self.steps:
            print(f"[Mesh][Sequence] WARNING: No steps configured for '{self.entity_name}'")

    # ------------------------------------------------------------------
    # Lifecycle helpers

    def update(self, dt: float) -> None:  # noqa: D401
        if not self.steps:
            return
        if not self._active:
            if self._pending_auto:
                started = self.start(trigger="auto")
                if started:
                    self._pending_auto = False
            return

        if self._step_index >= len(self.steps):
            self._finish_sequence(reason="complete")
            return

        step = self.steps[self._step_index]
        handler = self._get_step_handler(step)
        if handler is None:
            self._log(f"Unknown step type '{step.get('type')}', skipping")
            self._advance_step()
            return
        completed = handler(step, dt)
        if completed:
            self._advance_step()

    def on_event(self, event: MeshEvent) -> None:  # noqa: D401
        if self.start_event and event.type == self.start_event:
            if self._event_matches(event.payload or {}) and self._can_start_again():
                self.start(trigger=f"event:{event.type}")

        if not self._active or not self.steps:
            return
        if self._step_index >= len(self.steps):
            return
        current = self.steps[self._step_index]
        if current.get("type") != "wait_for_event":
            return
        expected_type = str(current.get("event") or current.get("event_type") or "").strip()
        if expected_type and event.type != expected_type:
            return
        if self._event_matches(event.payload or {}, step=current):
            self._step_state["event_received"] = True

    def start(self, *, trigger: str | None = None) -> bool:
        if not self.steps:
            self._log("Cannot start sequence with no steps configured")
            return False
        if self._active:
            return False
        if not self._can_start_again():
            return False
        self._active = True
        self._has_started = True
        self._step_index = 0
        self._step_state = {}
        self._pending_auto = False
        if self.lock_player_input:
            self._apply_player_lock()
        if trigger:
            self._log(f"Sequence started ({trigger})")
        return True

    def _can_start_again(self) -> bool:
        if not self.once:
            return True
        return not self._has_started or not self._active

    def _finish_sequence(self, *, reason: str) -> None:
        if not self._active:
            return
        self._release_player_lock()
        self._close_dialogue_if_needed()
        self._active = False
        self._step_index = 0
        self._step_state = {}
        self._pending_auto = False
        self._log(f"Sequence finished ({reason})")

    def _advance_step(self) -> None:
        lock_suspended = bool(self._step_state.get("lock_suspended"))
        self._step_index += 1
        has_more = self._step_index < len(self.steps)
        if lock_suspended and has_more and self.lock_player_input:
            self._apply_player_lock()
        self._step_state = {}
        if not has_more:
            self._finish_sequence(reason="complete")

    # ------------------------------------------------------------------
    # Step handlers

    def _get_step_handler(self, step: dict[str, Any]):
        step_type = str(step.get("type", "")).strip().lower()
        method_name = f"_step_{step_type}".replace("-", "_")
        handler = getattr(self, method_name, None)
        return handler if callable(handler) else None

    def _step_wait(self, step: dict[str, Any], dt: float) -> bool:
        duration = max(0.0, float(step.get("duration", 0.0)))
        state = self._step_state
        if "remaining" not in state:
            state["remaining"] = duration
        state["remaining"] = max(0.0, float(state["remaining"]) - dt)
        remaining = state.get("remaining", 0.0)
        return float(remaining) <= 0.0

    def _step_signal(self, step: dict[str, Any], dt: float) -> bool:  # noqa: ARG002
        event_type = str(step.get("event") or step.get("event_type") or "").strip()
        if not event_type:
            return True
        payload = step.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        payload = dict(payload)
        payload.setdefault("entity", self.entity_name)
        self.window.emit_signal(event_type, **payload)
        return True

    def _step_move_to(self, step: dict[str, Any], dt: float) -> bool:
        entity = getattr(self, "entity", None)
        window = getattr(self, "window", None)
        if entity is None or window is None:
            return True
        state = self._step_state
        if "target" not in state:
            target = self._compute_move_target(step, entity)
            state["target"] = target
        target_x, target_y = state["target"]
        dx = target_x - entity.center_x
        dy = target_y - entity.center_y
        distance = math.hypot(dx, dy)
        tolerance = max(0.1, float(step.get("tolerance", self.move_tolerance)))
        if distance <= tolerance:
            entity.center_x = target_x
            entity.center_y = target_y
            return True
        speed = float(step.get("speed", self.default_move_speed))
        if speed <= 0:
            entity.center_x = target_x
            entity.center_y = target_y
            return True
        vx = (dx / distance) * speed if distance > 0 else 0.0
        vy = (dy / distance) * speed if distance > 0 else 0.0
        window.move_entity_with_collision(entity, vx, vy, dt)
        return False

    def _compute_move_target(self, step: dict[str, Any], entity: Sprite) -> tuple[float, float]:
        current_x = float(entity.center_x)
        current_y = float(entity.center_y)
        relative = bool(step.get("relative"))
        target_x = step.get("x")
        target_y = step.get("y")
        offset_x = step.get("dx", 0.0)
        offset_y = step.get("dy", 0.0)
        if target_x is None:
            target_x = current_x
        else:
            target_x = float(target_x)
            if relative:
                target_x = current_x + target_x
        if target_y is None:
            target_y = current_y
        else:
            target_y = float(target_y)
            if relative:
                target_y = current_y + target_y
        target_x += float(offset_x or 0.0)
        target_y += float(offset_y or 0.0)
        return (float(target_x), float(target_y))

    def _step_dialogue(self, step: dict[str, Any], dt: float) -> bool:
        window = getattr(self, "window", None)
        if window is None:
            return True
        state = self._step_state
        if not state:
            if bool(step.get("lock_player_input") is False) and self.lock_player_input:
                self._release_player_lock()
                state["lock_suspended"] = True
            entries = self._build_dialogue_entries(step)
            if not entries:
                return True
            started = window.show_dialogue(entries, owner=self._dialogue_owner)
            if not started:
                return True
            state["auto_advance"] = bool(
                step.get("auto_advance", not bool(step.get("wait_for_close", False)))
            )
            state["line_duration"] = max(
                self._MIN_LINE_DURATION,
                float(step.get("line_duration") or step.get("duration") or 2.0),
            )
            state["elapsed"] = 0.0
            state["wait_for_close"] = bool(step.get("wait_for_close", False))
            state["post_wait"] = max(0.0, float(step.get("post_wait", 0.0)))

        if state.get("auto_advance") and window.is_dialogue_active(owner=self._dialogue_owner):
            state["elapsed"] += dt
            if state["elapsed"] >= state["line_duration"]:
                progressed = window.advance_dialogue(owner=self._dialogue_owner)
                state["elapsed"] = 0.0
                if not progressed:
                    # Box already closed after exhausting entries.
                    pass

        if not window.is_dialogue_active(owner=self._dialogue_owner):
            post_wait = float(state.get("post_wait", 0.0))
            if post_wait > 0.0:
                post_wait = max(0.0, post_wait - dt)
                state["post_wait"] = post_wait
                return post_wait <= 0.0
            return True

        wait_for_close = bool(state.get("wait_for_close", False))
        if wait_for_close:
            return False
        return False

    def _step_wait_for_event(self, step: dict[str, Any], dt: float) -> bool:
        state = self._step_state
        if "event_received" not in state:
            state["event_received"] = False
            state["timeout"] = max(0.0, float(step.get("timeout", 0.0)))
            state["elapsed"] = 0.0
        event_received = bool(state.get("event_received", False))
        if event_received:
            return True
        timeout = state.get("timeout", 0.0)
        if timeout > 0.0:
            state["elapsed"] += dt
            if state["elapsed"] >= timeout:
                return True
        return False

    # ------------------------------------------------------------------
    # Helper utilities

    def _event_matches(self, payload: dict[str, Any], step: dict[str, Any] | None = None) -> bool:
        field = self.event_field
        value = self.event_value
        if step is not None:
            field = str(step.get("field") or step.get("payload_field") or field).strip()
            raw_value = step.get("value")
            if raw_value in (None, ""):
                raw_value = step.get("payload_value")
            value = (
                str(raw_value).strip()
                if raw_value not in (None, "")
                else value
            )
        if not field:
            return True
        candidate = payload.get(field)
        if value is None:
            return candidate is not None
        return str(candidate) == str(value)

    def _build_dialogue_entries(self, step: dict[str, Any]) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        default_speaker = str(step.get("speaker") or self.entity_name)
        raw_lines = step.get("lines") or step.get("entries")
        if isinstance(raw_lines, dict):
            raw_lines = [raw_lines]
        if raw_lines is None and step.get("text"):
            raw_lines = [step]
        for entry in self._iter_dialogue_entries(raw_lines, default_speaker):
            entries.append(entry)
        return entries

    def _iter_dialogue_entries(
        self,
        lines: Any,
        default_speaker: str,
    ) -> Iterable[dict[str, str]]:
        if isinstance(lines, list):
            source = lines
        else:
            source = []
        for raw in source:
            if isinstance(raw, str):
                text = raw.strip()
                if not text:
                    continue
                yield {"speaker": default_speaker, "text": text}
            elif isinstance(raw, dict):
                text = str(raw.get("text", "")).strip()
                if not text:
                    continue
                speaker = str(raw.get("speaker", default_speaker)).strip() or default_speaker
                yield {"speaker": speaker, "text": text}

    def _normalize_steps(self, raw_steps: Any) -> list[dict[str, Any]]:
        if isinstance(raw_steps, dict):
            raw = raw_steps.get("steps") if "steps" in raw_steps else None
            if isinstance(raw, list):
                raw_steps = raw
            else:
                raw_steps = [raw_steps]
        if not isinstance(raw_steps, Iterable):
            return []
        normalized: list[dict[str, Any]] = []
        for entry in raw_steps:
            if isinstance(entry, str):
                step_type = entry.strip().lower()
                if not step_type:
                    continue
                normalized.append({"type": step_type})
                continue
            if not isinstance(entry, dict):
                continue
            step_type = str(
                entry.get("type")
                or entry.get("action")
                or entry.get("step")
                or ""
            ).strip()
            if not step_type:
                continue
            clean = dict(entry)
            clean["type"] = step_type.lower()
            normalized.append(clean)
        return normalized

    def _apply_player_lock(self) -> None:
        if self._lock_applied or not self.lock_player_input:
            return
        locker = getattr(self.window, "lock_player_input", None)
        if callable(locker):
            try:
                locker(owner=self._lock_owner)
                self._lock_applied = True
            except Exception:  # pragma: no cover - defensive
                self._lock_applied = False

    def _release_player_lock(self) -> None:
        if not self._lock_applied:
            return
        unlocker = getattr(self.window, "unlock_player_input", None)
        if callable(unlocker):
            try:
                unlocker(owner=self._lock_owner)
            except Exception:  # pragma: no cover - defensive
                _log_swallow("SEQU-001", "engine/behaviours/sequence_player.py pass-only blanket swallow")
                pass
        self._lock_applied = False

    def _close_dialogue_if_needed(self) -> None:
        window = getattr(self, "window", None)
        if window is None:
            return
        is_active = getattr(window, "is_dialogue_active", None)
        if callable(is_active):
            try:
                if not is_active(owner=self._dialogue_owner):
                    return
            except Exception:  # pragma: no cover - defensive
                return
        closer = getattr(window, "close_dialogue", None)
        if callable(closer):
            try:
                closer(owner=self._dialogue_owner)
            except Exception:  # pragma: no cover - defensive
                return

    def _log(self, message: str) -> None:
        window = getattr(self, "window", None)
        if window is None:
            print(f"[Mesh][Sequence] {self.entity_name}: {message}")
            return
        logger = getattr(window, "console_log", None)
        if callable(logger):
            logger(f"[Sequence:{self.entity_name}] {message}")
        else:
            print(f"[Mesh][Sequence] {self.entity_name}: {message}")
