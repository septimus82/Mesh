"""Deterministic QuestRunner for executing validated quest definitions.

This module provides:
- QuestRunner class for deterministic quest execution
- load_definitions() for loading and validating quest data
- process_events() for event-driven quest progression
- get_state()/apply_state() for save/restore compatibility

Design principles:
- Deterministic: Same event stream produces same state transitions
- Validated: Definitions are validated/migrated before execution
- Observable: Progress events emitted for other systems (QuestHook, UI)
- Debuggable: Step completion diagnostics for tooling
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from ..diagnostics import Diagnostic, diagnostics_to_text
from ..gameplay_event_bus import GameplayEvent
from ..save_runtime.state_codec import decode_state, encode_state
from ..save_runtime.quest_state import SavedQuestState, QUEST_STATE_SCHEMA_VERSION
from .normalize import normalize_quest
from .validation import (
    QUEST_DEFINITION_SCHEMA_VERSION,
    QuestValidationError,
    migrate_quest_definition,
    validate_quest_file,
)


@dataclass(frozen=True, slots=True)
class StepCompletionDiagnostic:
    """Diagnostic info for why a step did/didn't complete.
    
    Attributes:
        quest_id: Quest identifier
        step_id: Step/stage identifier
        event_type: Event type that was checked
        matched: Whether the event matched the completion criteria
        reason: Human-readable explanation
        expected: Expected filter criteria
        actual: Actual event payload
    """
    quest_id: str
    step_id: str
    event_type: str
    matched: bool
    reason: str
    expected: dict[str, Any] = field(default_factory=dict)
    actual: dict[str, Any] = field(default_factory=dict)


@dataclass
class QuestRunnerState:
    """Internal state for a single quest in the runner.
    
    Attributes:
        quest_id: Quest identifier
        status: "inactive", "active", "completed", "failed"
        current_stage: Current stage ID or None
        awaiting_stage: Next stage waiting for start trigger
        completed_stages: List of completed stage IDs
        counters: Quest-scoped counters
    """
    quest_id: str
    status: str = "inactive"
    current_stage: str | None = None
    awaiting_stage: str | None = None
    completed_stages: list[str] = field(default_factory=list)
    counters: dict[str, int] = field(default_factory=dict)
    
    def to_saved_state(self) -> SavedQuestState:
        """Convert to SavedQuestState for persistence."""
        # Map current_stage to current_step (can be string or index)
        current_step: int | str = 0
        if self.current_stage:
            current_step = self.current_stage
        elif self.awaiting_stage:
            current_step = self.awaiting_stage
        
        return SavedQuestState(
            quest_id=self.quest_id,
            state=self.status,
            current_step=current_step,
            counters=dict(self.counters),
            x_extra={
                "x_completed_stages": list(self.completed_stages),
                "x_awaiting_stage": self.awaiting_stage,
            },
        )
    
    @classmethod
    def from_saved_state(cls, saved: SavedQuestState) -> "QuestRunnerState":
        """Create from SavedQuestState."""
        # Decode current_step back to stage references
        current_stage: str | None = None
        awaiting_stage: str | None = None
        
        if isinstance(saved.current_step, str) and saved.current_step:
            # String step means it's a stage ID
            if saved.state == "active":
                current_stage = saved.current_step
        
        # Check for extended fields
        x_extra = saved.x_extra or {}
        if "x_completed_stages" in x_extra:
            completed_stages = list(x_extra["x_completed_stages"])
        else:
            completed_stages = []
        
        if "x_awaiting_stage" in x_extra:
            awaiting_stage = x_extra["x_awaiting_stage"]
        
        return cls(
            quest_id=saved.quest_id,
            status=saved.state,
            current_stage=current_stage,
            awaiting_stage=awaiting_stage,
            completed_stages=completed_stages,
            counters=dict(saved.counters),
        )


class QuestRunner:
    """Deterministic quest execution engine.
    
    QuestRunner loads validated quest definitions and processes gameplay
    events to advance quest state. It emits progress events that other
    systems (QuestHook, UI) can consume.
    
    Usage:
        runner = QuestRunner()
        errors = runner.load_definitions(Path("assets/data/quests.json"))
        if errors:
            print(f"Validation errors: {errors}")
        
        runner.start_quest("my_quest")
        
        # Process events from gameplay
        events = event_bus.drain()
        emitted = runner.process_events(events)
        
        # Emitted events can be fed back to other systems
        for event in emitted:
            event_bus.emit_event(event)
    """
    
    TYPE_ID = "quest_runner"
    STATE_VERSION = 1

    def __init__(self, *, emit_sequence_start: int = 10000) -> None:
        """Initialize QuestRunner.
        
        Args:
            emit_sequence_start: Starting sequence number for emitted events.
                                 Use high value to avoid collisions with input events.
        """
        self._definitions: dict[str, dict[str, Any]] = {}
        self._sorted_quest_ids: list[str] = []
        self._states: dict[str, QuestRunnerState] = {}
        self._emit_sequence = emit_sequence_start
        self._diagnostics: list[StepCompletionDiagnostic] = []
        self._diagnostics_limit = 50
        self._last_restore_diagnostics: tuple[Diagnostic, ...] = ()
    
    # ------------------------------------------------------------------
    # Definition Loading
    # ------------------------------------------------------------------
    
    def load_definitions(
        self,
        source: Path | dict[str, Any],
        *,
        strict: bool = False,
    ) -> list[QuestValidationError]:
        """Load and validate quest definitions.
        
        Args:
            source: Path to quests.json or dict with quest data
            strict: If True, enforce stricter validation
            
        Returns:
            List of validation errors (empty if valid)
        """
        if isinstance(source, Path):
            return self._load_from_file(source, strict=strict)
        else:
            return self._load_from_data(source, strict=strict)
    
    def _load_from_file(self, path: Path, *, strict: bool) -> list[QuestValidationError]:
        """Load definitions from a JSON file."""
        if not path.exists():
            return [QuestValidationError(
                file_path=str(path),
                json_path="",
                code="file.not_found",
                message=f"Quest file not found: {path}",
                hint="Check the file path",
            )]
        
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            return [QuestValidationError(
                file_path=str(path),
                json_path="",
                code="file.invalid_json",
                message=f"Invalid JSON: {e}",
                hint="Fix JSON syntax errors",
            )]
        
        return self._load_from_data(data, file_path=str(path), strict=strict)
    
    def _load_from_data(
        self,
        data: dict[str, Any],
        *,
        file_path: str = "",
        strict: bool = False,
    ) -> list[QuestValidationError]:
        """Load definitions from parsed data."""
        # Migrate to current schema
        try:
            data = migrate_quest_definition(data)
        except ValueError as e:
            return [QuestValidationError(
                file_path=file_path,
                json_path="schema_version",
                code="file.future_version",
                message=str(e),
                hint="Update your game to the latest version",
            )]
        
        # Validate
        errors = validate_quest_file(Path(file_path) if file_path else Path(""), data, strict=strict)
        
        # Even with errors, load what we can (for editor previews)
        self._definitions.clear()
        
        for raw_quest in data.get("quests", []):
            normalized = normalize_quest(raw_quest)
            if normalized:
                self._definitions[normalized["id"]] = normalized
                # Initialize state if not exists
                if normalized["id"] not in self._states:
                    self._states[normalized["id"]] = QuestRunnerState(quest_id=normalized["id"])
        self._sorted_quest_ids = sorted(self._definitions.keys())
        
        return errors
    
    def get_definition(self, quest_id: str) -> dict[str, Any] | None:
        """Get a quest definition by ID."""
        return self._definitions.get(quest_id)
    
    def list_definitions(self) -> list[str]:
        """List all loaded quest IDs."""
        return sorted(self._definitions.keys())
    
    # ------------------------------------------------------------------
    # Quest Control
    # ------------------------------------------------------------------
    
    def start_quest(self, quest_id: str, stage_id: str | None = None) -> bool:
        """Start a quest, optionally at a specific stage.
        
        Args:
            quest_id: Quest to start
            stage_id: Optional stage to start at (defaults to first)
            
        Returns:
            True if quest was started, False if not found/already active
        """
        quest = self._definitions.get(quest_id)
        if quest is None:
            return False
        
        state = self._ensure_state(quest_id)
        if state.status == "completed":
            return False  # Already completed
        
        stages = quest.get("stages", [])
        if not stages:
            return False
        
        # Find target stage
        if stage_id:
            target_stage = quest["stage_lookup"].get(stage_id)
            if not target_stage:
                return False
        else:
            target_stage = stages[0]
        
        # Activate quest
        state.status = "active"
        
        # Start at target stage
        if target_stage.get("start_event"):
            # Has start trigger - await it
            state.awaiting_stage = target_stage["id"]
            state.current_stage = None
        else:
            # No start trigger - activate immediately
            state.current_stage = target_stage["id"]
            state.awaiting_stage = None
        
        return True
    
    def complete_quest(self, quest_id: str) -> bool:
        """Force-complete a quest.
        
        Args:
            quest_id: Quest to complete
            
        Returns:
            True if quest was completed
        """
        state = self._states.get(quest_id)
        if state is None:
            return False
        
        state.status = "completed"
        state.current_stage = None
        state.awaiting_stage = None
        return True
    
    def is_quest_active(self, quest_id: str) -> bool:
        """Check if quest is active."""
        state = self._states.get(quest_id)
        return state is not None and state.status == "active"
    
    def is_quest_completed(self, quest_id: str) -> bool:
        """Check if quest is completed."""
        state = self._states.get(quest_id)
        return state is not None and state.status == "completed"
    
    # ------------------------------------------------------------------
    # Event Processing
    # ------------------------------------------------------------------
    
    def process_events(
        self,
        events: Sequence[GameplayEvent],
    ) -> list[GameplayEvent]:
        """Process events and return emitted quest events.
        
        This is the main entry point for deterministic quest progression.
        Events are processed in sequence order, and the same event stream
        will always produce the same state transitions and emitted events.
        
        Args:
            events: Sequence of gameplay events to process
            
        Returns:
            List of emitted quest progress events
        """
        emitted: list[GameplayEvent] = []
        
        # Sort events by sequence for deterministic processing
        sorted_events = sorted(events, key=lambda e: e.sequence)
        
        # Process each event in sequence order
        for event in sorted_events:
            event_emitted = self._process_single_event(event)
            emitted.extend(event_emitted)
        
        return emitted
    
    def _process_single_event(self, event: GameplayEvent) -> list[GameplayEvent]:
        """Process a single event across all quests."""
        emitted: list[GameplayEvent] = []
        
        # Two passes for determinism (quests may affect each other)
        for _ in range(2):
            for quest_id in self._sorted_quest_ids:
                quest = self._definitions[quest_id]
                state = self._ensure_state(quest_id)
                
                if state.status == "completed":
                    continue
                
                # Check start triggers for awaiting stages
                start_emitted = self._check_start_trigger(quest, state, event)
                emitted.extend(start_emitted)
                
                # Check completion triggers for current stages
                complete_emitted = self._check_completion_trigger(quest, state, event)
                emitted.extend(complete_emitted)
        
        return emitted
    
    def _check_start_trigger(
        self,
        quest: dict[str, Any],
        state: QuestRunnerState,
        event: GameplayEvent,
    ) -> list[GameplayEvent]:
        """Check if event starts an awaiting stage."""
        if not state.awaiting_stage:
            return []
        
        stage = quest["stage_lookup"].get(state.awaiting_stage)
        if not stage:
            state.awaiting_stage = None
            return []
        
        start_event = stage.get("start_event")
        if not start_event:
            # No start trigger - auto-start
            return self._start_stage(quest, state, stage)
        
        matched, diagnostic = self._event_matches_filter(
            event, start_event, quest["id"], stage["id"], "start"
        )
        self._record_diagnostic(diagnostic)
        
        if not matched:
            return []
        
        return self._start_stage(quest, state, stage)
    
    def _check_completion_trigger(
        self,
        quest: dict[str, Any],
        state: QuestRunnerState,
        event: GameplayEvent,
    ) -> list[GameplayEvent]:
        """Check if event completes the current stage."""
        if not state.current_stage:
            return []
        
        stage = quest["stage_lookup"].get(state.current_stage)
        if not stage:
            state.current_stage = None
            return []
        
        complete_event = stage.get("complete_event")
        if not complete_event:
            # No completion trigger - check requirements instead
            return []
        
        matched, diagnostic = self._event_matches_filter(
            event, complete_event, quest["id"], stage["id"], "complete"
        )
        self._record_diagnostic(diagnostic)
        
        if not matched:
            return []
        
        return self._complete_stage(quest, state, stage)
    
    def _event_matches_filter(
        self,
        event: GameplayEvent,
        filter_spec: dict[str, Any],
        quest_id: str,
        stage_id: str,
        trigger_type: str,
    ) -> tuple[bool, StepCompletionDiagnostic]:
        """Check if event matches a filter specification.
        
        Returns:
            Tuple of (matched, diagnostic)
        """
        expected_type = filter_spec.get("type", "")
        
        # Type must match
        if event.event_type != expected_type:
            return False, StepCompletionDiagnostic(
                quest_id=quest_id,
                step_id=stage_id,
                event_type=event.event_type,
                matched=False,
                reason=f"Event type mismatch: expected '{expected_type}', got '{event.event_type}'",
                expected={"type": expected_type},
                actual={"type": event.event_type},
            )
        
        payload = event.payload or {}
        
        # Check payload_field/payload_value pattern
        payload_field = filter_spec.get("payload_field")
        if payload_field:
            if payload_field not in payload:
                return False, StepCompletionDiagnostic(
                    quest_id=quest_id,
                    step_id=stage_id,
                    event_type=event.event_type,
                    matched=False,
                    reason=f"Missing payload field: '{payload_field}'",
                    expected={"payload_field": payload_field},
                    actual=dict(payload),
                )
            
            if "payload_value" in filter_spec:
                expected_value = filter_spec["payload_value"]
                actual_value = payload.get(payload_field)
                if actual_value != expected_value:
                    return False, StepCompletionDiagnostic(
                        quest_id=quest_id,
                        step_id=stage_id,
                        event_type=event.event_type,
                        matched=False,
                        reason=f"Payload value mismatch for '{payload_field}': expected '{expected_value}', got '{actual_value}'",
                        expected={payload_field: expected_value},
                        actual={payload_field: actual_value},
                    )
        
        # Check payload dict pattern
        expected_payload = filter_spec.get("payload")
        if isinstance(expected_payload, dict):
            for key, expected_val in expected_payload.items():
                actual_val = payload.get(key)
                if actual_val != expected_val:
                    return False, StepCompletionDiagnostic(
                        quest_id=quest_id,
                        step_id=stage_id,
                        event_type=event.event_type,
                        matched=False,
                        reason=f"Payload mismatch for '{key}': expected '{expected_val}', got '{actual_val}'",
                        expected={key: expected_val},
                        actual={key: actual_val},
                    )
        
        return True, StepCompletionDiagnostic(
            quest_id=quest_id,
            step_id=stage_id,
            event_type=event.event_type,
            matched=True,
            reason=f"{trigger_type.capitalize()} trigger matched",
            expected=dict(filter_spec),
            actual=dict(payload),
        )
    
    def _start_stage(
        self,
        quest: dict[str, Any],
        state: QuestRunnerState,
        stage: dict[str, Any],
    ) -> list[GameplayEvent]:
        """Start a stage and emit events."""
        state.current_stage = stage["id"]
        state.awaiting_stage = None
        
        if state.status == "inactive":
            state.status = "active"
        
        # Emit stage started event
        return [self._emit_event(
            "quest_stage_started",
            quest_id=quest["id"],
            stage_id=stage["id"],
            quest_title=quest.get("title", quest["id"]),
            stage_title=stage.get("title", stage["id"]),
            text=stage.get("text", ""),
        )]
    
    def _complete_stage(
        self,
        quest: dict[str, Any],
        state: QuestRunnerState,
        stage: dict[str, Any],
    ) -> list[GameplayEvent]:
        """Complete a stage and advance to next."""
        emitted: list[GameplayEvent] = []
        
        # Mark stage completed
        if stage["id"] not in state.completed_stages:
            state.completed_stages.append(stage["id"])
        state.current_stage = None
        
        # Apply counter updates from stage
        requirements = stage.get("requirements", {})
        counters_to_set = requirements.get("counters_set", {})
        counters_to_inc = requirements.get("counters_inc", {})
        
        for counter, value in counters_to_set.items():
            state.counters[counter] = int(value)
        for counter, value in counters_to_inc.items():
            state.counters[counter] = state.counters.get(counter, 0) + int(value)
        
        # Emit stage completed event
        emitted.append(self._emit_event(
            "quest_stage_completed",
            quest_id=quest["id"],
            stage_id=stage["id"],
            quest_title=quest.get("title", quest["id"]),
            stage_title=stage.get("title", stage["id"]),
            text=stage.get("text", ""),
        ))
        
        # Emit any custom events defined on completion
        emit_events = stage.get("emit_events_on_complete", [])
        for event_def in emit_events:
            if isinstance(event_def, str):
                emitted.append(self._emit_event(event_def))
            elif isinstance(event_def, dict):
                event_type = event_def.get("type", "")
                payload = event_def.get("payload", {})
                if event_type:
                    emitted.append(self._emit_event(event_type, **payload))
        
        # Find next stage
        next_stage = self._find_next_stage(quest, state)
        
        if next_stage is None:
            # Quest complete
            emitted.extend(self._complete_quest_internal(quest, state))
        else:
            # Move to next stage
            state.awaiting_stage = next_stage["id"]
            
            # Auto-start if no start trigger
            if not next_stage.get("start_event"):
                emitted.extend(self._start_stage(quest, state, next_stage))
        
        return emitted
    
    def _complete_quest_internal(
        self,
        quest: dict[str, Any],
        state: QuestRunnerState,
    ) -> list[GameplayEvent]:
        """Complete quest and apply rewards."""
        state.status = "completed"
        state.current_stage = None
        state.awaiting_stage = None
        
        # Note: Rewards (flags, counters) are applied by the host system
        # We just emit the event
        
        return [self._emit_event(
            "quest_completed",
            quest_id=quest["id"],
            quest_title=quest.get("title", quest["id"]),
            reward=quest.get("reward", {}),
        )]
    
    def _find_next_stage(
        self,
        quest: dict[str, Any],
        state: QuestRunnerState,
    ) -> dict[str, Any] | None:
        """Find the next uncompleted stage."""
        completed_set = set(state.completed_stages)
        stages: list[dict[str, Any]] = quest.get("stages", [])
        for stage in stages:
            if stage["id"] not in completed_set:
                return stage
        return None
    
    def _emit_event(self, event_type: str, **payload: Any) -> GameplayEvent:
        """Create an emitted event with unique sequence number."""
        event = GameplayEvent(
            event_type=event_type,
            payload=dict(payload),
            sequence=self._emit_sequence,
            source_entity="",
            source_behaviour="QuestRunner",
        )
        self._emit_sequence += 1
        return event
    
    # ------------------------------------------------------------------
    # State Management
    # ------------------------------------------------------------------
    
    def _ensure_state(self, quest_id: str) -> QuestRunnerState:
        """Get or create state for a quest."""
        if quest_id not in self._states:
            self._states[quest_id] = QuestRunnerState(quest_id=quest_id)
        return self._states[quest_id]
    
    def get_state(self, quest_id: str | None = None) -> dict[str, Any]:
        """Get quest state for save/serialization.
        
        Args:
            quest_id: Specific quest ID, or None for all quests
            
        Returns:
            Dict with "schema_version" and "quests" containing SavedQuestState data
        """
        result: dict[str, Any] = {
            "schema_version": QUEST_STATE_SCHEMA_VERSION,
            "quests": {},
        }
        
        if quest_id:
            state = self._states.get(quest_id)
            if state:
                saved = state.to_saved_state()
                result["quests"][quest_id] = saved.to_dict()
        else:
            for qid, state in sorted(self._states.items()):
                saved = state.to_saved_state()
                result["quests"][qid] = saved.to_dict()
        
        return result
    
    def apply_state(self, data: dict[str, Any]) -> int:
        """Apply saved state from a save file.
        
        Args:
            data: Dict with "quests" containing SavedQuestState data
            
        Returns:
            Number of quests restored
        """
        quests_data = data.get("quests", {})
        if not isinstance(quests_data, dict):
            return 0
        
        count = 0
        for quest_id, quest_data in quests_data.items():
            if not isinstance(quest_data, dict):
                continue
            
            saved = SavedQuestState.from_dict(quest_data)
            state = QuestRunnerState.from_saved_state(saved)
            self._states[quest_id] = state
            count += 1
        
        return count

    def saveable_state(self) -> dict[str, Any]:
        return encode_state(self.TYPE_ID, self.STATE_VERSION, self.get_state())

    def restore_state(
        self,
        payload: dict[str, Any],
        *,
        strict: bool = True,
        source: str = "quest_runner",
    ) -> None:
        inner_state, diagnostics = decode_state(
            payload,
            expected_type_id=self.TYPE_ID,
            supported_versions={self.STATE_VERSION},
            strict=bool(strict),
            source=str(source),
        )
        self._last_restore_diagnostics = tuple(diagnostics)
        if inner_state is None:
            if strict:
                details = diagnostics_to_text(self._last_restore_diagnostics).strip()
                if details:
                    raise ValueError(details)
                raise ValueError("quest_runner restore failed")
            return
        self.apply_state(inner_state)
    
    def get_quest_state(self, quest_id: str) -> QuestRunnerState | None:
        """Get internal state for a specific quest."""
        return self._states.get(quest_id)
    
    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    
    def _record_diagnostic(self, diagnostic: StepCompletionDiagnostic) -> None:
        """Record a diagnostic for debugging."""
        self._diagnostics.append(diagnostic)
        while len(self._diagnostics) > self._diagnostics_limit:
            self._diagnostics.pop(0)
    
    def get_diagnostics(self, quest_id: str | None = None) -> list[StepCompletionDiagnostic]:
        """Get recent diagnostics, optionally filtered by quest.
        
        Args:
            quest_id: Filter to specific quest, or None for all
            
        Returns:
            List of recent diagnostics
        """
        if quest_id is None:
            return list(self._diagnostics)
        return [d for d in self._diagnostics if d.quest_id == quest_id]
    
    def clear_diagnostics(self) -> None:
        """Clear all diagnostics."""
        self._diagnostics.clear()
    
    def get_step_completion_reason(
        self,
        quest_id: str,
        step_id: str,
    ) -> str | None:
        """Get the reason why a step did/didn't complete.
        
        This searches recent diagnostics for the most recent match.
        
        Args:
            quest_id: Quest identifier
            step_id: Step/stage identifier
            
        Returns:
            Reason string or None if not found
        """
        for diag in reversed(self._diagnostics):
            if diag.quest_id == quest_id and diag.step_id == step_id:
                return diag.reason
        return None
