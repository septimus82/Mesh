from __future__ import annotations

import hashlib
import json
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, cast
from unittest.mock import MagicMock

from engine.encounter_sets import get_theme_manager
from engine.encounter_cost import get_effective_encounter_cost, is_boss_payload, is_elite_payload, is_mini_boss_payload
from engine.prefabs import get_prefab_manager
from engine.scene_loader import SceneLoader
from engine.path_norm import normalize_scene_path
from engine.logging_tools import get_logger

_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)



@dataclass
class EncounterGroupReport:
    group_id: str
    budget: float
    spawn_count: int
    elite_count: int
    cost: float
    mini_boss_count: int = 0
    mini_boss_cost: float = 0.0
    mini_boss_cost_share: float = 0.0
    elite_cost: float = 0.0
    elite_cost_share: float = 0.0


@dataclass
class EncounterSceneReport:
    scene_path: str
    difficulty: str
    encounter_budget: float
    boss_budget_reserve: float
    elite_cap: int | None
    allow_elites: bool
    encounter_layout: str
    encounter_seed: int
    total_spawn_cost: float
    spawn_count: int
    elite_count: int
    boss_guard_heuristic: bool
    encounter_preset_id: str | None = None
    mini_boss_cap: int | None = None
    allow_mini_bosses: bool | None = None
    effective_mini_boss_cap: int | None = None
    effective_allow_mini_bosses: bool = True
    elite_cost: float = 0.0
    elite_cost_share: float = 0.0
    mini_boss_count: int = 0
    mini_boss_cost: float = 0.0
    mini_boss_cost_share: float = 0.0
    groups: List[EncounterGroupReport] = field(default_factory=list)


@dataclass
class EncounterReport:
    schema_version: int = 1
    scenes: List[EncounterSceneReport] = field(default_factory=list)


class HeadlessSceneController:
    def __init__(self, profiles: Dict[str, float]):
        # Mock window and config
        self.window = MagicMock()
        self.window.engine_config = MagicMock()
        self.window.engine_config.encounter_budget_profiles = profiles
        self.current_scene_path = ""
        # We don't need layers or sprites for this report
        self.layers: Dict[str, Any] = {}

    def resolve_spawns(self, scene_data: Dict[str, Any]) -> None:
        # Re-implement the relevant parts of _apply_theme_runtime to trigger spawn resolution
        settings = scene_data.get("settings", {})
        theme_id = settings.get("region_theme")
        if not theme_id:
            return

        tm = get_theme_manager()
        theme = tm.get_theme(theme_id)
        if not theme:
            return

        # Resolve Encounter Set
        encounter_set_id = settings.get("encounter_set_id")
        if encounter_set_id:
            encounter_set = tm.get_encounter_set(encounter_set_id)
        else:
            encounter_set = tm.resolve_encounter_set_for_theme(theme_id)

        if not encounter_set:
            return

        # Apply Spawns
        if settings.get("use_theme_spawns") and encounter_set.enemy_prefab_ids:
            self._resolve_budgeted_spawns(scene_data, encounter_set, theme)

    def _resolve_legacy_spawns(self, scene_data: Dict[str, Any], encounter_set: Any, theme: Any) -> None:
        settings = scene_data.get("settings", {})
        seed_val = 0
        if self.current_scene_path:
            seed_val = sum(ord(c) for c in self.current_scene_path)
        rng = random.Random(seed_val)

        variant_id = encounter_set.variant_id or theme.default_variant_id

        for entity in scene_data.get("entities", []):
            if entity.get("prefab_id") == "theme_enemy_placeholder":
                chosen = rng.choice(encounter_set.enemy_prefab_ids)
                if isinstance(chosen, dict):
                    pid = chosen.get("prefab_id")
                    if isinstance(pid, str) and pid.strip():
                        entity["prefab_id"] = pid.strip()
                    else:
                        continue
                    if "variant_id" not in entity:
                        v = chosen.get("variant_id")
                        if isinstance(v, str) and v.strip():
                            entity["variant_id"] = v.strip()
                else:
                    entity["prefab_id"] = chosen
                if encounter_set.drop_table_id and "drop_table_id" not in entity:
                    entity["drop_table_id"] = encounter_set.drop_table_id

                if variant_id and "variant_id" not in entity:
                    entity["variant_id"] = variant_id

    def _resolve_budgeted_spawns(self, scene_data: Dict[str, Any], encounter_set: Any, theme: Any) -> None:
        settings = scene_data.get("settings", {})

        preset_id_raw = settings.get("encounter_preset_id")
        preset_id = preset_id_raw.strip() if isinstance(preset_id_raw, str) and preset_id_raw.strip() else None
        if preset_id is None:
            difficulty_raw = settings.get("encounter_budget_profile")
            preset_id = difficulty_raw.strip() if isinstance(difficulty_raw, str) and difficulty_raw.strip() else None

        preset: dict | None = None
        if preset_id:
            try:
                preset = get_theme_manager().get_encounter_preset(preset_id)
            except Exception:
                _log_swallow("ENCR-001", "engine/encounter_report.py blanket swallow", once=True)
                preset = None

        base_budget = settings.get("encounter_budget")
        if base_budget is None and preset is not None and preset.get("encounter_budget") is not None:
            base_budget = preset.get("encounter_budget")

        # If no global budget and no group budgets, use legacy
        group_budgets = settings.get("encounter_group_budgets", {})
        if base_budget is None and not group_budgets:
            self._resolve_legacy_spawns(scene_data, encounter_set, theme)
            return

        profile = settings.get("encounter_budget_profile")
        multiplier = 1.0
        if profile and hasattr(self.window, "engine_config") and self.window.engine_config.encounter_budget_profiles:
            multiplier = self.window.engine_config.encounter_budget_profiles.get(profile, 1.0)

        # Global Rules
        global_elite_cap = settings.get("elite_cap")
        if global_elite_cap is None and preset is not None and preset.get("elite_cap") is not None:
            global_elite_cap = preset.get("elite_cap")

        allow_elites_raw = settings.get("allow_elites")
        preset_allow_elites = preset.get("allow_elites") if preset is not None else None
        if allow_elites_raw is not None:
            global_allow_elites = bool(allow_elites_raw)
        elif preset_allow_elites is not None:
            global_allow_elites = bool(preset_allow_elites)
        else:
            global_allow_elites = True

        global_mini_boss_cap = settings.get("mini_boss_cap")
        if global_mini_boss_cap is None and preset is not None and preset.get("mini_boss_cap") is not None:
            global_mini_boss_cap = preset.get("mini_boss_cap")

        global_allow_mini_bosses = settings.get("allow_mini_bosses")
        if global_allow_mini_bosses is None and preset is not None and preset.get("allow_mini_bosses") is not None:
            global_allow_mini_bosses = preset.get("allow_mini_bosses")

        boss_reserve_raw = settings.get("boss_budget_reserve")
        if boss_reserve_raw is None and preset is not None and preset.get("boss_budget_reserve") is not None:
            boss_reserve_raw = preset.get("boss_budget_reserve")
        boss_reserve = float(boss_reserve_raw or 0.0)

        # Group Rules
        group_elite_caps = settings.get("encounter_group_elite_caps", {})
        group_allow_elites = settings.get("encounter_group_allow_elites", {})

        seed_val = settings.get("encounter_seed")
        if seed_val is None and self.current_scene_path:
            seed_val = int(hashlib.sha256(self.current_scene_path.encode("utf-8")).hexdigest(), 16)

        rng = random.Random(seed_val)

        entities = scene_data.get("entities", [])

        # Bucket placeholders by group
        placeholders_by_group: Dict[str, list[int]] = {}
        for idx, entity in enumerate(entities):
            if entity.get("prefab_id") == "theme_enemy_placeholder":
                group = entity.get("encounter_group", "default")
                if group not in placeholders_by_group:
                    placeholders_by_group[group] = []
                placeholders_by_group[group].append(idx)

        if not placeholders_by_group:
            return

        # Shuffle placeholders within each group for determinism
        # We sort keys to ensure deterministic iteration order of groups
        sorted_groups = sorted(placeholders_by_group.keys())
        for group in sorted_groups:
            rng.shuffle(placeholders_by_group[group])

        # Calculate effective budgets per group
        effective_budgets: Dict[str, float] = {}
        for group in sorted_groups:
            # Fallback to global budget if group budget missing
            g_budget = group_budgets.get(group)
            if g_budget is None:
                g_budget = base_budget if base_budget is not None else 0.0

            effective_budgets[group] = float(g_budget) * multiplier

        # Apply Boss Reserve
        if boss_reserve > 0:
            target_group = "boss_guard" if "boss_guard" in placeholders_by_group else "default"
            if target_group in effective_budgets:
                effective_budgets[target_group] -= boss_reserve

        # Resolve Candidates (Master List)
        # Scene-level override applies only to themed spawn resolution (theme_enemy_placeholder).
        # - New key: theme_spawn_variant_id
        # - Legacy key (deprecated): variant_id
        scene_spawn_variant_id = settings.get("theme_spawn_variant_id")
        if scene_spawn_variant_id is None:
            scene_spawn_variant_id = settings.get("variant_id")
        global_variant_id = scene_spawn_variant_id or encounter_set.variant_id or theme.default_variant_id
        pm = get_prefab_manager()

        master_candidates = []
        for entry in encounter_set.enemy_prefab_ids:
            candidate_variant_id = None
            if isinstance(entry, dict):
                pid_raw = entry.get("prefab_id")
                if not isinstance(pid_raw, str) or not pid_raw.strip():
                    continue
                pid = pid_raw.strip()
                v_raw = entry.get("variant_id")
                if isinstance(v_raw, str) and v_raw.strip():
                    candidate_variant_id = v_raw.strip()
            else:
                pid = entry
                if not isinstance(pid, str) or not pid.strip():
                    continue
                pid = pid.strip()

            variant_id = candidate_variant_id or global_variant_id
            if variant_id:
                data = pm.resolve_with_variant(pid, variant_id)
            else:
                data = pm.get_prefab(pid)

            if data:
                cost = float(get_effective_encounter_cost(data, default=1.0))
                is_boss = is_boss_payload(data)
                is_mini_boss = is_mini_boss_payload(data) and not is_boss
                is_elite = is_elite_payload(data) and not is_boss and not is_mini_boss
                master_candidates.append(
                    {
                        "pid": pid,
                        "variant_id": candidate_variant_id,
                        "cost": cost,
                        "is_boss": is_boss,
                        "is_mini_boss": is_mini_boss,
                        "is_elite": is_elite,
                    }
                )

        if not master_candidates:
            return

        master_candidates.sort(key=lambda x: float(x["cost"] or 0))

        indices_to_remove = []

        # Process each group
        for group in sorted_groups:
            indices = placeholders_by_group[group]
            budget = effective_budgets[group]

            # Determine rules
            cap = group_elite_caps.get(group, global_elite_cap)
            allow = group_allow_elites.get(group, global_allow_elites)

            allow_mb = global_allow_mini_bosses if global_allow_mini_bosses is not None else allow
            mb_cap = global_mini_boss_cap if global_mini_boss_cap is not None else cap

            # Heuristic: Boss Guard safety
            if group == "boss_guard" and profile != "hard":
                # Check if explicitly overridden in group_allow_elites
                if group not in group_allow_elites:
                    allow = False
                    if global_allow_mini_bosses is None:
                        allow_mb = False

            # Filter candidates for this group
            group_candidates = [
                c
                for c in master_candidates
                if not ((c["is_elite"] and not allow) or (c["is_mini_boss"] and not allow_mb))
            ]

            if not group_candidates:
                # No valid candidates for this group (e.g. all elites and allow=False)
                indices_to_remove.extend(indices)
                continue

            spawned_count = 0
            elite_count = 0
            mini_boss_count = 0

            for idx in indices:
                affordable = []
                for c in group_candidates:
                    if float(c["cost"] or 0) > budget:
                        continue
                    if c["is_elite"] and cap is not None and elite_count >= cap:
                        continue
                    if c["is_mini_boss"] and mb_cap is not None:
                        if global_mini_boss_cap is None:
                            if elite_count >= mb_cap:
                                continue
                        else:
                            if mini_boss_count >= mb_cap:
                                continue
                    affordable.append(c)

                if not affordable:
                    if spawned_count == 0:
                        # Force at least one spawn if possible
                        # Prefer non-elites if capped
                        valid_fallback = []
                        for c in group_candidates:
                            if c["is_elite"] and cap is not None and elite_count >= cap:
                                continue
                            if c["is_mini_boss"] and mb_cap is not None:
                                if global_mini_boss_cap is None:
                                    if elite_count >= mb_cap:
                                        continue
                                else:
                                    if mini_boss_count >= mb_cap:
                                        continue
                            valid_fallback.append(c)
                        if valid_fallback:
                            chosen = valid_fallback[0]
                        else:
                            # If we must pick an elite even if capped (because it's the only option), so be it?
                            # Or just pick the cheapest candidate?
                            # Original logic: chosen = candidates[0] (cheapest)
                            chosen = group_candidates[0]
                    else:
                        indices_to_remove.append(idx)
                        continue
                else:
                    chosen = rng.choice(affordable)

                pid = str(chosen["pid"])
                cost = float(chosen["cost"] or 0)
                is_elite = bool(chosen["is_elite"])
                is_mini_boss = bool(chosen["is_mini_boss"])
                chosen_variant_id = chosen.get("variant_id")

                entity = entities[idx]
                entity["prefab_id"] = pid
                if encounter_set.drop_table_id and "drop_table_id" not in entity:
                    entity["drop_table_id"] = encounter_set.drop_table_id
                if "variant_id" not in entity:
                    if isinstance(chosen_variant_id, str) and chosen_variant_id.strip():
                        entity["variant_id"] = chosen_variant_id.strip()
                    elif global_variant_id:
                        entity["variant_id"] = global_variant_id

                budget -= cost
                spawned_count += 1
                if is_elite:
                    elite_count += 1
                elif is_mini_boss:
                    if global_mini_boss_cap is None:
                        elite_count += 1
                    else:
                        mini_boss_count += 1

        for idx in sorted(indices_to_remove, reverse=True):
            del entities[idx]


def generate_encounter_report(
    scene_paths: List[str],
    difficulties: List[str] | None = None,
    theme_filter: List[str] | None = None,
    only_dungeons: bool = False
) -> EncounterReport:
    if difficulties is None:
        difficulties = ["easy", "normal", "hard"]

    # We need to know the profiles to set up the controller
    # In a real run, these come from config.py or config.json
    # For now, we'll assume standard defaults if not loaded,
    # but ideally we should load them from the actual config.
    # Let's try to load from engine.config if available, or default.

    # We can't easily instantiate EngineConfig without a lot of context,
    # but we can check if there's a way to get defaults.
    # For this report, we will assume the standard multipliers:
    # easy: 0.5, normal: 1.0, hard: 1.5 (or whatever is in config.json)

    # Actually, we should load config.json to be accurate.
    config_path = Path("config.json")
    profiles = {"easy": 0.5, "normal": 1.0, "hard": 1.5}  # Fallback
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                data = json.load(f)
                if "encounter_budget_profiles" in data:
                    profiles = data["encounter_budget_profiles"]
        except Exception as exc:  # noqa: BLE001
            _log_swallow("ENCR-002", "engine/encounter_report.py blanket swallow", once=True)
            if not getattr(generate_encounter_report, "_mesh_profile_load_error_logged", False):
                print(f"[Mesh][EncounterReport] ERROR loading encounter budget profiles: {exc}")
                setattr(generate_encounter_report, "_mesh_profile_load_error_logged", True)

    report = EncounterReport()
    loader = SceneLoader()

    # Sort paths for stability
    scene_paths = sorted(scene_paths)

    for path in scene_paths:
        if not os.path.exists(path):
            continue

        try:
            # Load raw scene data
            original_scene_data = loader.load_scene(path)
        except Exception as e:
            _log_swallow("ENCR-003", "engine/encounter_report.py blanket swallow", once=True)
            print(f"Failed to load {path}: {e}")
            continue

        settings = original_scene_data.get("settings", {})

        # Filter by dungeon/theme
        if only_dungeons:
            # Heuristic: dungeons usually have "dungeon" in path or type
            # Or check if it has encounter settings
            if "dungeon" not in path.lower() and settings.get("type") != "dungeon":
                continue

        theme_id = settings.get("region_theme")
        if theme_filter and theme_id not in theme_filter:
            continue

        # Skip if no encounter logic would run
        if not settings.get("use_theme_spawns"):
            continue

        for difficulty in difficulties:
            # Deep copy scene data to avoid pollution between difficulties
            scene_data = json.loads(json.dumps(original_scene_data))
            scene_settings = scene_data.get("settings", {})

            # Apply difficulty override
            scene_settings["encounter_budget_profile"] = difficulty

            # Run simulation
            controller = HeadlessSceneController(profiles)
            controller.current_scene_path = path

            # This modifies scene_data in-place
            controller.resolve_spawns(scene_data)

            # Collect stats
            stats = _extract_stats(scene_data, path, difficulty, controller)
            report.scenes.append(stats)

    return report


def _extract_stats(scene_data: Dict[str, Any], path: str, difficulty: str, controller: HeadlessSceneController) -> EncounterSceneReport:
    settings = scene_data.get("settings", {})
    entities = scene_data.get("entities", [])

    preset_id_raw = settings.get("encounter_preset_id")
    preset_id = preset_id_raw.strip() if isinstance(preset_id_raw, str) and preset_id_raw.strip() else None
    if preset_id is None:
        difficulty_raw = settings.get("encounter_budget_profile")
        preset_id = difficulty_raw.strip() if isinstance(difficulty_raw, str) and difficulty_raw.strip() else None

    preset: dict | None = None
    if preset_id:
        try:
            preset = get_theme_manager().get_encounter_preset(preset_id)
        except Exception:
            _log_swallow("ENCR-004", "engine/encounter_report.py blanket swallow", once=True)
            preset = None

    total_cost = 0.0
    spawn_count = 0
    elite_count = 0
    mini_boss_count = 0
    mini_boss_cost = 0.0
    elite_cost = 0.0

    groups: Dict[str, EncounterGroupReport] = {}

    # We need to know the cost of prefabs.
    # The SceneController logic resolves prefabs but doesn't explicitly store cost on the entity
    # unless we look up the prefab again.
    # However, _resolve_budgeted_spawns replaces placeholders with actual prefabs.

    pm = get_prefab_manager()

    for entity in entities:
        # Check if this was a spawned entity (or pre-existing one that counts?)
        # The report asks for "spawn_count", implying things that were resolved.
        # But _resolve_budgeted_spawns modifies existing placeholders.
        # So we look for entities that are NOT placeholders anymore.

        # We can check if it has an 'encounter_group' tag, which placeholders usually have.
        group_id = entity.get("encounter_group", "default")

        prefab_id = entity.get("prefab_id")
        if not prefab_id:
            continue

        # If it's still a placeholder, it wasn't spawned (maybe budget ran out)
        if prefab_id == "theme_enemy_placeholder":
            continue

        # Resolve prefab (respect variant_id if present) to get tier-aware cost.
        variant_id = entity.get("variant_id")
        prefab = pm.resolve_with_variant(prefab_id, variant_id) if variant_id else pm.get_prefab(prefab_id)
        if not prefab:
            continue

        tags = prefab.get("tags", []) if isinstance(prefab, dict) else []
        if "enemy" not in tags and "boss" not in tags:
            # Might be a prop, ignore?
            # The prompt implies we are analyzing the result of spawn resolution.
            # If the placeholder turned into a crate, does it count?
            # Usually encounter logic spawns enemies.
            pass

        cost = float(get_effective_encounter_cost(prefab, default=1.0))
        is_boss = is_boss_payload(prefab)
        is_mini_boss = is_mini_boss_payload(prefab) and not is_boss
        is_elite = is_elite_payload(prefab) and not is_boss and not is_mini_boss

        # Update totals
        total_cost += cost
        spawn_count += 1
        if is_elite:
            elite_count += 1
            elite_cost += cost
        if is_mini_boss:
            mini_boss_count += 1
            mini_boss_cost += cost

        # Update group stats
        if group_id not in groups:
            groups[group_id] = EncounterGroupReport(
                group_id=group_id,
                budget=0.0,  # We'll fill this later if possible, or infer
                spawn_count=0,
                elite_count=0,
                cost=0.0
            )

        groups[group_id].spawn_count += 1
        groups[group_id].cost += cost
        if is_elite:
            groups[group_id].elite_count += 1
            groups[group_id].elite_cost += cost
        if is_mini_boss:
            groups[group_id].mini_boss_count += 1
            groups[group_id].mini_boss_cost += cost

    # Fill in budget info from settings
    base_budget_raw = settings.get("encounter_budget")
    if base_budget_raw is None and preset is not None and preset.get("encounter_budget") is not None:
        base_budget_raw = preset.get("encounter_budget")
    base_budget = float(base_budget_raw or 0.0)

    # We need to calculate the effective budget per group to report it accurately
    # This logic duplicates some of _resolve_budgeted_spawns but is needed for reporting
    # unless we capture it during resolution.
    # For now, we'll just report the configured budgets.
    group_budgets = settings.get("encounter_group_budgets", {})

    # Update group objects with configured budgets
    # Note: This doesn't account for the multiplier!
    multiplier = controller.window.engine_config.encounter_budget_profiles.get(difficulty, 1.0)

    for g_id, g_report in groups.items():
        raw_budget = group_budgets.get(g_id, base_budget)
        g_report.budget = float(raw_budget) * multiplier
        if g_report.cost > 0.0:
            g_report.mini_boss_cost_share = g_report.mini_boss_cost / g_report.cost
            g_report.elite_cost_share = g_report.elite_cost / g_report.cost

    # Boss guard heuristic check
    # If boss_budget_reserve > 0 and we have a boss_guard group
    boss_reserve_raw = settings.get("boss_budget_reserve")
    if boss_reserve_raw is None and preset is not None and preset.get("boss_budget_reserve") is not None:
        boss_reserve_raw = preset.get("boss_budget_reserve")
    boss_reserve = float(boss_reserve_raw or 0.0)
    boss_guard_heuristic = False
    if boss_reserve > 0 and "boss_guard" in groups:
        boss_guard_heuristic = True

    # Seed
    seed_val = settings.get("encounter_seed")
    if seed_val is None:
        seed_val = int(hashlib.sha256(path.encode('utf-8')).hexdigest(), 16)

    mini_boss_cost_share = (mini_boss_cost / total_cost) if total_cost > 0.0 else 0.0
    elite_cost_share = (elite_cost / total_cost) if total_cost > 0.0 else 0.0

    elite_cap_raw = settings.get("elite_cap")
    if elite_cap_raw is None and preset is not None and preset.get("elite_cap") is not None:
        elite_cap_raw = preset.get("elite_cap")
    elite_cap = int(elite_cap_raw) if elite_cap_raw is not None else None

    allow_elites_raw = settings.get("allow_elites")
    preset_allow_elites = preset.get("allow_elites") if preset is not None else None
    if allow_elites_raw is not None:
        allow_elites = bool(allow_elites_raw)
    elif preset_allow_elites is not None:
        allow_elites = bool(preset_allow_elites)
    else:
        allow_elites = True

    mini_boss_cap = settings.get("mini_boss_cap")
    if mini_boss_cap is None and preset is not None and preset.get("mini_boss_cap") is not None:
        mini_boss_cap = preset.get("mini_boss_cap")
    mini_boss_cap_val = int(mini_boss_cap) if mini_boss_cap is not None else None

    allow_mini_bosses = settings.get("allow_mini_bosses")
    if allow_mini_bosses is None and preset is not None and preset.get("allow_mini_bosses") is not None:
        allow_mini_bosses = preset.get("allow_mini_bosses")
    allow_mini_bosses_val = bool(allow_mini_bosses) if allow_mini_bosses is not None else None

    effective_allow_mini_bosses = allow_mini_bosses_val if allow_mini_bosses_val is not None else allow_elites
    effective_mini_boss_cap = mini_boss_cap_val if mini_boss_cap_val is not None else elite_cap

    return EncounterSceneReport(
        scene_path=path,
        difficulty=difficulty,
        encounter_budget=base_budget * multiplier,
        boss_budget_reserve=boss_reserve,
        elite_cap=elite_cap,
        allow_elites=allow_elites,
        encounter_layout=settings.get("encounter_layout", ""),
        encounter_seed=seed_val,
        total_spawn_cost=total_cost,
        spawn_count=spawn_count,
        elite_count=elite_count,
        mini_boss_count=mini_boss_count,
        mini_boss_cost=mini_boss_cost,
        mini_boss_cost_share=mini_boss_cost_share,
        boss_guard_heuristic=boss_guard_heuristic,
        encounter_preset_id=preset_id if preset is not None else None,
        mini_boss_cap=mini_boss_cap_val,
        allow_mini_bosses=allow_mini_bosses_val,
        effective_mini_boss_cap=effective_mini_boss_cap,
        effective_allow_mini_bosses=effective_allow_mini_bosses,
        elite_cost=elite_cost,
        elite_cost_share=elite_cost_share,
        groups=sorted(groups.values(), key=lambda g: g.group_id)
    )


def compute_current_scene_encounter_report(scene_controller: Any) -> EncounterSceneReport | None:
    """
    Build an EncounterSceneReport for the currently loaded scene (post spawn-resolution).

    Tooling/UI helper: reuses the existing EncounterSceneReport structure and extraction logic.
    """
    if scene_controller is None:
        return None
    scene_data = getattr(scene_controller, "_loaded_scene_data", None)
    if not isinstance(scene_data, dict):
        return None
    scene_path = getattr(scene_controller, "current_scene_path", None)
    if not isinstance(scene_path, str) or not scene_path.strip():
        return None
    settings = scene_data.get("settings", {})
    profile = settings.get("encounter_budget_profile") if isinstance(settings, dict) else None
    difficulty = str(profile).strip() if isinstance(profile, str) and profile.strip() else "normal"
    try:
        return _extract_stats(scene_data, scene_path, difficulty, cast(HeadlessSceneController, scene_controller))
    except Exception:  # noqa: BLE001
        _log_swallow("ENCR-005", "engine/encounter_report.py blanket swallow", once=True)
        return None


def encounter_report_to_audit_payload(report: EncounterReport | list[EncounterSceneReport]) -> dict[str, Any]:
    scenes = report.scenes if isinstance(report, EncounterReport) else list(report)

    def _sort_key(s: EncounterSceneReport) -> tuple[str, str]:
        return (
            normalize_scene_path(str(getattr(s, "scene_path", "") or "")),
            str(getattr(s, "difficulty", "") or ""),
        )

    lines: list[str] = []
    for scene in sorted(scenes, key=_sort_key):
        scene_path = normalize_scene_path(str(scene.scene_path))
        difficulty = str(scene.difficulty)
        preset = scene.encounter_preset_id if getattr(scene, "encounter_preset_id", None) else "-"

        budget = float(scene.encounter_budget)
        reserve = float(scene.boss_budget_reserve)

        elite_cap = getattr(scene, "elite_cap", None)
        elite_cap_str = "-" if elite_cap is None else str(int(elite_cap))

        mb_cap = getattr(scene, "mini_boss_cap", None)
        if mb_cap is None:
            mb_cap_display = f"->elite({elite_cap_str})"
        else:
            mb_cap_display = str(int(mb_cap))

        allow_elites = bool(scene.allow_elites)
        allow_elites_display = "Y" if allow_elites else "N"

        allow_mb = getattr(scene, "allow_mini_bosses", None)
        if allow_mb is None:
            mb_allow_display = f"->elites({allow_elites_display})"
        else:
            mb_allow_display = "Y" if bool(allow_mb) else "N"

        spawn_count = int(scene.spawn_count)
        elite_count = int(scene.elite_count)
        mini_count = int(getattr(scene, "mini_boss_count", 0))

        total_cost = float(scene.total_spawn_cost)
        elite_share = float(getattr(scene, "elite_cost_share", 0.0))
        mini_share = float(getattr(scene, "mini_boss_cost_share", 0.0))

        line = (
            f"{scene_path} | diff={difficulty} preset={preset} | budget={budget:.2f} reserve={reserve:.2f} | "
            f"caps e={elite_cap_str} mb={mb_cap_display} | allow e={allow_elites_display} mb={mb_allow_display} | "
            f"spawns={spawn_count} elite={elite_count} mini={mini_count} | cost={total_cost:.2f} "
            f"shares e={elite_share:.4f} mb={mini_share:.4f}"
        )
        lines.append(line)

    return {"ok": True, "scene_count": len(lines), "lines": lines}


def encounter_report_to_compact_payload(report: EncounterReport | list[EncounterSceneReport]) -> dict[str, Any]:
    scenes = report.scenes if isinstance(report, EncounterReport) else list(report)

    def _sort_key(s: EncounterSceneReport) -> tuple[str, str]:
        return (
            normalize_scene_path(str(getattr(s, "scene_path", "") or "")),
            str(getattr(s, "difficulty", "") or ""),
        )

    rows: list[dict[str, Any]] = []
    for scene in sorted(scenes, key=_sort_key):
        rows.append(
            {
                "scene_path": normalize_scene_path(str(scene.scene_path)),
                "difficulty": str(scene.difficulty),
                "encounter_preset_id": scene.encounter_preset_id,
                "encounter_budget": float(scene.encounter_budget),
                "boss_budget_reserve": float(scene.boss_budget_reserve),
                "elite_cap": scene.elite_cap,
                "mini_boss_cap": scene.mini_boss_cap,
                "allow_elites": bool(scene.allow_elites),
                "allow_mini_bosses": scene.allow_mini_bosses,
                "spawn_count": int(scene.spawn_count),
                "elite_count": int(scene.elite_count),
                "mini_boss_count": int(getattr(scene, "mini_boss_count", 0)),
                "total_spawn_cost": float(scene.total_spawn_cost),
                "elite_cost_share": float(getattr(scene, "elite_cost_share", 0.0)),
                "mini_boss_cost_share": float(getattr(scene, "mini_boss_cost_share", 0.0)),
            }
        )

    return {"ok": True, "scene_count": len(rows), "rows": rows}


def encounter_report_to_headroom_payload(report: EncounterReport | list[EncounterSceneReport]) -> dict[str, Any]:
    scenes = report.scenes if isinstance(report, EncounterReport) else list(report)

    def _sort_key(s: EncounterSceneReport) -> tuple[str, str]:
        return (
            normalize_scene_path(str(getattr(s, "scene_path", "") or "")),
            str(getattr(s, "difficulty", "") or ""),
        )

    rows: list[dict[str, Any]] = []
    for scene in sorted(scenes, key=_sort_key):
        scene_path = normalize_scene_path(str(scene.scene_path))
        difficulty = str(scene.difficulty)
        budget = float(scene.encounter_budget)
        reserve = float(scene.boss_budget_reserve)
        effective_budget = max(budget - reserve, 0.0)

        total_cost = float(scene.total_spawn_cost)
        headroom = float(effective_budget - total_cost)
        utilization = float(total_cost / max(effective_budget, 0.01))

        rows.append(
            {
                "scene_path": scene_path,
                "difficulty": difficulty,
                "budget": budget,
                "reserve": reserve,
                "effective_budget": effective_budget,
                "total_spawn_cost": total_cost,
                "headroom": headroom,
                "utilization": utilization,
            }
        )

    return {"ok": True, "scene_count": len(rows), "rows": rows}
