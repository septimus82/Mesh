"""Quest definition validation and migration framework.

This module provides:
- QUEST_DEFINITION_SCHEMA_VERSION tracking
- validate_quest_definition() for structural validation with actionable errors
- validate_quest_file() for file-level validation
- migrate_quest_definition() for upgrading old definitions

Validation produces QuestValidationError objects with:
- file_path: The source file (for editor integration)
- json_path: JSON pointer to the invalid field (e.g. "quests[0].stages[1].complete_on")
- code: Machine-readable error code for categorization
- message: Human-readable error description
- hint: Actionable suggestion for fixing the issue
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


# Current quest definition schema version.
# Increment when adding new required fields or changing semantics.
# v1: Initial schema with stages, rewards, triggers
QUEST_DEFINITION_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class QuestValidationError:
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
QuestMigrationFn = Callable[[dict[str, Any]], dict[str, Any]]

# Registry of migrations: version -> function that upgrades to next version
_QUEST_MIGRATIONS: dict[int, QuestMigrationFn] = {}


def register_quest_migration(from_version: int) -> Callable[[QuestMigrationFn], QuestMigrationFn]:
    """Decorator to register a quest definition migration function."""
    def decorator(fn: QuestMigrationFn) -> QuestMigrationFn:
        _QUEST_MIGRATIONS[from_version] = fn
        return fn
    return decorator


@register_quest_migration(0)
def _migrate_v0_to_v1(data: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate v0 (no schema_version field) to v1.
    
    v0 definitions may be missing:
    - schema_version field
    - Consistent trigger field naming (complete_on vs complete_event)
    """
    data["schema_version"] = 1
    
    # Normalize quests array
    quests = data.get("quests")
    if isinstance(quests, dict):
        # Convert dict-style quests to list
        data["quests"] = list(quests.values())
    elif not isinstance(quests, list):
        data["quests"] = []
    
    # Normalize each quest's stages
    for quest in data.get("quests", []):
        if not isinstance(quest, dict):
            continue
        stages = quest.get("stages")
        if isinstance(stages, dict):
            quest["stages"] = list(stages.values())
    
    return data


def migrate_quest_definition(data: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate a quest definition payload to the current schema version.
    
    Args:
        data: Raw quest definition payload (will be modified in place)
        
    Returns:
        The migrated payload
        
    Raises:
        ValueError: If definition is from a future version
    """
    if not isinstance(data, dict):
        return {"schema_version": QUEST_DEFINITION_SCHEMA_VERSION, "quests": []}
    
    # Determine current version
    raw_version = data.get("schema_version", 0)
    try:
        version = int(raw_version)
    except (TypeError, ValueError):
        version = 0
    
    # Reject future versions
    if version > QUEST_DEFINITION_SCHEMA_VERSION:
        raise ValueError(
            f"Quest definitions are from a newer game version (schema v{version}, "
            f"this game supports up to v{QUEST_DEFINITION_SCHEMA_VERSION}). "
            f"Please update your game."
        )
    
    # Apply migrations sequentially
    while version < QUEST_DEFINITION_SCHEMA_VERSION:
        migration = _QUEST_MIGRATIONS.get(version)
        if migration is None:
            # No explicit migration - just bump version
            version += 1
            data["schema_version"] = version
        else:
            data = migration(data)
            version = data.get("schema_version", version + 1)
    
    return data


def validate_quest_definition(
    quest: Any,
    *,
    file_path: str = "",
    quest_index: int = 0,
    strict: bool = False,
) -> list[QuestValidationError]:
    """
    Validate a single quest definition.
    
    Args:
        quest: Quest definition dict
        file_path: Source file path for error context
        quest_index: Index in the quests array for JSON path
        strict: If True, enforce stricter validation rules
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[QuestValidationError] = []
    base_path = f"quests[{quest_index}]"
    
    if not isinstance(quest, dict):
        errors.append(QuestValidationError(
            file_path=file_path,
            json_path=base_path,
            code="quest.type",
            message="Quest definition must be an object",
            hint="Wrap quest data in curly braces {}",
        ))
        return errors
    
    # Required: id
    quest_id = quest.get("id")
    if not quest_id or not isinstance(quest_id, str) or not quest_id.strip():
        errors.append(QuestValidationError(
            file_path=file_path,
            json_path=f"{base_path}.id",
            code="quest.id.required",
            message="Quest must have a non-empty 'id' string",
            hint="Add a unique identifier like \"id\": \"my_quest\"",
        ))
        quest_id = f"<unnamed_{quest_index}>"
    else:
        quest_id = quest_id.strip()
        # Validate id format
        if not quest_id.replace("_", "").replace("-", "").isalnum():
            errors.append(QuestValidationError(
                file_path=file_path,
                json_path=f"{base_path}.id",
                code="quest.id.format",
                message=f"Quest id '{quest_id}' contains invalid characters",
                hint="Use only letters, numbers, underscores, and hyphens",
            ))
    
    # Required: title
    title = quest.get("title")
    if not title or not isinstance(title, str) or not title.strip():
        errors.append(QuestValidationError(
            file_path=file_path,
            json_path=f"{base_path}.title",
            code="quest.title.required",
            message=f"Quest '{quest_id}' must have a non-empty 'title' string",
            hint="Add a display name like \"title\": \"My Quest\"",
        ))
    
    # Optional but recommended: description
    if strict:
        description = quest.get("description")
        if not description or not isinstance(description, str) or not description.strip():
            errors.append(QuestValidationError(
                file_path=file_path,
                json_path=f"{base_path}.description",
                code="quest.description.recommended",
                message=f"Quest '{quest_id}' should have a 'description' for the quest log",
                hint="Add a brief description of the quest objective",
            ))
    
    # Required: stages
    stages = quest.get("stages")
    if stages is None:
        errors.append(QuestValidationError(
            file_path=file_path,
            json_path=f"{base_path}.stages",
            code="quest.stages.required",
            message=f"Quest '{quest_id}' must have a 'stages' array",
            hint="Add stages array with at least one stage object",
        ))
    elif not isinstance(stages, list):
        errors.append(QuestValidationError(
            file_path=file_path,
            json_path=f"{base_path}.stages",
            code="quest.stages.type",
            message=f"Quest '{quest_id}' stages must be an array",
            hint="Convert stages to an array: \"stages\": [...]",
        ))
    elif len(stages) == 0:
        errors.append(QuestValidationError(
            file_path=file_path,
            json_path=f"{base_path}.stages",
            code="quest.stages.empty",
            message=f"Quest '{quest_id}' must have at least one stage",
            hint="Add at least one stage object to the stages array",
        ))
    else:
        # Validate each stage
        seen_stage_ids: set[str] = set()
        for stage_idx, stage in enumerate(stages):
            stage_errors = _validate_stage(
                stage,
                file_path=file_path,
                quest_id=quest_id,
                quest_index=quest_index,
                stage_index=stage_idx,
                seen_ids=seen_stage_ids,
                strict=strict,
            )
            errors.extend(stage_errors)
    
    # Validate reward structure if present
    reward = quest.get("reward")
    if reward is not None:
        reward_errors = _validate_reward(
            reward,
            file_path=file_path,
            quest_id=quest_id,
            quest_index=quest_index,
        )
        errors.extend(reward_errors)
    
    # Validate flags arrays
    for flag_field in ("requires_flags", "blocks_flags"):
        flags = quest.get(flag_field)
        if flags is not None and not isinstance(flags, list):
            errors.append(QuestValidationError(
                file_path=file_path,
                json_path=f"{base_path}.{flag_field}",
                code=f"quest.{flag_field}.type",
                message=f"Quest '{quest_id}' {flag_field} must be an array",
                hint=f"Convert to array: \"{flag_field}\": [\"flag_name\"]",
            ))
        elif isinstance(flags, list):
            for idx, flag in enumerate(flags):
                if not isinstance(flag, str) or not flag.strip():
                    errors.append(QuestValidationError(
                        file_path=file_path,
                        json_path=f"{base_path}.{flag_field}[{idx}]",
                        code=f"quest.{flag_field}.item.type",
                        message=f"Quest '{quest_id}' {flag_field}[{idx}] must be a non-empty string",
                        hint="Provide a valid flag name",
                    ))
    
    return errors


def _validate_stage(
    stage: Any,
    *,
    file_path: str,
    quest_id: str,
    quest_index: int,
    stage_index: int,
    seen_ids: set[str],
    strict: bool,
) -> list[QuestValidationError]:
    """Validate a single quest stage."""
    errors: list[QuestValidationError] = []
    base_path = f"quests[{quest_index}].stages[{stage_index}]"
    
    if not isinstance(stage, dict):
        errors.append(QuestValidationError(
            file_path=file_path,
            json_path=base_path,
            code="stage.type",
            message=f"Quest '{quest_id}' stage[{stage_index}] must be an object",
            hint="Wrap stage data in curly braces {}",
        ))
        return errors
    
    # Required: id
    stage_id = stage.get("id")
    if not stage_id or not isinstance(stage_id, str) or not stage_id.strip():
        errors.append(QuestValidationError(
            file_path=file_path,
            json_path=f"{base_path}.id",
            code="stage.id.required",
            message=f"Quest '{quest_id}' stage[{stage_index}] must have a non-empty 'id'",
            hint="Add a unique identifier like \"id\": \"stage_1\"",
        ))
        stage_id = f"<unnamed_{stage_index}>"
    else:
        stage_id = stage_id.strip()
        if stage_id in seen_ids:
            errors.append(QuestValidationError(
                file_path=file_path,
                json_path=f"{base_path}.id",
                code="stage.id.duplicate",
                message=f"Quest '{quest_id}' has duplicate stage id '{stage_id}'",
                hint="Each stage in a quest must have a unique id",
            ))
        else:
            seen_ids.add(stage_id)
    
    # Required: title
    title = stage.get("title")
    if not title or not isinstance(title, str) or not title.strip():
        errors.append(QuestValidationError(
            file_path=file_path,
            json_path=f"{base_path}.title",
            code="stage.title.required",
            message=f"Quest '{quest_id}' stage '{stage_id}' must have a 'title'",
            hint="Add a display title like \"title\": \"Find the key\"",
        ))
    
    # Validate event triggers
    for trigger_field in ("start_on_event", "start_event", "start_on"):
        trigger = stage.get(trigger_field)
        if trigger is not None:
            trigger_errors = _validate_event_trigger(
                trigger,
                file_path=file_path,
                json_path=f"{base_path}.{trigger_field}",
                quest_id=quest_id,
                stage_id=stage_id,
                trigger_type="start",
            )
            errors.extend(trigger_errors)
            break  # Only validate first found trigger variant
    
    for trigger_field in ("complete_on", "complete_event", "complete_when"):
        trigger = stage.get(trigger_field)
        if trigger is not None:
            trigger_errors = _validate_event_trigger(
                trigger,
                file_path=file_path,
                json_path=f"{base_path}.{trigger_field}",
                quest_id=quest_id,
                stage_id=stage_id,
                trigger_type="complete",
            )
            errors.extend(trigger_errors)
            break
    
    # Validate requirements if present
    requirements = stage.get("requirements") or stage.get("reqs") or stage.get("conditions")
    if requirements is not None:
        req_path = f"{base_path}.requirements"
        if not isinstance(requirements, dict):
            errors.append(QuestValidationError(
                file_path=file_path,
                json_path=req_path,
                code="stage.requirements.type",
                message=f"Quest '{quest_id}' stage '{stage_id}' requirements must be an object",
                hint="Use format: \"requirements\": {\"counters\": {...}, \"flags\": {...}}",
            ))
        else:
            # Validate counters
            counters = requirements.get("counters")
            if counters is not None and not isinstance(counters, dict):
                errors.append(QuestValidationError(
                    file_path=file_path,
                    json_path=f"{req_path}.counters",
                    code="stage.requirements.counters.type",
                    message=f"Quest '{quest_id}' stage '{stage_id}' requirements.counters must be an object",
                    hint="Use format: \"counters\": {\"counter_name\": target_value}",
                ))
            elif isinstance(counters, dict):
                for counter_name, target in counters.items():
                    if not isinstance(target, (int, float)) or isinstance(target, bool):
                        errors.append(QuestValidationError(
                            file_path=file_path,
                            json_path=f"{req_path}.counters.{counter_name}",
                            code="stage.requirements.counters.value.type",
                            message=f"Quest '{quest_id}' stage '{stage_id}' counter target '{counter_name}' must be a number",
                            hint=f"Use a numeric value like \"{counter_name}\": 5",
                        ))
            
            # Validate flags
            flags = requirements.get("flags")
            if flags is not None and not isinstance(flags, dict):
                errors.append(QuestValidationError(
                    file_path=file_path,
                    json_path=f"{req_path}.flags",
                    code="stage.requirements.flags.type",
                    message=f"Quest '{quest_id}' stage '{stage_id}' requirements.flags must be an object",
                    hint="Use format: \"flags\": {\"flag_name\": true}",
                ))
    
    return errors


def _validate_event_trigger(
    trigger: Any,
    *,
    file_path: str,
    json_path: str,
    quest_id: str,
    stage_id: str,
    trigger_type: str,
) -> list[QuestValidationError]:
    """Validate an event trigger (start_on_event, complete_on, etc.)."""
    errors: list[QuestValidationError] = []
    
    # String shorthand is valid
    if isinstance(trigger, str):
        if not trigger.strip():
            errors.append(QuestValidationError(
                file_path=file_path,
                json_path=json_path,
                code=f"trigger.{trigger_type}.empty",
                message=f"Quest '{quest_id}' stage '{stage_id}' {trigger_type} trigger must not be empty",
                hint="Provide an event type name or trigger object",
            ))
        return errors
    
    if not isinstance(trigger, dict):
        errors.append(QuestValidationError(
            file_path=file_path,
            json_path=json_path,
            code=f"trigger.{trigger_type}.type",
            message=f"Quest '{quest_id}' stage '{stage_id}' {trigger_type} trigger must be a string or object",
            hint="Use \"event_type\" or {\"type\": \"event_type\", \"payload\": {...}}",
        ))
        return errors
    
    # Object form requires 'type'
    event_type = trigger.get("type") or trigger.get("event")
    if not event_type or not isinstance(event_type, str) or not event_type.strip():
        errors.append(QuestValidationError(
            file_path=file_path,
            json_path=f"{json_path}.type",
            code=f"trigger.{trigger_type}.type.required",
            message=f"Quest '{quest_id}' stage '{stage_id}' {trigger_type} trigger must have a 'type' field",
            hint="Add event type like \"type\": \"dialogue_choice\"",
        ))
    
    # Validate payload if present
    payload = trigger.get("payload")
    if payload is not None and not isinstance(payload, dict):
        errors.append(QuestValidationError(
            file_path=file_path,
            json_path=f"{json_path}.payload",
            code=f"trigger.{trigger_type}.payload.type",
            message=f"Quest '{quest_id}' stage '{stage_id}' {trigger_type} trigger payload must be an object",
            hint="Use format: \"payload\": {\"key\": \"value\"}",
        ))
    
    return errors


def _validate_reward(
    reward: Any,
    *,
    file_path: str,
    quest_id: str,
    quest_index: int,
) -> list[QuestValidationError]:
    """Validate quest reward structure."""
    errors: list[QuestValidationError] = []
    base_path = f"quests[{quest_index}].reward"
    
    if not isinstance(reward, dict):
        errors.append(QuestValidationError(
            file_path=file_path,
            json_path=base_path,
            code="reward.type",
            message=f"Quest '{quest_id}' reward must be an object",
            hint="Use format: \"reward\": {\"set_flags\": {...}, \"inc_counters\": {...}}",
        ))
        return errors
    
    # Validate set_flags
    set_flags = reward.get("set_flags")
    if set_flags is not None:
        if not isinstance(set_flags, dict):
            errors.append(QuestValidationError(
                file_path=file_path,
                json_path=f"{base_path}.set_flags",
                code="reward.set_flags.type",
                message=f"Quest '{quest_id}' reward.set_flags must be an object",
                hint="Use format: \"set_flags\": {\"flag_name\": true}",
            ))
        else:
            for flag_name, value in set_flags.items():
                if not isinstance(value, bool):
                    errors.append(QuestValidationError(
                        file_path=file_path,
                        json_path=f"{base_path}.set_flags.{flag_name}",
                        code="reward.set_flags.value.type",
                        message=f"Quest '{quest_id}' reward.set_flags.{flag_name} must be a boolean",
                        hint="Use true or false",
                    ))
    
    # Validate inc_counters
    inc_counters = reward.get("inc_counters")
    if inc_counters is not None:
        if not isinstance(inc_counters, dict):
            errors.append(QuestValidationError(
                file_path=file_path,
                json_path=f"{base_path}.inc_counters",
                code="reward.inc_counters.type",
                message=f"Quest '{quest_id}' reward.inc_counters must be an object",
                hint="Use format: \"inc_counters\": {\"gold\": 100}",
            ))
        else:
            for counter_name, value in inc_counters.items():
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    errors.append(QuestValidationError(
                        file_path=file_path,
                        json_path=f"{base_path}.inc_counters.{counter_name}",
                        code="reward.inc_counters.value.type",
                        message=f"Quest '{quest_id}' reward.inc_counters.{counter_name} must be a number",
                        hint="Use a numeric value",
                    ))
    
    # Validate gold/xp shortcuts
    for field in ("gold", "xp"):
        value = reward.get(field)
        if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)):
            errors.append(QuestValidationError(
                file_path=file_path,
                json_path=f"{base_path}.{field}",
                code=f"reward.{field}.type",
                message=f"Quest '{quest_id}' reward.{field} must be a number",
                hint=f"Use a numeric value like \"{field}\": 100",
            ))
    
    return errors


def validate_quest_file(
    path: Path,
    data: Any,
    *,
    strict: bool = False,
) -> list[QuestValidationError]:
    """
    Validate a quest definition file.
    
    Args:
        path: File path for error context
        data: Parsed JSON data
        strict: If True, enforce stricter validation rules
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[QuestValidationError] = []
    file_path = str(path)
    
    if not isinstance(data, dict):
        errors.append(QuestValidationError(
            file_path=file_path,
            json_path="",
            code="file.root.type",
            message="Quest file must contain a JSON object",
            hint="Wrap content in curly braces {}",
        ))
        return errors
    
    # Check schema version
    version = data.get("schema_version")
    if version is not None:
        if not isinstance(version, int) or version < 1:
            errors.append(QuestValidationError(
                file_path=file_path,
                json_path="schema_version",
                code="file.schema_version.invalid",
                message=f"Invalid schema_version: {version}",
                hint=f"Use schema_version: {QUEST_DEFINITION_SCHEMA_VERSION}",
            ))
    
    # Validate quests array
    quests = data.get("quests")
    if quests is None:
        errors.append(QuestValidationError(
            file_path=file_path,
            json_path="quests",
            code="file.quests.required",
            message="Quest file must have a 'quests' array",
            hint="Add \"quests\": [...] to the file",
        ))
        return errors
    
    if not isinstance(quests, list):
        errors.append(QuestValidationError(
            file_path=file_path,
            json_path="quests",
            code="file.quests.type",
            message="'quests' must be an array",
            hint="Convert to array format: \"quests\": [...]",
        ))
        return errors
    
    # Check for duplicate quest IDs
    seen_quest_ids: dict[str, int] = {}
    for idx, quest in enumerate(quests):
        if isinstance(quest, dict):
            qid = quest.get("id")
            if isinstance(qid, str) and qid.strip():
                qid = qid.strip()
                if qid in seen_quest_ids:
                    errors.append(QuestValidationError(
                        file_path=file_path,
                        json_path=f"quests[{idx}].id",
                        code="file.quests.id.duplicate",
                        message=f"Duplicate quest id '{qid}' (first at index {seen_quest_ids[qid]})",
                        hint="Each quest must have a unique id",
                    ))
                else:
                    seen_quest_ids[qid] = idx
    
    # Validate each quest
    for idx, quest in enumerate(quests):
        quest_errors = validate_quest_definition(
            quest,
            file_path=file_path,
            quest_index=idx,
            strict=strict,
        )
        errors.extend(quest_errors)
    
    return errors


def sort_quest_validation_errors(errors: list[QuestValidationError]) -> list[QuestValidationError]:
    """Sort validation errors for deterministic output."""
    return sorted(
        errors,
        key=lambda e: (e.file_path, e.json_path, e.code, e.message),
    )
