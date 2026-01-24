"""Dialogue behaviour that shows scripted lines via DialogueBox."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Tuple

if TYPE_CHECKING:
    from arcade import Sprite

from ..events import MeshEvent
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "Dialogue",
    description="Displays speaker-tagged lines when interacted with or when events fire.",
    config_fields=[
        {
            "name": "start_event",
            "description": "Mesh event name that auto-starts this dialogue",
            "type": "string",
            "default": "",
        },
        {
            "name": "event_field",
            "description": "Payload field to match when start_event triggers",
            "type": "string",
            "default": "",
        },
        {
            "name": "event_value",
            "description": "Optional value that the payload field must equal",
            "type": "string",
            "default": "",
        },
        {
            "name": "auto_start",
            "description": "Show this dialogue once automatically after load",
            "type": "bool",
            "default": False,
        },
        {
            "name": "once",
            "description": "Prevent replaying the dialogue after it finishes",
            "type": "bool",
            "default": True,
        },
        {
            "name": "dialogue",
            "description": "Inline dialogue object (speaker, lines, nodes, start, once)",
            "type": "object",
            "default": {},
        },
        {
            "name": "role",
            "description": "Role of the speaker (e.g. Merchant, Guard)",
            "type": "string",
            "default": "",
        },
        {
            "name": "dialogue_lines",
            "description": "Legacy array of dialogue line entries",
            "type": "array",
            "default": [],
        },
        {
            "name": "dialogue_nodes",
            "description": "Graph-based dialogue nodes map",
            "type": "object",
            "default": {},
        },
    ],
)
class Dialogue(Behaviour):
    """Feeds scripted or branching dialogue into the DialogueBox overlay."""

    PARAM_DEFS = {
        "start_event": ParamDef(str, default="", description="Mesh event name that auto-starts this dialogue"),
        "event_field": ParamDef(str, default="", description="Payload field to match when start_event triggers"),
        "event_value": ParamDef(str, default="", description="Optional value that the payload field must equal"),
        "auto_start": ParamDef(bool, default=False, description="Show this dialogue once automatically after load"),
        "once": ParamDef(bool, default=True, description="Prevent replaying the dialogue after it finishes"),
        "dialogue": ParamDef(dict, default={}, description="Inline dialogue object"),
        "dialogue_lines": ParamDef(list, default=[], description="Legacy array of dialogue line entries"),
        "dialogue_nodes": ParamDef(dict, default={}, description="Graph-based dialogue nodes map"),
    }

    def __init__(self, entity: Sprite, window, **config) -> None:  # type: ignore[override]
        merged = self._merge_entity_data(entity, config)
        super().__init__(entity, window, **merged)
        self.entity_name = getattr(entity, "mesh_name", "<unnamed>")
        self.start_event = str(merged.get("start_event", "")).strip()
        self.event_field = str(merged.get("event_field", "")).strip()
        raw_value = merged.get("event_value")
        self.event_value = str(raw_value).strip() if raw_value not in (None, "") else None
        self.auto_start = bool(merged.get("auto_start", merged.get("dialogue_auto_start", False)))
        self.once = bool(merged.get("once", merged.get("dialogue_once", True)))
        self.config["start_event"] = self.start_event
        self.config["event_field"] = self.event_field
        self.config["event_value"] = self.event_value
        self.config["auto_start"] = self.auto_start
        self.config["once"] = self.once
        self._script = self._build_script(merged)
        self._graph_nodes, self._graph_start = self._build_graph(merged)
        self._owner_id = f"dialogue::{self.entity_name}"
        self._pending_auto = self.auto_start
        self._active = False
        self._has_played = False
        self._graph_active = False
        self._current_node_id: str | None = None
        self._choice_history: set[str] = set()
        self._last_actor: str | None = None
        self._ignore_interact_press_once: bool = False

        if not self._script and not self._graph_nodes:
            print(f"[Mesh][Dialogue] WARNING: No dialogue lines configured for '{self.entity_name}'")

    @staticmethod
    def _merge_entity_data(entity: Sprite, config: Dict[str, Any] | None) -> Dict[str, Any]:
        data = dict(getattr(entity, "mesh_entity_data", {}) or {})
        if config:
            data.update(config)
        return data

    # --- linear dialogue helpers -------------------------------------------

    def _build_script(self, data: Dict[str, Any]) -> List[dict[str, str]]:
        entries: List[dict[str, str]] = []
        default_speaker = str(data.get("dialogue_speaker") or self.entity_name)
        dialogue_root = data.get("dialogue")
        if isinstance(dialogue_root, dict):
            default_speaker = str(dialogue_root.get("speaker") or default_speaker)
            entries.extend(self._normalize_lines(dialogue_root.get("lines"), default_speaker))
            if "once" in dialogue_root:
                self.once = bool(dialogue_root.get("once"))
            if "auto_start" in dialogue_root:
                self.auto_start = bool(dialogue_root.get("auto_start"))
            if "start_event" in dialogue_root:
                self.start_event = str(dialogue_root.get("start_event", "")).strip()
        elif isinstance(dialogue_root, list):
            entries.extend(self._normalize_lines(dialogue_root, default_speaker))

        if not entries:
            entries.extend(self._normalize_lines(data.get("dialogue_lines"), default_speaker))

        single_line = data.get("dialogue_line") or data.get("dialogue_text") or data.get("text")
        if not entries and single_line:
            entries.append({"speaker": default_speaker, "text": str(single_line)})
        return entries

    def _normalize_lines(self, lines: Any, default_speaker: str) -> List[dict[str, str]]:
        normalized: List[dict[str, str]] = []
        if not isinstance(lines, list):
            return normalized
        for entry in lines:
            if isinstance(entry, str):
                text = entry.strip()
                if text:
                    normalized.append({"speaker": default_speaker, "text": text})
            elif isinstance(entry, dict):
                text = str(entry.get("text", "")).strip()
                if not text:
                    continue
                speaker = str(entry.get("speaker", default_speaker)).strip() or default_speaker
                normalized.append({"speaker": speaker, "text": text})
        return normalized

    # --- dialogue graph parsing --------------------------------------------

    def _build_graph(self, data: Dict[str, Any]) -> Tuple[dict[str, dict[str, Any]], str | None]:
        dialogue_root = data.get("dialogue")
        nodes_root = None
        start_node: str | None = None
        default_speaker = str(data.get("dialogue_speaker") or self.entity_name)
        if isinstance(dialogue_root, dict):
            nodes_root = dialogue_root.get("nodes")
            start_node = str(dialogue_root.get("start", "")).strip() or None
            if "speaker" in dialogue_root:
                default_speaker = str(dialogue_root.get("speaker") or default_speaker)
        if nodes_root is None:
            nodes_root = data.get("dialogue_nodes")
        normalized: dict[str, dict[str, Any]] = {}
        fallback_start: str | None = None
        for node_id, raw in self._iter_nodes(nodes_root):
            clean_id = str(node_id or "").strip()
            if not clean_id or not isinstance(raw, dict):
                continue
            normalized_node = self._normalize_node(clean_id, raw, default_speaker)
            if not normalized_node:
                continue
            normalized[clean_id] = normalized_node
            if fallback_start is None:
                fallback_start = clean_id
        if not normalized:
            return ({}, None)
        if not start_node:
            start_node = fallback_start
        return (normalized, start_node)

    def _iter_nodes(self, nodes_root: Any) -> Iterable[tuple[str, dict[str, Any]]]:
        if isinstance(nodes_root, dict):
            for node_id, payload in nodes_root.items():
                if isinstance(payload, dict):
                    yield str(node_id), payload
        elif isinstance(nodes_root, list):
            for payload in nodes_root:
                if not isinstance(payload, dict):
                    continue
                node_id = str(payload.get("id", "")).strip()
                if node_id:
                    yield node_id, payload

    def _normalize_node(self, node_id: str, data: dict[str, Any], default_speaker: str) -> dict[str, Any] | None:
        text = str(data.get("text", "")).strip()
        if not text:
            return None
        speaker = str(data.get("speaker", default_speaker)).strip() or default_speaker
        choices = self._normalize_choices(node_id, data.get("choices"))
        next_id = str(data.get("next", "")).strip() or None
        return {
            "id": node_id,
            "speaker": speaker,
            "text": text,
            "choices": choices,
            "next": next_id,
        }

    def _normalize_choices(self, node_id: str, raw_choices: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_choices, list):
            return []
        normalized: list[dict[str, Any]] = []
        auto_index = 0
        for entry in raw_choices:
            if isinstance(entry, str):
                text = entry.strip()
                if not text:
                    continue
                choice_data: dict[str, Any] = {"text": text}
            elif isinstance(entry, dict):
                text = str(entry.get("text", "")).strip()
                if not text:
                    continue
                choice_data = dict(entry)
                choice_data["text"] = text
            else:
                continue
            choice_id = str(choice_data.get("id", "")).strip()
            if not choice_id:
                choice_id = f"{node_id}_choice_{auto_index}"
                auto_index += 1
            choice = {
                "id": choice_id,
                "text": choice_data["text"],
                "next": str(choice_data.get("next", "")).strip() or None,
                "end": bool(choice_data.get("end") or choice_data.get("close")),
                "set_flags": self._normalize_flag_map(choice_data.get("set_flags")),
                "clear_flags": self._normalize_flag_list(choice_data.get("clear_flags")),
                "inc_counters": self._normalize_counter_map(choice_data.get("inc_counters")),
                "event": self._normalize_event_spec(choice_data.get("event") or choice_data.get("emit_event")),
                "event_payload": self._normalize_payload(choice_data.get("event_payload")),
                "require_flags": self._normalize_flag_list(choice_data.get("require_flags")),
                "forbid_flags": self._normalize_flag_list(choice_data.get("forbid_flags")),
                "once": bool(choice_data.get("once", False)),
            }
            normalized.append(choice)
        return normalized

    def _normalize_flag_map(self, value: Any) -> dict[str, bool]:
        if not isinstance(value, dict):
            return {}
        result: dict[str, bool] = {}
        for key, raw in value.items():
            name = str(key or "").strip()
            if not name:
                continue
            result[name] = bool(raw)
        return result

    def _normalize_flag_list(self, value: Any) -> list[str]:
        result: list[str] = []
        if value is None:
            return result
        if isinstance(value, str):
            value = [entry.strip() for entry in value.split(",") if entry.strip()]
        if isinstance(value, list):
            for entry in value:
                name = str(entry or "").strip()
                if name:
                    result.append(name)
        return result

    def _normalize_counter_map(self, value: Any) -> dict[str, float]:
        if not isinstance(value, dict):
            return {}
        normalized: dict[str, float] = {}
        for key, raw in value.items():
            name = str(key or "").strip()
            if not name:
                continue
            try:
                normalized[name] = float(raw)
            except (TypeError, ValueError):
                continue
        return normalized

    def _normalize_event_spec(self, value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None
            return {"type": cleaned, "payload": {}}
        if isinstance(value, dict):
            event_type = str(value.get("type") or value.get("event") or "").strip()
            if not event_type:
                return None
            payload = value.get("payload")
            if not isinstance(payload, dict):
                payload = {
                    key: val
                    for key, val in value.items()
                    if key not in {"type", "event", "payload"}
                }
            return {"type": event_type, "payload": dict(payload)}
        return None

    def _normalize_payload(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        return {}

    # --- behaviour lifecycle -----------------------------------------------

    def update(self, dt: float) -> None:  # noqa: D401 ARG002
        if self._pending_auto and (self._script or self._graph_nodes):
            if self._start_dialogue(trigger="auto"):
                self._pending_auto = False
                self._emit_line_event(stage="auto", actor_name=self._last_actor)
        if self._active and self._is_box_active():
            self._handle_dialogue_input()
        if self._active and not self._is_box_active():
            self._handle_dialogue_finished(reason="closed", actor_name=self._last_actor)
        if self._graph_active and self._active:
            self._update_graph_inputs()
        if self._ignore_interact_press_once:
            self._ignore_interact_press_once = False

    def on_interact(self, window, actor: Sprite) -> None:
        if not self._script and not self._graph_nodes:
            return
        actor_name = getattr(actor, "mesh_name", None)
        if self._is_box_active():
            if self._graph_active:
                progressed = self._advance_graph_dialogue()
                if progressed:
                    self._emit_line_event(stage="advance", actor_name=self._last_actor)
            else:
                advanced = self._advance_dialogue()
                if advanced:
                    self._emit_line_event(stage="advance", actor_name=actor_name)
                else:
                    self._handle_dialogue_finished(reason="advance_complete", actor_name=actor_name)
            return
        if self.once and self._has_played:
            return
        started = self._start_dialogue(trigger="interact", actor_name=actor_name)
        if started:
            self._emit_line_event(stage="start", actor_name=actor_name)

    def on_event(self, event: MeshEvent) -> None:
        if not self.start_event or event.type != self.start_event:
            return
        if self.event_field:
            payload = event.payload or {}
            candidate = payload.get(self.event_field)
            if self.event_value is not None:
                if str(candidate) != self.event_value:
                    return
            elif candidate is None:
                return
        if self.once and self._has_played and not self._is_box_active():
            return
        actor_name = None
        payload = event.payload or {}
        if "actor" in payload:
            actor_name = str(payload["actor"])
        started = self._start_dialogue(trigger=f"event:{event.type}", actor_name=actor_name)
        if started:
            self._emit_line_event(stage="event", actor_name=actor_name)

    def _start_dialogue(self, *, trigger: str, actor_name: str | None = None) -> bool:
        if not self._script and not self._graph_nodes:
            return False
        if self.once and self._has_played and not self._is_box_active():
            return False
        box = self._get_box()
        if box is None:
            print("[Mesh][Dialogue] WARNING: DialogueBox unavailable")
            return False
        if self._graph_nodes:
            success = self._start_graph_dialogue()
        else:
            success = box.play(self._script, owner=self._owner_id)
        if not success:
            return False
        self._has_played = True
        self._active = True
        self._last_actor = actor_name
        if trigger == "interact":
            self._ignore_interact_press_once = True
        self.window.emit_signal(
            "dialogue_started",
            entity=self.entity_name,
            owner=self._owner_id,
            trigger=trigger,
            actor=actor_name,
        )
        return True

    def _advance_dialogue(self) -> bool:
        if self._graph_nodes:
            return self._advance_graph_dialogue()
        box = self._get_box()
        if box is None:
            return False
        return box.advance(owner=self._owner_id)

    def _handle_dialogue_input(self) -> None:
        box = self._get_box()
        if box is None:
            return
        if getattr(box, "has_choices", lambda: False)():
            return
        if self._ignore_interact_press_once:
            return
        manager = getattr(self.window, "input", None)
        if manager is None:
            # Fallback to input_controller.manager if window.input is missing
            ctrl = getattr(self.window, "input_controller", None)
            manager = getattr(ctrl, "manager", None)
        if manager is None:
            return
        pressed = getattr(manager, "was_action_pressed", None)
        if not callable(pressed) or not pressed("interact"):
            return
        advanced = self._advance_dialogue()
        if advanced:
            self._emit_line_event(stage="advance", actor_name=self._last_actor)
        else:
            self._handle_dialogue_finished(reason="advance_complete", actor_name=self._last_actor)

    # --- branching support -------------------------------------------------

    def _start_graph_dialogue(self) -> bool:
        if not self._graph_nodes:
            return False
        start_id = self._graph_start or next(iter(self._graph_nodes))
        self._graph_active = True
        self._current_node_id = start_id
        return self._show_node(start_id)

    def _show_node(self, node_id: str) -> bool:
        node = self._graph_nodes.get(node_id)
        if not node:
            print(f"[Mesh][Dialogue] WARNING: Missing dialogue node '{node_id}' on '{self.entity_name}'")
            self._handle_dialogue_finished(reason="missing_node", actor_name=self._last_actor)
            return False
        box = self._get_box()
        if box is None:
            return False
        entry = self._build_entry_for_node(node)
        if box.play([entry], owner=self._owner_id):
            self._current_node_id = node_id
            return True
        return False

    def _build_entry_for_node(self, node: dict[str, Any]) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "speaker": node.get("speaker", self.entity_name),
            "text": node.get("text", ""),
        }
        rendered_choices: list[dict[str, Any]] = []
        for choice in node.get("choices") or []:
            available = self._choice_is_available(choice)
            rendered_choices.append(
                {
                    "id": choice.get("id"),
                    "text": choice.get("text", ""),
                    "disabled": not available,
                },
            )
        if rendered_choices:
            entry["choices"] = rendered_choices
        return entry

    def _choice_is_available(self, choice: dict[str, Any]) -> bool:
        if choice.get("once") and choice.get("id") in self._choice_history:
            return False
        state = getattr(self.window, "game_state", None)
        flags = getattr(state, "flags", {}) if state else {}
        for flag in choice.get("require_flags") or []:
            if not flags.get(flag, False):
                return False
        for flag in choice.get("forbid_flags") or []:
            if flags.get(flag, False):
                return False
        return True

    def _advance_graph_dialogue(self) -> bool:
        if not self._graph_active or not self._current_node_id:
            return False
        node = self._graph_nodes.get(self._current_node_id)
        if not node:
            return False
        box = self._get_box()
        if box is None:
            return False
        if getattr(box, "has_choices", lambda: False)():
            return False
        next_node = node.get("next")
        if next_node:
            if self._show_node(next_node):
                self._emit_line_event(stage="advance", actor_name=self._last_actor)
                return True
            return False
        self._handle_dialogue_finished(reason="advance_complete", actor_name=self._last_actor)
        return False

    def _update_graph_inputs(self) -> None:
        box = self._get_box()
        if box is None or not getattr(box, "has_choices", lambda: False)():
            return
        manager = getattr(self.window, "input", None)
        if manager is None:
            # Fallback to input_controller.manager if window.input is missing
            ctrl = getattr(self.window, "input_controller", None)
            manager = getattr(ctrl, "manager", None)
        if manager is None:
            return
        pressed = getattr(manager, "was_action_pressed", None)
        if not callable(pressed):
            return
        moved = False
        if pressed("move_up"):
            box.move_choice_cursor(-1, owner=self._owner_id)
            moved = True
        elif pressed("move_down"):
            box.move_choice_cursor(1, owner=self._owner_id)
            moved = True
        if moved:
            cursor = box.get_choice_cursor(owner=self._owner_id)
            if cursor is not None:
                self.window.emit_signal(
                    "dialogue_choice_cursor",
                    entity=self.entity_name,
                    owner=self._owner_id,
                    node=self._current_node_id,
                    index=cursor,
                )
        if self._ignore_interact_press_once:
            return
        if pressed("interact"):
            submitted = box.submit_choice(owner=self._owner_id)
            if submitted:
                self._handle_submitted_choice(submitted)

    def _handle_submitted_choice(self, submitted_choice: dict[str, Any]) -> None:
        node_id = self._current_node_id
        if not node_id:
            return
        node = self._graph_nodes.get(node_id)
        if node is None:
            return
        choice_id = submitted_choice.get("id")
        choice = None
        for candidate in node.get("choices", []):
            if candidate.get("id") == choice_id:
                choice = candidate
                break
        if choice is None or not self._choice_is_available(choice):
            return
        if choice.get("once"):
            self._choice_history.add(choice.get("id"))
        self._apply_choice_effects(choice)
        self._emit_choice_event(choice)
        next_node = choice.get("next")
        if next_node:
            if self._show_node(next_node):
                self._emit_line_event(stage="choice", actor_name=self._last_actor)
            return
        if choice.get("end") or not next_node:
            self._handle_dialogue_finished(reason="choice_complete", actor_name=self._last_actor)

    def _apply_choice_effects(self, choice: dict[str, Any]) -> None:
        window = self.window
        for name, value in (choice.get("set_flags") or {}).items():
            window.set_flag(name, bool(value))
        for name in choice.get("clear_flags") or []:
            window.set_flag(name, False)
        for name, amount in (choice.get("inc_counters") or {}).items():
            window.inc_counter(name, float(amount))
        event_spec = choice.get("event")
        payload = dict((event_spec.get("payload") if isinstance(event_spec, dict) else {}) or {})
        payload.update(choice.get("event_payload") or {})
        if isinstance(event_spec, dict):
            event_type = event_spec.get("type")
            if event_type:
                payload.setdefault("entity", self.entity_name)
                payload.setdefault("owner", self._owner_id)
                payload.setdefault("node", self._current_node_id)
                payload.setdefault("choice_id", choice.get("id"))
                window.emit_signal(event_type, **payload)

    def _emit_choice_event(self, choice: dict[str, Any]) -> None:
        self.window.emit_signal(
            "dialogue_choice",
            entity=self.entity_name,
            owner=self._owner_id,
            node=self._current_node_id,
            choice_id=choice.get("id"),
            choice_text=choice.get("text"),
            next=choice.get("next"),
            actor=self._last_actor,
        )

    # --- shared helpers ----------------------------------------------------

    def _handle_dialogue_finished(self, *, reason: str, actor_name: str | None = None) -> None:
        if not self._active:
            return
        self._active = False
        self._graph_active = False
        self._current_node_id = None
        box = self._get_box()
        if box is not None:
            box.clear(owner=self._owner_id)
        self.window.emit_signal(
            "dialogue_finished",
            entity=self.entity_name,
            owner=self._owner_id,
            reason=reason,
            actor=actor_name,
        )

    def _emit_line_event(self, *, stage: str, actor_name: str | None = None) -> None:
        box = self._get_box()
        if box is None:
            return
        entry = box.get_current_entry()
        if not entry:
            return
        payload = {
            "entity": self.entity_name,
            "owner": self._owner_id,
            "speaker": entry.get("speaker"),
            "text": entry.get("text"),
            "stage": stage,
            "actor": actor_name,
            "node": self._current_node_id,
            "has_choices": bool(entry.get("choices")),
        }
        self.window.emit_signal("dialogue_line", **payload)

    def _is_box_active(self) -> bool:
        box = self._get_box()
        return bool(box and box.is_active_for(self._owner_id))

    def _get_box(self):
        box = getattr(self.window, "dialogue_box", None)
        if box is None and hasattr(self.window, "ui_controller"):
            box = getattr(self.window.ui_controller, "dialogue_box", None)
        return box
