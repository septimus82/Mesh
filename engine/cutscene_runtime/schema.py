"""Cutscene script schema validation and migration framework.

This module provides:
- CUTSCENE_SCHEMA_VERSION tracking
- validate_cutscene_script() for structural validation with actionable errors
- validate_cutscene_command() for individual command validation
- migrate_cutscene_script() for upgrading old scripts

Supported commands (v1):
- wait: Pause for duration seconds
- emit_event: Emit gameplay event through GameplayEventBus
- set_flag: Set a game state flag to true
- clear_flag: Set a game state flag to false
- run_actions: Execute an ActionList
- start_dialogue: Start a DialogueRunner
- branch_on_flag: Conditional branch based on flag value

Validation produces CutsceneValidationError objects with:
- file_path: The source file (for editor integration)
- json_path: JSON pointer to the invalid field
- code: Machine-readable error code for categorization
- message: Human-readable error description
- hint: Actionable suggestion for fixing the issue
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


# Current cutscene script schema version.
# Increment when adding new required fields or changing semantics.
# v1: Initial schema with wait, emit_event, set_flag, clear_flag, run_actions, start_dialogue, branch_on_flag
CUTSCENE_SCHEMA_VERSION = 1


# Valid command types
VALID_COMMAND_TYPES = frozenset({
    "wait",
    "emit_event",
    "set_flag",
    "clear_flag",
    "run_actions",
    "start_dialogue",
    "branch_on_flag",
    "goto",  # Jump to a label
    "label",  # Define a jump target
    "stop",  # End cutscene
})


@dataclass(frozen=True, slots=True)
class CutsceneValidationError:
    """Validation error with actionable context."""
    file_path: str  # Source file path
    json_path: str  # JSON pointer to invalid field
    code: str  # Machine-readable error code
    message: str  # Human-readable error
    hint: str = ""  # Actionable fix suggestion
    
    def __str__(self) -> str:
        parts = [f"[{self.code}]"]
        if self.file_path:
            parts.append(f"in {self.file_path}")
        if self.json_path:
            parts.append(f"at {self.json_path}")
        parts.append(f": {self.message}")
        if self.hint:
            parts.append(f" (hint: {self.hint})")
        return " ".join(parts)


# Type alias for migration functions
CutsceneMigrationFn = Callable[[dict[str, Any]], dict[str, Any]]

# Registry of migrations: version -> function that upgrades to next version
_CUTSCENE_MIGRATIONS: dict[int, CutsceneMigrationFn] = {}


def register_cutscene_migration(from_version: int) -> Callable[[CutsceneMigrationFn], CutsceneMigrationFn]:
    """Decorator to register a cutscene script migration function."""
    def decorator(fn: CutsceneMigrationFn) -> CutsceneMigrationFn:
        _CUTSCENE_MIGRATIONS[from_version] = fn
        return fn
    return decorator


@register_cutscene_migration(0)
def _migrate_v0_to_v1(data: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate v0 (no schema_version field) to v1.
    
    v0 scripts may be missing:
    - schema_version field
    - Consistent command field naming
    """
    data["schema_version"] = 1
    
    # Normalize commands array
    commands = data.get("commands")
    if not isinstance(commands, list):
        data["commands"] = []
    
    # Normalize command types (e.g., "delay" -> "wait")
    for cmd in data.get("commands", []):
        if not isinstance(cmd, dict):
            continue
        cmd_type = cmd.get("type", "")
        if cmd_type == "delay":
            cmd["type"] = "wait"
    
    return data


def migrate_cutscene_script(data: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate a cutscene script payload to the current schema version.
    
    Args:
        data: Raw cutscene script payload (will be modified in place)
        
    Returns:
        The migrated payload
        
    Raises:
        ValueError: If script is from a future version
    """
    if not isinstance(data, dict):
        return {"schema_version": CUTSCENE_SCHEMA_VERSION, "commands": []}
    
    # Determine current version
    raw_version = data.get("schema_version", 0)
    try:
        version = int(raw_version)
    except (TypeError, ValueError):
        version = 0
    
    # Reject future versions
    if version > CUTSCENE_SCHEMA_VERSION:
        raise ValueError(
            f"Cutscene script is from a newer game version (schema v{version}, "
            f"this game supports up to v{CUTSCENE_SCHEMA_VERSION}). "
            f"Please update your game."
        )
    
    # Apply migrations sequentially
    while version < CUTSCENE_SCHEMA_VERSION:
        migration = _CUTSCENE_MIGRATIONS.get(version)
        if migration is None:
            # No explicit migration - just bump version
            version += 1
            data["schema_version"] = version
        else:
            data = migration(data)
            version = data.get("schema_version", version + 1)
    
    return data


def validate_cutscene_command(
    command: Any,
    *,
    file_path: str = "",
    command_index: int = 0,
    labels: set[str] | None = None,
) -> list[CutsceneValidationError]:
    """
    Validate a single cutscene command.
    
    Args:
        command: Command definition dict
        file_path: Source file path for error context
        command_index: Index in the commands array for JSON path
        labels: Set of defined labels (for goto validation)
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[CutsceneValidationError] = []
    base_path = f"commands[{command_index}]"
    
    if not isinstance(command, dict):
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path=base_path,
            code="command.type",
            message="Command must be an object",
            hint="Wrap command data in curly braces {}",
        ))
        return errors
    
    # Required: type
    cmd_type = command.get("type")
    if not cmd_type or not isinstance(cmd_type, str) or not cmd_type.strip():
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path=f"{base_path}.type",
            code="command.type.required",
            message="Command must have a non-empty 'type' string",
            hint=f"Add a command type like \"type\": \"wait\". Valid types: {sorted(VALID_COMMAND_TYPES)}",
        ))
        return errors
    
    cmd_type = cmd_type.strip()
    if cmd_type not in VALID_COMMAND_TYPES:
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path=f"{base_path}.type",
            code="command.type.invalid",
            message=f"Unknown command type '{cmd_type}'",
            hint=f"Valid types: {sorted(VALID_COMMAND_TYPES)}",
        ))
        return errors
    
    # Type-specific validation
    if cmd_type == "wait":
        errors.extend(_validate_wait_command(command, file_path, base_path))
    elif cmd_type == "emit_event":
        errors.extend(_validate_emit_event_command(command, file_path, base_path))
    elif cmd_type in ("set_flag", "clear_flag"):
        errors.extend(_validate_flag_command(command, file_path, base_path, cmd_type))
    elif cmd_type == "run_actions":
        errors.extend(_validate_run_actions_command(command, file_path, base_path))
    elif cmd_type == "start_dialogue":
        errors.extend(_validate_start_dialogue_command(command, file_path, base_path))
    elif cmd_type == "branch_on_flag":
        errors.extend(_validate_branch_command(command, file_path, base_path, labels))
    elif cmd_type == "goto":
        errors.extend(_validate_goto_command(command, file_path, base_path, labels))
    elif cmd_type == "label":
        errors.extend(_validate_label_command(command, file_path, base_path))
    # "stop" has no additional validation needed
    
    return errors


def _validate_wait_command(
    command: dict[str, Any],
    file_path: str,
    base_path: str,
) -> list[CutsceneValidationError]:
    """Validate wait command."""
    errors: list[CutsceneValidationError] = []
    
    duration = command.get("duration")
    if duration is None:
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path=f"{base_path}.duration",
            code="wait.duration.required",
            message="wait command requires 'duration'",
            hint="Add \"duration\": 1.0 for a 1-second wait",
        ))
    elif not isinstance(duration, (int, float)) or isinstance(duration, bool):
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path=f"{base_path}.duration",
            code="wait.duration.type",
            message=f"wait duration must be a number, got {type(duration).__name__}",
            hint="Use a numeric value like \"duration\": 1.5",
        ))
    elif duration < 0:
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path=f"{base_path}.duration",
            code="wait.duration.negative",
            message="wait duration cannot be negative",
            hint="Use a non-negative value",
        ))
    
    return errors


def _validate_emit_event_command(
    command: dict[str, Any],
    file_path: str,
    base_path: str,
) -> list[CutsceneValidationError]:
    """Validate emit_event command."""
    errors: list[CutsceneValidationError] = []
    
    event_type = command.get("event_type")
    if not event_type or not isinstance(event_type, str) or not event_type.strip():
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path=f"{base_path}.event_type",
            code="emit_event.event_type.required",
            message="emit_event command requires 'event_type'",
            hint="Add \"event_type\": \"my_event\"",
        ))
    
    payload = command.get("payload")
    if payload is not None and not isinstance(payload, dict):
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path=f"{base_path}.payload",
            code="emit_event.payload.type",
            message=f"emit_event payload must be an object, got {type(payload).__name__}",
            hint="Use format: \"payload\": {\"key\": \"value\"}",
        ))
    
    return errors


def _validate_flag_command(
    command: dict[str, Any],
    file_path: str,
    base_path: str,
    cmd_type: str,
) -> list[CutsceneValidationError]:
    """Validate set_flag/clear_flag command."""
    errors: list[CutsceneValidationError] = []
    
    flag = command.get("flag")
    if not flag or not isinstance(flag, str) or not flag.strip():
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path=f"{base_path}.flag",
            code=f"{cmd_type}.flag.required",
            message=f"{cmd_type} command requires 'flag'",
            hint="Add \"flag\": \"my_flag_name\"",
        ))
    
    return errors


def _validate_run_actions_command(
    command: dict[str, Any],
    file_path: str,
    base_path: str,
) -> list[CutsceneValidationError]:
    """Validate run_actions command."""
    errors: list[CutsceneValidationError] = []
    
    actions = command.get("actions")
    if actions is None:
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path=f"{base_path}.actions",
            code="run_actions.actions.required",
            message="run_actions command requires 'actions' array",
            hint="Add \"actions\": [{\"type\": \"emit_event\", ...}]",
        ))
    elif not isinstance(actions, list):
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path=f"{base_path}.actions",
            code="run_actions.actions.type",
            message=f"run_actions actions must be an array, got {type(actions).__name__}",
            hint="Use format: \"actions\": [...]",
        ))
    
    return errors


def _validate_start_dialogue_command(
    command: dict[str, Any],
    file_path: str,
    base_path: str,
) -> list[CutsceneValidationError]:
    """Validate start_dialogue command."""
    errors: list[CutsceneValidationError] = []
    
    # Either dialogue_id or target is required
    dialogue_id = command.get("dialogue_id")
    target = command.get("target")
    
    if not dialogue_id and not target:
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path=f"{base_path}",
            code="start_dialogue.target.required",
            message="start_dialogue requires 'dialogue_id' or 'target'",
            hint="Add \"dialogue_id\": \"my_dialogue\" or \"target\": \"EntityName\"",
        ))
    
    return errors


def _validate_branch_command(
    command: dict[str, Any],
    file_path: str,
    base_path: str,
    labels: set[str] | None,
) -> list[CutsceneValidationError]:
    """Validate branch_on_flag command."""
    errors: list[CutsceneValidationError] = []
    
    flag = command.get("flag")
    if not flag or not isinstance(flag, str) or not flag.strip():
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path=f"{base_path}.flag",
            code="branch_on_flag.flag.required",
            message="branch_on_flag command requires 'flag'",
            hint="Add \"flag\": \"my_flag_name\"",
        ))
    
    # At least one branch target required
    true_target = command.get("true_goto")
    false_target = command.get("false_goto")
    
    if not true_target and not false_target:
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path=f"{base_path}",
            code="branch_on_flag.target.required",
            message="branch_on_flag requires 'true_goto' and/or 'false_goto'",
            hint="Add \"true_goto\": \"label_name\" or \"false_goto\": \"label_name\"",
        ))
    
    # Validate label references if labels provided
    if labels is not None:
        for target_key in ("true_goto", "false_goto"):
            target = command.get(target_key)
            if target and isinstance(target, str) and target not in labels:
                errors.append(CutsceneValidationError(
                    file_path=file_path,
                    json_path=f"{base_path}.{target_key}",
                    code=f"branch_on_flag.{target_key}.undefined",
                    message=f"branch_on_flag {target_key} references undefined label '{target}'",
                    hint=f"Define a label: {{\"type\": \"label\", \"name\": \"{target}\"}}",
                ))
    
    return errors


def _validate_goto_command(
    command: dict[str, Any],
    file_path: str,
    base_path: str,
    labels: set[str] | None,
) -> list[CutsceneValidationError]:
    """Validate goto command."""
    errors: list[CutsceneValidationError] = []
    
    target = command.get("target")
    if not target or not isinstance(target, str) or not target.strip():
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path=f"{base_path}.target",
            code="goto.target.required",
            message="goto command requires 'target'",
            hint="Add \"target\": \"label_name\"",
        ))
    elif labels is not None and target not in labels:
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path=f"{base_path}.target",
            code="goto.target.undefined",
            message=f"goto references undefined label '{target}'",
            hint=f"Define a label: {{\"type\": \"label\", \"name\": \"{target}\"}}",
        ))
    
    return errors


def _validate_label_command(
    command: dict[str, Any],
    file_path: str,
    base_path: str,
) -> list[CutsceneValidationError]:
    """Validate label command."""
    errors: list[CutsceneValidationError] = []
    
    name = command.get("name")
    if not name or not isinstance(name, str) or not name.strip():
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path=f"{base_path}.name",
            code="label.name.required",
            message="label command requires 'name'",
            hint="Add \"name\": \"my_label\"",
        ))
    
    return errors


def validate_cutscene_script(
    data: Any,
    *,
    file_path: str = "",
    strict: bool = False,
) -> list[CutsceneValidationError]:
    """
    Validate a cutscene script.
    
    Args:
        data: Script data dict
        file_path: Source file path for error context
        strict: If True, enforce stricter validation rules
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[CutsceneValidationError] = []
    
    if not isinstance(data, dict):
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path="",
            code="script.root.type",
            message="Cutscene script must be a JSON object",
            hint="Wrap content in curly braces {}",
        ))
        return errors
    
    # Check schema version
    version = data.get("schema_version")
    if version is not None:
        if not isinstance(version, int) or version < 1:
            errors.append(CutsceneValidationError(
                file_path=file_path,
                json_path="schema_version",
                code="script.schema_version.invalid",
                message=f"Invalid schema_version: {version}",
                hint=f"Use schema_version: {CUTSCENE_SCHEMA_VERSION}",
            ))
    
    # Validate script ID if present
    script_id = data.get("id")
    if strict and not script_id:
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path="id",
            code="script.id.recommended",
            message="Script should have an 'id' for save/restore",
            hint="Add \"id\": \"my_cutscene\"",
        ))
    
    # Validate commands array
    commands = data.get("commands")
    if commands is None:
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path="commands",
            code="script.commands.required",
            message="Cutscene script must have a 'commands' array",
            hint="Add \"commands\": [...]",
        ))
        return errors
    
    if not isinstance(commands, list):
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path="commands",
            code="script.commands.type",
            message="'commands' must be an array",
            hint="Convert to array format: \"commands\": [...]",
        ))
        return errors
    
    # First pass: collect labels
    labels: set[str] = set()
    duplicate_labels: set[str] = set()
    for idx, cmd in enumerate(commands):
        if isinstance(cmd, dict) and cmd.get("type") == "label":
            name = cmd.get("name")
            if isinstance(name, str) and name.strip():
                name = name.strip()
                if name in labels:
                    duplicate_labels.add(name)
                else:
                    labels.add(name)
    
    # Report duplicate labels
    for dup in duplicate_labels:
        errors.append(CutsceneValidationError(
            file_path=file_path,
            json_path="commands",
            code="script.label.duplicate",
            message=f"Duplicate label '{dup}'",
            hint="Each label name must be unique",
        ))
    
    # Second pass: validate each command
    for idx, cmd in enumerate(commands):
        cmd_errors = validate_cutscene_command(
            cmd,
            file_path=file_path,
            command_index=idx,
            labels=labels,
        )
        errors.extend(cmd_errors)
    
    return errors


def sort_cutscene_validation_errors(errors: list[CutsceneValidationError]) -> list[CutsceneValidationError]:
    """Sort validation errors for deterministic output."""
    return sorted(
        errors,
        key=lambda e: (e.file_path, e.json_path, e.code, e.message),
    )
