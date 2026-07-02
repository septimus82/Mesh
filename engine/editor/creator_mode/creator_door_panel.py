"""Read-only Creator Mode door panel presentation model."""

from __future__ import annotations

from dataclasses import dataclass

from .creator_door_staging_readiness import build_creator_door_staging_readiness
from .creator_door_workflow import CreatorDoorWorkflowModel


@dataclass(frozen=True, slots=True)
class CreatorDoorPanelLine:
    """One line of friendly door panel text."""

    text: str
    severity: str = "info"


@dataclass(frozen=True, slots=True)
class CreatorDoorPanelSection:
    """A stable read-only section for a future door panel."""

    title: str
    lines: tuple[CreatorDoorPanelLine, ...]


@dataclass(frozen=True, slots=True)
class CreatorDoorPanelAction:
    """Future action display state for the door panel."""

    label: str
    enabled: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class CreatorDoorPanelModel:
    """Read-only presentation model for a future Creator Mode door panel."""

    title: str
    status: str
    summary: str
    sections: tuple[CreatorDoorPanelSection, ...]
    actions: tuple[CreatorDoorPanelAction, ...]


def build_creator_door_panel(
    workflow: CreatorDoorWorkflowModel,
    bridge: object,
) -> CreatorDoorPanelModel:
    """Build a friendly, read-only panel model without staging or rendering."""

    readiness = build_creator_door_staging_readiness(workflow, bridge)
    preview = workflow.preview
    title = _text(preview.title) or "Door Proposal"
    return CreatorDoorPanelModel(
        title=title,
        status=readiness.status,
        summary=readiness.summary,
        sections=(
            _plan_section(workflow),
            _steps_section(workflow),
            _staging_section(readiness.summary, readiness.live_ops_preview),
            _problems_section((*readiness.errors, *preview.errors)),
            _warnings_section((*readiness.warnings, *preview.warnings)),
        ),
        actions=tuple(
            CreatorDoorPanelAction(
                label=str(action.label),
                enabled=bool(action.enabled),
                reason=str(action.reason),
            )
            for action in readiness.actions
        ),
    )


def _plan_section(workflow: CreatorDoorWorkflowModel) -> CreatorDoorPanelSection:
    summary = _text(workflow.preview.summary) or _text(workflow.plan.summary) or "No door plan summary."
    return CreatorDoorPanelSection(
        title="Plan",
        lines=(CreatorDoorPanelLine(summary),),
    )


def _steps_section(workflow: CreatorDoorWorkflowModel) -> CreatorDoorPanelSection:
    lines = tuple(
        CreatorDoorPanelLine(
            text=f"{_text(step.title)}: {_text(step.detail)}",
            severity=_text(getattr(step, "severity", "")) or "info",
        )
        for step in workflow.preview.steps
    )
    if not lines:
        lines = (CreatorDoorPanelLine("No preview steps."),)
    return CreatorDoorPanelSection(title="What will happen", lines=lines)


def _staging_section(
    summary: str,
    live_ops_preview: tuple[str, ...],
) -> CreatorDoorPanelSection:
    lines = [CreatorDoorPanelLine(_text(summary))]
    if live_ops_preview:
        lines.extend(CreatorDoorPanelLine(_text(line)) for line in live_ops_preview)
    else:
        lines.append(CreatorDoorPanelLine("No live-op preview."))
    return CreatorDoorPanelSection(title="Staging", lines=tuple(lines))


def _problems_section(errors: tuple[str, ...]) -> CreatorDoorPanelSection:
    deduped = _dedupe_text(errors)
    if not deduped:
        return CreatorDoorPanelSection(
            title="Problems",
            lines=(CreatorDoorPanelLine("No blocking problems."),),
        )
    return CreatorDoorPanelSection(
        title="Problems",
        lines=tuple(CreatorDoorPanelLine(error, severity="error") for error in deduped),
    )


def _warnings_section(warnings: tuple[str, ...]) -> CreatorDoorPanelSection:
    deduped = _dedupe_text(warnings)
    if not deduped:
        return CreatorDoorPanelSection(
            title="Warnings",
            lines=(CreatorDoorPanelLine("No warnings."),),
        )
    return CreatorDoorPanelSection(
        title="Warnings",
        lines=tuple(CreatorDoorPanelLine(warning, severity="warning") for warning in deduped),
    )


def _dedupe_text(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return tuple(result)


def _text(value: object) -> str:
    return str(value or "").strip()
