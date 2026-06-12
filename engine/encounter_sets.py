"""Encounter Set and Theme management system."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .encounter_presets import load_encounter_presets
from .logging_tools import get_logger
from .paths import resolve_path

_LOG = get_logger("engine.encounter_sets")


def iter_encounter_set_source_paths() -> tuple[str, ...]:
    """Return the canonical encounter set definition sources.

    Keep this aligned with ThemeManager.load_data and validators that scan encounter sets.
    """
    return ("packs/core_regions/data/encounter_sets.json",)


@dataclass
class EncounterSet:
    id: str
    enemy_tags: List[str] = field(default_factory=list)
    enemy_prefab_ids: List[str] = field(default_factory=list)
    drop_table_id: Optional[str] = None
    ambient_audio_key: Optional[str] = None
    elite_modifiers: List[str] = field(default_factory=list)
    boss_modifiers: List[str] = field(default_factory=list)
    variant_id: Optional[str] = None


@dataclass
class RegionTheme:
    id: str
    description: str
    encounter_set_id: Optional[str] = None
    lighting_hint: Optional[str] = None
    default_variant_id: Optional[str] = None
    # Legacy/Fallback fields
    default_enemy_tags: List[str] = field(default_factory=list)
    default_drop_table_id: Optional[str] = None
    ambient_audio_key: Optional[str] = None


class ThemeManager:
    def __init__(self) -> None:
        self.themes: Dict[str, RegionTheme] = {}
        self.encounter_sets: Dict[str, EncounterSet] = {}
        self.encounter_presets: Dict[str, dict] = {}
        self._loaded = False

    def load_data(self) -> None:
        if self._loaded:
            return

        # Load Themes
        themes_path = resolve_path("assets/data/themes.json")
        if themes_path.exists():
            try:
                data = json.loads(themes_path.read_text(encoding="utf-8"))
                for theme_id, theme_data in data.items():
                    self.themes[theme_id] = RegionTheme(
                        id=theme_id,
                        description=theme_data.get("description", ""),
                        encounter_set_id=theme_data.get("encounter_set_id"),
                        lighting_hint=theme_data.get("lighting_hint"),
                        default_variant_id=theme_data.get("default_variant_id"),
                        default_enemy_tags=theme_data.get("default_enemy_tags", []),
                        default_drop_table_id=theme_data.get("default_drop_table_id"),
                        ambient_audio_key=theme_data.get("ambient_audio_key"),
                    )
            except Exception as e:
                _LOG.error("[Mesh][Themes] Error loading themes: %s", e)

        # Load Encounter Sets
        for sets_path in (resolve_path(p) for p in iter_encounter_set_source_paths()):
            if not sets_path.exists():
                continue
            try:
                data = json.loads(sets_path.read_text(encoding="utf-8"))
                for set_data in data.get("encounter_sets", []):
                    es_id = set_data["id"]
                    self.encounter_sets[es_id] = EncounterSet(
                        id=es_id,
                        enemy_tags=set_data.get("enemy_tags", []),
                        enemy_prefab_ids=set_data.get("enemy_prefab_ids", []),
                        drop_table_id=set_data.get("drop_table_id"),
                        ambient_audio_key=set_data.get("ambient_audio_key"),
                        elite_modifiers=set_data.get("elite_modifiers", []),
                        boss_modifiers=set_data.get("boss_modifiers", []),
                        variant_id=set_data.get("variant_id"),
                    )
            except Exception as e:
                _LOG.error("[Mesh][Themes] Error loading encounter sets from '%s': %s", sets_path, e)

        # Load Encounter Presets (optional)
        presets_path = resolve_path("packs/core_regions/data/encounter_presets.json")
        if presets_path.exists():
            presets, issues = load_encounter_presets(presets_path, strict_unknown_keys=False)
            self.encounter_presets = presets
            for issue in issues:
                if issue.level == "ERROR":
                    _LOG.error("[Mesh][EncounterPresets] %s", issue.message)
                else:
                    _LOG.warning("[Mesh][EncounterPresets] %s", issue.message)

        self._loaded = True

    def get_theme(self, theme_id: str) -> Optional[RegionTheme]:
        self.load_data()
        return self.themes.get(theme_id)

    def get_encounter_set(self, set_id: str) -> Optional[EncounterSet]:
        self.load_data()
        return self.encounter_sets.get(set_id)

    def get_encounter_preset(self, preset_id: str) -> dict | None:
        self.load_data()
        return self.encounter_presets.get(preset_id)

    def resolve_encounter_set_for_theme(self, theme_id: str) -> Optional[EncounterSet]:
        theme = self.get_theme(theme_id)
        if not theme:
            return None

        if theme.encounter_set_id:
            return self.get_encounter_set(theme.encounter_set_id)

        # Fallback: construct a virtual encounter set from legacy theme data
        return EncounterSet(
            id=f"virtual_{theme_id}",
            enemy_tags=theme.default_enemy_tags,
            drop_table_id=theme.default_drop_table_id,
            ambient_audio_key=theme.ambient_audio_key
        )

_THEME_MANAGER: ThemeManager | None = None

def get_theme_manager() -> ThemeManager:
    global _THEME_MANAGER
    if _THEME_MANAGER is None:
        _THEME_MANAGER = ThemeManager()
    return _THEME_MANAGER
