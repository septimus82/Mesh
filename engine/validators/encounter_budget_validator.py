from dataclasses import dataclass
from typing import Any, Dict, List

from engine.config import load_config
from engine.encounter_cost import get_base_encounter_cost
from engine.encounter_presets import load_encounter_presets
from engine.paths import resolve_path
from engine.prefabs import get_prefab_manager


@dataclass
class ValidationResult:
    path: str
    level: str
    message: str

class EncounterBudgetValidator:
    """Validates encounter budget settings and costs."""

    def __init__(self) -> None:
        self._preset_validation_emitted = False
        self._presets_loaded = False
        self._known_preset_ids: set[str] = set()
        self._preset_issues: list[ValidationResult] = []

    def validate(self, scene_data: Dict[str, Any], scene_path: str, strict: bool = False) -> List[ValidationResult]:
        results: list[ValidationResult] = []
        settings = scene_data.get("settings", {})

        preset_id_raw = settings.get("encounter_preset_id")
        preset_id = preset_id_raw.strip() if isinstance(preset_id_raw, str) and preset_id_raw.strip() else None
        difficulty_raw = settings.get("encounter_budget_profile")
        difficulty = difficulty_raw.strip() if isinstance(difficulty_raw, str) and difficulty_raw.strip() else None

        if not self._presets_loaded:
            presets_path = resolve_path("packs/core_regions/data/encounter_presets.json")
            presets, issues = load_encounter_presets(presets_path, strict_unknown_keys=bool(strict))
            self._known_preset_ids = set(presets.keys())
            self._preset_issues = [ValidationResult("packs/core_regions/data/encounter_presets.json", i.level, i.message) for i in issues]
            self._presets_loaded = True

        if (not self._preset_validation_emitted) and self._preset_issues:
            results.extend(self._preset_issues)
            self._preset_validation_emitted = True

        if preset_id is not None and preset_id not in self._known_preset_ids:
            results.append(ValidationResult(scene_path, "ERROR", f"Unknown encounter_preset_id '{preset_id}'"))

        # 1. Check encounter_budget
        budget = settings.get("encounter_budget")
        if budget is not None:
            if not isinstance(budget, (int, float)):
                results.append(ValidationResult(
                    scene_path,
                    "ERROR",
                    f"encounter_budget must be a number, got {type(budget).__name__}"
                ))
            elif budget < 0:
                results.append(ValidationResult(
                    scene_path,
                    "ERROR",
                    f"encounter_budget must be positive, got {budget}"
                ))

        # 1b. Check encounter_group_budgets
        group_budgets = settings.get("encounter_group_budgets")
        if group_budgets:
            if not isinstance(group_budgets, dict):
                results.append(ValidationResult(
                    scene_path,
                    "ERROR",
                    f"encounter_group_budgets must be a dictionary, got {type(group_budgets).__name__}"
                ))
            else:
                for group, val in group_budgets.items():
                    if not isinstance(val, (int, float)) or val < 0:
                        results.append(ValidationResult(
                            scene_path,
                            "ERROR",
                            f"encounter_group_budgets['{group}'] must be a positive number, got {val}"
                        ))

        # 1c. Check encounter_group_elite_caps
        group_caps = settings.get("encounter_group_elite_caps")
        if group_caps:
            if not isinstance(group_caps, dict):
                results.append(ValidationResult(
                    scene_path,
                    "ERROR",
                    f"encounter_group_elite_caps must be a dictionary, got {type(group_caps).__name__}"
                ))
            else:
                for group, val in group_caps.items():
                    if not isinstance(val, int) or val < 0:
                        results.append(ValidationResult(
                            scene_path,
                            "ERROR",
                            f"encounter_group_elite_caps['{group}'] must be a positive integer, got {val}"
                        ))

        # 1d. Check encounter_group_allow_elites
        group_allow = settings.get("encounter_group_allow_elites")
        if group_allow:
            if not isinstance(group_allow, dict):
                results.append(ValidationResult(
                    scene_path,
                    "ERROR",
                    f"encounter_group_allow_elites must be a dictionary, got {type(group_allow).__name__}"
                ))
            else:
                for group, val in group_allow.items():
                    if not isinstance(val, bool):
                        results.append(ValidationResult(
                            scene_path,
                            "ERROR",
                            f"encounter_group_allow_elites['{group}'] must be a boolean, got {val}"
                        ))

        # 2. Check encounter_budget_profile
        profile = settings.get("encounter_budget_profile")
        if profile:
            config = load_config()
            if not config.encounter_budget_profiles or profile not in config.encounter_budget_profiles:
                results.append(ValidationResult(
                    scene_path,
                    "WARN",
                    f"Unknown encounter_budget_profile '{profile}'"
                ))

        # 3. Check prefab costs (Strict Mode)
        # We only check prefabs referenced in the scene or encounter set?
        # The prompt says "referenced prefabs declare encounter_cost if strict mode enabled".
        # This implies checking entities in the scene.
        # But also maybe encounter sets if we could access them.
        # For now, let's check entities in the scene.

        # Strict mode check is usually passed in or configured.
        # BaseValidator doesn't have strict mode flag by default.
        # But we can check if we are running in strict mode via some global or config?
        # Or just always warn if missing?
        # "warn in dev, error in demo/release profiles" -> This implies the severity depends on profile.
        # But the validator just returns results. The runner decides if it's failure.
        # So I should return WARN if missing.

        pm = get_prefab_manager()
        for i, entity in enumerate(scene_data.get("entities", [])):
            pid = entity.get("prefab_id")
            if pid and pid != "theme_enemy_placeholder":
                prefab = pm.get_prefab(pid)
                if prefab:
                    cost = get_base_encounter_cost(prefab, default=None)
                    if cost is None:
                        results.append(ValidationResult(
                            scene_path,
                            "WARN", # Runner can upgrade to ERROR
                            f"Entity[{i}] '{entity.get('name')}' (prefab '{pid}') missing encounter_cost"
                        ))

        # 4. Check Pacing Rules
        boss_reserve = settings.get("boss_budget_reserve")
        if boss_reserve is not None:
            if not isinstance(boss_reserve, (int, float)):
                 results.append(ValidationResult(scene_path, "ERROR", "boss_budget_reserve must be a number"))
            elif boss_reserve < 0:
                 results.append(ValidationResult(scene_path, "ERROR", "boss_budget_reserve must be non-negative"))
            elif budget is not None and boss_reserve > budget:
                 results.append(ValidationResult(scene_path, "WARN", f"boss_budget_reserve ({boss_reserve}) exceeds encounter_budget ({budget})"))

        elite_cap = settings.get("elite_cap")
        if elite_cap is not None:
            if not isinstance(elite_cap, int):
                 results.append(ValidationResult(scene_path, "ERROR", "elite_cap must be an integer"))
            elif elite_cap < 0:
                 results.append(ValidationResult(scene_path, "ERROR", "elite_cap must be non-negative"))

        # 5. Check Encounter Groups
        group_budgets = settings.get("encounter_group_budgets", {})
        if group_budgets:
            known_groups = set(group_budgets.keys())
            # Also check entities for unknown groups
            for i, entity in enumerate(scene_data.get("entities", [])):
                if entity.get("prefab_id") == "theme_enemy_placeholder":
                    group = entity.get("encounter_group", "default")
                    if group not in known_groups:
                        # Suggest closest match?
                        import difflib
                        matches = difflib.get_close_matches(group, known_groups, n=1)
                        suggestion = f" Did you mean '{matches[0]}'?" if matches else ""

                        msg = f"Entity[{i}] references unknown encounter_group '{group}'.{suggestion}"
                        level = "ERROR" if strict else "WARN"
                        results.append(ValidationResult(scene_path, level, msg))

        return results
