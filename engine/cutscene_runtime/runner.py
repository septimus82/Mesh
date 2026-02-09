"""Deterministic CutsceneRunner for executing cutscene scripts.

This module provides:
- CutsceneRunner class for deterministic cutscene execution
- CutsceneRunnerState for save/restore compatibility
- CutsceneCommand for parsed command data

Design principles:
- Deterministic: Same dt + same inputs -> same state transitions
- Observable: Progress events emitted through GameplayEventBus
- Debuggable: Clear state inspection for tooling
- Integrates with ActionListRunner and DialogueRunner
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence, Protocol, runtime_checkable

from .schema import (
    CUTSCENE_SCHEMA_VERSION,
    migrate_cutscene_script,
    validate_cutscene_script,
    CutsceneValidationError,
)


@dataclass(frozen=True, slots=True)
class CutsceneCommand:
    """Parsed cutscene command for execution."""
    type: str
    index: int
    duration: float = 0.0
    event_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    flag: str = ""
    actions: list[dict[str, Any]] = field(default_factory=list)
    target: str = ""
    dialogue_id: str = ""
    node_id: str = ""
    true_goto: str = ""
    false_goto: str = ""
    name: str = ""  # For label commands


@dataclass
class CutsceneRunnerState:
    """Saveable state for CutsceneRunner.
    
    Fields:
        script_id: Identifier of the running script
        command_index: Current command index
        wait_remaining: Remaining wait time (for wait commands)
        emitted_count: Number of events emitted
        branch_history: List of branch decisions taken
        is_running: Whether cutscene is active
        completed: Whether cutscene finished
    """
    script_id: str = ""
    command_index: int = 0
    wait_remaining: float = 0.0
    emitted_count: int = 0
    branch_history: list[dict[str, Any]] = field(default_factory=list)
    is_running: bool = False
    completed: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-friendly dict."""
        result: dict[str, Any] = {
            "script_id": self.script_id,
            "command_index": self.command_index,
            "is_running": self.is_running,
            "completed": self.completed,
        }
        
        if self.wait_remaining > 0:
            result["wait_remaining"] = round(self.wait_remaining, 6)
        
        if self.emitted_count > 0:
            result["emitted_count"] = self.emitted_count
        
        if self.branch_history:
            result["branch_history"] = list(self.branch_history)
        
        return result
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CutsceneRunnerState":
        """Deserialize from dict with safe defaults."""
        if not isinstance(data, dict):
            return cls()
        
        return cls(
            script_id=str(data.get("script_id", "") or ""),
            command_index=int(data.get("command_index", 0) or 0),
            wait_remaining=float(data.get("wait_remaining", 0.0) or 0.0),
            emitted_count=int(data.get("emitted_count", 0) or 0),
            branch_history=list(data.get("branch_history", []) or []),
            is_running=bool(data.get("is_running", False)),
            completed=bool(data.get("completed", False)),
        )


@runtime_checkable
class FlagProvider(Protocol):
    """Protocol for getting flag values."""
    def get_flag(self, name: str, default: bool = False) -> bool: ...


@runtime_checkable
class FlagSetter(Protocol):
    """Protocol for setting flag values."""
    def set_flag(self, name: str, value: bool) -> None: ...


@runtime_checkable
class EventEmitter(Protocol):
    """Protocol for emitting gameplay events."""
    def emit(self, event_type: str, **payload: Any) -> Any: ...


class CutsceneRunner:
    """Deterministic cutscene timeline runner.
    
    Executes cutscene scripts with:
    - wait: Pause for duration
    - emit_event: Emit gameplay event
    - set_flag/clear_flag: Modify game state flags
    - run_actions: Execute action list
    - start_dialogue: Start dialogue runner
    - branch_on_flag: Conditional branching
    - goto: Jump to label
    - label: Define jump target
    - stop: End cutscene
    
    Example:
        runner = CutsceneRunner()
        errors = runner.load_script(path_or_data)
        if errors:
            print("Validation errors:", errors)
            return
        runner.start()
        while runner.is_running():
            emitted = runner.tick(dt)
            # Process emitted events...
    """
    
    def __init__(
        self,
        event_bus: EventEmitter | None = None,
        flag_provider: FlagProvider | None = None,
        flag_setter: FlagSetter | None = None,
    ) -> None:
        """Initialize CutsceneRunner.
        
        Args:
            event_bus: GameplayEventBus for emitting events
            flag_provider: Provider for getting flag values
            flag_setter: Setter for modifying flags
        """
        self._event_bus = event_bus
        self._flag_provider = flag_provider
        self._flag_setter = flag_setter
        
        # Script data
        self._script_id: str = ""
        self._raw_script: dict[str, Any] = {}
        self._commands: list[CutsceneCommand] = []
        self._label_indices: dict[str, int] = {}
        
        # Runtime state
        self._state = CutsceneRunnerState()
        
        # Diagnostics
        self._last_validation_errors: list[CutsceneValidationError] = []
    
    @property
    def script_id(self) -> str:
        """Get script identifier."""
        return self._script_id
    
    @property
    def is_running(self) -> bool:
        """Whether cutscene is currently running."""
        return self._state.is_running
    
    @property
    def is_completed(self) -> bool:
        """Whether cutscene has completed."""
        return self._state.completed
    
    @property
    def current_command_index(self) -> int:
        """Get current command index."""
        return self._state.command_index
    
    def current_command(self) -> CutsceneCommand | None:
        """Get current command being executed."""
        if not self._state.is_running:
            return None
        if self._state.command_index >= len(self._commands):
            return None
        return self._commands[self._state.command_index]
    
    def load_script(self, source: Path | str | dict[str, Any]) -> list[CutsceneValidationError]:
        """Load and validate a cutscene script.
        
        Args:
            source: Path to JSON file, JSON string, or dict
            
        Returns:
            List of validation errors (empty if valid)
        """
        # Reset state
        self._state = CutsceneRunnerState()
        self._commands = []
        self._label_indices = {}
        self._raw_script = {}
        self._script_id = ""
        
        # Load data
        file_path = ""
        if isinstance(source, Path):
            file_path = str(source)
            if not source.exists():
                error = CutsceneValidationError(
                    file_path=file_path,
                    json_path="",
                    code="script.file.missing",
                    message=f"Script file not found: {source}",
                    hint="Check the file path",
                )
                self._last_validation_errors = [error]
                return [error]
            try:
                from ..json_io import read_json
                data = read_json(source)
            except json.JSONDecodeError as e:
                error = CutsceneValidationError(
                    file_path=file_path,
                    json_path="",
                    code="script.file.invalid_json",
                    message=f"Invalid JSON: {e}",
                    hint="Check JSON syntax",
                )
                self._last_validation_errors = [error]
                return [error]
        elif isinstance(source, str):
            try:
                from ..json_io import loads_safe
                data = loads_safe(source, source="cutscene_script")
            except json.JSONDecodeError as e:
                error = CutsceneValidationError(
                    file_path="",
                    json_path="",
                    code="script.string.invalid_json",
                    message=f"Invalid JSON string: {e}",
                    hint="Check JSON syntax",
                )
                self._last_validation_errors = [error]
                return [error]
        else:
            data = source
        
        # Migrate
        try:
            data = migrate_cutscene_script(dict(data) if isinstance(data, dict) else {})
        except ValueError as e:
            error = CutsceneValidationError(
                file_path=file_path,
                json_path="",
                code="script.migration.failed",
                message=str(e),
                hint="Check schema_version",
            )
            self._last_validation_errors = [error]
            return [error]
        
        # Validate
        errors = validate_cutscene_script(data, file_path=file_path)
        self._last_validation_errors = errors
        
        if errors:
            return errors
        
        # Store raw script
        self._raw_script = data
        self._script_id = str(data.get("id", "") or "").strip()
        
        # Parse commands
        self._parse_commands(data.get("commands", []))
        
        return []
    
    def load_script_from_data(self, data: dict[str, Any]) -> list[CutsceneValidationError]:
        """Load script from dict data (convenience wrapper)."""
        return self.load_script(data)
    
    def _parse_commands(self, commands: list[Any]) -> None:
        """Parse command list into CutsceneCommand objects."""
        self._commands = []
        self._label_indices = {}
        
        for idx, cmd in enumerate(commands):
            if not isinstance(cmd, dict):
                continue
            
            cmd_type = str(cmd.get("type", "")).strip()
            if not cmd_type:
                continue
            
            # Build CutsceneCommand
            parsed = CutsceneCommand(
                type=cmd_type,
                index=idx,
                duration=float(cmd.get("duration", 0.0) or 0.0),
                event_type=str(cmd.get("event_type", "") or ""),
                payload=dict(cmd.get("payload", {}) or {}),
                flag=str(cmd.get("flag", "") or ""),
                actions=list(cmd.get("actions", []) or []),
                target=str(cmd.get("target", "") or ""),
                dialogue_id=str(cmd.get("dialogue_id", "") or ""),
                node_id=str(cmd.get("node_id", "") or ""),
                true_goto=str(cmd.get("true_goto", "") or ""),
                false_goto=str(cmd.get("false_goto", "") or ""),
                name=str(cmd.get("name", "") or ""),
            )
            
            self._commands.append(parsed)
            
            # Index labels
            if cmd_type == "label" and parsed.name:
                self._label_indices[parsed.name] = len(self._commands) - 1
    
    def start(self, from_index: int = 0) -> bool:
        """Start cutscene execution.
        
        Args:
            from_index: Command index to start from
            
        Returns:
            True if started successfully
        """
        if not self._commands:
            return False
        
        if from_index < 0 or from_index >= len(self._commands):
            from_index = 0
        
        self._state = CutsceneRunnerState(
            script_id=self._script_id,
            command_index=from_index,
            is_running=True,
            completed=False,
        )
        
        # Emit start event
        self._emit_event(
            "cutscene_started",
            script_id=self._script_id,
            command_count=len(self._commands),
        )
        
        return True
    
    def stop(self) -> None:
        """Stop cutscene execution without completing."""
        if not self._state.is_running:
            return
        
        self._state.is_running = False
        
        self._emit_event(
            "cutscene_stopped",
            script_id=self._script_id,
            command_index=self._state.command_index,
        )
    
    def tick(self, dt: float) -> list[dict[str, Any]]:
        """Advance cutscene by dt seconds.
        
        Args:
            dt: Time delta in seconds
            
        Returns:
            List of emitted events during this tick
        """
        emitted: list[dict[str, Any]] = []
        
        if not self._state.is_running:
            return emitted
        
        # Handle wait
        if self._state.wait_remaining > 0:
            self._state.wait_remaining -= dt
            if self._state.wait_remaining > 0:
                return emitted
            self._state.wait_remaining = 0.0
            self._state.command_index += 1
        
        # Execute commands until wait, stop, or end
        while self._state.command_index < len(self._commands):
            cmd = self._commands[self._state.command_index]
            
            result = self._execute_command(cmd)
            if result.get("emitted"):
                emitted.append(result["emitted"])
            
            if result.get("wait"):
                # Start waiting
                self._state.wait_remaining = result["wait"]
                break
            
            if result.get("goto_label"):
                # Jump to label
                label = result["goto_label"]
                if label in self._label_indices:
                    self._state.command_index = self._label_indices[label]
                else:
                    # Invalid label, advance
                    self._state.command_index += 1
                continue
            
            if result.get("stop"):
                # End cutscene
                self._complete()
                break
            
            # Advance to next command
            self._state.command_index += 1
        
        # Check if we've reached the end
        if self._state.is_running and self._state.command_index >= len(self._commands):
            self._complete()
        
        return emitted
    
    def _execute_command(self, cmd: CutsceneCommand) -> dict[str, Any]:
        """Execute a single command.
        
        Returns:
            Dict with execution result:
            - emitted: Event that was emitted (if any)
            - wait: Duration to wait (for wait command)
            - goto_label: Label to jump to (for goto/branch)
            - stop: True if cutscene should stop
        """
        result: dict[str, Any] = {}
        
        if cmd.type == "wait":
            result["wait"] = max(0.0, cmd.duration)
        
        elif cmd.type == "emit_event":
            if cmd.event_type:
                event_data = self._emit_event(cmd.event_type, **cmd.payload)
                self._state.emitted_count += 1
                result["emitted"] = {
                    "type": cmd.event_type,
                    "payload": dict(cmd.payload),
                }
        
        elif cmd.type == "set_flag":
            if cmd.flag and self._flag_setter:
                self._flag_setter.set_flag(cmd.flag, True)
        
        elif cmd.type == "clear_flag":
            if cmd.flag and self._flag_setter:
                self._flag_setter.set_flag(cmd.flag, False)
        
        elif cmd.type == "run_actions":
            # Emit event for ActionListRunner integration
            self._emit_event(
                "cutscene_run_actions",
                script_id=self._script_id,
                actions=cmd.actions,
            )
        
        elif cmd.type == "start_dialogue":
            # Emit event for DialogueRunner integration
            self._emit_event(
                "cutscene_start_dialogue",
                script_id=self._script_id,
                dialogue_id=cmd.dialogue_id,
                target=cmd.target,
                node_id=cmd.node_id,
            )
        
        elif cmd.type == "branch_on_flag":
            flag_value = False
            if self._flag_provider and cmd.flag:
                flag_value = self._flag_provider.get_flag(cmd.flag, False)
            
            # Record branch decision
            self._state.branch_history.append({
                "command_index": cmd.index,
                "flag": cmd.flag,
                "value": flag_value,
            })
            
            if flag_value and cmd.true_goto:
                result["goto_label"] = cmd.true_goto
            elif not flag_value and cmd.false_goto:
                result["goto_label"] = cmd.false_goto
        
        elif cmd.type == "goto":
            if cmd.target:
                result["goto_label"] = cmd.target
        
        elif cmd.type == "label":
            # Labels are no-ops during execution
            pass
        
        elif cmd.type == "stop":
            result["stop"] = True
        
        return result
    
    def _emit_event(self, event_type: str, **payload: Any) -> dict[str, Any] | None:
        """Emit an event through the event bus."""
        if self._event_bus is None:
            return None
        
        full_payload = {
            "source_script": self._script_id,
            **payload,
        }
        
        self._event_bus.emit(
            event_type,
            source_entity="",
            source_behaviour="CutsceneRunner",
            **full_payload,
        )
        
        return {"type": event_type, "payload": full_payload}
    
    def _complete(self) -> None:
        """Mark cutscene as completed."""
        self._state.is_running = False
        self._state.completed = True
        
        self._emit_event(
            "cutscene_completed",
            script_id=self._script_id,
            emitted_count=self._state.emitted_count,
            branch_count=len(self._state.branch_history),
        )
    
    # Save/Restore API
    
    def get_state(self) -> CutsceneRunnerState:
        """Get current runner state for saving."""
        return CutsceneRunnerState(
            script_id=self._state.script_id,
            command_index=self._state.command_index,
            wait_remaining=self._state.wait_remaining,
            emitted_count=self._state.emitted_count,
            branch_history=list(self._state.branch_history),
            is_running=self._state.is_running,
            completed=self._state.completed,
        )
    
    def apply_state(self, state: CutsceneRunnerState) -> None:
        """Restore runner state from saved data.
        
        Note: Script must be loaded first with load_script().
        """
        self._state = CutsceneRunnerState(
            script_id=state.script_id,
            command_index=state.command_index,
            wait_remaining=state.wait_remaining,
            emitted_count=state.emitted_count,
            branch_history=list(state.branch_history),
            is_running=state.is_running,
            completed=state.completed,
        )
    
    def saveable_state(self) -> dict[str, Any]:
        """Return JSON-serializable state dict."""
        return self._state.to_dict()
    
    def restore_state(self, state: dict[str, Any]) -> None:
        """Apply previously saved state from dict."""
        self._state = CutsceneRunnerState.from_dict(state)
    
    # Inspection API
    
    def get_inspector_state(self) -> dict[str, Any]:
        """Return state summary for editor inspection."""
        cmd = self.current_command()
        return {
            "script_id": self._script_id,
            "is_running": self._state.is_running,
            "completed": self._state.completed,
            "command_index": self._state.command_index,
            "command_count": len(self._commands),
            "current_command_type": cmd.type if cmd else None,
            "wait_remaining": round(self._state.wait_remaining, 2),
            "emitted_count": self._state.emitted_count,
            "branch_count": len(self._state.branch_history),
        }
    
    def get_command_list(self) -> list[dict[str, Any]]:
        """Return list of command summaries for inspection."""
        result: list[dict[str, Any]] = []
        for i, cmd in enumerate(self._commands):
            entry: dict[str, Any] = {
                "index": i,
                "type": cmd.type,
            }
            if cmd.type == "wait":
                entry["duration"] = cmd.duration
            elif cmd.type == "emit_event":
                entry["event_type"] = cmd.event_type
            elif cmd.type in ("set_flag", "clear_flag", "branch_on_flag"):
                entry["flag"] = cmd.flag
            elif cmd.type == "label":
                entry["name"] = cmd.name
            elif cmd.type == "goto":
                entry["target"] = cmd.target
            result.append(entry)
        return result
    
    def get_validation_errors(self) -> list[CutsceneValidationError]:
        """Return last validation errors."""
        return list(self._last_validation_errors)


def simulate_cutscene(
    script: dict[str, Any] | Path | str,
    dt_schedule: Sequence[float],
    *,
    flags: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Simulate cutscene execution with a schedule of dt values.
    
    Args:
        script: Cutscene script (dict, path, or JSON string)
        dt_schedule: Sequence of dt values to tick
        flags: Initial flag values
        
    Returns:
        Simulation result dict with:
        - ok: Whether simulation succeeded
        - errors: Validation errors (if any)
        - steps: List of step results
        - final_state: Final runner state
        - emitted_events: All emitted events
    """
    # Create mock flag provider/setter
    flag_store = dict(flags or {})
    
    class MockFlags:
        def get_flag(self, name: str, default: bool = False) -> bool:
            return flag_store.get(name, default)
        
        def set_flag(self, name: str, value: bool) -> None:
            flag_store[name] = value
    
    # Create mock event bus
    emitted_events: list[dict[str, Any]] = []
    
    class MockEventBus:
        def emit(self, event_type: str, **payload: Any) -> dict[str, Any]:
            event = {"type": event_type, "payload": payload}
            emitted_events.append(event)
            return event
    
    mock_flags = MockFlags()
    mock_bus = MockEventBus()
    
    # Create runner
    runner = CutsceneRunner(
        event_bus=mock_bus,
        flag_provider=mock_flags,
        flag_setter=mock_flags,
    )
    
    # Load script
    errors = runner.load_script(script)
    if errors:
        return {
            "ok": False,
            "errors": [str(e) for e in errors],
            "steps": [],
            "final_state": {},
            "emitted_events": [],
        }
    
    # Start
    if not runner.start():
        return {
            "ok": False,
            "errors": ["Failed to start cutscene"],
            "steps": [],
            "final_state": {},
            "emitted_events": [],
        }
    
    # Execute dt schedule
    steps: list[dict[str, Any]] = []
    for dt in dt_schedule:
        step_emitted = runner.tick(dt)
        cmd = runner.current_command()
        steps.append({
            "dt": dt,
            "command_index": runner.current_command_index,
            "command_type": cmd.type if cmd else None,
            "is_running": runner.is_running,
            "wait_remaining": round(runner._state.wait_remaining, 6),
            "emitted_count": len(step_emitted),
        })
        
        if not runner.is_running:
            break
    
    return {
        "ok": True,
        "errors": [],
        "steps": steps,
        "final_state": runner.saveable_state(),
        "emitted_events": emitted_events,
        "flags": dict(flag_store),
    }
