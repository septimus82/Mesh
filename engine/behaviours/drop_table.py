"""DropTable behaviour: rolls configured loot on events."""

from __future__ import annotations

import random
from typing import Any, Callable

from ..inventory import get_or_create_inventory, load_item_database
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "DropTable",
    description="Rolls item/gold drops when a configured event fires.",
    config_fields=[
        {"name": "listen_event", "type": "string", "default": "died", "description": "Event name to listen for."},
        {"name": "drops", "type": "array", "default": [], "description": "List of drop entries."},
        {"name": "match_self", "type": "bool", "default": True, "description": "If true, require actor/entity to be this sprite."},
        {"name": "seed", "type": "int", "default": None, "description": "Optional RNG seed for deterministic rolls."},
    ],
)
class DropTable(Behaviour):
    PARAM_DEFS = {
        "listen_event": ParamDef(str, default="died", description="Event name to listen for."),
        "drops": ParamDef(list, default=[], description="List of drop entries."),
        "match_self": ParamDef(bool, default=True, description="Require actor/entity to match this sprite."),
        "seed": ParamDef(int, default=-1, description="Optional RNG seed for deterministic tests."),
    }

    def __init__(self, entity: Any, window: Any, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self.listen_event = str(self.config.get("listen_event", "died") or "died")
        self.match_self = bool(self.config.get("match_self", True))

        seed = self.config.get("seed")
        if seed == -1:
            seed = None
        self._rng = random.Random(seed)

        self._unsubscribe: Callable[[], None] | None
        self._unsubscribe = None
        raw_drops = self.config.get("drops") or []
        normalized: list[dict[str, Any]] = []
        for entry in raw_drops:
            drop = self._normalize_drop(entry)
            if drop:
                normalized.append(drop)
        self.drops = normalized
        self._bus = getattr(window, "event_bus", None)
        if self._bus is not None and self.listen_event:
            try:
                self._unsubscribe = self._bus.subscribe(self.listen_event, self._on_event)
            except Exception:
                self._unsubscribe = None
        else:
            self._unsubscribe = None

    def _normalize_drop(self, entry: Any) -> dict[str, Any]:
        if not isinstance(entry, dict):
            return {}
        chance = float(entry.get("chance", 1.0) or 1.0)
        min_q = int(entry.get("min_quantity", entry.get("quantity", 1)) or 1)
        max_q = int(entry.get("max_quantity", min_q) or min_q)
        if max_q < min_q:
            max_q = min_q
        item_id = entry.get("item_id")
        gold = entry.get("gold")
        return {
            "item_id": str(item_id).strip() if item_id else None,
            "gold": int(gold) if gold is not None else None,
            "chance": max(0.0, min(1.0, chance)),
            "min_quantity": min_q,
            "max_quantity": max_q,
        }

    def _on_event(self, event: Any) -> None:
        payload_obj = getattr(event, "payload", None)
        payload: dict[str, Any] = payload_obj if isinstance(payload_obj, dict) else {}
        if self.match_self:
            actor = payload.get("actor") or payload.get("entity") or payload.get("target")
            if actor is not None and actor is not self.entity:
                return

        if not self.drops:
            return

        for drop in self.drops:
            if not drop:
                continue
            if not self._roll(drop["chance"]):
                continue
            qty = self._rng.randint(drop["min_quantity"], drop["max_quantity"])
            if qty <= 0:
                continue
            self._apply_drop(drop, qty)

    def _roll(self, chance: float) -> bool:
        if chance >= 1.0:
            return True
        if chance <= 0.0:
            return False
        return self._rng.random() <= chance

    def _apply_drop(self, drop: dict[str, Any], qty: int) -> None:
        gs = getattr(self.window, "game_state_controller", None)
        if gs is None:
            return
        item_id = drop.get("item_id")
        gold = drop.get("gold")
        if item_id:
            try:
                db = load_item_database()
                item_def = db.get(item_id)
                label = item_def.name if item_def is not None else item_id
            except Exception:
                label = item_id
            inv = get_or_create_inventory(gs.state.values)
            inv.add_item(item_id, qty)
            self._log(f"Loot: +{qty}x {label}")
        if gold is not None:
            gold_total = int(gold) * max(1, qty)
            gs.add_counter("gold", gold_total)
            self._log(f"Loot: +{gold_total} gold")

    def _log(self, message: str) -> None:
        logger = getattr(self.window, "console_log", None)
        if callable(logger):
            try:
                logger(message)
                return
            except Exception as exc:  # noqa: BLE001  # REASON: HUD console hooks are optional and loot flow must continue
                if not getattr(self, "_mesh_console_log_error_logged", False):
                    print(f"[Mesh][DropTable] ERROR calling console_log: {exc}")
                    setattr(self, "_mesh_console_log_error_logged", True)
        print(f"[Loot] {message}")

    def on_destroy(self) -> None:
        unsubscribe = self._unsubscribe
        if unsubscribe is not None:
            try:
                unsubscribe()
            except Exception as exc:  # noqa: BLE001  # REASON: event-bus unsubscribe callbacks must not break teardown
                if not getattr(self, "_mesh_unsubscribe_error_logged", False):
                    print(f"[Mesh][DropTable] ERROR running unsubscribe handler: {exc}")
                    setattr(self, "_mesh_unsubscribe_error_logged", True)
        on_destroy = getattr(super(), "on_destroy", None)
        if callable(on_destroy):
            on_destroy()
