"""S1-0 part D: Studio's "Shopkeeper" (Vendor) opens only on an ``open_shop`` bus event that nothing Studio authors sends.

    py -3.13 docs/s1/evidence/repro_shopkeeper_never_opens.py        (PYTHONPATH = this checkout)

Real hidden, muted, never-activated GameWindow (docs/s1/evidence/_hidden_game.py) in this checkout (whose
assets/data/items.json exists, so the Vendor can be built); the game's own key input and update loop.

1. A Shopkeeper authored the Studio way (project_ops.add_behaviour Vendor + set_behaviour_param stock): walk up, E.
2. The shipped merchants: Ashen_hub's and Hollow Grove_hub's (Dialogue + Vendor, nothing in the room sends open_shop),
   and Ridge Outpost_hub's, whose conversation has a choice with an ``open_shop`` event (hand-written JSON: Studio's
   set_choice cannot add an event) - E, Down, Down, E.
3. The Studio-authored Shopkeeper again, with ``open_shop`` sent on the bus (what a creator would have to arrange).

Exits 1 when the Studio-authored Shopkeeper does not open on E (1) or a shipped merchant can't be opened (2).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hidden_game import HERO, hidden_game, scene  # noqa: E402

defects: list[str] = []


def main() -> int:
    from engine import project_ops as ops

    shop_room = scene("Shop", dict(HERO, x=100, y=100),
                      {"id": "merchant", "name": "Merchant", "x": 100, "y": 150, "sprite": "assets/placeholder.png"})
    shop_room = ops.add_behaviour(shop_room, "merchant", "Vendor")
    shop_room = ops.set_behaviour_param(shop_room, "merchant", "Vendor", "stock",
                                        [{"item_id": "healing_potion", "price": 5, "quantity": 3}])
    with hidden_game({"shop": shop_room}) as (window, paths, _tmp):
        import engine.optional_arcade as optional_arcade

        K = optional_arcade.arcade.key
        sc = window.scene_controller
        window._allow_dispatch_event = True

        class _Panel:  # (the UI is rebuilt with each room: always the current shop panel)
            @property
            def visible(self) -> bool:
                return bool(window.ui_controller.shop_panel.visible)

            def close(self) -> None:
                window.ui_controller.shop_panel.close()

        panel = _Panel()

        def step(n: int = 1) -> None:
            for _ in range(n):
                window.dispatch_event("on_update", 1 / 60)

        def press(symbol: int) -> None:
            window.dispatch_event("on_key_press", symbol, 0)
            step()
            window.dispatch_event("on_key_release", symbol, 0)
            step(3)

        def enter(path: str) -> None:
            window.load_scene(path)
            window.main_menu_overlay.close()  # (a checkout boots into the project browser: closed, as Play does)
            step(3)

        def stand_by(name: str) -> None:
            target = next(s for s in sc.all_sprites if getattr(s, "mesh_name", "") == name)
            hero = sc._find_player_sprite()
            hero.center_x, hero.center_y = target.center_x, target.center_y - 40  # (placed beside it; walking is
            step(2)                                                              #  covered by the chain script)

        enter(paths["shop"])
        stand_by("Merchant")
        press(K.E)
        vendor = [type(b).__name__ for b in next(s for s in sc.all_sprites if s.mesh_name == "Merchant").mesh_behaviours_runtime]
        print(f"1. Studio-authored Shopkeeper {vendor}: E -> shop open: {panel.visible}")
        if not panel.visible:
            defects.append("a Studio-authored Shopkeeper does not open on E")
        window.emit_signal("open_shop")
        step(2)
        print(f"3. same Shopkeeper after an 'open_shop' event on the bus: shop open: {panel.visible}")
        panel.close()

        for path, merchant, keys in (("packs/core_regions/scenes/Ashen_hub.json", "Ashen_Merchant", (K.E,)),
                                     ("packs/core_regions/scenes/Hollow Grove_hub.json", "Hollow Grove_Merchant", (K.E,)),
                                     ("packs/core_regions/scenes/Ridge Outpost_hub.json", "RidgeMerchant",
                                      (K.E, K.DOWN, K.DOWN, K.E))):
            enter(path)
            stand_by(merchant)
            box = window.ui_controller.dialogue_box
            seen = []
            for key in keys:
                press(key)
                seen.append((box.get_current_entry() or {}).get("text", "")[:40] if box is not None else "")
                if panel.visible:
                    break
            for _ in range(3):  # any conversation that opened: closed with E (its lines end)
                if panel.visible:
                    break
                press(K.E)
            opened = panel.visible
            print(f"2. {Path(path).name} {merchant}: keys {len(keys)} -> shop open: {opened} | lines seen: {seen}")
            if not opened:
                defects.append(f"{Path(path).name}: {merchant}'s shop can't be opened")
            panel.close()
    if defects:
        print("DEFECTS:", "; ".join(defects))
        return 1
    print("not reproduced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
