"""DialogueRunner behaviour - runs dialogue scripts deterministically.

Provides dialogue progression with branching choices.
Emits events for dialogue nodes, choices, and completion.

Events emitted:
- dialogue_started: When dialogue begins
- dialogue_node: When entering a node
- dialogue_choice: When player makes a choice
- dialogue_completed: When dialogue ends

Save/restore:
- Tracks current node, visited nodes, choice history
- Fully deterministic on restore
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from ..diagnostics import Diagnostic, diagnostics_to_text
from ..event_emit import emit_gameplay_event
from ..gameplay_event_bus import EventConfigError
from ..save_runtime.state_codec import decode_state, encode_state
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "DialogueRunner",
    description="Runs dialogue scripts with branching choices.",
    config_fields=[
        {
            "name": "script",
            "description": "Dialogue script (dict of nodes)",
            "type": "object",
            "default": {},
        },
        {
            "name": "start_node",
            "description": "Initial node ID to start from",
            "type": "string",
            "default": "start",
        },
        {
            "name": "auto_advance",
            "description": "Advance to next node automatically (no choices)",
            "type": "bool",
            "default": False,
        },
        {
            "name": "dialogue_id",
            "description": "Optional identifier for this dialogue",
            "type": "string",
            "default": "",
        },
        {
            "name": "enabled",
            "description": "Whether the dialogue runner is active",
            "type": "bool",
            "default": True,
        },
    ],
)
class DialogueRunnerBehaviour(Behaviour):
    """Dialogue runner that advances through a script deterministically.
    
    Script format:
    {
        "start": {
            "text": "Hello!",
            "speaker": "NPC",
            "choices": [
                {"text": "Hi!", "next": "response1"},
                {"text": "Bye!", "next": "end"}
            ],
            "next": null,  // Used if no choices
            "events": [{"type": "quest_started", "payload": {...}}]
        },
        ...
    }
    
    Implements SaveableBehaviour for deterministic save/restore.
    """

    TYPE_ID = "dialogue_runner"
    STATE_VERSION = 1

    PARAM_DEFS = {
        "script": ParamDef(dict, {}, "Dialogue script"),
        "start_node": ParamDef(str, "start", "Initial node ID"),
        "auto_advance": ParamDef(bool, False, "Auto-advance mode"),
        "dialogue_id": ParamDef(str, "", "Dialogue identifier"),
        "enabled": ParamDef(bool, True, "Whether active"),
    }

    def __init__(self, entity, window, **config) -> None:
        # Initialize private state before super().__init__ (which calls setattr for params)
        self._enabled: bool = True
        self._current_node: Optional[str] = None
        self._visited_nodes: List[str] = []
        self._choice_history: List[Dict[str, Any]] = []
        self._is_running: bool = False
        self._completed: bool = False
        self._last_restore_diagnostics: tuple[Diagnostic, ...] = ()

        super().__init__(entity, window, **config)

        # Config
        self.script = dict(self.config.get("script", {}))
        self.start_node = str(self.config.get("start_node", "start"))
        self.auto_advance = bool(self.config.get("auto_advance", False))
        self.dialogue_id = str(self.config.get("dialogue_id", "")).strip()
        self._enabled = bool(self.config.get("enabled", True))

    @property
    def enabled(self) -> bool:
        """Whether the dialogue runner is active."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)

    @property
    def is_running(self) -> bool:
        """Whether dialogue is currently active."""
        return self._is_running

    @property
    def current_node(self) -> Optional[str]:
        """Current node ID."""
        return self._current_node

    @property
    def current_node_data(self) -> Optional[Dict[str, Any]]:
        """Current node data dict."""
        if self._current_node is None:
            return None
        return self.script.get(self._current_node)

    @property
    def current_text(self) -> str:
        """Text of current node."""
        node = self.current_node_data
        if node is None:
            return ""
        return str(node.get("text", ""))

    @property
    def current_speaker(self) -> str:
        """Speaker of current node."""
        node = self.current_node_data
        if node is None:
            return ""
        return str(node.get("speaker", ""))

    @property
    def current_choices(self) -> List[Dict[str, Any]]:
        """Choices available at current node."""
        node = self.current_node_data
        if node is None:
            return []
        choices = node.get("choices", [])
        if not isinstance(choices, list):
            return []
        return list(choices)

    def start(self, node_id: Optional[str] = None) -> bool:
        """Start or restart dialogue from a node.
        
        Args:
            node_id: Node to start from (defaults to start_node).
            
        Returns:
            True if dialogue started successfully.
        """
        if not self._enabled:
            return False

        target = node_id or self.start_node
        if target not in self.script:
            return False

        self._is_running = True
        self._completed = False
        self._go_to_node(target, is_start=True)
        return True

    def stop(self) -> None:
        """Stop dialogue without completing."""
        self._is_running = False
        self._current_node = None

    def reset(self) -> None:
        """Reset dialogue to initial state."""
        self._current_node = None
        self._visited_nodes = []
        self._choice_history = []
        self._is_running = False
        self._completed = False

    def _emit_event(
        self,
        event_type: str,
        **kwargs,
    ) -> None:
        """Emit a gameplay event."""
        my_id = getattr(self.entity, "mesh_id", "")

        payload = {
            "dialogue_id": self.dialogue_id or my_id,
            "entity": my_id,
            "entity_name": getattr(self.entity, "mesh_name", ""),
            **kwargs,
        }

        emit_gameplay_event(
            self.window,
            event_type,
            payload,
            source_entity_id=my_id,
            source_behaviour="DialogueRunner",
        )

    def _go_to_node(self, node_id: str, is_start: bool = False) -> None:
        """Navigate to a specific node."""
        if node_id not in self.script:
            # Invalid node, end dialogue
            self._complete()
            return

        prev_node = self._current_node
        self._current_node = node_id

        # Track visited
        if node_id not in self._visited_nodes:
            self._visited_nodes.append(node_id)

        # Emit start event if beginning
        if is_start:
            self._emit_event(
                "dialogue_started",
                node=node_id,
            )

        # Emit node event
        node = self.script[node_id]
        self._emit_event(
            "dialogue_node",
            node=node_id,
            previous_node=prev_node,
            text=node.get("text", ""),
            speaker=node.get("speaker", ""),
            has_choices=bool(node.get("choices")),
        )

        # Emit any node-specific events
        for evt in node.get("events", []):
            if isinstance(evt, dict) and "type" in evt:
                evt_payload = dict(evt.get("payload", {}))
                self._emit_event(evt["type"], **evt_payload)

        # Handle auto-advance
        if self.auto_advance and not node.get("choices"):
            next_node = node.get("next")
            if next_node:
                self._go_to_node(next_node)
            else:
                self._complete()

    def _complete(self) -> None:
        """Complete the dialogue."""
        self._is_running = False
        self._completed = True
        self._emit_event(
            "dialogue_completed",
            visited_count=len(self._visited_nodes),
            choice_count=len(self._choice_history),
        )

    def choose(self, choice_index: int) -> bool:
        """Select a choice at the current node.
        
        Args:
            choice_index: Index of choice to select (0-based).
            
        Returns:
            True if choice was valid and processed.
        """
        if not self._is_running or self._current_node is None:
            return False

        choices = self.current_choices
        if choice_index < 0 or choice_index >= len(choices):
            return False

        choice = choices[choice_index]

        # Record choice
        self._choice_history.append({
            "node": self._current_node,
            "choice_index": choice_index,
            "choice_text": str(choice.get("text", "")),
        })

        # Emit choice event
        self._emit_event(
            "dialogue_choice",
            node=self._current_node,
            choice_index=choice_index,
            choice_text=choice.get("text", ""),
        )

        # Navigate to next node
        next_node = choice.get("next")
        if next_node:
            self._go_to_node(next_node)
        else:
            self._complete()

        return True

    def advance(self) -> bool:
        """Advance to next node (when no choices available).
        
        Returns:
            True if advanced successfully.
        """
        if not self._is_running or self._current_node is None:
            return False

        node = self.current_node_data
        if node is None:
            return False

        # Can't advance if there are choices
        if node.get("choices"):
            return False

        next_node = node.get("next")
        if next_node:
            self._go_to_node(next_node)
            return True
        else:
            self._complete()
            return True

    def has_visited(self, node_id: str) -> bool:
        """Check if a node has been visited."""
        return node_id in self._visited_nodes

    # SaveableBehaviour protocol
    def _inner_save_state(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "current_node": self._current_node,
            "visited_nodes": list(self._visited_nodes),
            "choice_history": list(self._choice_history),
            "is_running": self._is_running,
            "completed": self._completed,
        }

    def saveable_state(self) -> Dict[str, Any]:
        """Return JSON-serializable wrapped state dict."""
        return encode_state(self.TYPE_ID, self.STATE_VERSION, self._inner_save_state())

    @staticmethod
    def _is_legacy_v0_payload(payload: Mapping[str, Any]) -> bool:
        required = {
            "enabled",
            "current_node",
            "visited_nodes",
            "choice_history",
            "is_running",
            "completed",
        }
        return required.issubset(set(payload.keys()))

    @staticmethod
    def _adapt_legacy_v0(payload: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "enabled": bool(payload.get("enabled", True)),
            "current_node": payload.get("current_node"),
            "visited_nodes": list(payload.get("visited_nodes", [])),
            "choice_history": list(payload.get("choice_history", [])),
            "is_running": bool(payload.get("is_running", False)),
            "completed": bool(payload.get("completed", False)),
        }

    def restore_state(
        self,
        state: Dict[str, Any],
        *,
        strict: bool = True,
        source: str = "dialogue_runner",
    ) -> None:
        """Apply previously saved state."""
        inner_state, diagnostics = decode_state(
            state,
            expected_type_id=self.TYPE_ID,
            supported_versions={self.STATE_VERSION},
            strict=bool(strict),
            source=str(source),
            legacy_v0_predicate=self._is_legacy_v0_payload,
            legacy_v0_adapter=self._adapt_legacy_v0,
        )
        self._last_restore_diagnostics = tuple(diagnostics)
        if inner_state is None:
            if strict:
                details = diagnostics_to_text(self._last_restore_diagnostics).strip()
                if details:
                    raise ValueError(details)
                raise ValueError("dialogue_runner restore failed")
            return

        self._enabled = bool(inner_state.get("enabled", True))
        self._current_node = inner_state.get("current_node")
        self._visited_nodes = list(inner_state.get("visited_nodes", []))
        self._choice_history = list(inner_state.get("choice_history", []))
        self._is_running = bool(inner_state.get("is_running", False))
        self._completed = bool(inner_state.get("completed", False))

    def get_inspector_state(self) -> Dict[str, Any]:
        """Return state summary for editor inspection."""
        return {
            "enabled": self._enabled,
            "is_running": self._is_running,
            "completed": self._completed,
            "current_node": self._current_node,
            "current_text": self.current_text[:50] + ("..." if len(self.current_text) > 50 else ""),
            "current_speaker": self.current_speaker,
            "choice_count": len(self.current_choices),
            "visited_count": len(self._visited_nodes),
            "total_choices_made": len(self._choice_history),
            "node_count": len(self.script),
        }


def validate_dialogue_script(
    script: Dict[str, Any],
    *,
    entity_id: str = "",
    behaviour_name: str = "DialogueRunner",
) -> List[EventConfigError]:
    """Validate dialogue script structure.
    
    Args:
        script: Script dictionary.
        entity_id: Entity ID for error reporting.
        behaviour_name: Behaviour name for error reporting.
        
    Returns:
        List of validation errors.
    """
    errors: List[EventConfigError] = []

    if not isinstance(script, dict):
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="script",
            message=f"script must be a dict, got {type(script).__name__}",
        ))
        return errors

    # Validate each node
    for node_id, node in script.items():
        path_prefix = f"script.{node_id}"

        if not isinstance(node, dict):
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path=path_prefix,
                message=f"node must be a dict, got {type(node).__name__}",
            ))
            continue

        # Validate choices
        choices = node.get("choices", [])
        if choices and not isinstance(choices, list):
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path=f"{path_prefix}.choices",
                message=f"choices must be a list, got {type(choices).__name__}",
            ))
        elif isinstance(choices, list):
            for i, choice in enumerate(choices):
                if not isinstance(choice, dict):
                    errors.append(EventConfigError(
                        entity_id=entity_id,
                        behaviour_name=behaviour_name,
                        config_path=f"{path_prefix}.choices[{i}]",
                        message=f"choice must be a dict, got {type(choice).__name__}",
                    ))
                elif "next" in choice:
                    next_id = choice["next"]
                    if next_id is not None and next_id not in script:
                        errors.append(EventConfigError(
                            entity_id=entity_id,
                            behaviour_name=behaviour_name,
                            config_path=f"{path_prefix}.choices[{i}].next",
                            message=f"choice references unknown node: {next_id!r}",
                        ))

        # Validate next reference
        next_id = node.get("next")
        if next_id is not None and next_id not in script:
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path=f"{path_prefix}.next",
                message=f"next references unknown node: {next_id!r}",
            ))

        # Validate events
        events = node.get("events", [])
        if events and not isinstance(events, list):
            errors.append(EventConfigError(
                entity_id=entity_id,
                behaviour_name=behaviour_name,
                config_path=f"{path_prefix}.events",
                message=f"events must be a list, got {type(events).__name__}",
            ))

    return errors


def validate_dialogue_runner_config(
    config: Dict[str, Any],
    *,
    entity_id: str = "",
) -> List[EventConfigError]:
    """Validate DialogueRunner configuration.
    
    Args:
        config: Configuration dictionary.
        entity_id: Entity ID for error reporting.
        
    Returns:
        List of validation errors.
    """
    errors: List[EventConfigError] = []
    behaviour_name = "DialogueRunner"

    # Validate script
    script = config.get("script", {})
    if script:
        errors.extend(validate_dialogue_script(
            script,
            entity_id=entity_id,
            behaviour_name=behaviour_name,
        ))

    # Validate start_node
    start_node = config.get("start_node", "start")
    if script and start_node not in script:
        errors.append(EventConfigError(
            entity_id=entity_id,
            behaviour_name=behaviour_name,
            config_path="start_node",
            message=f"start_node references unknown node: {start_node!r}",
        ))

    return errors
