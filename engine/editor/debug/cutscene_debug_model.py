"""Pure cutscene debug view models for editor tooling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True, slots=True)
class CutsceneEventSummary:
    sequence: int
    event_type: str
    payload_preview: str


@dataclass(frozen=True, slots=True)
class CutsceneDebugViewModel:
    is_running: bool
    script_id: str
    command_index: int
    command_count: int
    current_command: str
    current_label: str
    wait_remaining: float
    recent_events: tuple[CutsceneEventSummary, ...]


def build_cutscene_debug_view_model(
    inspector_state: dict[str, Any] | None,
    command_list: Sequence[dict[str, Any]] | None = None,
    recent_events: Sequence[Any] | None = None,
) -> CutsceneDebugViewModel:
    """Build a deterministic cutscene debug view model."""
    state = inspector_state if isinstance(inspector_state, dict) else {}
    script_id = _coerce_str(state.get("script_id"))
    is_running = bool(state.get("is_running", False))
    command_index = int(state.get("command_index", 0) or 0)
    command_count = int(state.get("command_count", 0) or 0)
    wait_remaining = float(state.get("wait_remaining", 0.0) or 0.0)
    current_command_type = _coerce_str(state.get("current_command_type"))

    commands = list(command_list) if isinstance(command_list, (list, tuple)) else []
    current_command = _format_current_command(commands, command_index, current_command_type)
    current_label = _resolve_current_label(commands, command_index)

    summaries = _build_event_summaries(recent_events or [])

    return CutsceneDebugViewModel(
        is_running=is_running,
        script_id=script_id,
        command_index=command_index,
        command_count=command_count,
        current_command=current_command,
        current_label=current_label,
        wait_remaining=wait_remaining,
        recent_events=tuple(summaries),
    )


def build_cutscene_debug_lines(
    view_model: CutsceneDebugViewModel,
    *,
    max_events: int | None = None,
) -> list[str]:
    """Format cutscene debug view model as deterministic lines."""
    lines = ["Cutscene Debug"]
    lines.extend(build_cutscene_summary_lines(view_model))
    lines.append("Recent Events:")

    events = list(view_model.recent_events)
    if max_events is not None and max_events >= 0:
        events, remaining = _trim_list(events, max_events)
    else:
        remaining = 0

    if not events:
        lines.append("  (none)")
    else:
        for event in events:
            payload = event.payload_preview or "(empty)"
            lines.append(f"  #{event.sequence} {event.event_type} {payload}")
        if remaining > 0:
            lines.append(f"  ... ({remaining} more)")

    return lines


def build_cutscene_summary_lines(view_model: CutsceneDebugViewModel) -> list[str]:
    """Format summary lines for cutscene state (status/command/label)."""
    status = "running" if view_model.is_running else "stopped"
    cmd_total = max(0, view_model.command_count)
    cmd_index = max(0, view_model.command_index)
    display_index = cmd_index + 1 if cmd_total > 0 else 0
    cmd_label = view_model.current_command or "-"
    script_id = view_model.script_id or "-"
    label = view_model.current_label or "-"

    return [
        f"Status: {status}",
        f"Script: {script_id}",
        f"Command: {display_index}/{cmd_total} {cmd_label}",
        f"Label: {label}",
        f"Wait: {view_model.wait_remaining:.2f}s",
    ]


def format_cutscene_summary_text(view_model: CutsceneDebugViewModel) -> str:
    """Format cutscene summary as multi-line text for clipboard."""
    return "\n".join(build_cutscene_summary_lines(view_model))


def _trim_list(items: list[Any], limit: int) -> tuple[list[Any], int]:
    if limit <= 0:
        return ([], len(items))
    if len(items) <= limit:
        return (items, 0)
    return (items[:limit], len(items) - limit)


def _coerce_str(value: Any) -> str:
    return str(value or "").strip()


def _resolve_current_label(commands: list[dict[str, Any]], command_index: int) -> str:
    label = ""
    for cmd in commands:
        if not isinstance(cmd, dict):
            continue
        if str(cmd.get("type", "")).strip().lower() != "label":
            continue
        try:
            idx = int(cmd.get("index", -1))
        except (TypeError, ValueError):
            continue
        if idx <= command_index:
            name = _coerce_str(cmd.get("name"))
            if name:
                label = name
    return label


def _format_current_command(
    commands: list[dict[str, Any]],
    command_index: int,
    fallback_type: str,
) -> str:
    entry = _find_command(commands, command_index)
    if entry is None:
        return fallback_type or "-"
    return _format_command_entry(entry)


def _find_command(commands: list[dict[str, Any]], command_index: int) -> dict[str, Any] | None:
    for cmd in commands:
        if not isinstance(cmd, dict):
            continue
        try:
            idx = int(cmd.get("index", -1))
        except (TypeError, ValueError):
            continue
        if idx == command_index:
            return cmd
    return None


def _format_command_entry(entry: dict[str, Any]) -> str:
    ctype = _coerce_str(entry.get("type")).lower()
    if not ctype:
        return "-"
    if ctype == "wait":
        duration = entry.get("duration")
        if isinstance(duration, (int, float)):
            return f"wait {float(duration):.2f}s"
        return "wait"
    if ctype == "emit_event":
        event_type = _coerce_str(entry.get("event_type"))
        return f"emit {event_type}" if event_type else "emit_event"
    if ctype == "label":
        name = _coerce_str(entry.get("name"))
        return f"label {name}" if name else "label"
    if ctype == "goto":
        target = _coerce_str(entry.get("target"))
        return f"goto {target}" if target else "goto"
    if ctype in {"set_flag", "clear_flag", "branch_on_flag"}:
        flag = _coerce_str(entry.get("flag"))
        return f"{ctype} {flag}" if flag else ctype
    return ctype


def _build_event_summaries(events: Sequence[Any]) -> list[CutsceneEventSummary]:
    summaries: list[CutsceneEventSummary] = []
    for event in events:
        summary = _coerce_event(event)
        if summary is not None:
            summaries.append(summary)
    summaries.sort(key=lambda e: e.sequence)
    return summaries


def _coerce_event(event: Any) -> CutsceneEventSummary | None:
    if event is None:
        return None
    if isinstance(event, dict):
        event_type = _coerce_str(event.get("event_type") or event.get("type"))
        payload_raw = event.get("payload")
        sequence = event.get("sequence", 0)
    else:
        event_type = _coerce_str(getattr(event, "event_type", ""))
        payload_raw = getattr(event, "payload", None)
        sequence = getattr(event, "sequence", 0)
    try:
        seq = int(sequence)
    except (TypeError, ValueError):
        seq = 0
    payload_dict: dict[Any, Any] = payload_raw if isinstance(payload_raw, dict) else {}
    return CutsceneEventSummary(
        sequence=seq,
        event_type=event_type or "-",
        payload_preview=_format_payload_preview(payload_dict),
    )


def _format_payload_preview(payload: dict[Any, Any]) -> str:
    if not payload:
        return "(empty)"
    keys = sorted(str(k) for k in payload.keys())
    head = keys[:3]
    preview = ", ".join(head)
    if len(keys) > len(head):
        preview = f"{preview} (+{len(keys) - len(head)})"
    return preview
