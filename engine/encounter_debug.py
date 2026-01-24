"""Debug helpers for the Encounter system."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from .encounter_sets import get_theme_manager

if TYPE_CHECKING:
    from .scene_controller import SceneController


def get_encounter_debug_lines(scene_controller: SceneController) -> List[str]:
    """Extract encounter debug information from the scene controller."""
    settings = scene_controller.scene_settings
    lines = ["--- Encounter ---"]

    theme_id = settings.get("region_theme")
    lines.append(f"Theme: {theme_id}")

    tm = get_theme_manager()
    encounter_set_id = settings.get("encounter_set_id")

    # Try to resolve if not explicit
    if not encounter_set_id and theme_id:
        es = tm.resolve_encounter_set_for_theme(theme_id)
        if es:
            encounter_set_id = f"{es.id} (derived)"

    lines.append(f"Set: {encounter_set_id}")

    variant = settings.get("variant_id")
    # Try to resolve default if not explicit
    if not variant and theme_id:
        theme = tm.get_theme(theme_id)
        if theme and theme.default_variant_id:
            variant = f"{theme.default_variant_id} (theme)"

    lines.append(f"Variant: {variant}")

    budget = settings.get("encounter_budget")
    profile = settings.get("encounter_budget_profile")
    lines.append(f"Budget: {budget} (Profile: {profile})")

    layout = settings.get("encounter_layout")
    lines.append(f"Layout: {layout}")

    boss_reserve = settings.get("boss_budget_reserve")
    lines.append(f"Boss Reserve: {boss_reserve}")

    elite_cap = settings.get("elite_cap")
    lines.append(f"Elite Cap: {elite_cap}")

    seed = settings.get("encounter_seed")
    lines.append(f"Seed: {seed}")

    group_budgets = settings.get("encounter_group_budgets", {})
    group_caps = settings.get("encounter_group_elite_caps", {})
    group_allow = settings.get("encounter_group_allow_elites", {})

    if group_budgets:
        lines.append("Groups:")
        for g, b in group_budgets.items():
            cap = group_caps.get(g, "global")
            allow = group_allow.get(g, "global")
            lines.append(f"  {g}: {b} (Cap: {cap}, Allow: {allow})")

    return lines
