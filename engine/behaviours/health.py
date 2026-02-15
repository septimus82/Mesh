"""Health behaviour for Mesh Engine."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

from engine.combat_constants import (
    EVENT_COMBAT_DAMAGE,
    EVENT_COMBAT_DEATH,
    EVENT_COMBAT_HIT,
    EVENT_COMBAT_MISS,
    EVENT_DAMAGE_APPLIED_ALIAS,
    KEY_AMOUNT,
    KEY_ATTACKER,
    KEY_SOURCE,
    KEY_TARGET,
    KEY_WAS_CRIT,
)
from engine.combat_model import AttackSpec, TargetState, resolve_attack
from engine.event_emit import emit_gameplay_event

from .base import Behaviour, ParamDef
from .registry import register_behaviour

if TYPE_CHECKING:  # pragma: no cover
    from arcade import Sprite

    from engine.game import GameWindow


@register_behaviour(
    "Health",
    description="Tracks hit points and signals when the entity dies.",
    config_fields=[
        {
            "name": "max_hp",
            "description": "Maximum health value",
            "type": "float",
            "default": 1.0,
        },
        {
            "name": "hp",
            "description": "Initial health value",
            "type": "float",
            "default": 1.0,
        },
        {
            "name": "invulnerable",
            "description": "Disable damage processing when true",
            "type": "bool",
            "default": False,
        },
    ],
)
class Health(Behaviour):
    """Simple HP container for an entity."""

    STATE_VERSION = 1

    PARAM_DEFS = {
        "max_hp": ParamDef(float, default=1.0, description="Maximum health value"),
        "hp": ParamDef(float, default=1.0, description="Initial health value"),
        "invulnerable": ParamDef(bool, default=False, description="Disable damage processing when true"),
    }

    def __init__(self, entity: "Sprite", window: "GameWindow", **config) -> None:
        merged = dict(getattr(entity, "mesh_entity_data", {}) or {})
        if config:
            merged.update(config)
        super().__init__(entity, window, **merged)

        cfg = getattr(window, "engine_config", None)
        self._use_player_stats = bool(getattr(cfg, "player_stats_enabled", True))

        stats = None
        try:
            if self._use_player_stats and getattr(entity, "mesh_tag", "") == "player":
                gs = getattr(window, "game_state_controller", None)
                if gs is not None:
                    stats = gs.get_player_stats()
        except Exception:
            stats = None

        default_max_hp = stats.get("max_hp") if stats else None
        self.max_hp = float(self.config.get("max_hp", default_max_hp if default_max_hp is not None else 1.0))
        if "hp" not in self._explicit_params:
            self.hp = float(self.max_hp)
            self.config["hp"] = self.hp
        else:
            self.hp = float(self.config.get("hp", self.max_hp))
        self.invulnerable = bool(self.config.get("invulnerable", False))
        self._dead: bool = False

    def update(self, dt: float) -> None:  # noqa: D401 ARG002
        """Health currently has no per-frame logic."""

    # ------------------------------------------------------------------ #
    # Save / Restore
    # ------------------------------------------------------------------ #

    def saveable_state(self) -> dict:
        """Return HP state for save serialization."""
        return {
            "version": self.STATE_VERSION,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "invulnerable": self.invulnerable,
            "dead": self._dead,
        }

    def restore_state(self, state: dict) -> None:
        """Restore HP state from save data."""
        self.max_hp = float(state.get("max_hp", self.max_hp))
        hp_raw = float(state.get("hp", self.max_hp))
        # Clamp to [0, max_hp]
        self.hp = max(0.0, min(hp_raw, self.max_hp))
        self.invulnerable = bool(state.get("invulnerable", False))
        self._dead = bool(state.get("dead", self.hp <= 0))

    def apply_damage(
        self,
        amount: float,
        *,
        source_entity: str | None = None,
        source_behaviour: str | None = None,
        attack_tags: tuple[str, ...] = (),
    ) -> None:
        """Apply incoming damage, respecting invulnerability and death state."""
        if self.invulnerable or self._dead:
            return
        incoming = float(amount)
        if self._use_player_stats and getattr(self.entity, "mesh_tag", "") == "player":
            try:
                gs = getattr(self.window, "game_state_controller", None)
                defense = float(gs.get_player_stats().get("defense", 0)) if gs is not None else 0.0
                incoming = max(0.0, incoming - defense)
            except Exception as exc:  # noqa: BLE001
                if not getattr(self, "_mesh_defense_error_logged", False):
                    print(f"[Mesh][Health] ERROR applying defense reduction: {exc}")
                    setattr(self, "_mesh_defense_error_logged", True)

        name = getattr(self.entity, "mesh_name", "<unnamed>")
        attacker_name = str(source_entity or "").strip() or "<unknown>"
        current_state = TargetState(
            hp=float(self.hp),
            max_hp=float(self.max_hp),
            dead=bool(self._dead),
            invulnerable=bool(self.invulnerable),
        )
        attack_spec = AttackSpec(
            source_id=attacker_name,
            target_id=name,
            base_damage=float(incoming),
            crit_chance=0.0,
            rng_stream="combat.default",
            tags=tuple(str(item) for item in attack_tags if str(item).strip()),
        )
        next_state, result = resolve_attack(attack_spec, current_state, rng=None)

        self.hp = float(next_state.hp)
        self._dead = bool(next_state.dead)
        print(f"[Mesh][Health] '{name}' took {result.applied_damage} damage -> {self.hp}/{self.max_hp}")

        payload = {
            KEY_ATTACKER: attacker_name,
            KEY_SOURCE: attacker_name,
            KEY_TARGET: name,
            KEY_AMOUNT: float(result.applied_damage),
            KEY_WAS_CRIT: bool(result.was_crit),
            "source_behaviour": str(source_behaviour or ""),
        }
        source_entity_id = str(getattr(self.entity, "mesh_id", "") or "")
        if result.applied_damage > 0:
            emit_gameplay_event(
                self.window,
                EVENT_COMBAT_HIT,
                payload,
                source_entity_id=source_entity_id,
                source_behaviour="Health",
            )
            emit_gameplay_event(
                self.window,
                EVENT_COMBAT_DAMAGE,
                payload,
                source_entity_id=source_entity_id,
                source_behaviour="Health",
            )
            emit_gameplay_event(
                self.window,
                EVENT_DAMAGE_APPLIED_ALIAS,
                payload,
                source_entity_id=source_entity_id,
                source_behaviour="Health",
            )
        else:
            emit_gameplay_event(
                self.window,
                EVENT_COMBAT_MISS,
                payload,
                source_entity_id=source_entity_id,
                source_behaviour="Health",
            )
        if result.target_dead:
            emit_gameplay_event(
                self.window,
                EVENT_COMBAT_DEATH,
                payload,
                source_entity_id=source_entity_id,
                source_behaviour="Health",
            )

        if result.target_dead:
            # self.window.on_entity_died(self.entity)
            emit_gameplay_event(
                self.window,
                "died",
                {"name": name, "entity": source_entity_id or name},
                source_entity_id=source_entity_id,
                source_behaviour="Health",
            )
            # Preserve legacy died event payload for old event_bus subscribers.
            legacy_bus = getattr(self.window, "event_bus", None)
            if legacy_bus is not None:
                emit_gameplay_event(
                    SimpleNamespace(event_bus=legacy_bus),
                    "died",
                    {"actor": self.entity, "name": name},
                )
            self.entity.remove_from_sprite_lists()
