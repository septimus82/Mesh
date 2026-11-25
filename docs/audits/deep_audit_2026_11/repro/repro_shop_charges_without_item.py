"""Repro: Vendor.handle_buy_request deducts gold, then ignores Inventory.add_item()'s False (stack full, non-stackable
item already owned, unknown item id) and reports a successful purchase.

Chain exercised: ShopPanel.confirm_purchase (the Enter key in the shop overlay) -> Vendor.handle_buy_request ->
GameStateController.add_counter / Inventory.add_item, with the real classes and the repo's items.json. Stock taken
from shipped content: scenes/door_interior.json (healing_potion, unlimited, 10g) and
packs/core_regions/scenes/Hollow Grove_hub.json + Ashen_hub.json (iron_sword, non-stackable).
Run from D:\\Games\\Mesh-audit with PYTHONPATH=D:\\Games\\Mesh-audit (items.json is read from the working folder).
"""
import os
import sys
from types import SimpleNamespace

os.chdir(r"D:\Games\Mesh-audit")
import engine  # noqa: E402
from engine.behaviours.vendor import Vendor  # noqa: E402
from engine.game_state_controller import GameStateController  # noqa: E402
from engine.inventory import get_or_create_inventory  # noqa: E402
from engine.ui_overlays.shop_panel import ShopPanel  # noqa: E402

print("engine from", engine.__file__)
toasts = []
window = SimpleNamespace(event_bus=None, ui_controller=None, width=800, height=600,
                         player_hud=SimpleNamespace(enqueue_toast=lambda m, **k: toasts.append(m)))
gs = GameStateController(window)
window.game_state_controller = gs
gs.add_counter("gold", 1000)
inv = get_or_create_inventory(gs.state.values)
entity = SimpleNamespace(name="shopkeeper", properties={})

failures = []


def buy(stock_entry, label):
    vendor = Vendor(entity, window, stock=[stock_entry])
    panel = ShopPanel(window)
    panel.open(vendor, vendor.stock)
    gold0, count0 = gs.get_counter("gold", 0), inv.get_count(stock_entry["item_id"])
    panel.confirm_purchase()
    gold1, count1 = gs.get_counter("gold", 0), inv.get_count(stock_entry["item_id"])
    print(f"{label}: gold {gold0}->{gold1}, {stock_entry['item_id']} {count0}->{count1}, toast={toasts[-1]!r}")
    if gold1 < gold0 and count1 == count0:
        failures.append(label)


# 1) potion stack full (max_stack 10 in items.json), door_interior vendor sells unlimited potions
inv.add_item("healing_potion", 10)
buy({"item_id": "healing_potion", "price": 10, "quantity": -1}, "potion with full stack")
# 2) non-stackable sword already owned (bought from Ashen hub), buy again at Hollow Grove hub
inv.add_item("iron_sword", 1)
buy({"item_id": "iron_sword", "price": 50, "quantity": 1}, "second iron_sword")
# 3) stock entry whose id isn't in items.json (typo in authored stock)
buy({"item_id": "iron_swrod", "price": 50, "quantity": 1}, "unknown item id")

print("DEFECT REPRODUCED:" if failures else "not reproduced", failures)
sys.exit(1 if failures else 0)
