"""S1v play driver: run GAME/main.py as the game does, with GameWindow.run replaced by a scripted drive.

usage: py -3.13 s1v_play.py GAME MODE HIDDEN_WINDOWS_PY LAYOUT_JSON [ITEMS_JSON]
MODE: dev | export. Hidden, never-activated window; pyglet audio = silent; inputs via window.dispatch_event.
ITEMS_JSON (optional): after phase G the file is copied to GAME/assets/data/items.json (the only route a creator
has: by hand) and the start room is re-entered to test items/shops with an item list.
"""
import importlib.util
import json
import runpy
import shutil
import sys
from pathlib import Path

GAME, MODE, HIDDEN, LAYOUT = Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4])
ITEMS = Path(sys.argv[5]) if len(sys.argv) > 5 else None
if MODE == "export":
    sys.path.insert(0, str(GAME))
import pyglet  # noqa: E402

pyglet.options["audio"] = ("silent",)
spec = importlib.util.spec_from_file_location("hidden_windows", HIDDEN)
hw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hw)
hw.no_activate()
import engine.optional_arcade as optional_arcade  # noqa: E402

arcade = optional_arcade.arcade
_shown = arcade.Window.__init__


def _hidden(self, *a, **k):
    k["visible"] = False
    _shown(self, *a, **k)


arcade.Window.__init__ = _hidden
from engine.game import GameWindow  # noqa: E402

K = arcade.key
layout = json.loads(LAYOUT.read_text(encoding="utf-8"))


def say(tag, **kw):
    print("S1V", tag, json.dumps(kw, default=str), flush=True)


def drive(window):
    import engine
    window._allow_dispatch_event = True
    window.audio.set_master_volume(0.0)
    sc = window.scene_controller
    say("engine", file=engine.__file__, mode=MODE)

    def step(n=1):
        for _ in range(n):
            window.dispatch_event("on_update", 1 / 60)

    def press(sym):
        window.dispatch_event("on_key_press", sym, 0)
        step(1)
        window.dispatch_event("on_key_release", sym, 0)
        step(3)

    def named(name):
        return next((s for s in sc.all_sprites if getattr(s, "mesh_name", "") == name), None)

    def hero():
        return sc._find_player_sprite()

    def room():
        return Path(str(getattr(sc, "room_path", "") or sc.current_scene_path or "")).stem

    def beh(sprite, t):
        return next((b for b in (sprite.mesh_behaviours_runtime if sprite else []) if type(b).__name__ == t), None)

    def stand_by(name, dy=-40):
        t = named(name)
        h = hero()
        if t is None or h is None:
            return False
        h.center_x, h.center_y = t.center_x, t.center_y + dy - 12
        step(2)
        window.dispatch_event("on_key_press", K.UP, 0)  # walk a step toward it (sets facing, as a player would)
        step(6)
        window.dispatch_event("on_key_release", K.UP, 0)
        step(2)
        return True

    def potions():
        from engine.inventory import get_or_create_inventory
        return int(get_or_create_inventory(window.game_state_controller.state.values).get_count("healing_potion"))

    def shop_open():
        return bool(window.ui_controller.shop_panel.visible)

    def close_shop():
        if shop_open():
            window.ui_controller.shop_panel.close()
            step(2)

    def healths():
        out = {}
        for s in sc.all_sprites:
            h = beh(s, "Health")
            if h is not None:
                out[s.mesh_name or s.mesh_id] = [h.hp, h.max_hp, getattr(s, "mesh_tag", "")]
        return out

    step(5)
    start_path = sc.current_scene_path
    say("start", room=room(), player=hero() is not None, sprites=len(list(sc.all_sprites)))

    # ---- #651
    gs = window.game_state_controller
    stats = gs.get_player_stats()
    h = hero()
    say("651_player", stats_max_hp=stats.get("max_hp"), stats_attack=stats.get("attack"),
        health=[beh(h, "Health").hp, beh(h, "Health").max_hp] if beh(h, "Health") else None,
        combat_damage=beh(h, "Combat").damage if beh(h, "Combat") else None)
    say("651_healths", **healths())
    w = named("WolfS")
    if beh(w, "Health"):
        beh(w, "Health").apply_damage(1.0, source_entity="player")
        step(5)
        say("651_wolfS_after_one_damage", still_there=named("WolfS") is not None,
            hp=beh(named("WolfS"), "Health").hp if named("WolfS") else None)

    def item_round(tag, drop_name="WolfDrop"):
        res = {}
        p0 = potions()
        stand_by("Potion")
        press(K.E)
        res["pickup"] = {"potions_before": p0, "after": potions(), "potion_still_there": named("Potion") is not None}
        for m in ("MerchantS", "MerchantPlain"):
            close_shop()
            ok = stand_by(m)
            press(K.E)
            res[m] = {"present": ok, "behaviours": [type(b).__name__ for b in named(m).mesh_behaviours_runtime] if named(m) else None,
                      "shop_open_after_E": shop_open()}
            if shop_open():
                res[m]["stock_rows"] = len(getattr(window.ui_controller.shop_panel, "_items", []) or [])
            close_shop()
        p0 = potions()
        stand_by("Button")
        press(K.E)
        ch = beh(named("Chest"), "RewardChest")
        res["chest_before_E"] = {"enabled": getattr(ch, "enabled", None), "looted": getattr(ch, "looted", None)}
        stand_by("Chest")
        press(K.E)
        ch = beh(named("Chest"), "RewardChest")
        res["chest"] = {"potions_before": p0, "after": potions(), "looted": getattr(ch, "looted", None)}
        p0 = potions()
        wd = named(drop_name)
        if beh(wd, "Health"):
            beh(wd, "Health").apply_damage(99.0, source_entity="player")
            step(10)
        res["drop"] = {"potions_before": p0, "after": potions(), "drop_enemy": drop_name, "present_before": wd is not None, "still_there": named(drop_name) is not None,
                       "loose_pickups": [s.mesh_name for s in sc.all_sprites if beh(s, "PickupCollectible") and s.mesh_name != "Potion"]}
        say(tag, **res)

    # ---- #652 / #654 without items.json
    say("652_items_json_present", present=(GAME / "assets/data/items.json").is_file())
    item_round("652_no_items")

    # ---- #653
    zone = named("ObjZone")
    say("653_before", flag=bool(gs.get_flag("objective_done")),
        vault_door=[named("Door to Vault") is not None, bool(getattr(named("Door to Vault"), "visible", False))],
        annex_door=named("Door to Annex") is not None, gated_sign=named("GatedSign") is not None)
    vd0 = named("Door to Vault")
    if vd0 is not None:  # touch the hidden door before its flag: must not go through
        h = hero()
        h.center_x, h.center_y = vd0.center_x, vd0.center_y
        step(30)
        say("653_touch_hidden_vault_door_before_flag", room_now=room())
        if room() != "start":
            window.load_scene(start_path)
            step(5)
    if zone is not None:
        h = hero()
        h.center_x, h.center_y = zone.center_x, zone.center_y
        step(10)
        h.center_x, h.center_y = zone.center_x - 200, zone.center_y  # step out (no door under it)
        step(5)
    vd = named("Door to Vault")
    say("653_after_flag_same_visit", flag=bool(gs.get_flag("objective_done")), room=room(),
        vault_door=[vd is not None, bool(getattr(vd, "visible", False))],
        annex_door_built=named("Door to Annex") is not None, gated_sign_built=named("GatedSign") is not None)
    if vd is not None:
        h = hero()
        h.center_x, h.center_y = vd.center_x, vd.center_y
        step(30)
        say("653_touch_vault_door", room_now=room())
    window.load_scene(start_path)  # re-entry
    step(10)
    say("653_after_reentry", room=room(), annex_door_built=named("Door to Annex") is not None,
        gated_sign_built=named("GatedSign") is not None)
    ad = named("Door to Annex")
    if ad is not None:
        h = hero()
        h.center_x, h.center_y = ad.center_x, ad.center_y
        step(30)
        say("653_touch_annex_door_after_reentry", room_now=room())
        window.load_scene(start_path)
        step(10)

    # ---- #652 / #654 with a hand-written items.json
    if ITEMS is not None:
        shutil.copyfile(ITEMS, GAME / "assets/data/items.json")
        window.load_scene(start_path)
        step(10)
        item_round("652_with_items", "WolfDrop2")
        # purchase: give gold the game's way is out of scope; check the panel's buy result with 0 gold, then 50
        close_shop()
        step(60)
        stand_by("MerchantS")
        press(K.E)
        if shop_open():
            gs.add_counter("gold", 50)
            press(K.ENTER)
            step(3)
            say("654_purchase_enter", gold=gs.get_counter("gold", 0), potions=potions())
        close_shop()

    # ---- root-cause experiment (dev only): fill_defaults=False in the factory, a hand-written scene
    if MODE == "dev":
        x = GAME / "s1v_experiment.json"
        x.write_text(json.dumps({"name": "X", "schema_version": 1, "version": 1, "layers": [], "entities": [
            {"id": "hero", "name": "Hero", "tag": "player", "x": 100, "y": 100, "sprite": "assets/sprites/starter_sign.png",
             "behaviours": ["PlayerController", "Health", "Combat"]},
            {"id": "bear", "name": "Bear", "x": 200, "y": 100, "sprite": "assets/sprites/starter_sign.png",
             "behaviours": ["Health"], "behaviour_config": {"Health": {"max_hp": 50}}}]}), encoding="utf-8")
        import engine.scene_controller_core as scm
        for patched in (False, True):
            if patched:
                orig = scm.create_behaviour
                scm.create_behaviour = lambda *a, **k: orig(*a, **{**k, "fill_defaults": False})
            window.load_scene(str(x))
            step(3)
            hh = hero()
            say("651_experiment", fill_defaults=not patched, healths=healths(),
                hero_combat=beh(hh, "Combat").damage if beh(hh, "Combat") else None,
                hero_name=getattr(hh, "mesh_name", None))
            if patched:
                window.load_scene(start_path)
                step(3)
                say("651_experiment_authored_room", fill_defaults=False, healths=healths(),
                    player_combat=beh(hero(), "Combat").damage if beh(hero(), "Combat") else None)
                scm.create_behaviour = orig
        x.unlink()
    window.close()


GameWindow.run = drive
try:
    runpy.run_path(str(GAME / "main.py"), run_name="__main__")
except SystemExit:
    pass
