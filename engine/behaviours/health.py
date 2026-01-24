"""Health behaviour for Mesh Engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

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

    def apply_damage(self, amount: float) -> None:
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

        self.hp -= incoming
        name = getattr(self.entity, "mesh_name", "<unnamed>")
        print(f"[Mesh][Health] '{name}' took {incoming} damage -> {self.hp}/{self.max_hp}")

        if self.hp <= 0 and not self._dead:
            self._dead = True
            # self.window.on_entity_died(self.entity)
            self.window.event_bus.emit("died", actor=self.entity, name=name)
            self.entity.remove_from_sprite_lists()
