"""DropTable behaviour: rolls configured loot on events."""

from __future__ import annotations

import random
from typing import Any, Callable

from ..inventory import get_or_create_inventory, load_item_database
from ..logging_tools import get_logger
from ..scene_runtime import room_memory
from .base import Behaviour, ParamDef
from .registry import register_behaviour

_LOG = get_logger("engine.behaviours.drop_table")
LEFT_TAG = "left_loot"  # a remembered drop lying on the ground (its DropTable's fact ``left``)


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
    """Grants its rolled items and gold. What the inventory can't take is left on the ground where its entity was, as
    a pickup, never lost (#627, owner decision D7); the fact ``left`` keeps it there across re-entry and saves (it is
    laid again as the room loads, ``lay_remembered_loot``) until it is picked up. On an entity without its own
    authored id the loot is not remembered: it is gone once the player leaves the room."""

    FACT_FIELDS = ("left",)  # {"x", "y", "elevation"[, "floor"], "items": {item id: count}}, or None: nothing left

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

        refused: dict[str, int] = {}
        for drop in self.drops:
            if not drop:
                continue
            if not self._roll(drop["chance"]):
                continue
            qty = self._rng.randint(drop["min_quantity"], drop["max_quantity"])
            if qty <= 0:
                continue
            left = self._apply_drop(drop, qty)
            if left:
                refused[drop["item_id"]] = refused.get(drop["item_id"], 0) + left
        if refused:
            at = getattr(self, "_mesh_fact_key", None)
            spot = _spot_of(self.entity)
            if at is not None:
                items = _left(self.window, at)
                for item_id, count in refused.items():
                    items[item_id] = items.get(item_id, 0) + count
                room_memory.write_fact(self.window, at, "DropTable", "left", {**spot, "items": items})
            for item_id, count in refused.items():
                _lay(self.window, at, spot, item_id, count)

    def _roll(self, chance: float) -> bool:
        if chance >= 1.0:
            return True
        if chance <= 0.0:
            return False
        return self._rng.random() <= chance

    def _apply_drop(self, drop: dict[str, Any], qty: int) -> int:
        """Grant one rolled drop; returns how many of its item the inventory refused (to leave on the ground)."""
        gs = getattr(self.window, "game_state_controller", None)
        if gs is None:
            return 0
        left = 0
        item_id = drop.get("item_id")
        gold = drop.get("gold")
        if item_id:
            item_def = load_item_database().get(item_id)
            label = item_def.name if item_def is not None else item_id
            inv = get_or_create_inventory(gs.state.values)
            refusal = inv.refusal(item_id, qty)  # (asked before adding: add_item takes what fits)
            before = inv.get_count(item_id)
            inv.add_item(item_id, qty)
            granted = inv.get_count(item_id) - before
            if granted > 0:
                self._log(f"Loot: +{granted}x {label}")
            if refusal is not None:  # never silently (#652/#627, owner decision D7); the gold below still comes
                _LOG.warning("Drop of %sx %s refused (%s granted): %s", qty, item_id, granted, refusal)
                self._log(f"Loot: {qty - granted}x {label} left behind: {refusal}")
                if item_def is not None:  # (on the ground to take once there's room; an unknown id never could be)
                    left = qty - granted
                hud = getattr(self.window, "player_hud", None)
                enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
                # The player is told about a full bag; an unknown id is the creator's to fix (the log and console).
                if item_def is not None and callable(enqueue):
                    enqueue(refusal, seconds=2.0)
        if gold is not None:
            gold_total = int(gold) * max(1, qty)
            gs.add_counter("gold", gold_total)
            self._log(f"Loot: +{gold_total} gold")
        return left

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


def _fact(window: Any, room: str, entity_id: str) -> dict[str, Any]:
    """The fact ``left`` of the DropTable on ``entity_id`` in ``room`` ({} when there is none)."""
    own = room_memory.room_facts(window, room).get(entity_id)
    kind = own.get("DropTable") if isinstance(own, dict) else None
    left = kind.get("left") if isinstance(kind, dict) else None
    return left if isinstance(left, dict) and isinstance(left.get("items"), dict) else {}


def _left(window: Any, at: tuple[str, str, Any]) -> dict[str, int]:
    """What the DropTable at ``at`` (room, entity id, session) has left on the ground: {item id: count}."""
    return dict(_fact(window, at[0], at[1]).get("items", {}))


SPOT = ("x", "y", "elevation", "floor")


def _spot_of(entity: Any) -> dict[str, Any]:
    """Where ``entity`` stands: its centre (px), its HD-2D elevation (px: what same_level compares, so the loot is on
    the level it fell on: a deck, a platform, a hill) and the floor it stands on (``mesh_hd2d_floor``) if it has one."""
    data = getattr(entity, "mesh_entity_data", None)
    z = data.get("elevation", 0.0) if isinstance(data, dict) else 0.0
    spot: dict[str, Any] = {
        "x": float(entity.center_x),
        "y": float(entity.center_y),
        "elevation": float(z) if isinstance(z, (int, float)) and not isinstance(z, bool) else 0.0,
    }
    floor = getattr(entity, "mesh_hd2d_floor", None)
    if isinstance(floor, str):
        spot["floor"] = floor
    return spot


def _lay(window: Any, at: tuple[str, str, Any] | None, spot: dict[str, Any], item_id: str, count: int) -> None:
    """Put ``count`` of ``item_id`` on the ground at ``spot`` (``_spot_of``): a pickup ("Can be picked up") with the
    item's icon. Taking it takes it off the fact ``left`` of the DropTable at ``at`` (None: not remembered)."""
    controller = getattr(window, "scene_controller", None)
    item = load_item_database().get(item_id)
    if controller is None or item is None:
        return
    sprite = controller._create_sprite(
        {
            "name": item.name,
            "x": float(spot["x"]),
            "y": float(spot["y"]),
            "elevation": float(spot.get("elevation", 0.0)),
            "sprite": item.icon or "assets/placeholder.png",
            "scale": 0.5,
            "layer": "entities",
            "behaviours": ["PickupCollectible"],
            "behaviour_config": {"PickupCollectible": {"item_id": item_id, "item_amount": count}},
            **({"tags": [LEFT_TAG]} if at is not None else {}),  # (a save carries it too: lay_remembered_loot)
        }
    )
    if sprite is None:
        return
    if isinstance(spot.get("floor"), str):
        sprite.mesh_hd2d_floor = spot["floor"]
    controller.entities.enqueue_spawn(sprite, layer_name="entities", is_solid=False)
    controller.entities.apply_pending_ops(controller, stage="immediate")
    if at is None:
        return

    def taken() -> None:
        items = _left(window, at)
        items[item_id] = items.get(item_id, 0) - count
        items = {k: v for k, v in items.items() if v > 0}
        room_memory.write_fact(window, at, "DropTable", "left", {**spot, "items": items} if items else None)

    # ponytail: a runtime callback; a pile whose behaviours are rebuilt (the console's rebuild, dev only) no longer
    # clears the fact when taken and comes back on re-entry. Derive the link from entity data if that ever matters.
    for behaviour in sprite.mesh_behaviours_runtime:
        if type(behaviour).__name__ == "PickupCollectible":
            behaviour.on_taken = taken


def lay_remembered_loot(controller: Any) -> None:
    """Lay again what defeated enemies left on the ground in the room ``controller`` is loading (its DropTables' fact
    ``left``): the room loader calls this once its objects are made. A save carries the remembered loot it was made
    with as objects of its own (``engine.scene_runtime.saved_world``): those are replaced by the facts' loot."""
    for sprite in list(controller.all_sprites):  # a loaded save's copies of it: the facts say what is still there
        if LEFT_TAG in (getattr(sprite, "mesh_tags", None) or ()):
            sprite.remove_from_sprite_lists()
    room = room_memory.room_key(getattr(controller, "room_path", None))
    # Every enemy's, also one whose id the room no longer has (renamed or deleted since): its loot is still the
    # player's. One fact per id, so each pile is laid once; taking it clears that id's fact.
    for entity_id in room_memory.room_facts(controller.window, room):
        left = _fact(controller.window, room, entity_id)
        if not left:
            continue
        at = (room, entity_id, getattr(controller, "_room_session", None))
        spot = {key: left[key] for key in SPOT if key in left}
        for item_id, count in left["items"].items():
            _lay(controller.window, at, {"x": 0.0, "y": 0.0, **spot}, str(item_id), int(count))
