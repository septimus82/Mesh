"""Monster encounter zone behaviour."""

from __future__ import annotations

import math
import random
from typing import Any

from engine.monster.battle_model import MonsterInstance
from engine.monster.data_load import MonsterCatalog, load_monster_catalog
from engine.monster.encounter import EncounterRollResult, roll_monster_encounter
from engine.paths import resolve_monster_data_dir

from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "MonsterEncounterZone",
    description="Starts a monster battle when the target enters an eligible encounter zone.",
    config_fields=[
        {"name": "trigger_radius", "description": "Distance threshold for triggering", "type": "float", "default": 0.0},
        {"name": "trigger_target", "description": "Name of the player sprite to watch", "type": "string", "default": ""},
        {"name": "encounter_id", "description": "Stable encounter id for return context", "type": "string", "default": ""},
        {"name": "enabled", "description": "Whether encounters can trigger", "type": "bool", "default": True},
        {"name": "enabled_flag", "description": "Optional game-state flag required to enable encounters", "type": "string", "default": ""},
        {"name": "cooldown_seconds", "description": "Cooldown after a roll/start", "type": "float", "default": 1.0},
        {"name": "chance", "description": "Encounter chance per eligible enter update", "type": "float", "default": 1.0},
        {"name": "player_species_id", "description": "Temporary player-side species id for MON-0e", "type": "string", "default": ""},
        {"name": "player_level", "description": "Temporary player-side level for MON-0e", "type": "int", "default": 5},
        {"name": "encounter_table", "description": "Weighted encounter table", "type": "array", "default": []},
        {"name": "companion_mode", "description": "Start a companion battle (auto-acting monster + Praise/Scold/Wait)", "type": "bool", "default": False},
    ],
)
class MonsterEncounterZoneBehaviour(Behaviour):
    """Detect a player entering a zone and start MON-0d battle mode."""

    PARAM_DEFS = {
        "trigger_radius": ParamDef(float, default=0.0, description="Distance threshold for triggering"),
        "trigger_target": ParamDef(str, default="", description="Name of the player sprite to watch"),
        "encounter_id": ParamDef(str, default="", description="Stable encounter id for return context"),
        "enabled": ParamDef(bool, default=True, description="Whether encounters can trigger"),
        "enabled_flag": ParamDef(str, default="", description="Optional game-state flag required to enable encounters"),
        "cooldown_seconds": ParamDef(float, default=1.0, description="Cooldown after a roll/start"),
        "chance": ParamDef(float, default=1.0, description="Encounter chance per eligible enter update"),
        "player_species_id": ParamDef(str, default="", description="Temporary player-side species id for MON-0e"),
        "player_level": ParamDef(int, default=5, description="Temporary player-side level for MON-0e"),
        "encounter_table": ParamDef(list, default=[], description="Weighted encounter table"),
        "companion_mode": ParamDef(bool, default=False, description="Start companion battle instead of command battler"),
    }

    def __init__(self, entity: Any, window: Any, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self.radius = float(self.config.get("trigger_radius", 0.0) or 0.0)
        self.target_name = str(self.config.get("trigger_target", "") or "").strip()
        self.encounter_id = str(self.config.get("encounter_id", "") or "").strip()
        self.enabled = bool(self.config.get("enabled", True))
        self.enabled_flag = str(self.config.get("enabled_flag", "") or "").strip()
        self.cooldown_seconds = max(0.0, float(self.config.get("cooldown_seconds", 1.0) or 0.0))
        self.chance = max(0.0, min(1.0, float(self.config.get("chance", 1.0) or 0.0)))
        self.player_species_id = str(self.config.get("player_species_id", "") or "").strip()
        self.player_level = max(1, int(self.config.get("player_level", 5) or 5))
        self.encounter_table = list(self.config.get("encounter_table", []) or [])
        self.companion_mode = bool(self.config.get("companion_mode", False))
        self.rng = self._build_rng(config)
        self.cooldown_remaining = 0.0
        self.last_roll: EncounterRollResult | None = None
        self.last_error: str = ""
        self.last_return_context: dict[str, Any] = {}
        self._disabled = self.radius <= 0.0 or not self.target_name

    def update(self, dt: float) -> None:
        self.last_error = ""
        if self.cooldown_remaining > 0.0:
            self.cooldown_remaining = max(0.0, self.cooldown_remaining - float(dt))
            return
        if self._disabled or not self._eligible():
            return
        target = self.window.find_sprite_by_name(self.target_name)
        if target is None or not self._contains(target):
            return
        if self.chance < 1.0 and float(self.rng.random()) >= self.chance:
            self.cooldown_remaining = self.cooldown_seconds
            return

        catalog = self._catalog()
        if catalog is None:
            return
        roll = roll_monster_encounter(self.encounter_table, catalog, self.rng)
        self.last_roll = roll
        if not roll.ok or roll.monster is None:
            self.last_error = "; ".join(roll.errors)
            return

        context = self._return_context(roll)
        self.last_return_context = dict(context)
        starter = getattr(self.window, "start_monster_battle", None)
        if not callable(starter):
            self.last_error = "window.start_monster_battle is unavailable"
            return

        if self.companion_mode:
            resolved = self._resolve_companion_party(catalog)
            if resolved is None:
                return
            party, party_instance_ids, mind, player_monster, instance_id = resolved
            context["source"] = "companion_encounter_zone"
            context["player_instance_id"] = instance_id
            context["companion_mode"] = True
            starter(
                player_monster=player_monster,
                player_party=party,
                player_party_instance_ids=party_instance_ids,
                opponent_monster=roll.monster,
                moves=catalog.moves,
                type_chart=catalog.type_chart,
                companion_mode=True,
                companion_mind=mind,
                return_context=context,
            )
            self.cooldown_remaining = self.cooldown_seconds
            return

        player_monster = self._player_monster(catalog)
        if player_monster is None:
            return
        starter(
            player_monster=player_monster,
            opponent_monster=roll.monster,
            moves=catalog.moves,
            type_chart=catalog.type_chart,
            return_context=context,
        )
        self.cooldown_remaining = self.cooldown_seconds

    def _eligible(self) -> bool:
        if not self.enabled:
            return False
        if getattr(getattr(self.window, "monster_battle_mode", None), "active", False):
            return False
        if not self.enabled_flag:
            return True
        getter = getattr(self.window, "get_flag", None)
        if callable(getter):
            return bool(getter(self.enabled_flag, False))
        controller = getattr(self.window, "game_state_controller", None)
        getter = getattr(controller, "get_flag", None)
        if callable(getter):
            return bool(getter(self.enabled_flag, False))
        return False

    def _contains(self, target: Any) -> bool:
        dx = float(getattr(target, "center_x", 0.0)) - float(getattr(self.entity, "center_x", 0.0))
        dy = float(getattr(target, "center_y", 0.0)) - float(getattr(self.entity, "center_y", 0.0))
        return math.hypot(dx, dy) <= self.radius

    def _catalog(self) -> MonsterCatalog | None:
        catalog = getattr(self.window, "monster_catalog", None)
        if isinstance(catalog, MonsterCatalog):
            return catalog
        data_dir = self.config.get("catalog_data_dir")
        loaded, validation = load_monster_catalog(
            data_dir if data_dir else resolve_monster_data_dir(),
        )
        if not validation.ok or loaded is None:
            self.last_error = "; ".join(validation.errors)
            return None
        self.window.monster_catalog = loaded
        return loaded

    def _player_monster(self, catalog: MonsterCatalog) -> MonsterInstance | None:
        existing = getattr(self.window, "monster_player_monster", None)
        if isinstance(existing, MonsterInstance):
            return existing
        species_id = self.player_species_id
        if not species_id:
            species_id = next(iter(catalog.species), "")
        if species_id not in catalog.species:
            self.last_error = f"player_species_id references unknown species '{species_id}'"
            return None
        species = catalog.species[species_id]
        return MonsterInstance(species, level=self.player_level, known_moves=species.learnset)

    def _state_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        controller = getattr(self.window, "game_state_controller", None)
        state = getattr(controller, "state", None)
        state_values = getattr(state, "values", None)
        if isinstance(state_values, dict):
            values = state_values
        return values

    def _resolve_companion_party(
        self,
        catalog: MonsterCatalog,
    ) -> tuple[list[MonsterInstance], list[str | None], Any, MonsterInstance, str] | None:
        from engine.monster.collection import (  # noqa: PLC0415
            MONSTER_PARTY_KEY,
            add_caught_monster,
            companion_starter_was_granted,
            default_companion_mind_for_instance,
            ensure_monster_collection,
            load_battle_party_from_values,
            load_companion_mind_for_instance,
            mark_companion_starter_granted,
            mark_companion_starter_instance,
        )

        values = self._state_values()
        ensure_monster_collection(values)

        fallback_species = catalog.species.get("sproutling")
        if fallback_species is None:
            first_id = next(iter(catalog.species), "")
            fallback_species = catalog.species.get(first_id)
        if fallback_species is None:
            self.last_error = "catalog has no species for companion fallback"
            return None

        party_ids = [str(item) for item in values.get(MONSTER_PARTY_KEY, []) if str(item).strip()]
        if not party_ids:
            if not companion_starter_was_granted(values):
                debug_monster = MonsterInstance(fallback_species, level=8, known_moves=fallback_species.learnset)
                stored = add_caught_monster(values, debug_monster)
                mark_companion_starter_instance(values, stored.instance_id)
                mark_companion_starter_granted(values)
                party_ids = [stored.instance_id]
            else:
                self.last_error = "companion party is empty after abandonment"
                logger = getattr(self.window, "console_log", None)
                message = "[Mesh][Companion] No companion available; encounter skipped."
                if callable(logger):
                    logger(message)
                else:
                    print(message)
                return None

        fallback = MonsterInstance(fallback_species, level=8, known_moves=fallback_species.learnset)
        party, party_instance_ids = load_battle_party_from_values(values, catalog.species, fallback=fallback)
        if not party_instance_ids or party_instance_ids[0] is None:
            self.last_error = "companion party could not be resolved"
            return None

        active = party[0]
        instance_id = str(party_instance_ids[0])
        mind = load_companion_mind_for_instance(values, instance_id)
        if mind is None:
            mind = default_companion_mind_for_instance(values, instance_id)
        return party, party_instance_ids, mind, active, instance_id

    def _return_context(self, roll: EncounterRollResult) -> dict[str, Any]:
        scene_controller = getattr(self.window, "scene_controller", None)
        scene_path = str(getattr(scene_controller, "current_scene_path", "") or "")
        zone_id = str(getattr(self.entity, "mesh_name", "") or getattr(self.entity, "name", "") or "")
        encounter_id = self.encounter_id or zone_id
        return {
            "scene_path": scene_path,
            "zone_id": zone_id,
            "encounter_id": encounter_id,
            "species_id": roll.species_id,
            "level": roll.level,
        }

    def _build_rng(self, raw_config: dict[str, Any]) -> Any:
        injected = raw_config.get("rng")
        if hasattr(injected, "random"):
            return injected
        seed = raw_config.get("seed", raw_config.get("encounter_seed"))
        return random.Random(int(seed)) if seed not in (None, "") else random.Random()
