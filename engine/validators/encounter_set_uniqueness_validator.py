from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from engine.encounter_sets import iter_encounter_set_source_paths
from engine.paths import resolve_path


@dataclass(frozen=True)
class EncounterSetUniquenessIssue:
    level: str  # "ERROR" | "WARN"
    code: str
    encounter_set_id: str
    source_paths: tuple[str, ...]
    message: str
    sort_key: tuple[Any, ...]


def _norm_path(value: str | Path) -> str:
    return str(value).replace("\\", "/")


def _iter_encounter_set_ids(data: Mapping[str, Any]) -> list[str]:
    raw = data.get("encounter_sets")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        raw_id = item.get("id")
        if isinstance(raw_id, str) and raw_id.strip():
            out.append(raw_id.strip())
    return out


def validate_encounter_set_uniqueness(
    *,
    source_paths: Sequence[str | Path] | None = None,
) -> dict[str, Any]:
    """Detect duplicate encounter_set_id definitions across loaded encounter set sources.

    Tooling-only guard: does not change runtime loading or resolution. By default, it checks the same
    encounter set sources the runtime ThemeManager loads today.
    """
    if source_paths is None:
        source_paths = iter_encounter_set_source_paths()

    seen: dict[str, list[str]] = {}
    issues: list[EncounterSetUniquenessIssue] = []

    for src in source_paths:
        src_display = _norm_path(src)
        resolved = resolve_path(str(src))
        if not resolved.exists():
            continue
        try:
            loaded = json.loads(resolved.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            msg = f"encounter_sets.load_failed source={src_display} error={type(exc).__name__}"
            issues.append(
                EncounterSetUniquenessIssue(
                    level="WARN",
                    code="encounter_sets.load_failed",
                    encounter_set_id="",
                    source_paths=(src_display,),
                    message=msg,
                    sort_key=("WARN", "", src_display, msg),
                )
            )
            continue
        if not isinstance(loaded, Mapping):
            msg = f"encounter_sets.invalid_json source={src_display} error=not_object"
            issues.append(
                EncounterSetUniquenessIssue(
                    level="WARN",
                    code="encounter_sets.invalid_json",
                    encounter_set_id="",
                    source_paths=(src_display,),
                    message=msg,
                    sort_key=("WARN", "", src_display, msg),
                )
            )
            continue

        for set_id in _iter_encounter_set_ids(loaded):
            seen.setdefault(set_id, []).append(src_display)

    for set_id, sources in seen.items():
        if len(sources) <= 1:
            continue
        sources_sorted = tuple(sorted([_norm_path(s) for s in sources]))
        msg = f"encounter_sets.duplicate_id encounter_set_id={set_id} sources={list(sources_sorted)}"
        issues.append(
            EncounterSetUniquenessIssue(
                level="ERROR",
                code="encounter_sets.duplicate_id",
                encounter_set_id=set_id,
                source_paths=sources_sorted,
                message=msg,
                sort_key=("ERROR", set_id, sources_sorted, msg),
            )
        )

    issues_sorted = sorted(issues, key=lambda i: (i.encounter_set_id, i.level, i.source_paths, i.message))
    errors = [i for i in issues_sorted if i.level == "ERROR"]
    warnings = [i for i in issues_sorted if i.level != "ERROR"]

    return {
        "ok": not errors,
        "errors": [
            {
                "code": i.code,
                "encounter_set_id": i.encounter_set_id,
                "source_paths": list(i.source_paths),
                "message": i.message,
            }
            for i in errors
        ],
        "warnings": [
            {
                "code": i.code,
                "encounter_set_id": i.encounter_set_id,
                "source_paths": list(i.source_paths),
                "message": i.message,
            }
            for i in warnings
        ],
    }
