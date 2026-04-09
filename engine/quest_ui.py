from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class QuestSummary:
    quest_id: str
    title: str
    current_objective: str
    is_complete: bool


def _resolve_manager(window: Any) -> Any | None:
    manager = getattr(window, "quest_manager", None)
    if manager is not None and callable(getattr(manager, "list_active_quests", None)):
        return manager
    controller = getattr(window, "game_state_controller", None)
    manager = getattr(controller, "quests", None) if controller is not None else None
    if manager is not None and callable(getattr(manager, "list_active_quests", None)):
        return manager
    return None


def _iter_entries(manager: Any) -> Iterable[dict[str, Any]]:
    try:
        entries = manager.list_active_quests()
    except Exception:  # noqa: BLE001  # REASON: quest-manager list failures should fall back to no active quest entries for the UI
        return []
    return entries if isinstance(entries, list) else []


def get_active_quests(window: Any) -> list[QuestSummary]:
    manager = _resolve_manager(window)
    if manager is None:
        return []

    summaries: list[QuestSummary] = []
    for entry in _iter_entries(manager):
        if not isinstance(entry, dict):
            continue
        quest_id = str(entry.get("id") or "").strip()
        if not quest_id:
            continue
        status = str(entry.get("status") or entry.get("state") or "inactive").strip().lower()
        if status == "inactive":
            continue
        title = str(entry.get("title") or quest_id).strip()
        objective = (
            str(entry.get("stage_text") or entry.get("stage_title") or entry.get("description") or "")
        ).strip()
        completed = bool(entry.get("completed")) or status == "completed"
        summaries.append(
            QuestSummary(
                quest_id=quest_id,
                title=title,
                current_objective=objective,
                is_complete=completed,
            )
        )
    return summaries
