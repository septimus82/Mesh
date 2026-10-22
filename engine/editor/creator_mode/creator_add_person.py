"""Creator Mode "Add Person": stage one proposal that adds a person who says a line.

The proposal is two live ops accepted as one undo step: ``add_entity_from_prefab``
for the project's ``person`` prefab, then ``set_behaviour_params`` on its Dialogue
for the typed line. Projects without a person prefab get a disabled action with a
reason (fail closed); there is no engine fallback prefab.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from engine.ai_ops import find_prefab_palette_entry
from engine.entity_paint_mode import make_entity_id

from .creator_terms import classify_entity_snapshot

ADD_PERSON_STAGE_ACTION_ID = "person.add.stage"
ADD_PERSON_LINE_ACTION_ID = "person.add.line"
PERSON_PREFAB_ID = "person"
PERSON_KIND = "Person"
DEFAULT_PERSON_LINE = "Hello!"
MAX_PERSON_LINE_CHARS = 120


@dataclass(frozen=True, slots=True)
class CreatorAddPersonPanelModel:
    title: str
    line: str
    focused: bool
    enabled: bool
    reason: str
    editable: bool = False  # the line field takes clicks only when adding could actually work


@dataclass(frozen=True, slots=True)
class CreatorAddPersonStagingResult:
    ok: bool
    proposal_id: str = ""
    summary: str = ""
    errors: tuple[str, ...] = ()


def person_prefab_entry(palette: object) -> dict[str, Any] | None:
    """The project's ``person`` prefab, if it is one Creator Mode would call a Person."""
    entries = [entry for entry in palette if isinstance(entry, dict)] if isinstance(palette, list) else []
    entry = find_prefab_palette_entry(entries, PERSON_PREFAB_ID, include_id=True)
    if entry is None or classify_entity_snapshot(entry.get("entity")) != PERSON_KIND:
        return None
    return entry


def normalize_person_line(text: object) -> str:
    line = " ".join(str(text or "").split())
    return line[:MAX_PERSON_LINE_CHARS]


def add_person_unavailable_reason(
    *,
    palette: object,
    scene_path: str,
    bridge: object | None,
    line: str,
    pending_proposal_id: str = "",
) -> str:
    if not scene_path:
        return "Open a map first."
    if person_prefab_entry(palette) is None:
        return "This project has no person prefab."
    if not callable(getattr(bridge, "stage_pending_proposal", None)):
        return "Proposal bridge is unavailable."
    if not normalize_person_line(line):
        return "Type what the person says."
    if pending_proposal_id:
        # Two pending adds would both claim the same name; review the first one.
        return "Waiting for review in AI Proposals."
    return ""


def build_add_person_panel(
    *,
    palette: object,
    scene_path: str,
    bridge: object | None,
    line: str,
    focused: bool,
    pending_proposal_id: str = "",
) -> CreatorAddPersonPanelModel:
    reason = add_person_unavailable_reason(
        palette=palette,
        scene_path=scene_path,
        bridge=bridge,
        line=line,
        pending_proposal_id=pending_proposal_id,
    )
    editable = bool(
        scene_path
        and person_prefab_entry(palette) is not None
        and callable(getattr(bridge, "stage_pending_proposal", None))
    )
    return CreatorAddPersonPanelModel(
        title=f"Add {PERSON_KIND}",
        line=str(line or ""),
        focused=bool(focused) and editable,
        enabled=not reason,
        reason=reason,
        editable=editable,
    )


def unique_person_name(entities: Iterable[object]) -> str:
    taken = {str(e.get("name") or "") for e in entities if isinstance(e, Mapping)}
    if PERSON_KIND not in taken:
        return PERSON_KIND
    index = 2
    while f"{PERSON_KIND} {index}" in taken:
        index += 1
    return f"{PERSON_KIND} {index}"


def unique_person_id(scene_path: str, x: float, y: float, entities: Iterable[object]) -> str:
    """Stable id like painted prefabs get; Move/Rename need it to find the person later."""
    taken = {str(e.get("id") or "") for e in entities if isinstance(e, Mapping)}
    base = make_entity_id(scene_path, PERSON_PREFAB_ID, x, y)
    candidate, index = base, 2
    while candidate in taken:
        candidate = f"{base}_{index}"
        index += 1
    return candidate


def build_add_person_ops(
    *,
    scene_path: str,
    entities: Iterable[object],
    x: float,
    y: float,
    line: str,
) -> list[dict[str, Any]]:
    entities = list(entities)
    name = unique_person_name(entities)
    return [
        {
            "type": "add_entity_from_prefab",
            "scene_path": scene_path,
            "prefab_id": PERSON_PREFAB_ID,
            "id": unique_person_id(scene_path, x, y, entities),
            "name": name,
            "x": float(x),
            "y": float(y),
        },
        {
            "type": "set_behaviour_params",
            "scene_path": scene_path,
            "entity_name": name,
            "behaviour_name": "Dialogue",
            "params": {
                "dialogue": {
                    "speaker": name,
                    "start": "root",
                    "nodes": {"root": {"text": normalize_person_line(line)}},
                },
            },
        },
    ]


def stage_add_person_proposal(ops: list[dict[str, Any]], bridge: object | None) -> CreatorAddPersonStagingResult:
    stage = getattr(bridge, "stage_pending_proposal", None)
    if not callable(stage):
        return CreatorAddPersonStagingResult(ok=False, errors=("Proposal bridge is unavailable.",))
    result = stage(copy.deepcopy(ops))
    if not isinstance(result, dict):
        return CreatorAddPersonStagingResult(ok=False, errors=("Proposal bridge returned an invalid result.",))
    if result.get("ok") is not True:
        message = next(
            (str(result[k]).strip() for k in ("message", "reason", "error") if str(result.get(k) or "").strip()),
            "Failed to stage the add-person proposal.",
        )
        return CreatorAddPersonStagingResult(ok=False, errors=(message,))
    dry_run = result.get("dry_run")
    if isinstance(dry_run, dict) and dry_run.get("ok") is not True:
        # The bridge stages even a failing dry-run; withdraw it so AI Proposals isn't left
        # holding a proposal that can't apply, then report why.
        staged_id = str(result.get("proposal_id") or "").strip()
        reject = getattr(bridge, "reject_pending_proposal", None)
        if staged_id and callable(reject):
            reject(staged_id)
        warnings = [str(w) for w in dry_run.get("warnings") or [] if str(w).strip()]
        return CreatorAddPersonStagingResult(ok=False, errors=(warnings[0] if warnings else "The person can't be added here.",))
    return CreatorAddPersonStagingResult(
        ok=True,
        proposal_id=str(result.get("proposal_id") or "").strip(),
        summary=str(result.get("preview") or ""),
    )


def snap_to_grid(value: float, step: float) -> float:
    return float(round(value / step) * step) if step > 0 else float(value)
