"""Data-driven cutscene controller for scripted sequences."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.logging_tools import get_logger
from engine.schema_validation import validate
from engine.swallowed_exceptions import _log_swallow

logger = get_logger(__name__)


@dataclass(slots=True)
class CutsceneStep:
    type: str
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Cutscene:
    id: str
    steps: List[CutsceneStep]


class CutsceneController:
    """Runs simple step-based cutscenes and blocks player input while active."""

    def __init__(self, window) -> None:
        self.window = window
        self.cutscenes: dict[str, Cutscene] = {}
        self.active: Optional[Cutscene] = None
        self.step_index: int = -1
        self.step_elapsed: float = 0.0
        self._step_state: dict[str, Any] = {}

    @property
    def is_running(self) -> bool:
        return self.active is not None

    # ------------------------------------------------------------------
    # Cutscene definitions
    # ------------------------------------------------------------------
    def register_cutscenes(self, entries: list[dict[str, Any]]) -> None:
        for entry in entries:
            cutscene = self._parse_cutscene(entry)
            if cutscene:
                self.cutscenes[cutscene.id] = cutscene

    def load_from_file(self, path: str) -> None:
        p = Path(path)
        raw = json.loads(p.read_text(encoding="utf-8"))
        validate(raw, "cutscene.schema.json", p)
        raw_entries = raw.get("cutscenes", [])
        self.register_cutscenes([e for e in raw_entries if isinstance(e, dict)])

    def _parse_cutscene(self, payload: dict[str, Any]) -> Optional[Cutscene]:
        cid = str(payload.get("id") or "").strip()
        if not cid:
            return None
        steps_raw = payload.get("steps") or []
        steps: list[CutsceneStep] = []
        for step in steps_raw:
            if not isinstance(step, dict):
                continue
            stype = str(step.get("type") or "").strip().lower()
            if not stype:
                continue
            data = dict(step)
            data.pop("type", None)
            steps.append(CutsceneStep(type=stype, data=data))
        return Cutscene(id=cid, steps=steps)

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------
    def play_cutscene(self, cutscene_id: str) -> bool:
        cs = self.cutscenes.get(cutscene_id)
        if cs is None:
            print(f"[Mesh][Cutscene] Unknown cutscene '{cutscene_id}'")
            return False
        self.active = cs
        self.step_index = 0
        self.step_elapsed = 0.0
        self._step_state = {}
        print(f"[Mesh][Cutscene] Playing '{cutscene_id}'")
        return True

    def stop(self) -> None:
        self.active = None
        self.step_index = -1
        self.step_elapsed = 0.0
        self._step_state = {}

    def update(self, dt: float) -> None:
        if not self.active:
            return
        if self.step_index >= len(self.active.steps):
            self.stop()
            return
        step = self.active.steps[self.step_index]
        done = self._update_step(step, dt)
        if done:
            self.step_index += 1
            self.step_elapsed = 0.0
            self._step_state = {}
            if self.step_index >= len(self.active.steps):
                self.stop()

    # ------------------------------------------------------------------
    # Step processing
    # ------------------------------------------------------------------
    def _update_step(self, step: CutsceneStep, dt: float) -> bool:
        stype = step.type
        self.step_elapsed += dt
        data = step.data
        if stype == "wait":
            duration = float(data.get("duration", 0.0))
            return self.step_elapsed >= duration
        if stype == "start_dialogue":
            return self._step_start_dialogue(data)
        if stype == "wait_dialogue_end":
            return self._step_wait_dialogue_end(data)
        if stype == "move_entity":
            return self._step_move_entity(data, dt)
        if stype == "camera_focus":
            return self._step_camera_focus(data)
        if stype == "camera_pan":
            return self._step_camera_pan(data, dt)
        if stype == "set_flag":
            return self._step_set_flag(data)
        if stype == "add_counter":
            return self._step_add_counter(data)
        if stype == "emit_event":
            return self._step_emit_event(data)
        # Unknown step: skip
        return True

    def _find_entity(self, identifier: Any):
        sc = getattr(self.window, "scene_controller", None)
        if sc is None:
            return None
        return sc.find_sprite(identifier)

    def _step_move_entity(self, data: dict[str, Any], dt: float) -> bool:
        target_name = data.get("entity") or data.get("target")
        sprite = self._find_entity(target_name)
        if sprite is None:
            return True
        dest_x = float(data.get("x", sprite.center_x))
        dest_y = float(data.get("y", sprite.center_y))
        duration = max(0.001, float(data.get("duration", 0.0)))
        state = self._step_state
        if not state:
            state["start_x"] = sprite.center_x
            state["start_y"] = sprite.center_y
        start_x = state.get("start_x", sprite.center_x)
        start_y = state.get("start_y", sprite.center_y)
        t = min(1.0, self.step_elapsed / duration)
        sprite.center_x = start_x + (dest_x - start_x) * t
        sprite.center_y = start_y + (dest_y - start_y) * t
        return t >= 1.0

    def _step_camera_focus(self, data: dict[str, Any]) -> bool:
        target_name = data.get("entity") or data.get("target")
        sprite = self._find_entity(target_name) if target_name else None
        if sprite is None:
            return True
        self._set_camera_position(sprite.center_x, sprite.center_y)
        return True

    def _step_camera_pan(self, data: dict[str, Any], dt: float) -> bool:
        cam = getattr(self.window, "camera_controller", None)
        if cam is None or cam.camera is None:
            return True
        dest_x = float(data.get("x", 0.0))
        dest_y = float(data.get("y", 0.0))
        duration = max(0.001, float(data.get("duration", 0.0)))
        state = self._step_state
        if not state:
            cx, cy = cam.get_camera_center()
            state["start_x"] = cx
            state["start_y"] = cy
        start_x = state.get("start_x", 0.0)
        start_y = state.get("start_y", 0.0)
        t = min(1.0, self.step_elapsed / duration)
        nx = start_x + (dest_x - start_x) * t
        ny = start_y + (dest_y - start_y) * t
        self._set_camera_position(nx, ny)
        return t >= 1.0

    def _step_set_flag(self, data: dict[str, Any]) -> bool:
        gs = getattr(self.window, "game_state_controller", None)
        if gs is None:
            return True
        name = data.get("name") or data.get("flag")
        value = data.get("value", True)
        gs.set_flag(str(name), bool(value))
        return True

    def _step_add_counter(self, data: dict[str, Any]) -> bool:
        gs = getattr(self.window, "game_state_controller", None)
        if gs is None:
            return True
        name = data.get("name") or data.get("counter")
        delta = data.get("delta", 0)
        gs.add_counter(str(name), float(delta))
        return True

    def _step_emit_event(self, data: dict[str, Any]) -> bool:
        bus = getattr(self.window, "event_bus", None)
        event_type = data.get("event") or data.get("name")
        if bus is not None and event_type:
            try:
                bus.emit(event_type, **{k: v for k, v in data.items() if k not in {"type", "event", "name"}})
            except Exception as exc:  # noqa: BLE001  # REASON: runtime fallback isolation
                logger.error("[Mesh][Cutscene] emit_event failed: %s", exc)
        return True

    def _step_start_dialogue(self, data: dict[str, Any]) -> bool:
        """Start a dialogue; returns immediately and rely on wait_dialogue_end to block."""
        entries = data.get("entries") or data.get("lines")
        speaker = data.get("speaker") or ""
        text = data.get("text")
        target_id = str(data.get("target") or "").strip()
        dialogue_id = str(data.get("dialogue_id") or "").strip()
        node_id = data.get("node_id")
        if target_id or dialogue_id:
            target = self._find_entity(target_id) if target_id else None
            candidates = [target] if target is not None else list(getattr(getattr(self.window, "scene_controller", None), "all_sprites", []) or [])
            try:
                for entity in candidates:
                    for behaviour in getattr(entity, "behaviours", []):
                        if type(behaviour).__name__ != "DialogueRunnerBehaviour":
                            continue
                        if dialogue_id and getattr(behaviour, "dialogue_id", "") != dialogue_id:
                            continue
                        behaviour.start(node_id if isinstance(node_id, str) and node_id else None)
                        return True
            except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
                _log_swallow("CUTS-001", "engine/cutscene_controller.py start_dialogue behaviour.start", once=True)
            return True
        owner = "cutscene"
        ui = getattr(self.window, "ui_controller", None)
        if entries is None and text:
            entries = [{"speaker": speaker, "text": text}]
        if ui is not None and entries:
            try:
                ui.show_dialogue(entries, owner=owner)
            except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
                _log_swallow("CUTS-002", "engine/cutscene_controller.py start_dialogue ui.show_dialogue", once=True)
        return True

    def _step_wait_dialogue_end(self, data: dict[str, Any]) -> bool:  # noqa: ARG002
        """Block until dialogue owned by cutscene is closed."""
        ui = getattr(self.window, "ui_controller", None)
        if ui is None:
            return True
        return not ui.is_dialogue_active(owner="cutscene")

    def _set_camera_position(self, x: float, y: float) -> None:
        cam = getattr(self.window, "camera_controller", None)
        if cam is None or cam.camera is None:
            return
        camera = cam.camera
        mover = getattr(camera, "move_to", None)
        if callable(mover):
            try:
                mover((x, y))
                return
            except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
                _log_swallow("CUTS-004", "engine/cutscene_controller.py blanket swallow", once=True)
        try:
            camera.position = (x, y)
        except Exception:  # noqa: BLE001  # REASON: runtime fallback isolation
            _log_swallow("CUTS-005", "engine/cutscene_controller.py blanket swallow", once=True)
