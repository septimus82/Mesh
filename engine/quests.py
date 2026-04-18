"""Quest and journal runtime management for Mesh Engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, cast

from .events import MeshEvent
from .paths import resolve_path
from .quest_runtime import normalize as quest_normalize
from .quest_runtime import progress as quest_progress


def _lookup_stage(quest: dict[str, Any], stage_id: object) -> dict[str, Any] | None:
    if not isinstance(stage_id, str) or not stage_id:
        return None
    stage_lookup = quest.get("stage_lookup")
    if not isinstance(stage_lookup, dict):
        return None
    stage = stage_lookup.get(stage_id)
    return cast(dict[str, Any] | None, stage if isinstance(stage, dict) else None)


class QuestManager:
    """Loads quest definitions and tracks per-save progress."""

    def __init__(self, window, data_path: str = "assets/data/quests.json") -> None:
        self.window = window
        self.data_path = resolve_path(data_path)
        self._definitions: dict[str, dict[str, Any]] = {}
        self._stage_lookup: dict[str, dict[str, Any]] = {}
        self.load_definitions()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load_definitions(self) -> None:
        """Load quest definitions from disk and reconcile runtime state."""

        # Load core quests
        payload = self._load_json(self.data_path)
        quests_root = payload.get("quests") if isinstance(payload, dict) else None
        normalized: dict[str, dict[str, Any]] = {}

        def _process_entries(root):
            if isinstance(root, dict):
                entries: Iterable[tuple[str, Any]] = root.items()
            elif isinstance(root, list):
                entries = [(None, entry) for entry in root]
            else:
                entries = []
            for _, raw in entries:
                quest = self._normalize_quest(raw)
                if quest is None:
                    continue
                normalized[quest["id"]] = quest

        _process_entries(quests_root)

        # Load pack quests
        packs_dir = resolve_path("packs")
        if packs_dir.exists():
            for pack_dir in packs_dir.iterdir():
                if not pack_dir.is_dir():
                    continue
                pack_quests_path = pack_dir / "assets/data/quests.json"
                if pack_quests_path.exists():
                    try:
                        pack_payload = self._load_json(pack_quests_path)
                        pack_root = pack_payload.get("quests") if isinstance(pack_payload, dict) else None
                        _process_entries(pack_root)
                    except Exception as e:
                        print(f"[Mesh][Quests] Failed to load quests from {pack_dir.name}: {e}")

        self._definitions = normalized
        self._rebuild_stage_lookup()
        self.reload_from_state()

    def reload_from_state(self) -> None:
        """Ensure quest runtime state aligns with current definitions."""

        state_root = self._state_root()
        for quest_id in list(state_root.keys()):
            if quest_id not in self._definitions:
                state_root.pop(quest_id, None)
        for quest_id, quest in self._definitions.items():
            state = self._ensure_state(quest_id)
            self._coerce_state_schema(state)
            self._sync_pending_stage(quest, state)

    def handle_event(self, event: MeshEvent) -> None:
        """Inspect Mesh events and update quests when triggers match."""
        quest_progress.handle_event(self, event)

    def request_progress(self, quest_id: str, action: str, stage_id: str | None = None) -> bool:
        """Allow behaviours to manipulate quest progression directly."""

        quest = self._definitions.get(quest_id)
        if quest is None:
            print(f"[Mesh][Quests] WARNING: Unknown quest '{quest_id}'")
            return False
        state = self._ensure_state(quest_id)
        action_key = (action or "").strip().lower()
        if action_key in {"start", "activate"}:
            return self._request_stage_start(quest, state, stage_id)
        if action_key in {"set_stage", "stage"}:
            return self._force_stage(quest, state, stage_id)
        if action_key in {"complete", "complete_stage"}:
            return self._request_stage_completion(quest, state, stage_id)
        if action_key in {"finish", "complete_quest"}:
            self._complete_quest(quest, state, source="behaviour")
            return True
        print(f"[Mesh][Quests] WARNING: Unknown quest action '{action}'")
        return False

    def start_quest(self, quest_id: str, stage_id: str | None = None) -> bool:
        """Convenience wrapper over request_progress(..., "start")."""

        return self.request_progress(quest_id, "start", stage_id)

    def set_stage(self, quest_id: str, stage_id: str) -> bool:
        """Force the quest into a specific stage."""

        return self.request_progress(quest_id, "set_stage", stage_id)

    def complete_stage(self, quest_id: str, stage_id: str | None = None) -> bool:
        """Mark the active (or provided) stage as finished."""

        return self.request_progress(quest_id, "complete_stage", stage_id)

    def complete_quest(self, quest_id: str) -> bool:
        """Complete the quest immediately, applying rewards."""

        return self.request_progress(quest_id, "finish")

    def is_quest_active(self, quest_id: str) -> bool:
        """Return True when the quest has started but not finished."""

        state = self._state_root().get(quest_id)
        return bool(state and state.get("status") == "active")

    def is_quest_completed(self, quest_id: str) -> bool:
        """Return True when the quest status is 'completed'."""

        state = self._state_root().get(quest_id)
        return bool(state and state.get("status") == "completed")

    def is_stage_completed(self, quest_id: str, stage_id: str) -> bool:
        """Return True if the provided stage id is in the completed list."""

        if not stage_id:
            return False
        state = self._state_root().get(quest_id)
        if not isinstance(state, dict):
            return False
        completed = state.get("completed_stages", [])
        return stage_id in completed if isinstance(completed, list) else False

    def get_current_stage(self, quest_id: str) -> dict[str, Any] | None:
        """Expose the currently active stage payload (if any)."""

        quest = self._definitions.get(quest_id)
        if quest is None:
            return None
        state = self._state_root().get(quest_id)
        if not isinstance(state, dict):
            return None
        current_id = state.get("current_stage")
        if not current_id:
            return None
        return _lookup_stage(quest, current_id)

    def get_pending_stage(self, quest_id: str) -> dict[str, Any] | None:
        """Return the next stage waiting for its start trigger (if any)."""

        quest = self._definitions.get(quest_id)
        if quest is None:
            return None
        state = self._state_root().get(quest_id)
        if not isinstance(state, dict):
            return None
        pending_id = state.get("awaiting_stage")
        if not pending_id:
            return None
        return _lookup_stage(quest, pending_id)

    def get_state_snapshot(self, quest_id: str | None = None) -> dict[str, Any] | None:
        """Return a copy of the quest state for debugging/UI purposes."""

        root = self._state_root()
        if quest_id is None:
            return {qid: self._copy_state(state) for qid, state in root.items()}
        if quest_id not in self._definitions:
            return None
        return self._copy_state(self._ensure_state(quest_id))

    def list_active_quests(self) -> list[dict[str, Any]]:
        """Return quest log entries for UI overlays."""

        entries: list[dict[str, Any]] = []
        for quest_id, quest in self._definitions.items():
            state = self._ensure_state(quest_id)
            stage = self._current_or_pending_stage(quest, state)
            completed = list(state.get("completed_stages", []))
            entries.append(
                {
                    "id": quest_id,
                    "title": quest["title"],
                    "description": quest["description"],
                    "start_toast": quest.get("start_toast"),
                    "complete_toast": quest.get("complete_toast"),
                    "status": state.get("status", "inactive"),
                    "stage_id": stage.get("id") if stage else None,
                    "stage_title": stage.get("title") if stage else None,
                    "stage_text": stage.get("text") if stage else None,
                    "completed": state.get("status") == "completed",
                    "current_stage": state.get("current_stage"),
                    "awaiting_stage": state.get("awaiting_stage"),
                    "completed_stages": completed,
                    "total_stages": len(quest.get("stages", [])),
                },
            )
        return entries

    def get_inspector_state(self) -> dict[str, Any]:
        """Return read-only quest status summary for editor inspector.
        
        This provides a comprehensive overview of all quests and their
        current state, suitable for debugging and editor tooling.
        
        Returns:
            Dictionary with quest summaries, counts, and metadata.
        """
        quests: list[dict[str, Any]] = []
        active_count = 0
        completed_count = 0
        inactive_count = 0
        
        for quest_id, quest in self._definitions.items():
            state = self._ensure_state(quest_id)
            status = state.get("status", "inactive")
            
            if status == "active":
                active_count += 1
            elif status == "completed":
                completed_count += 1
            else:
                inactive_count += 1
            
            current_stage = state.get("current_stage")
            awaiting_stage = state.get("awaiting_stage")
            completed_stages = state.get("completed_stages", [])
            total_stages = len(quest.get("stages", []))
            
            # Get current stage info
            stage_info: dict[str, Any] | None = None
            if current_stage:
                stage_def = quest["stage_lookup"].get(current_stage)
                if stage_def:
                    stage_info = {
                        "id": current_stage,
                        "title": stage_def.get("title", current_stage),
                        "text": stage_def.get("text", ""),
                        "has_complete_trigger": stage_def.get("complete_event") is not None,
                        "has_requirements": bool(stage_def.get("requirements")),
                    }
            
            quests.append({
                "id": quest_id,
                "title": quest.get("title", quest_id),
                "status": status,
                "progress": f"{len(completed_stages)}/{total_stages}",
                "progress_pct": len(completed_stages) / total_stages if total_stages > 0 else 0.0,
                "current_stage": stage_info,
                "awaiting_stage": awaiting_stage,
                "completed_stages": list(completed_stages),
                "requires_flags": quest.get("requires_flags", []),
                "blocks_flags": quest.get("blocks_flags", []),
            })
        
        return {
            "total_quests": len(self._definitions),
            "active_count": active_count,
            "completed_count": completed_count,
            "inactive_count": inactive_count,
            "quests": quests,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            print(f"[Mesh][Quests] Quest file missing: {path}")
            return {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                result = json.load(handle)
                return result if isinstance(result, dict) else {}
        except OSError as exc:
            print(f"[Mesh][Quests] Failed to read {path}: {exc}")
        except json.JSONDecodeError as exc:
            print(f"[Mesh][Quests] Invalid JSON in {path}: {exc}")
        return {}

    def _normalize_quest(self, data: Any) -> dict[str, Any] | None:
        return quest_normalize.normalize_quest(data)

    def _normalize_stages(self, root: Any) -> list[dict[str, Any]]:
        return quest_normalize.normalize_stages(root)

    def _normalize_event_trigger(self, value: Any) -> dict[str, Any] | None:
        return quest_normalize.normalize_event_trigger(value)

    def _normalize_requirements(self, data: Any) -> dict[str, Any]:
        return quest_normalize.normalize_requirements(data)

    def _normalize_reward(self, data: Any) -> dict[str, Any]:
        return quest_normalize.normalize_reward(data)

    def _rebuild_stage_lookup(self) -> None:
        lookup: dict[str, dict[str, Any]] = {}
        for quest_id, quest in self._definitions.items():
            for stage in quest.get("stages", []):
                lookup_key = f"{quest_id}:{stage['id']}"
                lookup[lookup_key] = stage
        self._stage_lookup = lookup

    def _state_root(self) -> dict[str, Any]:
        state = self.window.game_state
        values = state.values
        quests_block = values.get("quests")
        if not isinstance(quests_block, dict):
            quests_block = {}
            values["quests"] = quests_block
        return quests_block

    def _ensure_state(self, quest_id: str) -> dict[str, Any]:
        root = self._state_root()
        state = root.get(quest_id)
        if not isinstance(state, dict):
            state = {
                "status": "inactive",
                "current_stage": None,
                "awaiting_stage": None,
                "completed_stages": [],
            }
            root[quest_id] = state
        return state

    def _coerce_state_schema(self, state: dict[str, Any]) -> None:
        status = state.get("status")
        if status not in {"inactive", "active", "completed"}:
            state["status"] = "inactive"
        completed = state.get("completed_stages")
        if not isinstance(completed, list):
            completed = []
        cleaned: list[str] = []
        for entry in completed:
            name = str(entry or "").strip()
            if name:
                cleaned.append(name)
        state["completed_stages"] = cleaned
        if not isinstance(state.get("current_stage"), str):
            state["current_stage"] = None
        if not isinstance(state.get("awaiting_stage"), str):
            state["awaiting_stage"] = None

    def _copy_state(self, state: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": state.get("status", "inactive"),
            "current_stage": state.get("current_stage"),
            "awaiting_stage": state.get("awaiting_stage"),
            "completed_stages": list(state.get("completed_stages", [])),
        }

    def _sync_pending_stage(self, quest: dict[str, Any], state: dict[str, Any]) -> None:
        quest_progress.sync_pending_stage(self, quest, state)

    def _find_next_stage(self, quest: dict[str, Any], completed: Iterable[str]) -> dict[str, Any] | None:
        return quest_progress.find_next_stage(quest, completed)

    def _maybe_start_pending(self, quest: dict[str, Any], state: dict[str, Any]) -> None:
        quest_progress.maybe_start_pending(self, quest, state)

    def _check_start_triggers(self, quest: dict[str, Any], state: dict[str, Any], event: MeshEvent) -> None:
        quest_progress.check_start_triggers(self, quest, state, event)

    def _check_completion_triggers(self, quest: dict[str, Any], state: dict[str, Any], event: MeshEvent) -> None:
        quest_progress.check_completion_triggers(self, quest, state, event)

    def _event_matches(self, spec: dict[str, Any] | None, event: MeshEvent) -> bool:
        return quest_progress.event_matches(spec, event)

    def _request_stage_start(
        self,
        quest: dict[str, Any],
        state: dict[str, Any],
        stage_id: str | None,
    ) -> bool:
        return quest_progress.request_stage_start(self, quest, state, stage_id)

    def _request_stage_completion(
        self,
        quest: dict[str, Any],
        state: dict[str, Any],
        stage_id: str | None,
    ) -> bool:
        return quest_progress.request_stage_completion(self, quest, state, stage_id)

    def _force_stage(self, quest: dict[str, Any], state: dict[str, Any], stage_id: str | None) -> bool:
        return quest_progress.force_stage(self, quest, state, stage_id)

    def _stage_is_next(self, quest: dict[str, Any], state: dict[str, Any], stage_id: str) -> bool:
        return quest_progress.stage_is_next(quest, state, stage_id)

    def _start_stage(
        self,
        quest: dict[str, Any],
        stage: dict[str, Any],
        state: dict[str, Any],
        *,
        source: str,
    ) -> None:
        quest_progress.start_stage(self, quest, stage, state, source=source)

    def _complete_stage(
        self,
        quest: dict[str, Any],
        stage: dict[str, Any],
        state: dict[str, Any],
        *,
        source: str,
    ) -> None:
        quest_progress.complete_stage(self, quest, stage, state, source=source)

    def _complete_quest(self, quest: dict[str, Any], state: dict[str, Any], *, source: str) -> None:
        quest_progress.complete_quest(self, quest, state, source=source)

    def check_requirements(self) -> None:
        """Check if active quests meet their requirements (flags/counters)."""
        quest_progress.check_requirements(self)

    def _current_or_pending_stage(
        self,
        quest: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any] | None:
        return quest_progress.current_or_pending_stage(quest, state)
