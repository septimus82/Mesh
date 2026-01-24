import json
from dataclasses import dataclass, field
from typing import Dict, List

from engine.encounter_report import EncounterReport, EncounterSceneReport


@dataclass
class EncounterGroupDiff:
    group_id: str
    spawn_count_delta: int
    elite_count_delta: int
    cost_delta: float
    budget_delta: float


@dataclass
class EncounterSceneDiff:
    scene_path: str
    difficulty: str
    spawn_count_delta: int
    elite_count_delta: int
    total_spawn_cost_delta: float
    cost_over_budget_before: float
    cost_over_budget_after: float
    cost_over_budget_delta: float
    boss_reserve_delta: float
    groups: List[EncounterGroupDiff] = field(default_factory=list)


@dataclass
class EncounterReportDiff:
    scene_diffs: List[EncounterSceneDiff] = field(default_factory=list)


def load_report(path: str) -> EncounterReport:
    with open(path, "r") as f:
        data = json.load(f)
    # Reconstruct objects from dict
    # We assume the JSON structure matches the dataclasses
    # We might need a helper to reconstruct if dataclasses are nested
    # For now, let's assume simple reconstruction or use dacite if available,
    # but we don't have dacite. We'll do manual reconstruction or simple dict access if we were just reading.
    # But we need EncounterReport objects for type safety if we use them in diff_reports.
    # Let's implement a simple from_dict.

    scenes = []
    for s in data.get("scenes", []):
        # We need to reconstruct groups
        from engine.encounter_report import EncounterGroupReport, EncounterSceneReport

        groups = []
        for g in s.get("groups", []):
            groups.append(EncounterGroupReport(
                group_id=g["group_id"],
                budget=g["budget"],
                spawn_count=g["spawn_count"],
                elite_count=g["elite_count"],
                cost=g["cost"]
            ))

        scenes.append(EncounterSceneReport(
            scene_path=s["scene_path"],
            difficulty=s["difficulty"],
            encounter_budget=s["encounter_budget"],
            boss_budget_reserve=s["boss_budget_reserve"],
            elite_cap=s["elite_cap"],
            allow_elites=s["allow_elites"],
            encounter_layout=s["encounter_layout"],
            encounter_seed=s["encounter_seed"],
            total_spawn_cost=s["total_spawn_cost"],
            spawn_count=s["spawn_count"],
            elite_count=s["elite_count"],
            boss_guard_heuristic=s["boss_guard_heuristic"],
            groups=groups
        ))

    return EncounterReport(scenes=scenes)


def diff_reports(old: EncounterReport, new: EncounterReport) -> EncounterReportDiff:
    diff = EncounterReportDiff()

    # Index old scenes by (path, difficulty)
    old_map: Dict[str, EncounterSceneReport] = {}
    for s in old.scenes:
        key = f"{s.scene_path}::{s.difficulty}"
        old_map[key] = s

    # Iterate new scenes
    for new_scene in new.scenes:
        key = f"{new_scene.scene_path}::{new_scene.difficulty}"
        old_scene = old_map.get(key)

        if not old_scene:
            # New scene or difficulty, treat old as zero?
            # Or just skip? Usually diff implies comparison of existing things.
            # If we treat old as zero, deltas are full values.
            # Let's treat it as zero for now to show "added" difficulty.
            # But we need a dummy old scene.
            # Actually, let's just skip for now or handle gracefully.
            # If we skip, we miss new content drift.
            # Let's create a zeroed old scene.
            old_scene = _create_zero_scene(new_scene.scene_path, new_scene.difficulty)

        scene_diff = _diff_scene(old_scene, new_scene)
        diff.scene_diffs.append(scene_diff)

    # Check for removed scenes?
    # The user didn't explicitly ask for removed scenes, but it's good practice.
    # For now, we focus on drift of existing/new.

    # Sort by path then difficulty
    diff.scene_diffs.sort(key=lambda x: (x.scene_path, x.difficulty))

    return diff

def _create_zero_scene(path: str, difficulty: str) -> EncounterSceneReport:
    from engine.encounter_report import EncounterSceneReport
    return EncounterSceneReport(
        scene_path=path,
        difficulty=difficulty,
        encounter_budget=0.0,
        boss_budget_reserve=0.0,
        elite_cap=0,
        allow_elites=False,
        encounter_layout="",
        encounter_seed=0,
        total_spawn_cost=0.0,
        spawn_count=0,
        elite_count=0,
        boss_guard_heuristic=False,
        groups=[]
    )

def _diff_scene(old: EncounterSceneReport, new: EncounterSceneReport) -> EncounterSceneDiff:
    # Calculate overruns
    # Overrun is cost - budget (if positive)
    # Note: budget is total encounter_budget.
    # But wait, budget is per group usually?
    # The report has `encounter_budget` (base * multiplier).
    # And `total_spawn_cost`.
    # So global overrun is total_cost - encounter_budget.

    old_overrun = max(0.0, old.total_spawn_cost - old.encounter_budget)
    new_overrun = max(0.0, new.total_spawn_cost - new.encounter_budget)

    # Group diffs
    group_diffs = []
    old_groups = {g.group_id: g for g in old.groups}
    for new_g in new.groups:
        old_g = old_groups.get(new_g.group_id)
        if not old_g:
            # New group
            from engine.encounter_report import EncounterGroupReport
            old_g = EncounterGroupReport(new_g.group_id, 0.0, 0, 0, 0.0)

        group_diffs.append(EncounterGroupDiff(
            group_id=new_g.group_id,
            spawn_count_delta=new_g.spawn_count - old_g.spawn_count,
            elite_count_delta=new_g.elite_count - old_g.elite_count,
            cost_delta=new_g.cost - old_g.cost,
            budget_delta=new_g.budget - old_g.budget
        ))

    return EncounterSceneDiff(
        scene_path=new.scene_path,
        difficulty=new.difficulty,
        spawn_count_delta=new.spawn_count - old.spawn_count,
        elite_count_delta=new.elite_count - old.elite_count,
        total_spawn_cost_delta=new.total_spawn_cost - old.total_spawn_cost,
        cost_over_budget_before=old_overrun,
        cost_over_budget_after=new_overrun,
        cost_over_budget_delta=new_overrun - old_overrun,
        boss_reserve_delta=new.boss_budget_reserve - old.boss_budget_reserve,
        groups=group_diffs
    )

def check_thresholds(
    diff: EncounterReportDiff,
    max_elite_delta: int | None = None,
    max_spawn_delta: int | None = None,
    max_cost_overrun: float | None = None,
    fail_on_overrun: bool = False,
) -> List[str]:
    errors = []
    for scene in diff.scene_diffs:
        if max_elite_delta is not None and abs(scene.elite_count_delta) > max_elite_delta:
            errors.append(
                f"{scene.scene_path} ({scene.difficulty}): Elite delta {scene.elite_count_delta} exceeds limit {max_elite_delta}"
            )

        if max_spawn_delta is not None and abs(scene.spawn_count_delta) > max_spawn_delta:
            errors.append(
                f"{scene.scene_path} ({scene.difficulty}): Spawn delta {scene.spawn_count_delta} exceeds limit {max_spawn_delta}"
            )

        if max_cost_overrun is not None and scene.cost_over_budget_after > max_cost_overrun:
            errors.append(
                f"{scene.scene_path} ({scene.difficulty}): Cost overrun {scene.cost_over_budget_after:.2f} exceeds limit {max_cost_overrun}"
            )

        if fail_on_overrun and scene.cost_over_budget_after > 0:
            errors.append(
                f"{scene.scene_path} ({scene.difficulty}): Cost overrun {scene.cost_over_budget_after:.2f} not allowed"
            )

    return errors
