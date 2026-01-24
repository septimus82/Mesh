from __future__ import annotations

from typing import Any

from ..events import MeshEvent
from .gating import can_activate_quest


def handle_event(manager: Any, event: MeshEvent) -> None:
    if not getattr(manager, "_definitions", None):
        return
    # Two passes ensure quests that depend on flags/counters set by other quests completing
    # on the same event get a chance to start deterministically, regardless of definition order.
    for _ in range(2):
        for quest in manager._definitions.values():
            state = manager._ensure_state(quest["id"])
            if state.get("status") == "completed":
                continue
            check_start_triggers(manager, quest, state, event)
            check_completion_triggers(manager, quest, state, event)

    # Also check requirements since state might have changed
    manager.check_requirements()


def check_start_triggers(manager: Any, quest: dict[str, Any], state: dict[str, Any], event: MeshEvent) -> None:
    pending_id = state.get("awaiting_stage")
    if not pending_id:
        return
    stage = quest["stage_lookup"].get(pending_id)
    if stage is None:
        state["awaiting_stage"] = None
        return
    if not event_matches(stage.get("start_event"), event):
        return
    start_stage(manager, quest, stage, state, source=f"event:{event.type}")


def check_completion_triggers(manager: Any, quest: dict[str, Any], state: dict[str, Any], event: MeshEvent) -> None:
    current_id = state.get("current_stage")
    if not current_id:
        return
    stage = quest["stage_lookup"].get(current_id)
    if stage is None:
        state["current_stage"] = None
        return
    if not event_matches(stage.get("complete_event"), event):
        return
    complete_stage(manager, quest, stage, state, source=f"event:{event.type}")


def event_matches(spec: dict[str, Any] | None, event: MeshEvent) -> bool:
    if not spec:
        return False
    if event.type != spec.get("type"):
        return False
    payload = event.payload or {}
    payload_field = spec.get("payload_field")
    if payload_field:
        if payload_field not in payload:
            return False
        if "payload_value" in spec and payload.get(payload_field) != spec.get("payload_value"):
            return False
    expected_payload = spec.get("payload")
    if isinstance(expected_payload, dict):
        for key, value in expected_payload.items():
            if payload.get(key) != value:
                return False
    return True


def request_stage_start(manager: Any, quest: dict[str, Any], state: dict[str, Any], stage_id: str | None) -> bool:
    if stage_id:
        stage = quest["stage_lookup"].get(stage_id)
    else:
        stage = current_or_pending_stage(quest, state)
    if stage is None:
        return False
    if state.get("current_stage") == stage["id"]:
        return True
    if not stage_is_next(quest, state, stage["id"]):
        return False
    start_stage(manager, quest, stage, state, source="behaviour")
    return True


def request_stage_completion(manager: Any, quest: dict[str, Any], state: dict[str, Any], stage_id: str | None) -> bool:
    current_id = state.get("current_stage")
    target_id = stage_id or current_id
    if not target_id or current_id != target_id:
        return False
    stage = quest["stage_lookup"].get(target_id)
    if stage is None:
        return False
    complete_stage(manager, quest, stage, state, source="behaviour")
    return True


def force_stage(manager: Any, quest: dict[str, Any], state: dict[str, Any], stage_id: str | None) -> bool:
    if not stage_id:
        return False
    stage = quest["stage_lookup"].get(stage_id)
    if stage is None:
        return False
    completed = state.get("completed_stages", [])
    completed_set = set(completed)
    for candidate in quest["stages"]:
        if candidate["id"] == stage_id:
            break
        completed_set.add(candidate["id"])
    state["completed_stages"] = [sid for sid in completed_set if sid in quest["stage_lookup"]]
    state["awaiting_stage"] = stage_id
    state["current_stage"] = None
    start_stage(manager, quest, stage, state, source="behaviour:set")
    return True


def stage_is_next(quest: dict[str, Any], state: dict[str, Any], stage_id: str) -> bool:
    completed = set(state.get("completed_stages", []))
    for stage in quest["stages"]:
        if stage["id"] in completed:
            continue
        return stage["id"] == stage_id
    return False


def _resolve_flag_getter(window: Any):
    getter = getattr(window, "get_flag", None)
    if not callable(getter):
        getter = getattr(getattr(window, "game_state_controller", None), "get_flag", None)
    return getter if callable(getter) else None


def start_stage(
    manager: Any,
    quest: dict[str, Any],
    stage: dict[str, Any],
    state: dict[str, Any],
    *,
    source: str,
) -> None:
    if state.get("current_stage") == stage["id"]:
        return
    if state.get("status") == "inactive":
        getter = _resolve_flag_getter(manager.window)
        if callable(getter):
            if not can_activate_quest(getter, quest):
                return
    state["status"] = "active"
    state["current_stage"] = stage["id"]
    state["awaiting_stage"] = None
    manager.window.emit_signal(
        "quest_stage_started",
        quest_id=quest["id"],
        stage_id=stage["id"],
        quest_title=quest["title"],
        stage_title=stage["title"],
        text=stage["text"],
        source=source,
    )


def complete_stage(
    manager: Any,
    quest: dict[str, Any],
    stage: dict[str, Any],
    state: dict[str, Any],
    *,
    source: str,
) -> None:
    if state.get("current_stage") != stage["id"]:
        return
    completed = state.get("completed_stages", [])
    if not isinstance(completed, list):
        completed = []
    if stage["id"] not in completed:
        completed.append(stage["id"])
    state["current_stage"] = None
    manager.window.emit_signal(
        "quest_stage_completed",
        quest_id=quest["id"],
        stage_id=stage["id"],
        quest_title=quest["title"],
        stage_title=stage["title"],
        text=stage["text"],
        source=source,
    )
    next_stage = find_next_stage(quest, completed)
    if next_stage is None:
        complete_quest(manager, quest, state, source=source)
        return
    state["awaiting_stage"] = next_stage["id"]
    maybe_start_pending(manager, quest, state)


def complete_quest(manager: Any, quest: dict[str, Any], state: dict[str, Any], *, source: str) -> None:
    if state.get("status") == "completed":
        return
    state["status"] = "completed"
    state["current_stage"] = None
    state["awaiting_stage"] = None
    reward = quest.get("reward", {})
    for flag, value in reward.get("set_flags", {}).items():
        manager.window.set_flag(flag, bool(value))
    for counter, amount in reward.get("inc_counters", {}).items():
        manager.window.inc_counter(counter, float(amount))

    # Apply Gold and XP rewards with perk bonuses
    gold = reward.get("gold", 0)
    if gold > 0:
        bonus = manager.window.game_state_controller.get_perk_bonus("gold_bonus_pct")
        amount = int(gold * (1.0 + bonus))
        current_gold = manager.window.game_state.values.get("gold", 0)
        manager.window.game_state.values["gold"] = current_gold + amount
        print(f"[Mesh][Quests] Rewarded {amount} gold (base {gold} + {int(bonus*100)}%)")

    xp = reward.get("xp", 0)
    if xp > 0:
        # Let add_xp handle the bonus
        manager.window.game_state_controller.add_xp(xp)
        print(f"[Mesh][Quests] Rewarded {xp} XP")

    manager.window.emit_signal(
        "quest_completed",
        quest_id=quest["id"],
        quest_title=quest["title"],
        source=source,
    )


def find_next_stage(quest: dict[str, Any], completed: Any) -> dict[str, Any] | None:
    completed_set = set(completed or [])
    for stage in quest.get("stages", []):
        if stage["id"] in completed_set:
            continue
        return stage
    return None


def maybe_start_pending(manager: Any, quest: dict[str, Any], state: dict[str, Any]) -> None:
    pending_id = state.get("awaiting_stage")
    if not pending_id:
        return
    pending_stage = quest["stage_lookup"].get(pending_id)
    if pending_stage is None:
        state["awaiting_stage"] = None
        return
    if pending_stage.get("start_event"):
        return
    start_stage(manager, quest, pending_stage, state, source="auto")


def current_or_pending_stage(quest: dict[str, Any], state: dict[str, Any]) -> dict[str, Any] | None:
    current_id = state.get("current_stage")
    if current_id:
        return quest["stage_lookup"].get(current_id)
    pending_id = state.get("awaiting_stage")
    if pending_id:
        return quest["stage_lookup"].get(pending_id)
    return None


def sync_pending_stage(manager: Any, quest: dict[str, Any], state: dict[str, Any]) -> None:
    if state.get("status") == "completed":
        return
    stages = quest.get("stages", [])
    if not stages:
        state["status"] = "completed"
        return
    completed = state.get("completed_stages", [])
    completed = [stage_id for stage_id in completed if stage_id in quest["stage_lookup"]]
    state["completed_stages"] = completed
    current = state.get("current_stage")
    if current not in quest["stage_lookup"]:
        current = None
        state["current_stage"] = None
    awaiting = state.get("awaiting_stage")
    if awaiting not in quest["stage_lookup"]:
        awaiting = None
    if current is None and awaiting is None:
        next_stage = find_next_stage(quest, completed)
        awaiting = next_stage["id"] if next_stage else None
    state["awaiting_stage"] = awaiting
    if quest.get("auto_start") and state.get("status") == "inactive":
        first_stage = quest["stages"][0]
        start_stage(manager, quest, first_stage, state, source="auto")
        return
    maybe_start_pending(manager, quest, state)


def check_requirements(manager: Any) -> None:
    for quest_id, quest in manager._definitions.items():
        state = manager._ensure_state(quest_id)
        if state.get("status") != "active":
            continue

        current_id = state.get("current_stage")
        if not current_id:
            continue

        stage = quest["stage_lookup"].get(current_id)
        if not stage:
            continue

        reqs = stage.get("requirements", {})
        if not reqs:
            continue

        met = True
        # Check flags
        for flag, expected in reqs.get("flags", {}).items():
            if manager.window.get_flag(flag) != expected:
                met = False
                break
        if not met:
            continue

        # Check counters
        for counter, target in reqs.get("counters", {}).items():
            # Check scoped counter first, then global
            # We assume requirements counters are scoped to the quest if they exist there?
            # Or should we check both?
            # The user requirement implies scoped counters are preferred for quests.
            # Let's check scoped first.
            val = manager.window.game_state_controller.get_quest_counter(quest_id, counter)
            if val == 0.0: # If 0, maybe it's global? Or maybe it's just 0.
                # If we want to support global counters in quests too, we should check global if scoped is 0?
                # But what if scoped is legitimately 0?
                # Let's check if the key exists in counters dict?
                # GameStateController.get_quest_counter returns 0.0 default.
                # Let's check global as fallback if we assume implicit fallback.
                # But explicit is better.
                # For now, let's check global as well to support legacy quests using global counters.
                global_val = manager.window.get_counter(counter)
                val = max(val, global_val)

            if val < target:
                met = False
                break

        if met:
            complete_stage(manager, quest, stage, state, source="requirements")

