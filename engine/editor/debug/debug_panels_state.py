"""State extraction helpers for editor debug panels."""

from __future__ import annotations

from typing import Any
from engine.logging_tools import get_logger

_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)



def get_quest_inspector_state(window: Any) -> dict[str, Any] | None:
    quest_manager = getattr(window, "quest_manager", None)
    if quest_manager is None:
        quest_manager = getattr(getattr(window, "game_state_controller", None), "quests", None)
    getter = getattr(quest_manager, "get_inspector_state", None)
    if callable(getter):
        try:
            state = getter()
            return state if isinstance(state, dict) else None
        except Exception:
            _log_swallow("DBPS-001", "engine/editor/debug/debug_panels_state.py blanket swallow", once=True)
            return None
    return None


def get_quest_diagnostics(window: Any) -> list[Any]:
    runner = getattr(window, "quest_runner", None)
    getter = getattr(runner, "get_diagnostics", None) if runner is not None else None
    if callable(getter):
        try:
            value = getter()
            return list(value) if isinstance(value, list) else []
        except Exception:
            _log_swallow("DBPS-002", "engine/editor/debug/debug_panels_state.py blanket swallow", once=True)
            return []
    return []


def get_cutscene_state(window: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    runner = getattr(window, "cutscene_runner", None)
    if runner is not None and hasattr(runner, "get_inspector_state"):
        try:
            inspector_state = runner.get_inspector_state()
        except Exception:
            _log_swallow("DBPS-003", "engine/editor/debug/debug_panels_state.py blanket swallow", once=True)
            inspector_state = None
        try:
            runner_commands = runner.get_command_list()
        except Exception:
            _log_swallow("DBPS-004", "engine/editor/debug/debug_panels_state.py blanket swallow", once=True)
            runner_commands = []
        return (inspector_state, runner_commands if isinstance(runner_commands, list) else [])

    controller = getattr(window, "cutscene_controller", None)
    if controller is None:
        return (None, [])

    active = getattr(controller, "active", None)
    is_running = bool(getattr(controller, "is_running", False))
    step_index = int(getattr(controller, "step_index", -1) or -1)
    step_elapsed = float(getattr(controller, "step_elapsed", 0.0) or 0.0)
    command_list: list[dict[str, Any]] = []

    if active is not None and hasattr(active, "steps"):
        steps = list(getattr(active, "steps", []))
        for idx, step in enumerate(steps):
            entry = {"index": idx, "type": getattr(step, "type", "")}
            data = getattr(step, "data", {}) if hasattr(step, "data") else {}
            if isinstance(data, dict):
                if "duration" in data:
                    entry["duration"] = data.get("duration")
                if "event" in data or "name" in data:
                    entry["event_type"] = data.get("event") or data.get("name")
            command_list.append(entry)

    command_count = len(command_list)
    current_type = ""
    wait_remaining = 0.0
    if 0 <= step_index < len(command_list):
        current_type = str(command_list[step_index].get("type") or "")
        if current_type == "wait":
            duration = command_list[step_index].get("duration")
            if isinstance(duration, (int, float)):
                wait_remaining = max(0.0, float(duration) - step_elapsed)

    inspector_state = {
        "script_id": getattr(active, "id", "") if active is not None else "",
        "is_running": is_running,
        "completed": False,
        "command_index": step_index if step_index >= 0 else 0,
        "command_count": command_count,
        "current_command_type": current_type,
        "wait_remaining": wait_remaining,
        "emitted_count": 0,
        "branch_count": 0,
    }
    return (inspector_state, command_list)


def get_cutscene_events(window: Any) -> list[Any]:
    runner = getattr(window, "cutscene_runner", None)
    bus = getattr(runner, "_event_bus", None) if runner is not None else None
    if bus is None:
        bus = getattr(window, "gameplay_event_bus", None)
    if bus is None or not hasattr(bus, "get_history"):
        return []
    try:
        events = list(bus.get_history(20))
    except Exception:
        _log_swallow("DBPS-005", "engine/editor/debug/debug_panels_state.py blanket swallow", once=True)
        return []
    filtered = []
    for event in events:
        source = str(getattr(event, "source_behaviour", "") or "")
        if source == "CutsceneRunner":
            filtered.append(event)
    return filtered
