from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from engine.config import load_config
from engine.encounter_cost import get_effective_encounter_cost, is_elite_payload, is_mini_boss_payload
from engine.encounter_sets import iter_encounter_set_source_paths
from engine.encounter_presets import load_encounter_presets
from engine.paths import resolve_path
from engine.prefabs import get_prefab_manager


@dataclass(frozen=True)
class EncounterCoverageIssue:
    level: str  # "ERROR" | "WARN"
    encounter_set_id: str
    difficulty: str
    budget: float | None
    cheapest_candidate_cost: float | None
    message: str
    sort_key: tuple[Any, ...]


@dataclass(frozen=True)
class EncounterCoverageRow:
    encounter_set_id: str
    difficulty: str
    budget: float | None
    reserve: float | None
    effective_budget: float | None
    candidate_count: int
    eligible_count: int
    cheapest_candidate_cost: float | None
    cheapest_eligible_cost: float | None
    note: str | None = None


def _load_encounter_sets(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    raw = data.get("encounter_sets")
    if not isinstance(raw, list):
        return {}

    out: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            continue
        set_id = raw_id.strip()
        if set_id in out:
            continue
        out[set_id] = item
    return out


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _resolve_effective_budget(
    *,
    difficulty: str,
    presets: Mapping[str, Mapping[str, Any]],
    budget_profiles: Mapping[str, float],
    default_base_budget: float | None,
) -> tuple[float | None, float]:
    preset = presets.get(difficulty) if isinstance(presets, Mapping) else None
    preset_budget = _coerce_float(preset.get("encounter_budget")) if isinstance(preset, Mapping) else None
    preset_reserve = _coerce_float(preset.get("boss_budget_reserve")) if isinstance(preset, Mapping) else None

    base_budget = preset_budget if preset_budget is not None else default_base_budget
    if base_budget is None:
        return None, float(preset_reserve or 0.0)

    multiplier = float(budget_profiles.get(difficulty, 1.0))
    effective = float(base_budget) * multiplier
    return effective, float(preset_reserve or 0.0)


def compute_encounter_coverage_rows(
    *,
    difficulties: Sequence[str] = ("easy", "hard"),
    encounter_set_ids: set[str] | None = None,
    encounter_sets: Mapping[str, Mapping[str, Any]] | None = None,
    presets: Mapping[str, Mapping[str, Any]] | None = None,
    budget_profiles: Mapping[str, float] | None = None,
    default_base_budget: float | None = 10.0,
    prefab_manager: Any | None = None,
) -> list[EncounterCoverageRow]:
    if encounter_sets is None:
        encounter_sets = {}
        for source in iter_encounter_set_source_paths():
            encounter_sets.update(_load_encounter_sets(resolve_path(source)))

    if presets is None:
        presets_path = resolve_path("packs/core_regions/data/encounter_presets.json")
        presets_loaded, _preset_issues = load_encounter_presets(presets_path, strict_unknown_keys=False)
        presets = presets_loaded

    if budget_profiles is None:
        cfg = load_config()
        raw = getattr(cfg, "encounter_budget_profiles", None)
        budget_profiles = raw if isinstance(raw, dict) else {}

    if prefab_manager is None:
        prefab_manager = get_prefab_manager()

    requested = set(encounter_set_ids or [])
    normalized_difficulties = [str(d).strip() for d in difficulties if str(d).strip()]

    rows: list[EncounterCoverageRow] = []
    for set_id in sorted(encounter_sets.keys()):
        if requested and set_id not in requested:
            continue
        set_data = encounter_sets.get(set_id)
        if not isinstance(set_data, Mapping):
            continue

        enemy_prefab_ids = set_data.get("enemy_prefab_ids")
        if not isinstance(enemy_prefab_ids, list):
            enemy_prefab_ids = []

        for difficulty in normalized_difficulties:
            budget, reserve = _resolve_effective_budget(
                difficulty=difficulty,
                presets=presets,
                budget_profiles=budget_profiles,
                default_base_budget=default_base_budget,
            )

            note: str | None = None
            if budget is None:
                note = "no_budget"
                budget_val = None
                reserve_val = None
                effective_budget = None
            else:
                budget_val = float(budget)
                reserve_val = float(reserve or 0.0)
                effective_budget = max(budget_val - reserve_val, 0.0)

            allow_elites = True
            allow_mini_bosses: bool | None = None
            preset = presets.get(difficulty) if isinstance(presets, Mapping) else None
            if isinstance(preset, Mapping):
                if preset.get("allow_elites") is not None:
                    allow_elites = bool(preset.get("allow_elites"))
                if preset.get("allow_mini_bosses") is not None:
                    allow_mini_bosses = bool(preset.get("allow_mini_bosses"))
            allow_mb_effective = bool(allow_mini_bosses) if allow_mini_bosses is not None else allow_elites

            candidate_costs: list[float] = []
            eligible_costs: list[float] = []

            for pid_raw in enemy_prefab_ids:
                variant_id = None
                if isinstance(pid_raw, Mapping):
                    raw_pid = pid_raw.get("prefab_id")
                    if not isinstance(raw_pid, str) or not raw_pid.strip():
                        continue
                    pid = raw_pid.strip()
                    raw_variant = pid_raw.get("variant_id")
                    if isinstance(raw_variant, str) and raw_variant.strip():
                        variant_id = raw_variant.strip()
                else:
                    if not isinstance(pid_raw, str) or not pid_raw.strip():
                        continue
                    pid = pid_raw.strip()

                payload = None
                resolve = getattr(prefab_manager, "resolve_with_variant", None)
                if variant_id and callable(resolve):
                    payload = resolve(pid, variant_id)
                else:
                    prefab = getattr(prefab_manager, "get_prefab", None)
                    payload = prefab(pid) if callable(prefab) else None
                if not isinstance(payload, Mapping) or not payload:
                    continue

                cost = float(get_effective_encounter_cost(payload, default=1.0))
                candidate_costs.append(cost)

                if is_elite_payload(payload) and not allow_elites:
                    continue
                if is_mini_boss_payload(payload) and not allow_mb_effective:
                    continue

                if effective_budget is not None and cost <= float(effective_budget):
                    eligible_costs.append(cost)

            rows.append(
                EncounterCoverageRow(
                    encounter_set_id=set_id,
                    difficulty=difficulty,
                    budget=budget_val,
                    reserve=reserve_val,
                    effective_budget=effective_budget,
                    candidate_count=len(candidate_costs),
                    eligible_count=(len(eligible_costs) if effective_budget is not None else 0),
                    cheapest_candidate_cost=(min(candidate_costs) if candidate_costs else None),
                    cheapest_eligible_cost=(min(eligible_costs) if eligible_costs else None),
                    note=note,
                )
            )

    return sorted(rows, key=lambda r: (r.encounter_set_id, r.difficulty))


def encounter_coverage_rows_to_payload(rows: Sequence[EncounterCoverageRow], difficulties: Sequence[str]) -> dict[str, Any]:
    out_rows: list[dict[str, Any]] = []
    for row in rows:
        payload_row: dict[str, Any] = {
            "encounter_set_id": row.encounter_set_id,
            "difficulty": row.difficulty,
            "budget": row.budget,
            "reserve": row.reserve,
            "effective_budget": row.effective_budget,
            "candidate_count": int(row.candidate_count),
            "eligible_count": int(row.eligible_count),
            "cheapest_candidate_cost": row.cheapest_candidate_cost,
            "cheapest_eligible_cost": row.cheapest_eligible_cost,
        }
        if row.note is not None:
            payload_row["note"] = row.note
        out_rows.append(payload_row)

    return {
        "ok": True,
        "difficulties": [str(d) for d in difficulties],
        "rows": sorted(out_rows, key=lambda r: (str(r.get("encounter_set_id", "")), str(r.get("difficulty", "")))),
    }


def validate_encounter_coverage(
    *,
    difficulties: Sequence[str] = ("easy", "hard"),
    encounter_set_ids: set[str] | None = None,
    encounter_sets: Mapping[str, Mapping[str, Any]] | None = None,
    presets: Mapping[str, Mapping[str, Any]] | None = None,
    budget_profiles: Mapping[str, float] | None = None,
    default_base_budget: float | None = 10.0,
    prefab_manager: Any | None = None,
) -> dict[str, Any]:
    """Validate that encounter sets can produce at least one affordable candidate per difficulty.

    Tooling-only guard: does not change runtime spawning logic. This checks for at least one candidate with
    effective encounter cost <= effective budget (post-reserve), which helps prevent "no affordable spawns"
    regressions (especially on easy).
    """
    issues: list[EncounterCoverageIssue] = []

    if encounter_sets is None:
        encounter_sets = {}
        for source in iter_encounter_set_source_paths():
            encounter_sets.update(_load_encounter_sets(resolve_path(source)))
    if presets is None:
        presets_path = resolve_path("packs/core_regions/data/encounter_presets.json")
        presets_loaded, preset_issues = load_encounter_presets(presets_path, strict_unknown_keys=False)
        presets = presets_loaded
        for issue in preset_issues:
            issues.append(
                EncounterCoverageIssue(
                    level="WARN",
                    encounter_set_id="",
                    difficulty="",
                    budget=None,
                    cheapest_candidate_cost=None,
                    message=issue.message,
                    sort_key=("WARN", "", "", issue.message),
                )
            )
    if budget_profiles is None:
        cfg = load_config()
        raw = getattr(cfg, "encounter_budget_profiles", None)
        budget_profiles = raw if isinstance(raw, dict) else {}

    if prefab_manager is None:
        prefab_manager = get_prefab_manager()

    rows = compute_encounter_coverage_rows(
        difficulties=difficulties,
        encounter_set_ids=encounter_set_ids,
        encounter_sets=encounter_sets,
        presets=presets,
        budget_profiles=budget_profiles,
        default_base_budget=default_base_budget,
        prefab_manager=prefab_manager,
    )

    for row in rows:
        if row.note == "no_budget":
            msg = f"encounter_coverage.skip encounter_set_id={row.encounter_set_id} difficulty={row.difficulty} reason=budget_unknown"
            issues.append(
                EncounterCoverageIssue(
                    level="WARN",
                    encounter_set_id=row.encounter_set_id,
                    difficulty=row.difficulty,
                    budget=None,
                    cheapest_candidate_cost=None,
                    message=msg,
                    sort_key=("WARN", row.encounter_set_id, row.difficulty, msg),
                )
            )
            continue

        if row.effective_budget is None:
            continue

        # If we can't resolve any candidate prefabs in the current environment (e.g. tests running
        # in a temporary repo without content packs), treat it as a warning rather than a failure.
        # The primary purpose of this validator is affordability (given known candidates), not
        # completeness of content loading.
        if int(row.candidate_count) == 0:
            msg = (
                "encounter_coverage.no_candidates_resolved "
                f"encounter_set_id={row.encounter_set_id} difficulty={row.difficulty}"
            )
            issues.append(
                EncounterCoverageIssue(
                    level="WARN",
                    encounter_set_id=row.encounter_set_id,
                    difficulty=row.difficulty,
                    budget=row.effective_budget,
                    cheapest_candidate_cost=None,
                    message=msg,
                    sort_key=("WARN", row.encounter_set_id, row.difficulty, msg),
                )
            )
            continue

        if int(row.eligible_count) == 0:
            msg = (
                "encounter_coverage.no_eligible_candidates "
                f"encounter_set_id={row.encounter_set_id} difficulty={row.difficulty} "
                f"budget={row.effective_budget} cheapest_candidate_cost={row.cheapest_candidate_cost}"
            )
            issues.append(
                EncounterCoverageIssue(
                    level="ERROR",
                    encounter_set_id=row.encounter_set_id,
                    difficulty=row.difficulty,
                    budget=row.effective_budget,
                    cheapest_candidate_cost=row.cheapest_candidate_cost,
                    message=msg,
                    sort_key=("ERROR", row.encounter_set_id, row.difficulty, msg),
                )
            )

    issues_sorted = sorted(issues, key=lambda i: (i.encounter_set_id, i.difficulty, i.level, i.message))
    errors = [i for i in issues_sorted if i.level == "ERROR"]
    warnings = [i for i in issues_sorted if i.level != "ERROR"]

    return {
        "ok": not errors,
        "errors": [
            {
                "encounter_set_id": i.encounter_set_id,
                "difficulty": i.difficulty,
                "budget": i.budget,
                "cheapest_candidate_cost": i.cheapest_candidate_cost,
                "message": i.message,
            }
            for i in errors
        ],
        "warnings": [
            {
                "encounter_set_id": i.encounter_set_id,
                "difficulty": i.difficulty,
                "budget": i.budget,
                "cheapest_candidate_cost": i.cheapest_candidate_cost,
                "message": i.message,
            }
            for i in warnings
        ],
    }
