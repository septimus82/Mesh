"""#619: a shop purchase the inventory refuses must cost neither gold nor stock, and must not toast "Bought".

Driven through the real runtime path: ShopPanel.confirm_purchase (the shop overlay's Enter) -> Vendor.handle_buy_request
-> GameStateController + Inventory, with the repo's real assets/data/items.json (healing_potion stacks to 10,
iron_sword is non-stackable), as in the shipped door_interior / core_regions hub shops.
"""

from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

import engine.inventory as inventory_module
from engine.behaviours.vendor import Vendor
from engine.game_state_controller import GameStateController
from engine.inventory import ItemDatabase, ItemDefinition, get_or_create_inventory
from engine.ui_overlays.shop_panel import ShopPanel
from tests._typing import as_any

pytestmark = pytest.mark.integration  # reads the repo's items.json and perks

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def shop(monkeypatch):
    # The real item database, whatever the cwd; the previous cache comes back at teardown.
    monkeypatch.setattr(inventory_module, "_ITEM_DB_CACHE", ItemDatabase.load(REPO_ROOT))
    toasts: list[str] = []
    sounds: list[str] = []
    window = types.SimpleNamespace(
        event_bus=None,
        ui_controller=None,
        width=800,
        height=600,
        player_hud=types.SimpleNamespace(enqueue_toast=lambda message, **_: toasts.append(message)),
        audio=types.SimpleNamespace(play_sound=sounds.append),
    )
    window.game_state_controller = GameStateController(as_any(window))
    window.game_state_controller.set_counter("gold", 1000)

    def buy(stock_entry: dict, times: int = 1) -> dict:
        vendor = Vendor(
            types.SimpleNamespace(name="shopkeeper", properties={}),
            window,
            stock=[stock_entry],
            buy_sound="buy.wav",
            fail_sound="fail.wav",
        )
        panel = ShopPanel(as_any(window))
        panel.open(vendor, vendor.stock)
        for _ in range(times):
            panel.confirm_purchase()
        return vendor.stock[0]

    gs = window.game_state_controller
    return types.SimpleNamespace(window=window, gs=gs, inv=get_or_create_inventory(gs.state.values), toasts=toasts, sounds=sounds, buy=buy)


def _assert_refused(shop, entry: dict, item_id: str, count: int, quantity: int, message: str) -> None:
    assert shop.gs.get_counter("gold") == 1000
    assert shop.inv.get_count(item_id) == count
    assert entry["quantity"] == quantity
    assert shop.toasts == [message]
    assert shop.sounds == ["fail.wav"]


def test_full_stack_costs_nothing(shop):
    shop.inv.add_item("healing_potion", 10)
    entry = shop.buy({"item_id": "healing_potion", "price": 10, "quantity": 5})
    _assert_refused(shop, entry, "healing_potion", 10, 5, "Can't carry any more Healing Potion")


def test_full_stack_unlimited_stock_stays_unlimited(shop):
    shop.inv.add_item("healing_potion", 10)
    entry = shop.buy({"item_id": "healing_potion", "price": 10, "quantity": -1})  # door_interior's potions
    _assert_refused(shop, entry, "healing_potion", 10, -1, "Can't carry any more Healing Potion")


def test_owned_non_stackable_costs_nothing(shop):
    shop.inv.add_item("iron_sword", 1)
    entry = shop.buy({"item_id": "iron_sword", "price": 50, "quantity": 1})
    _assert_refused(shop, entry, "iron_sword", 1, 1, "Can't carry any more Iron Sword")


def test_unknown_item_id_costs_nothing(shop):
    entry = shop.buy({"item_id": "iron_swrod", "price": 50, "quantity": 1})
    _assert_refused(shop, entry, "iron_swrod", 0, 1, "Can't buy iron_swrod: unknown item")
    assert "iron_swrod" not in shop.inv.state_bucket["items"]


def test_normal_purchase_still_works(shop):
    entry = shop.buy({"item_id": "iron_sword", "price": 50, "quantity": 2})
    assert shop.gs.get_counter("gold") == 950
    assert shop.inv.get_count("iron_sword") == 1
    assert entry["quantity"] == 1
    assert shop.toasts == ["Bought Iron Sword x1 (-50g)"]
    assert shop.sounds == ["buy.wav"]


def test_last_free_slot_buys_then_refuses(shop):
    shop.inv.add_item("healing_potion", 9)
    entry = shop.buy({"item_id": "healing_potion", "price": 10, "quantity": 3}, times=2)
    assert (shop.gs.get_counter("gold"), shop.inv.get_count("healing_potion"), entry["quantity"]) == (990, 10, 2)
    assert shop.toasts == ["Bought Healing Potion x1 (-10g)", "Can't carry any more Healing Potion"]
    assert shop.sounds == ["buy.wav", "fail.wav"]


def test_save_round_trip_after_refused_purchase(shop):
    shop.buy({"item_id": "iron_sword", "price": 50, "quantity": 2}, times=2)  # the second is refused: owned
    saved = json.loads(json.dumps(shop.gs.export_state()))

    restored = GameStateController(as_any(types.SimpleNamespace()))
    restored.import_state(saved)
    assert restored.get_counter("gold") == 950
    assert get_or_create_inventory(restored.state.values).get_count("iron_sword") == 1
    assert saved["values"]["inventory"] == {"items": {"iron_sword": 1}}


def _own_items(monkeypatch, *items: ItemDefinition) -> None:
    monkeypatch.setattr(inventory_module, "_ITEM_DB_CACHE", ItemDatabase({item.id: item for item in items}))


def test_a_non_stackable_item_is_one_per_inventory_whatever_its_max_stack(shop, monkeypatch):
    """#627 (mutant O5 of #625): ``stackable: false`` wins over a ``max_stack`` above 1."""
    _own_items(monkeypatch, ItemDefinition("lantern", "Lantern", "", None, False, 5, [], {}))
    entry = shop.buy({"item_id": "lantern", "price": 10, "quantity": 3}, times=2)
    assert (shop.gs.get_counter("gold"), shop.inv.get_count("lantern"), entry["quantity"]) == (990, 1, 2)
    assert shop.toasts == ["Bought Lantern x1 (-10g)", "Can't carry any more Lantern"]


def test_a_non_string_item_id_is_checked_and_added_as_the_same_id(shop, monkeypatch):
    """#627: a direct caller's ``42`` is the database's ``"42"`` for both the check and the add, so a purchase never
    charges for an item it didn't add."""
    _own_items(monkeypatch, ItemDefinition("42", "Lucky Coin", "", None, True, 9, [], {}))
    vendor = Vendor(types.SimpleNamespace(name="shopkeeper", properties={}), shop.window, stock=[])
    result = vendor.handle_buy_request({"item_id": 42, "price": 10, "quantity": 3})
    assert result.ok and (shop.gs.get_counter("gold"), shop.inv.get_count("42")) == (990, 1)
