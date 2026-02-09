"""Pure quest debug view models for editor tooling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True, slots=True)
class QuestStepInfo:
    step_id: str
    title: str
    text: str
    has_complete_trigger: bool
    has_requirements: bool


@dataclass(frozen=True, slots=True)
class QuestDebugEntry:
    quest_id: str
    title: str
    status: str
    progress: str
    completed_count: int
    total_count: int
    current_step: QuestStepInfo | None
    awaiting_step: str | None


@dataclass(frozen=True, slots=True)
class QuestStepDiagnosticView:
    quest_id: str
    step_id: str
    event_type: str
    matched: bool
    reason: str


@dataclass(frozen=True, slots=True)
class QuestDebugViewModel:
    total_quests: int
    active_count: int
    completed_count: int
    inactive_count: int
    quests: tuple[QuestDebugEntry, ...]
    diagnostics: tuple[QuestStepDiagnosticView, ...]


def build_quest_debug_view_model(
    inspector_state: dict[str, Any] | None,
    diagnostics: Sequence[Any] | None = None,
) -> QuestDebugViewModel:
    """Build a deterministic quest debug view model."""
    state = inspector_state if isinstance(inspector_state, dict) else {}
    raw_quests = state.get("quests")
    if not isinstance(raw_quests, list):
        raw_quests = []

    quests: list[QuestDebugEntry] = []
    for raw in raw_quests:
        if not isinstance(raw, dict):
            continue
        quest_id = _coerce_str(raw.get("id"))
        if not quest_id:
            continue
        title = _coerce_str(raw.get("title") or quest_id)
        status = _coerce_str(raw.get("status") or "inactive")
        progress_text = _coerce_str(raw.get("progress") or "")
        completed_stages = raw.get("completed_stages")
        if not isinstance(completed_stages, list):
            completed_stages = []
        completed_count = len(completed_stages)
        parsed_completed, parsed_total = _parse_progress(progress_text)
        if parsed_total > 0:
            total_count = parsed_total
            completed_count = parsed_completed
            progress_text = f"{parsed_completed}/{parsed_total}"
        else:
            total_count = 0
            if not progress_text and total_count > 0:
                progress_text = f"{completed_count}/{total_count}"
        current_step = _build_step_info(raw.get("current_stage"))
        awaiting_step = _coerce_str(raw.get("awaiting_stage")) or None

        quests.append(
            QuestDebugEntry(
                quest_id=quest_id,
                title=title,
                status=status,
                progress=progress_text,
                completed_count=completed_count,
                total_count=total_count,
                current_step=current_step,
                awaiting_step=awaiting_step,
            )
        )

    quests.sort(key=lambda q: q.quest_id.lower())

    diag_rows: list[QuestStepDiagnosticView] = []
    if diagnostics:
        for diag in diagnostics:
            row = _coerce_diagnostic(diag)
            if row is not None:
                diag_rows.append(row)
    diag_rows.sort(key=lambda d: (d.quest_id.lower(), d.step_id.lower(), d.event_type.lower(), d.reason.lower()))

    total_quests = int(state.get("total_quests", len(quests)) or 0)
    active_count = int(state.get("active_count", 0) or 0)
    completed_count = int(state.get("completed_count", 0) or 0)
    inactive_count = int(state.get("inactive_count", max(0, total_quests - active_count - completed_count)) or 0)

    return QuestDebugViewModel(
        total_quests=total_quests,
        active_count=active_count,
        completed_count=completed_count,
        inactive_count=inactive_count,
        quests=tuple(quests),
        diagnostics=tuple(diag_rows),
    )


def build_quest_debug_lines(
    view_model: QuestDebugViewModel,
    *,
    max_quests: int | None = None,
    max_diagnostics: int | None = None,
) -> list[str]:
    """Format quest debug view model as deterministic lines."""
    lines: list[str] = [
        "Quest Debug",
        f"Total: {view_model.total_quests} Active: {view_model.active_count} "
        f"Completed: {view_model.completed_count} Inactive: {view_model.inactive_count}",
    ]

    quests = list(view_model.quests)
    if max_quests is not None and max_quests >= 0:
        quests, remaining = _trim_list(quests, max_quests)
    else:
        remaining = 0

    if not quests:
        lines.append("No quests")
    else:
        for quest in quests:
            progress = quest.progress or "-"
            lines.append(f"- {quest.quest_id} [{quest.status}] {progress}")
            if quest.current_step is not None:
                step = quest.current_step
                label = step.title or step.step_id
                lines.append(f"  step: {step.step_id} {label}")
            elif quest.awaiting_step:
                lines.append(f"  awaiting: {quest.awaiting_step}")
        if remaining > 0:
            lines.append(f"... ({remaining} more quests)")

    lines.append("Diagnostics:")
    diags = list(view_model.diagnostics)
    if max_diagnostics is not None and max_diagnostics >= 0:
        diags, remaining = _trim_list(diags, max_diagnostics)
    else:
        remaining = 0

    if not diags:
        lines.append("  (none)")
    else:
        for diag in diags:
            match_tag = "match" if diag.matched else "no-match"
            reason = diag.reason or "-"
            event = diag.event_type or "-"
            lines.append(f"  {diag.quest_id}:{diag.step_id} {event} [{match_tag}] {reason}")
        if remaining > 0:
            lines.append(f"  ... ({remaining} more)")

    return lines


def _trim_list(items: list[Any], limit: int) -> tuple[list[Any], int]:
    if limit <= 0:
        return ([], len(items))
    if len(items) <= limit:
        return (items, 0)
    return (items[:limit], len(items) - limit)


def _coerce_str(value: Any) -> str:
    return str(value or "").strip()


def _parse_progress(progress: str) -> tuple[int, int]:
    text = _coerce_str(progress)
    if "/" not in text:
        return (0, 0)
    left, right = text.split("/", 1)
    try:
        return (int(left.strip()), int(right.strip()))
    except ValueError:
        return (0, 0)


def _build_step_info(payload: Any) -> QuestStepInfo | None:
    if not isinstance(payload, dict):
        return None
    step_id = _coerce_str(payload.get("id"))
    if not step_id:
        return None
    return QuestStepInfo(
        step_id=step_id,
        title=_coerce_str(payload.get("title") or step_id),
        text=_coerce_str(payload.get("text") or ""),
        has_complete_trigger=bool(payload.get("has_complete_trigger")),
        has_requirements=bool(payload.get("has_requirements")),
    )


def _coerce_diagnostic(diag: Any) -> QuestStepDiagnosticView | None:
    if diag is None:
        return None
    if isinstance(diag, dict):
        quest_id = _coerce_str(diag.get("quest_id"))
        step_id = _coerce_str(diag.get("step_id"))
        event_type = _coerce_str(diag.get("event_type"))
        matched = bool(diag.get("matched"))
        reason = _coerce_str(diag.get("reason"))
    else:
        quest_id = _coerce_str(getattr(diag, "quest_id", ""))
        step_id = _coerce_str(getattr(diag, "step_id", ""))
        event_type = _coerce_str(getattr(diag, "event_type", ""))
        matched = bool(getattr(diag, "matched", False))
        reason = _coerce_str(getattr(diag, "reason", ""))
    if not quest_id or not step_id:
        return None
    return QuestStepDiagnosticView(
        quest_id=quest_id,
        step_id=step_id,
        event_type=event_type,
        matched=matched,
        reason=reason,
    )
