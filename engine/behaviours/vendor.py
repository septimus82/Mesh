from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..events import MeshEventBus
from ..inventory import get_or_create_inventory, load_item_database
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "Vendor",
    description="Handles shop stock and opens the shop UI on events.",
    config_fields=[
        {"name": "shop_id", "type": "string", "default": "", "description": "Logical id of this shop."},
        {"name": "currency_counter", "type": "string", "default": "gold", "description": "GameState counter used as currency."},
        {"name": "stock", "type": "array", "default": [], "description": "List of {item_id, price, quantity} entries."},
        {"name": "listen_event", "type": "string", "default": "open_shop", "description": "Mesh event to open this shop."},
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
        self.buy_sound = str(self.config.get("buy_sound", "") or "")
        self.fail_sound = str(self.config.get("fail_sound", "") or "")
        self._buy_rate = float(self.config.get("buy_rate", 1.0) or 1.0)
        self._sell_rate = float(self.config.get("sell_rate", 0.5) or 0.5)
        self._sell_enabled = bool(self.config.get("sell_enabled", True))
        self._sell_whitelist = [str(x) for x in self.config.get("sell_whitelist", []) or []]
        self._sell_blacklist = [str(x) for x in self.config.get("sell_blacklist", []) or []]
        self._bus = getattr(window, "event_bus", None)
        self._item_db = load_item_database()
        self.stock: list[dict[str, Any]] = [self._normalize_entry(entry) for entry in (self.config.get("stock") or [])]
        if isinstance(self._bus, MeshEventBus) and self.listen_event:
            try:
                self._bus.subscribe(self.listen_event, self._on_event)
            except Exception:
                pass

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

    def _on_event(self, event: Any) -> None:
        opener = getattr(self.window, "ui_controller", None)
        if opener is None:
            return
        opener.open_shop(self, self.stock)

    # ------------------------------------------------------------------
    def handle_buy_request(self, item: dict[str, Any]) -> "VendorResult":
        item_id = item.get("item_id")
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
            return self._result(False, "Out of stock", item_id=str(item_id), qty=1)
        current_currency = gs.get_counter(self.currency_counter, 0)
        if current_currency < price:
            return self._result(False, "Not enough gold", item_id=str(item_id), qty=1)

        # Deduct currency
        gs.add_counter(self.currency_counter, -price)
        # Add item to inventory
        inv = get_or_create_inventory(gs.state.values)
        inv.add_item(item_id, 1)
        # Decrement stock if finite
        if quantity > 0:
            item["quantity"] = quantity - 1
        name = self._resolve_item_name(str(item_id), item)
        return self._result(
            True,
            f"Bought {name} x1 (-{price}g)",
            gold_delta=-price,
            item_id=str(item_id),
            qty=1,
        )

    def handle_sell_request(self, item: dict[str, Any]) -> "VendorResult":
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
