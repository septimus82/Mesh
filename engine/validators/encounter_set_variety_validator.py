from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from engine.encounter_sets import iter_encounter_set_source_paths
from engine.paths import resolve_path


@dataclass(frozen=True)
class EncounterSetVarietyIssue:
    level: str  # "ERROR" | "WARN"
    code: str
    encounter_set_id: str
    unique_prefabs: int
    required: int
    message: str
    sort_key: tuple[Any, ...]


def _iter_sets(data: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = data.get("encounter_sets")
    if not isinstance(raw, list):
        return []
    out: list[Mapping[str, Any]] = []
    for item in raw:
        if isinstance(item, Mapping):
            out.append(item)
    return out


def _unique_prefab_ids(enemy_prefab_ids: object) -> set[str]:
    if not isinstance(enemy_prefab_ids, list):
        return set()
    out: set[str] = set()
    for entry in enemy_prefab_ids:
        if isinstance(entry, str):
            pid = entry.strip()
            if pid:
                out.add(pid)
            continue
        if isinstance(entry, Mapping):
            raw_pid = entry.get("prefab_id")
            if isinstance(raw_pid, str):
                pid = raw_pid.strip()
                if pid:
                    out.add(pid)
    return out


def _required_unique_prefabs(*, candidate_count: int, min_unique_prefabs: object) -> int:
    if isinstance(min_unique_prefabs, bool):
        min_unique_prefabs = None
    if isinstance(min_unique_prefabs, int):
        return max(0, int(min_unique_prefabs))
    if isinstance(min_unique_prefabs, float) and min_unique_prefabs.is_integer():
        return max(0, int(min_unique_prefabs))
    if candidate_count >= 6:
        return 3
    return 2


def validate_encounter_set_variety(
    *,
    source_paths: Sequence[str | Path] | None = None,
) -> dict[str, Any]:
    """Enforce a minimum unique prefab variety per encounter set.

    Default policy:
    - candidate_count >= 6 => require >= 3 unique prefab_ids
    - otherwise => require >= 2 unique prefab_ids

    Per-set override:
    - min_unique_prefabs: int
    """
    if source_paths is None:
        source_paths = iter_encounter_set_source_paths()

    issues: list[EncounterSetVarietyIssue] = []

    for src in source_paths:
        resolved = resolve_path(str(src))
        if not resolved.exists():
            continue
        try:
            loaded = json.loads(resolved.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001  # REASON: variety validation should record per-source JSON load failures and continue checking the remaining encounter set sources
            src_display = str(src).replace("\\", "/")
            msg = f"encounter_sets.load_failed source={src_display} error={type(exc).__name__}"
            issues.append(
                EncounterSetVarietyIssue(
                    level="WARN",
                    code="encounter_sets.load_failed",
                    encounter_set_id="",
                    unique_prefabs=0,
                    required=0,
                    message=msg,
                    sort_key=("WARN", "", msg),
                )
            )
            continue
        if not isinstance(loaded, Mapping):
            continue

        for item in _iter_sets(loaded):
            raw_id = item.get("id")
            if not isinstance(raw_id, str) or not raw_id.strip():
                continue
            set_id = raw_id.strip()

            candidates = item.get("enemy_prefab_ids")
            candidate_count = len(candidates) if isinstance(candidates, list) else 0
            unique_count = len(_unique_prefab_ids(candidates))
            required = _required_unique_prefabs(candidate_count=candidate_count, min_unique_prefabs=item.get("min_unique_prefabs"))

            if unique_count < required:
                msg = (
                    "encounter_sets.low_variety "
                    f"encounter_set_id={set_id} unique_prefabs={unique_count} required={required}"
                )
                issues.append(
                    EncounterSetVarietyIssue(
                        level="ERROR",
                        code="encounter_sets.low_variety",
                        encounter_set_id=set_id,
                        unique_prefabs=unique_count,
                        required=required,
                        message=msg,
                        sort_key=("ERROR", set_id, unique_count, required),
                    )
                )

    issues_sorted = sorted(issues, key=lambda i: (i.encounter_set_id, i.level, i.sort_key, i.message))
    errors = [i for i in issues_sorted if i.level == "ERROR"]
    warnings = [i for i in issues_sorted if i.level != "ERROR"]

    return {
        "ok": not errors,
        "errors": [
            {
                "code": i.code,
                "encounter_set_id": i.encounter_set_id,
                "unique_prefabs": int(i.unique_prefabs),
                "required": int(i.required),
                "message": i.message,
            }
            for i in errors
        ],
        "warnings": [
            {
                "code": i.code,
                "encounter_set_id": i.encounter_set_id,
                "unique_prefabs": int(i.unique_prefabs),
                "required": int(i.required),
                "message": i.message,
            }
            for i in warnings
        ],
    }
