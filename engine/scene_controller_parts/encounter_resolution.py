# mypy: ignore-errors
from __future__ import annotations

from typing import Any, Dict


def _apply_theme_runtime(self, scene_data: Dict[str, Any]) -> None:
    import engine.scene_controller as scene_controller_module

    settings = scene_data.get("settings", {})
    theme_id = settings.get("region_theme")
    if not theme_id:
        return

    tm = scene_controller_module.get_theme_manager()
    theme = tm.get_theme(theme_id)
    if not theme:
        return

    encounter_set_id = settings.get("encounter_set_id")
    if encounter_set_id:
        encounter_set = tm.get_encounter_set(encounter_set_id)
    else:
        encounter_set = tm.resolve_encounter_set_for_theme(theme_id)

    if not encounter_set:
        return

    if "music" not in settings and encounter_set.ambient_audio_key:
        audio_map = {
            "forest_ambience": "assets/music/forest_ambience.mp3",
            "lava_rumble": "assets/music/lava_rumble.mp3",
            "void_hum": "assets/music/void_hum.mp3",
        }
        if encounter_set.ambient_audio_key in audio_map:
            settings["music"] = audio_map[encounter_set.ambient_audio_key]

    if "lights" not in scene_data and theme.lighting_hint:
        lighting_map = {
            "green_dim": [{"type": "ambient", "color": [50, 100, 50], "intensity": 0.4}],
            "red_glow": [{"type": "ambient", "color": [100, 50, 50], "intensity": 0.5}],
            "purple_dark": [{"type": "ambient", "color": [60, 20, 80], "intensity": 0.3}],
        }
        if theme.lighting_hint in lighting_map:
            scene_data["lights"] = lighting_map[theme.lighting_hint]

    if settings.get("use_theme_spawns") and encounter_set.enemy_prefab_ids:
        self._resolve_budgeted_spawns(scene_data, encounter_set, theme)


def _resolve_legacy_spawns(self, scene_data: Dict[str, Any], encounter_set: Any, theme: Any) -> None:
    import engine.scene_controller as scene_controller_module

    settings = scene_data.get("settings", {})
    seed_val = 0
    if self.current_scene_path:
        seed_val = sum(ord(c) for c in self.current_scene_path)
    rng = scene_controller_module.random.Random(seed_val)

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
    import engine.scene_controller as scene_controller_module

    settings = scene_data.get("settings", {})

    preset_id_raw = settings.get("encounter_preset_id")
    preset_id = preset_id_raw.strip() if isinstance(preset_id_raw, str) and preset_id_raw.strip() else None
    if preset_id is None:
        difficulty_raw = settings.get("encounter_budget_profile")
        preset_id = difficulty_raw.strip() if isinstance(difficulty_raw, str) and difficulty_raw.strip() else None

    preset: dict | None = None
    if preset_id:
        try:
            preset = scene_controller_module.get_theme_manager().get_encounter_preset(preset_id)
        except Exception:
            scene_controller_module.logger.debug("Encounter preset lookup failed for %r", preset_id, exc_info=True); preset = None

    base_budget = settings.get("encounter_budget")
    if base_budget is None and preset is not None and preset.get("encounter_budget") is not None:
        base_budget = preset.get("encounter_budget")

    group_budgets = settings.get("encounter_group_budgets", {})
    if base_budget is None and not group_budgets:
        self._resolve_legacy_spawns(scene_data, encounter_set, theme)
        return

    profile = settings.get("encounter_budget_profile")
    multiplier = 1.0
    if profile and hasattr(self.window, "engine_config") and self.window.engine_config.encounter_budget_profiles:
        multiplier = self.window.engine_config.encounter_budget_profiles.get(profile, 1.0)

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

    group_elite_caps = settings.get("encounter_group_elite_caps", {})
    group_allow_elites = settings.get("encounter_group_allow_elites", {})

    seed_val = settings.get("encounter_seed")
    if seed_val is None and self.current_scene_path:
         seed_val = int(scene_controller_module.hashlib.sha256(self.current_scene_path.encode('utf-8')).hexdigest(), 16)

    rng = scene_controller_module.random.Random(seed_val)

    entities = scene_data.get("entities", [])

    placeholders_by_group: Dict[str, list[int]] = {}
    for idx, entity in enumerate(entities):
        if entity.get("prefab_id") == "theme_enemy_placeholder":
            group = entity.get("encounter_group", "default")
            if group not in placeholders_by_group:
                placeholders_by_group[group] = []
            placeholders_by_group[group].append(idx)

    if not placeholders_by_group:
        return

    sorted_groups = sorted(placeholders_by_group.keys())
    for group in sorted_groups:
        rng.shuffle(placeholders_by_group[group])

    effective_budgets: Dict[str, float] = {}
    for group in sorted_groups:
        g_budget = group_budgets.get(group)
        if g_budget is None:
            g_budget = base_budget if base_budget is not None else 0.0

        effective_budgets[group] = float(g_budget) * multiplier

    if boss_reserve > 0:
        target_group = "boss_guard" if "boss_guard" in placeholders_by_group else "default"
        if target_group in effective_budgets:
            effective_budgets[target_group] -= boss_reserve

    scene_spawn_variant_id = settings.get("theme_spawn_variant_id")
    if scene_spawn_variant_id is None:
        scene_spawn_variant_id = settings.get("variant_id")
    global_variant_id = scene_spawn_variant_id or encounter_set.variant_id or theme.default_variant_id
    pm = scene_controller_module.get_prefab_manager()

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
            cost = float(scene_controller_module.get_effective_encounter_cost(data, default=1.0))
            is_boss = scene_controller_module.is_boss_payload(data)
            is_mini_boss = scene_controller_module.is_mini_boss_payload(data) and not is_boss
            is_elite = scene_controller_module.is_elite_payload(data) and not is_boss and not is_mini_boss
            master_candidates.append({
                "pid": pid,
                "variant_id": candidate_variant_id,
                "cost": cost,
                "is_boss": is_boss,
                "is_mini_boss": is_mini_boss,
                "is_elite": is_elite,
            })

    if not master_candidates:
        return

    master_candidates.sort(key=lambda x: x["cost"])

    indices_to_remove = []

    for group in sorted_groups:
        indices = placeholders_by_group[group]
        budget = effective_budgets[group]

        cap = group_elite_caps.get(group, global_elite_cap)
        allow = group_allow_elites.get(group, global_allow_elites)

        allow_mb = global_allow_mini_bosses if global_allow_mini_bosses is not None else allow
        mb_cap = global_mini_boss_cap if global_mini_boss_cap is not None else cap

        if group == "boss_guard" and profile != "hard":
            if group not in group_allow_elites:
                allow = False
                if global_allow_mini_bosses is None:
                    allow_mb = False

        group_candidates = [
            c
            for c in master_candidates
            if not ((c["is_elite"] and not allow) or (c["is_mini_boss"] and not allow_mb))
        ]

        if not group_candidates:
            indices_to_remove.extend(indices)
            continue

        spawned_count = 0
        elite_count = 0
        mini_boss_count = 0

        for idx in indices:
            affordable = []
            for c in group_candidates:
                if c["cost"] > budget:
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
                        chosen = group_candidates[0]
                else:
                    indices_to_remove.append(idx)
                    continue
            else:
                chosen = rng.choice(affordable)

            pid = chosen["pid"]
            cost = chosen["cost"]
            is_elite = chosen["is_elite"]
            is_mini_boss = chosen["is_mini_boss"]
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


def bind_encounter_resolution_methods(cls) -> None:
    cls._apply_theme_runtime = _apply_theme_runtime
    cls._resolve_legacy_spawns = _resolve_legacy_spawns
    cls._resolve_budgeted_spawns = _resolve_budgeted_spawns