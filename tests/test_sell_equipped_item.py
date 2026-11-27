"""Programme finding 4: selling an equipped item left it equipped (slot filled, stat bonus kept).

Equipment is never more than the inventory (``GameStateController._normalize_equipment``): each filled slot needs an
owned copy, so a sale (or any other removal) of the last copy unequips it, and its bonus goes with it; while another
copy is owned the equipped one stays equipped. A save whose equipped item is no longer owned loads unequipped.

A real hidden GameWindow on a small project: its Vendor is the scene's own, sold to through the shop panel's sell
mode (Enter), and saves go through the window's SaveManager. Hits aren't asserted: Combat adds the weapon's damage
again on top of the stats (a separate item of #751), so the authority here is ``get_equipment``/``get_player_stats``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import engine.inventory as inventory_module
import engine.optional_arcade as optional_arcade
from engine.inventory import ItemDatabase, get_or_create_inventory
from engine.save_manager import SaveManager
from tests._game_window_live import dispose_game_window

pytestmark = [pytest.mark.integration,  # (a project in a temporary folder; hidden game windows)
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

REPO = Path(__file__).resolve().parents[1]
KNIFE = {"id": "throwing_knife", "name": "Throwing Knife", "description": "", "stackable": True, "max_stack": 5,
         "tags": ["equipment", "weapon"], "effects": {"damage": 5}}  # (a weapon that stacks: the duplicates rule)
STOCK = [{"item_id": "rusty_sword", "price": 10, "quantity": -1},
         {"item_id": "throwing_knife", "price": 4, "quantity": -1},
         {"item_id": "healing_potion", "price": 6, "quantity": -1}]


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "game"
    (root / "scenes").mkdir(parents=True)
    (root / "assets" / "data").mkdir(parents=True)
    items = json.loads((REPO / "assets" / "data" / "items.json").read_text(encoding="utf-8"))
    items["items"].append(KNIFE)
    (root / "assets" / "data" / "items.json").write_text(json.dumps(items), encoding="utf-8")
    config = {"title": "Sell test", "game_id": "sell-test-0000", "start_scene": "scenes/start.json",
              "width": 320, "height": 200, "vsync": False, "fullscreen": False, "main_menu_scene": None}
    (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
    smith = {"id": "smith", "name": "Smith", "x": 64.0, "y": 64.0, "behaviours": ["Vendor"],
             "behaviour_config": {"Vendor": {"stock": STOCK, "sell_blacklist": ["healing_potion"]}}}
    (root / "scenes" / "start.json").write_text(json.dumps(
        {"name": "Start", "schema_version": 1, "version": 1, "layers": [], "entities": [smith]}), encoding="utf-8")
    return root.resolve()


class Game:
    def __init__(self, project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from engine.config import load_config
        from engine.game import GameWindow

        monkeypatch.delenv("MESH_LEGACY_EDITOR", raising=False)
        config = load_config(str(project / "config.json"))
        self.window = GameWindow(width=320, height=200, title=config.title, vsync=False, config=config)
        monkeypatch.setattr(inventory_module, "_ITEM_DB_CACHE", ItemDatabase.load(project))  # (this game's items)
        self.window.load_scene(str(project / "scenes" / "start.json"))
        menu = getattr(self.window, "main_menu_overlay", None)
        if menu is not None and menu.visible:
            menu.close()
        self.window.save_manager = SaveManager(self.window, save_dir=project / "saves")
        self.gs = self.window.game_state_controller

    @property
    def inv(self) -> Any:
        return get_or_create_inventory(self.gs.state.values)

    def vendor(self) -> Any:
        sprites = self.window.scene_controller.all_sprites
        return next(b for s in sprites for b in getattr(s, "mesh_behaviours_runtime", None) or []
                    if type(b).__name__ == "Vendor")

    def sell(self, item_id: str) -> None:
        """The shop's SELL mode: the cursor on ``item_id``'s row, Enter."""
        panel = self.window.ui_controller.shop_panel
        vendor = self.vendor()
        panel.open(vendor, vendor.stock, mode="sell")
        rows = [row["item_id"] for row in panel._items]
        if item_id in rows:
            panel.move_cursor(rows.index(item_id))
        else:  # (not on the list: the sale the panel would send for a stale row)
            panel._items = [{"item_id": item_id, "price": 1, "quantity": 1}]
        panel.confirm_purchase()
        panel.close()

    def state(self) -> tuple[Any, float, float, dict[str, int]]:
        stats = self.gs.get_player_stats()
        return (self.gs.get_equipment()["weapon"], stats["attack"], self.gs.get_counter("gold", 0),
                dict(self.inv.list_items()))

    def close(self) -> None:
        dispose_game_window(self.window)


@pytest.fixture
def game(project: Path, monkeypatch: pytest.MonkeyPatch):
    made: list[Game] = []

    def start() -> Game:
        made.append(Game(project, monkeypatch))
        return made[-1]

    yield start
    for g in made:
        g.close()


def test_selling_the_equipped_sword_unequips_it_and_drops_its_bonus(game) -> None:
    g = game()
    assert g.gs.get_player_stats()["attack"] == 5
    g.inv.add_item("rusty_sword", 1)
    assert g.gs.equip_item("rusty_sword")["ok"]
    assert g.state() == ("rusty_sword", 10, 0, {"rusty_sword": 1})
    g.sell("rusty_sword")
    assert g.state() == (None, 5, 5, {})
    assert g.gs.export_state()["equipment"]["weapon"] is None


def test_selling_one_of_two_copies_keeps_the_equipped_one(game) -> None:
    g = game()
    g.inv.add_item("throwing_knife", 2)
    assert g.gs.equip_item("throwing_knife")["ok"]
    g.sell("throwing_knife")
    assert g.state() == ("throwing_knife", 10, 2, {"throwing_knife": 1})
    g.sell("throwing_knife")
    assert g.state() == (None, 5, 4, {})


@pytest.mark.parametrize("case", ["not_owned", "refused", "not_stocked", "zero_count", "negative_count", "disabled"])
def test_a_failed_sale_changes_nothing(game, case: str) -> None:
    g = game()
    g.inv.add_item("rusty_sword", 1)
    g.inv.add_item("healing_potion", 3)
    assert g.gs.equip_item("rusty_sword")["ok"]
    g.gs.set_counter("gold", 7)
    items = g.inv.state_bucket["items"]
    target = {"not_owned": "throwing_knife", "refused": "healing_potion", "not_stocked": "iron_sword",
              "zero_count": "throwing_knife", "negative_count": "throwing_knife", "disabled": "rusty_sword"}[case]
    if case == "not_stocked":
        items["iron_sword"] = 1
    if case in ("zero_count", "negative_count"):
        items["throwing_knife"] = 0 if case == "zero_count" else -2
    if case == "disabled":
        g.vendor()._sell_enabled = False
    before = (g.gs.get_equipment(), g.gs.get_player_stats()["attack"], dict(items))
    g.sell(target)
    assert (g.gs.get_equipment(), g.gs.get_player_stats()["attack"], dict(items)) == before
    assert g.gs.get_counter("gold", 0) == 7


def test_save_then_load_in_a_fresh_window_keeps_the_sale(game) -> None:
    g = game()
    g.inv.add_item("rusty_sword", 1)
    g.inv.add_item("throwing_knife", 2)
    assert g.gs.equip_item("rusty_sword")["ok"]
    g.sell("rusty_sword")
    assert g.window.save_manager.save_game("slot1")
    saved = json.loads((g.window.save_manager.get_save_path("slot1")).read_text(encoding="utf-8"))
    assert saved["game_state"]["equipment"]["weapon"] is None
    g.close()
    fresh = game()
    assert fresh.window.save_manager.load_game("slot1")
    assert fresh.state() == (None, 5, 5, {"throwing_knife": 2})
    assert fresh.gs.equip_item("throwing_knife")["ok"]
    assert fresh.gs.get_player_stats()["attack"] == 10


def test_an_old_save_with_an_equipped_item_no_longer_owned_loads_unequipped(game) -> None:
    g = game()
    g.inv.add_item("rusty_sword", 1)
    assert g.gs.equip_item("rusty_sword")["ok"]
    assert g.window.save_manager.save_game("old")
    g.close()
    path = g.window.save_manager.get_save_path("old")
    data = json.loads(path.read_text(encoding="utf-8"))  # as a save made before the fix: sold, still equipped
    for block in (data["game_state"]["values"], data["game_state"]["variables"]):
        block["inventory"]["items"].pop("rusty_sword")
    assert data["game_state"]["equipment"]["weapon"] == "rusty_sword"
    path.write_text(json.dumps(data), encoding="utf-8")
    on_disk = path.read_bytes()
    fresh = game()
    assert fresh.window.save_manager.load_game("old")
    assert fresh.state() == (None, 5, 0, {})
    assert path.read_bytes() == on_disk  # (repaired in the game, never by rewriting the player's file)


def test_any_other_removal_of_the_last_copy_unequips_too(game) -> None:
    """The console's ``inventory remove``/``clear`` and using an item remove through ``Inventory`` with no word to the
    game state: the equipment still follows (one rule, where equipment is read)."""
    g = game()
    g.inv.add_item("rusty_sword", 1)
    assert g.gs.equip_item("rusty_sword")["ok"]
    g.inv.remove_item("rusty_sword", 1)
    assert g.state() == (None, 5, 0, {})
