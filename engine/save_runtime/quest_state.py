"""
SavedQuestState - Quest state for save/restore.

This module provides:
- SavedQuestState dataclass for serializing quest progress
- serialize_quests() to capture current quest state
- apply_quests() to restore quest state
- Migration support via schema_version

Design principles:
- Minimal: Only persist what's needed for meaningful restore
- Safe defaults: Missing fields use sensible defaults
- Extensible: Unknown fields preserved under x_ namespace
- Deterministic: Output is sorted and stable for hashing
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine.diagnostics import Diagnostic, DiagnosticLevel
from engine.log_utils import normalize_path

# Schema version for quest state serialization
QUEST_STATE_SCHEMA_VERSION = 1


def _diagnostic(
    *,
    level: DiagnosticLevel,
    code: str,
    message: str,
    source: str,
    pointer: str,
    hint: str | None = None,
    context_extra: dict[str, Any] | None = None,
) -> Diagnostic:
    context: dict[str, Any] = {
        "source": normalize_path(source),
        "pointer": pointer,
    }
    if context_extra:
        for key in sorted(context_extra.keys()):
            context[str(key)] = context_extra[key]
    return Diagnostic(
        level=level,
        code=code,
        message=str(message),
        context=context,
        hint=hint,
    )


def _append_diagnostic(diagnostics: list[Diagnostic] | None, diagnostic: Diagnostic) -> None:
    if diagnostics is not None:
        diagnostics.append(diagnostic)


@dataclass
class SavedQuestState:
    """Quest state for persistence.
    
    Fields:
        quest_id: Unique identifier for this quest
        state: Quest state ("inactive", "active", "completed", "failed")
        current_step: Current step index or identifier
        counters: Dict of progress counters (e.g. {"enemies_killed": 3})
        timestamp_started: Optional ISO timestamp when quest started
        timestamp_completed: Optional ISO timestamp when quest completed
        x_extra: Extension fields for forward compatibility
    """
    quest_id: str
    state: str = "inactive"
    current_step: int | str = 0
    counters: dict[str, int] = field(default_factory=dict)
    timestamp_started: str | None = None
    timestamp_completed: str | None = None
    x_extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-friendly dict."""
        result: dict[str, Any] = {
            "quest_id": self.quest_id,
            "state": self.state,
        }

        if self.current_step != 0:
            result["current_step"] = self.current_step

        if self.counters:
            result["counters"] = dict(sorted(self.counters.items()))

        if self.timestamp_started:
            result["timestamp_started"] = self.timestamp_started

        if self.timestamp_completed:
            result["timestamp_completed"] = self.timestamp_completed

        # Preserve unknown fields under x_ namespace
        if self.x_extra:
            for k, v in sorted(self.x_extra.items()):
                if k.startswith("x_"):
                    result[k] = v

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SavedQuestState":
        """Deserialize from dict with safe defaults."""
        if not isinstance(data, dict):
            return cls(quest_id="unknown")

        quest_id = str(data.get("quest_id", "") or data.get("id", "") or "").strip()
        if not quest_id:
            quest_id = "unknown"

        state = str(data.get("state", "inactive") or "inactive").lower()
        if state not in ("inactive", "active", "completed", "failed"):
            state = "inactive"

        current_step = data.get("current_step", 0)
        if current_step is None:
            current_step = 0
        elif isinstance(current_step, str):
            current_step = current_step.strip() or 0
        else:
            try:
                current_step = int(current_step)
            except (TypeError, ValueError):
                current_step = 0

        counters_raw = data.get("counters", {})
        counters: dict[str, int] = {}
        if isinstance(counters_raw, dict):
            for k, v in counters_raw.items():
                key = str(k).strip()
                if not key:
                    continue
                try:
                    counters[key] = int(v)
                except (TypeError, ValueError):
                    counters[key] = 0

        timestamp_started = data.get("timestamp_started")
        if timestamp_started is not None:
            timestamp_started = str(timestamp_started).strip() or None

        timestamp_completed = data.get("timestamp_completed")
        if timestamp_completed is not None:
            timestamp_completed = str(timestamp_completed).strip() or None

        # Collect x_ extension fields
        x_extra: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(k, str) and k.startswith("x_"):
                x_extra[k] = v

        return cls(
            quest_id=quest_id,
            state=state,
            current_step=current_step,
            counters=counters,
            timestamp_started=timestamp_started,
            timestamp_completed=timestamp_completed,
            x_extra=x_extra,
        )


def serialize_quest(quest: Any) -> SavedQuestState | None:
    """Extract SavedQuestState from a Quest object.
    
    Args:
        quest: A Quest object from QuestManager
        
    Returns:
        SavedQuestState or None if quest has no valid ID
    """
    quest_id = getattr(quest, "id", None)
    if not isinstance(quest_id, str) or not quest_id.strip():
        return None

    quest_id = quest_id.strip()

    state = getattr(quest, "state", "inactive")
    if not isinstance(state, str):
        state = "inactive"
    state = state.lower()
    if state not in ("inactive", "active", "completed", "failed"):
        state = "inactive"

    # Get current step if available
    current_step = getattr(quest, "current_step", 0)
    if current_step is None:
        current_step = 0

    # Get counters if available
    counters: dict[str, int] = {}
    quest_counters = getattr(quest, "counters", None)
    if isinstance(quest_counters, dict):
        for k, v in quest_counters.items():
            key = str(k).strip()
            if key:
                try:
                    counters[key] = int(v)
                except (TypeError, ValueError):
                    pass

    # Get timestamps if available
    timestamp_started = getattr(quest, "timestamp_started", None)
    timestamp_completed = getattr(quest, "timestamp_completed", None)

    return SavedQuestState(
        quest_id=quest_id,
        state=state,
        current_step=current_step,
        counters=counters,
        timestamp_started=timestamp_started if isinstance(timestamp_started, str) else None,
        timestamp_completed=timestamp_completed if isinstance(timestamp_completed, str) else None,
    )


def serialize_quests(quest_manager: Any) -> dict[str, Any]:
    """Serialize all quests from a QuestManager.
    
    Args:
        quest_manager: QuestManager or similar with get_all_quests()
        
    Returns:
        Dict with "schema_version" and "quests" containing quest states
    """
    result: dict[str, Any] = {
        "schema_version": QUEST_STATE_SCHEMA_VERSION,
        "quests": {},
    }

    # Try to get quests from manager
    quests: list[Any] = []
    if hasattr(quest_manager, "get_all_quests"):
        quests = quest_manager.get_all_quests() or []
    elif hasattr(quest_manager, "_quests"):
        quests = list(getattr(quest_manager, "_quests", {}).values())

    for quest in quests:
        state = serialize_quest(quest)
        if state is not None:
            result["quests"][state.quest_id] = state.to_dict()

    # Sort quests for determinism
    result["quests"] = dict(sorted(result["quests"].items()))

    return result


def apply_quest_state(
    quest: Any,
    state: SavedQuestState,
    *,
    diagnostics: list[Diagnostic] | None = None,
    source: str = "save_runtime/quest_state",
) -> bool:
    """Apply saved state to an existing quest.
    
    Args:
        quest: Target Quest object
        state: SavedQuestState to apply
        
    Returns:
        True if state was applied, False on error
    """
    try:
        # Apply state
        if hasattr(quest, "state"):
            quest.state = state.state

        # Apply current_step if supported
        if hasattr(quest, "current_step"):
            quest.current_step = state.current_step

        # Apply counters if supported
        if hasattr(quest, "counters") and state.counters:
            if isinstance(quest.counters, dict):
                quest.counters.update(state.counters)
            else:
                quest.counters = dict(state.counters)

        # Apply timestamps if supported
        if hasattr(quest, "timestamp_started") and state.timestamp_started:
            quest.timestamp_started = state.timestamp_started
        if hasattr(quest, "timestamp_completed") and state.timestamp_completed:
            quest.timestamp_completed = state.timestamp_completed

        return True
    except Exception as exc:
        _append_diagnostic(
            diagnostics,
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="save.restore.quest_apply_failed",
                message=f"Failed to apply quest '{state.quest_id}': {exc}",
                source=source,
                pointer=f"/saved_quests/quests/{state.quest_id}",
                hint="Verify quest state payload fields and runtime quest object compatibility.",
            ),
        )
        return False


def apply_quests(
    quest_manager: Any,
    saved_quests: dict[str, Any],
    *,
    diagnostics: list[Diagnostic] | None = None,
    source: str = "save_runtime/quest_state",
) -> tuple[int, int]:
    """Apply saved quest states to quest manager.
    
    Args:
        quest_manager: QuestManager to update
        saved_quests: Dict from serialize_quests() with "quests" key
        
    Returns:
        Tuple of (applied_count, created_count)
    """
    if not isinstance(saved_quests, dict):
        _append_diagnostic(
            diagnostics,
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="save.restore.quest_payload_invalid",
                message="saved_quests payload must be an object.",
                source=source,
                pointer="/saved_quests",
                hint="Expected {'schema_version': int, 'quests': {...}}.",
            ),
        )
        return (0, 0)

    quests_data = saved_quests.get("quests", saved_quests)
    if not isinstance(quests_data, dict):
        _append_diagnostic(
            diagnostics,
            _diagnostic(
                level=DiagnosticLevel.ERROR,
                code="save.restore.quest_entries_invalid",
                message="saved_quests.quests must be an object.",
                source=source,
                pointer="/saved_quests/quests",
                hint="Provide quest-id keyed objects.",
            ),
        )
        return (0, 0)

    applied = 0
    created = 0

    for quest_id, quest_dict in quests_data.items():
        if not isinstance(quest_dict, dict):
            continue

        state = SavedQuestState.from_dict(quest_dict)

        # Try to find existing quest
        quest = None
        if hasattr(quest_manager, "get_quest"):
            quest = quest_manager.get_quest(state.quest_id)
        elif hasattr(quest_manager, "_quests"):
            quest = quest_manager._quests.get(state.quest_id)

        if quest is not None:
            # Update existing quest
            if apply_quest_state(
                quest,
                state,
                diagnostics=diagnostics,
                source=source,
            ):
                applied += 1
        else:
            # Register new quest if manager supports it
            if hasattr(quest_manager, "register_quest"):
                try:
                    new_quest = quest_manager.register_quest({
                        "id": state.quest_id,
                        "title": state.quest_id,
                        "state": state.state,
                    })
                    if new_quest is not None:
                        apply_quest_state(
                            new_quest,
                            state,
                            diagnostics=diagnostics,
                            source=source,
                        )
                        created += 1
                except Exception as exc:
                    _append_diagnostic(
                        diagnostics,
                        _diagnostic(
                            level=DiagnosticLevel.ERROR,
                            code="save.restore.quest_register_failed",
                            message=f"Failed to register quest '{state.quest_id}': {exc}",
                            source=source,
                            pointer=f"/saved_quests/quests/{state.quest_id}",
                            hint="Ensure quest manager accepts dynamic register_quest payloads.",
                        ),
                    )
            else:
                _append_diagnostic(
                    diagnostics,
                    _diagnostic(
                        level=DiagnosticLevel.WARN,
                        code="save.restore.quest_manager_missing_register",
                        message=f"Quest manager cannot register missing quest '{state.quest_id}'.",
                        source=source,
                        pointer=f"/saved_quests/quests/{state.quest_id}",
                        hint="Provide quest definitions before loading saves with new quests.",
                    ),
                )

    return (applied, created)


def migrate_quest_state_v0(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate v0 quest state (no schema_version) to v1.
    
    v0 may have:
    - "id" instead of "quest_id"
    - "status" instead of "state"
    - Missing counters
    """
    # Add schema version
    data["schema_version"] = QUEST_STATE_SCHEMA_VERSION

    quests = data.get("quests", {})
    if isinstance(quests, dict):
        for quest_id, quest_data in quests.items():
            if not isinstance(quest_data, dict):
                continue

            # Normalize quest_id
            if "quest_id" not in quest_data and "id" in quest_data:
                quest_data["quest_id"] = quest_data.pop("id")
            if "quest_id" not in quest_data:
                quest_data["quest_id"] = quest_id

            # Normalize state
            if "state" not in quest_data and "status" in quest_data:
                quest_data["state"] = quest_data.pop("status")

            # Ensure counters exists
            if "counters" not in quest_data:
                quest_data["counters"] = {}

    return data
