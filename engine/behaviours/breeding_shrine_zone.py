"""Breeding shrine zone behaviour."""

from __future__ import annotations

import math
import random
from typing import Any

from engine.monster.breeding_shrine import attempt_breeding_at_shrine
from engine.monster.data_load import MonsterCatalog, load_battle_terms, load_monster_catalog
from engine.paths import resolve_monster_data_dir

from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "BreedingShrineZone",
    description="Creates a breeding egg when two sufficiently bonded companions visit the shrine.",
    config_fields=[
        {"name": "trigger_radius", "description": "Distance threshold for triggering", "type": "float", "default": 0.0},
        {"name": "trigger_target", "description": "Name of the player sprite to watch", "type": "string", "default": ""},
        {"name": "enabled", "description": "Whether the shrine can trigger", "type": "bool", "default": True},
        {"name": "enabled_flag", "description": "Optional game-state flag required to enable the shrine", "type": "string", "default": ""},
        {"name": "cooldown_seconds", "description": "Cooldown after an attempt", "type": "float", "default": 3.0},
        {"name": "bond_threshold", "description": "Minimum companion bond required to breed", "type": "float", "default": 50.0},
        {"name": "max_eggs", "description": "Maximum pending eggs allowed", "type": "int", "default": 1},
        {"name": "hatch_steps", "description": "Egg steps required before hatching", "type": "int", "default": 200},
    ],
)
class BreedingShrineZoneBehaviour(Behaviour):
    """Detect a player entering a shrine zone and attempt companion breeding."""

    PARAM_DEFS = {
        "trigger_radius": ParamDef(float, default=0.0, description="Distance threshold for triggering"),
        "trigger_target": ParamDef(str, default="", description="Name of the player sprite to watch"),
        "enabled": ParamDef(bool, default=True, description="Whether the shrine can trigger"),
        "enabled_flag": ParamDef(str, default="", description="Optional game-state flag required to enable the shrine"),
        "cooldown_seconds": ParamDef(float, default=3.0, description="Cooldown after an attempt"),
        "bond_threshold": ParamDef(float, default=50.0, description="Minimum companion bond required to breed"),
        "max_eggs": ParamDef(int, default=1, description="Maximum pending eggs allowed"),
        "hatch_steps": ParamDef(int, default=200, description="Egg steps required before hatching"),
    }

    def __init__(self, entity: Any, window: Any, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self.radius = float(self.config.get("trigger_radius", 0.0) or 0.0)
        self.target_name = str(self.config.get("trigger_target", "") or "").strip()
        self.enabled = bool(self.config.get("enabled", True))
        self.enabled_flag = str(self.config.get("enabled_flag", "") or "").strip()
        self.cooldown_seconds = max(0.0, float(self.config.get("cooldown_seconds", 3.0) or 0.0))
        self.bond_threshold = float(self.config.get("bond_threshold", 50.0) or 50.0)
        self.max_eggs = max(1, int(self.config.get("max_eggs", 1) or 1))
        self.hatch_steps = max(1, int(self.config.get("hatch_steps", 200) or 200))
        self.rng = self._build_rng(config)
        self.cooldown_remaining = 0.0
        self._was_inside = False
        self.last_outcome: str = ""
        self._disabled = self.radius <= 0.0 or not self.target_name

    def update(self, dt: float) -> None:
        self.last_outcome = ""
        if self.cooldown_remaining > 0.0:
            self.cooldown_remaining = max(0.0, self.cooldown_remaining - float(dt))

        if self._disabled or not self._eligible():
            self._was_inside = False
            return

        target = self.window.find_sprite_by_name(self.target_name)
        if target is None:
            self._was_inside = False
            return

        inside = self._contains(target)
        if not inside:
            self._was_inside = False
            return
        if self._was_inside:
            return
        self._was_inside = True

        if self.cooldown_remaining > 0.0:
            self._log_terms_line("breeding_cooldown")
            self.last_outcome = "cooldown"
            return

        catalog = self._catalog()
        if catalog is None:
            self.last_outcome = "catalog_error"
            return

        result = attempt_breeding_at_shrine(
            self._state_values(),
            catalog=catalog,
            bond_threshold=self.bond_threshold,
            max_eggs=self.max_eggs,
            hatch_steps=self.hatch_steps,
            rng=self.rng,
        )
        self.last_outcome = result.outcome
        self.cooldown_remaining = self.cooldown_seconds

        terms = self._terms()
        if result.outcome == "success":
            self._log_line(terms.egg_created)
            return
        if result.outcome == "not_enough_bonded":
            self._log_line(terms.breeding_not_enough_bonded)
            return
        if result.outcome == "egg_waiting":
            self._log_line(terms.breeding_egg_waiting)
            return
        if result.outcome == "party_error":
            self._log_line(terms.breeding_not_enough_bonded)

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
            return None
        self.window.monster_catalog = loaded
        return loaded

    def _state_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        controller = getattr(self.window, "game_state_controller", None)
        state = getattr(controller, "state", None)
        state_values = getattr(state, "values", None)
        if isinstance(state_values, dict):
            values = state_values
        return values

    def _terms(self) -> Any:
        cached = getattr(self.window, "battle_terms", None)
        if cached is not None:
            return cached
        terms, result = load_battle_terms(resolve_monster_data_dir())
        resolved = terms if result.ok else terms
        self.window.battle_terms = resolved
        return resolved

    def _log_terms_line(self, field_name: str) -> None:
        terms = self._terms()
        self._log_line(str(getattr(terms, field_name, "")))

    def _log_line(self, line: str) -> None:
        if not line:
            return
        logger = getattr(self.window, "console_log", None)
        if callable(logger):
            logger(line)
            return
        print(f"[Mesh][BreedingShrine] {line}")

    def _build_rng(self, raw_config: dict[str, Any]) -> Any:
        injected = raw_config.get("rng")
        if hasattr(injected, "random"):
            return injected
        seed = raw_config.get("seed", raw_config.get("breeding_seed"))
        return random.Random(int(seed)) if seed not in (None, "") else random.Random()

    def saveable_state(self) -> dict[str, Any]:
        return {
            "cooldown_remaining": float(max(0.0, self.cooldown_remaining)),
            "was_inside": bool(self._was_inside),
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        if not isinstance(state, dict):
            state = {}
        raw_cooldown = state.get("cooldown_remaining", 0.0)
        try:
            cooldown = float(raw_cooldown)
        except (TypeError, ValueError):
            cooldown = 0.0
        if not math.isfinite(cooldown):
            cooldown = 0.0
        self.cooldown_remaining = max(0.0, cooldown)
        self._was_inside = bool(state.get("was_inside", False))
        self.last_outcome = ""
