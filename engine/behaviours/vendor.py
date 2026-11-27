from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..events import MeshEvent
from ..inventory import get_or_create_inventory, load_item_database
from .base import Behaviour, ParamDef
from .registry import register_behaviour

# #654 (owner decision D2). "interact": E opens the shop; when the object also talks (Dialogue), E starts the
# conversation and the shop opens once it completes (an "Only once" conversation already had: E opens the shop). "event":
# only listen_event opens it, e.g. a conversation choice that sends open_shop ("Let me see your wares").
OPEN_ON_HELP = ('"interact": E opens it; on an object that also talks, after the conversation. '
                '"event": only listen_event does (e.g. a conversation choice that sends it).')
_COMPLETED = frozenset({"advance_complete", "choice_complete"})  # (Dialogue's dialogue_finished reasons)


def _entity_id(entity: Any) -> Any:
    data = getattr(entity, "mesh_entity_data", None)
    return data.get("id") if isinstance(data, dict) else None


@register_behaviour(
    "Vendor",
    description="Sells items: E opens its shop (on an object that also talks, once the conversation ends), as does "
    "its listen_event.",
    config_fields=[
        {"name": "shop_id", "type": "string", "default": "", "description": "Logical id of this shop."},
        {"name": "currency_counter", "type": "string", "default": "gold", "description": "GameState counter used as currency."},
        {"name": "stock", "type": "array", "default": [], "description": "List of {item_id, price, quantity} entries."},
        {"name": "listen_event", "type": "string", "default": "open_shop", "description": "Mesh event to open this shop."},
        {"name": "open_on", "type": "string", "default": "interact", "description": OPEN_ON_HELP},
        {"name": "buy_sound", "type": "string", "default": "", "description": "Sound to play on successful purchase."},
        {"name": "fail_sound", "type": "string", "default": "", "description": "Sound to play on failed purchase."},
        {"name": "buy_rate", "type": "float", "default": 1.0, "description": "Multiplier for prices when buying."},
        {"name": "sell_rate", "type": "float", "default": 0.5, "description": "Multiplier for prices when selling to vendor."},
        {"name": "sell_enabled", "type": "bool", "default": True, "description": "If false, vendor will not buy items."},
        {"name": "sell_whitelist", "type": "array", "default": [], "description": "List of item_ids allowed to sell (if empty, allow all)."},
        {"name": "sell_blacklist", "type": "array", "default": [], "description": "List of item_ids vendor will never buy."},
    ],
)
class Vendor(Behaviour):
    PARAM_DEFS = {
        "shop_id": ParamDef(str, default="", description="Logical id of this shop."),
        "currency_counter": ParamDef(str, default="gold", description="GameState counter used as currency."),
        "stock": ParamDef(list, default=[], description="List of {item_id, price, quantity} entries."),
        "listen_event": ParamDef(str, default="open_shop", description="Mesh event to open this shop."),
        "open_on": ParamDef(str, default="interact", description=OPEN_ON_HELP),
        "buy_sound": ParamDef(str, default="", description="Sound to play on successful purchase."),
        "fail_sound": ParamDef(str, default="", description="Sound to play on failed purchase."),
        "buy_rate": ParamDef(float, default=1.0, description="Multiplier for prices when buying."),
        "sell_rate": ParamDef(float, default=0.5, description="Multiplier for prices when selling to vendor."),
        "sell_enabled": ParamDef(bool, default=True, description="If false, vendor will not buy items."),
        "sell_whitelist": ParamDef(list, default=[], description="Allowed item_ids to sell (empty=all)."),
        "sell_blacklist": ParamDef(list, default=[], description="Disallowed item_ids."),
    }

    def __init__(self, entity, window, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self.shop_id = str(self.config.get("shop_id", "") or "")
        self.currency_counter = str(self.config.get("currency_counter", "gold") or "gold")
        self.listen_event = str(self.config.get("listen_event", "open_shop") or "open_shop")
        self.open_on = str(self.config.get("open_on", "interact") or "interact").strip().lower()
        self._after_talk = False  # the conversation E started here: the shop opens when it completes
        self.buy_sound = str(self.config.get("buy_sound", "") or "")
        self.fail_sound = str(self.config.get("fail_sound", "") or "")
        self._buy_rate = float(self.config.get("buy_rate", 1.0) or 1.0)
        self._sell_rate = float(self.config.get("sell_rate", 0.5) or 0.5)
        self._sell_enabled = bool(self.config.get("sell_enabled", True))
        self._sell_whitelist = [str(x) for x in self.config.get("sell_whitelist", []) or []]
        self._sell_blacklist = [str(x) for x in self.config.get("sell_blacklist", []) or []]
        self._item_db = load_item_database()
        self.stock: list[dict[str, Any]] = [self._normalize_entry(entry) for entry in (self.config.get("stock") or [])]

    def _normalize_entry(self, entry: Any) -> dict[str, Any]:
        if not isinstance(entry, dict):
            return {}
        item_id = str(entry.get("item_id", "")).strip()
        price = int(entry.get("price", 0))
        qty = int(entry.get("quantity", -1))
        data = {"item_id": item_id, "price": price, "quantity": qty}
        item_def = self._item_db.get(item_id)
        if item_def is not None:
            data["name"] = item_def.name
        return data

    def _talk(self) -> Any:
        """The object's own conversation (its Dialogue), if it has one."""
        behaviours = getattr(self.entity, "mesh_behaviours_runtime", None) or []
        return next((b for b in behaviours if type(b).__name__ == "Dialogue"), None)

    def can_interact_with(self, actor: Any) -> bool:
        if self.open_on != "interact":
            return False
        talk = self._talk()
        # While the object has something to say (or is saying it), E is the conversation's (#654, D2).
        return talk is None or not talk.can_interact_with(actor)

    def on_interact(self, window: Any, actor: Any) -> None:  # noqa: ARG002
        self.open()

    def subscribed_event_types(self) -> frozenset[str] | None:
        if self.open_on != "interact":
            return frozenset({self.listen_event})
        return frozenset({self.listen_event, "dialogue_started", "dialogue_finished"})

    def on_event(self, event: MeshEvent) -> None:
        payload = event.payload or {}
        talk = self._talk() if self.open_on == "interact" else None
        if event.type == self.listen_event:
            if self._for_another_shop(payload):
                return
            if talk is not None and talk.talking:
                self._after_talk = True  # sent during the conversation (#663): the shop waits for its end
                return
            self.open()
        elif talk is not None and payload.get("entity") == talk.entity_name:
            if event.type == "dialogue_started":
                self._after_talk = payload.get("trigger") == "interact"
            elif self._after_talk:
                self._after_talk = False
                if payload.get("reason") in _COMPLETED:
                    self.open()

    def _for_another_shop(self, payload: dict[str, Any]) -> bool:
        """The event names another shop (its ``shop_id``), or was sent by another shopkeeper (an Interactable's
        ``target``, a conversation choice's ``entity``): that one opens, not every shop in the room (#654)."""
        wanted = str(payload.get("shop_id") or "")
        if wanted:
            return wanted != self.shop_id
        sender = payload.get("target") or payload.get("entity")
        if not sender or sender in (_entity_id(self.entity), getattr(self.entity, "mesh_name", None)):
            return False
        sprites = getattr(getattr(self.window, "scene_controller", None), "all_sprites", None) or []
        return any(sender in (_entity_id(s), getattr(s, "mesh_name", None))
                   and any(type(b).__name__ == "Vendor" for b in getattr(s, "mesh_behaviours_runtime", None) or [])
                   for s in sprites)

    def open(self) -> None:
        """Show this shop's stock (once: a second request while it's showing changes nothing)."""
        self._after_talk = False
        opener = getattr(self.window, "ui_controller", None)
        panel = getattr(opener, "shop_panel", None)
        if opener is None or (panel is not None and panel.visible and panel.vendor is self):
            return
        opener.open_shop(self, self.stock)

    # ------------------------------------------------------------------
    def handle_buy_request(self, item: dict[str, Any]) -> "VendorResult":
        item_id = str(item.get("item_id") or "")  # (one id for the check and the add: items.json ids are strings, #627)
        base_price = int(item.get("price", 0))
        price = int(base_price * self._buy_rate)
        if price < 0:
            price = 0
        quantity = int(item.get("quantity", -1))
        if not item_id:
            return self._result(False, "Purchase failed")
        gs = getattr(self.window, "game_state_controller", None)
        if gs is None:
            return self._result(False, "Purchase failed")
        if quantity == 0:
            return self._result(False, "Out of stock", item_id=item_id, qty=1)
        current_currency = gs.get_counter(self.currency_counter, 0)
        if current_currency < price:
            return self._result(False, "Not enough gold", item_id=item_id, qty=1)
        inv = get_or_create_inventory(gs.state.values)
        # Check before charging: a purchase the inventory refuses (unknown id, full stack, owned non-stackable)
        # must cost neither gold nor stock (#619).
        if not inv.can_add(item_id, 1):
            if self._item_db.get(item_id) is None:
                return self._result(False, f"Can't buy {item_id}: unknown item", item_id=item_id, qty=1)
            name = self._resolve_item_name(item_id, item)
            return self._result(False, f"Can't carry any more {name}", item_id=item_id, qty=1)

        # Deduct currency
        gs.add_counter(self.currency_counter, -price)
        # Add item to inventory
        inv.add_item(item_id, 1)
        # Decrement stock if finite
        if quantity > 0:
            item["quantity"] = quantity - 1
        name = self._resolve_item_name(item_id, item)
        return self._result(
            True,
            f"Bought {name} x1 (-{price}g)",
            gold_delta=-price,
            item_id=item_id,
            qty=1,
        )

    def handle_sell_request(self, item: dict[str, Any]) -> "VendorResult":
        """Sell one ``item_id`` for its stock price times ``sell_rate``; a refusal changes no item, gold or equipment.
        Selling the last owned copy of an equipped item unequips it; while another copy is owned the equipped one
        stays equipped (GameStateController._normalize_equipment, #757)."""
        if not self._sell_enabled:
            return self._result(False, "Cannot sell here")
        item_id = item.get("item_id")
        if not item_id:
            return self._result(False, "Sell failed")
        if self._sell_whitelist and item_id not in self._sell_whitelist:
            return self._result(False, "Cannot sell that item", item_id=str(item_id), qty=1)
        if item_id in self._sell_blacklist:
            return self._result(False, "Cannot sell that item", item_id=str(item_id), qty=1)
        gs = getattr(self.window, "game_state_controller", None)
        if gs is None:
            return self._result(False, "Sell failed", item_id=str(item_id), qty=1)
        inv = get_or_create_inventory(gs.state.values)
        if not inv.has_item(item_id, 1):
            return self._result(False, "You don't have that item", item_id=str(item_id), qty=1)
        base_price = self.get_base_price_for_item(item_id)
        if base_price <= 0:
            return self._result(False, "Cannot sell that item", item_id=str(item_id), qty=1)
        payout = max(0, int(base_price * self._sell_rate))
        if payout <= 0:
            return self._result(False, "Cannot sell that item", item_id=str(item_id), qty=1)
        inv.remove_item(item_id, 1)
        gs.add_counter(self.currency_counter, payout)
        name = self._resolve_item_name(str(item_id), item)
        return self._result(
            True,
            f"Sold {name} x1 (+{payout}g)",
            gold_delta=payout,
            item_id=str(item_id),
            qty=1,
        )

    def _result(
        self,
        ok: bool,
        message: str,
        *,
        gold_delta: int = 0,
        item_id: str | None = None,
        qty: int = 1,
    ) -> "VendorResult":
        self._play_sound(ok)
        return VendorResult(ok=bool(ok), message=str(message), gold_delta=int(gold_delta), item_id=item_id, qty=int(qty))

    def _play_sound(self, ok: bool) -> None:
        path = self.buy_sound if ok else self.fail_sound
        if not path or not hasattr(self.window, "audio"):
            return
        try:
            self.window.audio.play_sound(path)
        except Exception:
            return

    def _resolve_item_name(self, item_id: str, item: dict[str, Any] | None = None) -> str:
        if isinstance(item, dict):
            candidate = item.get("name")
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        item_def = self._item_db.get(item_id)
        return item_def.name if item_def is not None else item_id

    # ------------------------------------------------------------------
    def get_base_price_for_item(self, item_id: str) -> int:
        for entry in self.stock:
            if entry.get("item_id") == item_id:
                return int(entry.get("price", 0))
        return 0

    def get_buy_price(self, item_entry: dict[str, Any]) -> int:
        base = int(item_entry.get("price", 0))
        price = int(base * self._buy_rate)
        return max(0, price)

    def get_sellable_items(self, inventory_state: dict[str, Any]) -> list[dict[str, Any]]:
        if not self._sell_enabled:
            return []
        items: list[dict[str, Any]] = []
        inv = get_or_create_inventory(inventory_state)
        for item_id, count in inv.list_items():
            if count <= 0:
                continue
            if self._sell_whitelist and item_id not in self._sell_whitelist:
                continue
            if item_id in self._sell_blacklist:
                continue
            base_price = self.get_base_price_for_item(item_id)
            if base_price <= 0:
                continue
            sell_price = max(0, int(base_price * self._sell_rate))
            item_def = self._item_db.get(item_id)
            items.append(
                {
                    "item_id": item_id,
                    "name": item_def.name if item_def else item_id,
                    "price": sell_price,
                    "quantity": count,
                }
            )
        return items


@dataclass(frozen=True, slots=True)
class VendorResult:
    ok: bool
    message: str
    gold_delta: int = 0
    item_id: str | None = None
    qty: int = 1
