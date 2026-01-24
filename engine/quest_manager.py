from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .migrations import migrate_payload

if TYPE_CHECKING:
    from .game_state_controller import GameStateController


@dataclass
class Quest:
    id: str
    title: str
    description: str = ""
    state: str = "inactive"  # inactive, active, completed, failed
    tags: List[str] = field(default_factory=list)
    requirements: Dict[str, Any] = field(default_factory=dict)  # flags/counters requirements


class QuestManager:
    """Lightweight quest tracker driven by GameState flags/counters."""

    def __init__(self) -> None:
        self._quests: Dict[str, Quest] = {}

    # ------------------------------------------------------------------ #
    # Quest registry and lookup                                          #
    # ------------------------------------------------------------------ #
    def register_quest(self, data: Dict[str, Any]) -> Quest:
        quest_id = str(data.get("id", "")).strip()
        if not quest_id:
            raise ValueError("Quest id is required")
        title = str(data.get("title") or quest_id).strip()
        description = str(data.get("description", "") or "").strip()
        state = str(data.get("state", "inactive") or "inactive").lower()
        tags = list(data.get("tags", []) or [])
        requirements = dict(data.get("requirements", {}) or {})

        quest = self._quests.get(quest_id)
        if quest is None:
            quest = Quest(
                id=quest_id,
                title=title,
                description=description,
                state=state if state in {"inactive", "active", "completed", "failed"} else "inactive",
                tags=tags,
                requirements=requirements,
            )
            self._quests[quest_id] = quest
        else:
            quest.title = title
            quest.description = description
            quest.tags = tags
            quest.requirements = requirements
            if state in {"inactive", "active", "completed", "failed"}:
                quest.state = state
        return quest

    def get_quest(self, quest_id: str) -> Optional[Quest]:
        return self._quests.get(quest_id)

    def get_all_quests(self) -> List[Quest]:
        return list(self._quests.values())

    def get_quests_by_state(self, state: str) -> List[Quest]:
        s = str(state or "").lower()
        return [q for q in self._quests.values() if q.state == s]

    # ------------------------------------------------------------------ #
    # State transitions                                                  #
    # ------------------------------------------------------------------ #
    def start_quest(self, quest_id: str) -> None:
        quest = self._quests.get(quest_id)
        if quest is None:
            quest = self.register_quest({"id": quest_id, "title": quest_id})
        if quest.state in {"completed", "failed"}:
            return
        quest.state = "active"

    def complete_quest(self, quest_id: str) -> None:
        quest = self._quests.get(quest_id)
        if quest is None:
            return
        if quest.state == "failed":
            return
        quest.state = "completed"

    def fail_quest(self, quest_id: str) -> None:
        quest = self._quests.get(quest_id)
        if quest is None:
            return
        if quest.state == "completed":
            return
        quest.state = "failed"

    # ------------------------------------------------------------------ #
    # Persistence                                                        #
    # ------------------------------------------------------------------ #
    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for quest in self._quests.values():
            payload[quest.id] = {
                "id": quest.id,
                "title": quest.title,
                "description": quest.description,
                "state": quest.state,
                "tags": list(quest.tags),
                "requirements": dict(quest.requirements),
            }
        return {"quests": payload, "schema_version": 1}

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            return

        # Migrate
        data = migrate_payload("quests", data)

        # Handle both legacy (direct dict of quests) and new (wrapped) formats
        quests_data = data.get("quests", data) if "schema_version" in data else data

        for quest_id, raw in quests_data.items():
            if not isinstance(raw, dict):
                continue
            merged = dict(raw)
            merged.setdefault("id", quest_id)
            self.register_quest(merged)

    # ------------------------------------------------------------------ #
    # Requirements / auto-complete                                       #
    # ------------------------------------------------------------------ #
    def _requirements_met(self, quest: Quest, game_state: "GameStateController") -> bool:  # type: ignore[name-defined]
        req = quest.requirements or {}
        flags = req.get("flags", []) or []
        counters = req.get("counters", {}) or {}

        for flag_name in flags:
            if not game_state.get_flag(flag_name, False):
                return False

        for name, needed in counters.items():
            try:
                needed_val = int(needed)
            except (TypeError, ValueError):
                continue
            if game_state.get_counter(name, 0) < needed_val:
                return False

        return True

    def update_quest_states(self, game_state: "GameStateController") -> None:  # type: ignore[name-defined]
        for quest in self._quests.values():
            if quest.state == "active" and self._requirements_met(quest, game_state):
                quest.state = "completed"

    def list_active_quests(self) -> List[dict[str, Any]]:
        """Return quests that are not inactive for display/log purposes."""
        entries: List[dict[str, Any]] = []
        for quest in self._quests.values():
            if quest.state == "inactive":
                continue
            entries.append(
                {
                    "id": quest.id,
                    "title": quest.title,
                    "description": quest.description,
                    "status": quest.state,
                    "completed": quest.state == "completed",
                    "completed_steps": 0,
                    "total_steps": 0,
                }
            )
        return entries

    def handle_event(self, event: Any, game_state: "GameStateController") -> None:
        """Handle a gameplay event to update quest states."""
        # Normalize event to dict-like access if possible, or just use attributes
        # We only care about checking requirements after significant events

        # For now, we just trigger a state update check on every event
        # In a real system, we might filter by event type (e.g. "died", "collected")
        self.update_quest_states(game_state)
