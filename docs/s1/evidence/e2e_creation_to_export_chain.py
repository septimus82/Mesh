"""S1-0 part D: the creation-to-play chain, end to end, through the supported entry points.

    py -3.13 docs/s1/evidence/e2e_creation_to_export_chain.py        (PYTHONPATH = this checkout)

One throwaway folder (removed afterwards) holds everything: the project, the creator's "own" files, the export and a
stand-in for the player's per-user data folder (APPDATA / XDG_DATA_HOME point there for the exported game, so nothing
reaches the real one).

Steps (each a real entry point; nothing is written into the scene files by hand):
  A. ``mesh new chain`` (mesh_cli main, starter template, the default).
  B. Studio's project model (engine.studio_project.Project, under Studio's ownership lock): import a picture, a tileset,
     a sound and a Blender .glb; add a 2D room ("Shed") and an HD-2D room ("Glade"); save.
  C. ``mesh author apply`` (engine.authoring_session.apply, the same operations Studio and MCP use): walls, an Elder
     with a conversation whose reward choice is "once", a Shopkeeper, a Button + "Locked until an event" gate, a
     Treasure chest behind it, a zone behind it, an enemy, doors to both rooms, the imported model in the HD-2D room,
     Combat/Health on the player.
  D. Quests: ``mesh new-quest`` (the CLI) and MCP ``apply_ops add_quest_definition`` (the AI path).
  E. Play (child process: the project's own main.py, GameWindow.run replaced by a script that drives the game's own
     key input and update loop in a hidden, muted, never-activated window): talk, take the reward, shop, fight, pull
     the lever, try the gate, open the chest, visit both rooms, re-enter, quicksave (F5).
  F. Reopen (child process: main.py again): quickload (F9), check what survived.
  G. ``mesh export build`` into the project's dist folder, then run the exported main.py (child process: the export's
     own engine, not this checkout's) twice: play + save, then start again + load.

Exits 1 when a step that should work does not (each defect is listed at the end, with the tracked issue when known).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

# --------------------------------------------------------------------------------------------- the play driver
# Runs in a child process as the game's own GameWindow.run. Uses only the game's input path (on_key_press /
# on_key_release / on_update dispatched to the window, as pyglet's loop would) and reads state from the window.
DRIVER = r'''
import json, runpy, sys
from pathlib import Path
MODE, GAME, HIDDEN = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
if MODE.startswith("export"):
    sys.path.insert(0, str(GAME))          # (as `python <game>/main.py` does: the game's folder first)
import importlib.util
spec = importlib.util.spec_from_file_location("hidden_windows", HIDDEN)
hw = importlib.util.module_from_spec(spec); spec.loader.exec_module(hw); hw.no_activate()
import engine.optional_arcade as optional_arcade
arcade = optional_arcade.arcade
_shown = arcade.Window.__init__
def _hidden(self, *a, **k):
    k["visible"] = False
    _shown(self, *a, **k)
arcade.Window.__init__ = _hidden
from engine.game import GameWindow
K = arcade.key
facts = {"mode": MODE, "steps": {}}

def note(step, ok, **detail):
    facts["steps"][step] = {"ok": ok, **detail}

def drive(window):
    window._allow_dispatch_event = True
    window.audio.set_master_volume(0.0)
    sc = window.scene_controller
    held = set()
    def step(n=1):
        for _ in range(n):
            window.dispatch_event("on_update", 1 / 60)
    def press(symbol, frames=2):
        window.dispatch_event("on_key_press", symbol, 0); step(1)
        window.dispatch_event("on_key_release", symbol, 0); step(frames)
    def hold(keys):
        for k in held - keys:
            window.dispatch_event("on_key_release", k, 0)
        for k in keys - held:
            window.dispatch_event("on_key_press", k, 0)
        held.clear(); held.update(keys)
    def hero():
        return sc._find_player_sprite()
    def named(name):
        return next((s for s in sc.all_sprites if getattr(s, "mesh_name", "") == name), None)
    def room():  # (after a load, current_scene_path is the save slot; room_path is the room it was made in)
        return Path(str(getattr(sc, "room_path", "") or getattr(sc, "current_scene_path", "") or "")).stem
    def walk_to(x, y, tol=10, frames=900):
        start_room, last, still = room(), None, 0
        for _ in range(frames):
            h = hero()
            if h is None or room() != start_room:
                hold(set()); step(2); return "left_room"
            dx, dy = x - h.center_x, y - h.center_y
            if abs(dx) <= tol and abs(dy) <= tol:
                hold(set()); step(1); return "arrived"
            keys = set()
            if dx > tol: keys.add(K.RIGHT)
            if dx < -tol: keys.add(K.LEFT)
            if dy > tol: keys.add(K.UP)
            if dy < -tol: keys.add(K.DOWN)
            hold(keys); step(1)
            pos = (round(h.center_x, 1), round(h.center_y, 1))
            still = still + 1 if pos == last else 0
            last = pos
            if still > 45:
                hold(set()); step(1); return f"blocked at {pos}"
        hold(set()); return "timeout"
    def gs():
        return window.game_state_controller
    def gold():
        return float(gs().get_counter("gold", 0) or 0)
    def flag(name):
        return bool(gs().get_flag(name))
    def potions():
        from engine.inventory import get_or_create_inventory
        inv = get_or_create_inventory(gs().state.values)
        return int(inv.get_count("healing_potion"))
    def quest():
        import copy
        return copy.deepcopy(dict((gs().state.values.get("quests") or {}).get("vault_quest") or {}))
    def snapshot():
        return {"room": room(), "gold": gold(), "elder_thanked": flag("elder_thanked"),
                "reached_vault": flag("reached_vault"), "potions": potions(), "quest": quest(),
                "wolf_present": named("Wolf") is not None,
                "gate_locked": getattr(next((b for b in (named("Gate").mesh_behaviours_runtime if named("Gate") else [])
                                             if type(b).__name__ == "DoorLock"), None), "locked", None)}

    facts["engine"] = __import__("engine").__file__
    facts["save_dir"] = str(window.save_manager.save_dir)
    step(5)
    facts["start"] = snapshot()

    if MODE in ("play",):
        # 1. The Elder: talk (E), take the once-only reward (E on the choice), talk again.
        e = named("Elder")
        r = walk_to(e.center_x, e.center_y - 40)
        press(K.E, 3); press(K.E, 3)
        g1, q1 = gold(), quest()
        press(K.E, 3); press(K.E, 3); step(5)
        g2 = gold()
        note("elder_reward_once_in_visit", g1 == 25.0 and g2 == 25.0, walk=r, gold_after_first=g1, gold_after_second_talk=g2)
        note("quest_started_by_dialogue_choice", q1.get("status") not in (None, "", "inactive", "not_started"), quest=q1)
        # 1b. Something to pick up (E beside it): a healing potion, in a project that has no item list.
        p = named("Potion")
        r = walk_to(p.center_x, p.center_y - 40)
        press(K.E, 3)
        note("pickup_item", potions() == 1, walk=r, potions=potions(), still_there=named("Potion") is not None)
        # 2. The Shopkeeper: E beside it.
        m = named("Merchant")
        vend = [type(b).__name__ for b in (m.mesh_behaviours_runtime if m else [])]
        r = walk_to(m.center_x, m.center_y - 40)
        before_potions = potions()
        press(K.E, 3)
        panel = window.ui_controller.shop_panel
        note("shop_opens_on_interact", bool(panel and panel.visible), walk=r, merchant_behaviours=vend)
        if panel and panel.visible:
            press(K.ENTER, 2); press(K.ESCAPE, 2)
        note("shop_purchase", potions() == before_potions + 1, potions=potions(), gold=gold())
        # 3. The enemy: fight with the attack key until it is gone.
        hits = 0
        for _ in range(40):
            w = named("Wolf")
            if w is None:
                break
            walk_to(w.center_x - 24, w.center_y, tol=12, frames=60)
            press(K.SPACE, 20); hits += 1
            if hero() is None:
                break
        step(30)
        note("enemy_defeated", named("Wolf") is None, attacks=hits, player_alive=hero() is not None, gold=gold(),
             player_hp=getattr(next((b for b in hero().mesh_behaviours_runtime if type(b).__name__ == "Health"), None), "hp", None) if hero() else None)
        # 4. The Button, then walk through the gate it opens.
        lv = named("Lever")
        r = walk_to(lv.center_x, lv.center_y - 40)
        press(K.E, 3); step(5)
        gate = named("Gate")
        lock = next(b for b in gate.mesh_behaviours_runtime if type(b).__name__ == "DoorLock")
        note("lever_unlocks_gate", not lock.locked, walk=r, quest=quest())
        r1 = walk_to(gate.center_x - 60, gate.center_y)
        r2 = walk_to(gate.center_x + 70, gate.center_y)
        passed = hero().center_x > gate.center_x + 40
        note("walk_through_unlocked_gate", passed, walk=r2, gate_in_solid_sprites=gate in sc.solid_sprites)
        if not passed:   # (what a fix would do: the gate leaves solid_sprites; only to check what lies behind it)
            sc.solid_sprites.remove(gate)
            r2 = walk_to(gate.center_x + 70, gate.center_y)
            facts["workaround_gate_removed_from_solid_sprites"] = r2
        # 5. The chest behind the gate, then the zone behind it.
        c = named("Chest")
        g0 = gold()
        r = walk_to(c.center_x, c.center_y - 40)
        press(K.E, 3)
        chest = next(b for b in c.mesh_behaviours_runtime if type(b).__name__ == "RewardChest")
        note("chest_grants_gold", gold() == g0 + 10, walk=r, looted=chest.looted, gold_before=g0, gold_after=gold())
        z = named("VaultZone")
        r = walk_to(z.center_x, z.center_y); step(10)
        note("zone_sets_flag_and_quest_completes", flag("reached_vault") and quest().get("status") == "completed",
             walk=r, quest=quest(), vault_badge=gs().get_counter("vault_badge", 0))
        # 6. The doors: back through the gate gap, to the HD-2D Glade and back, to the Shed and back.
        walk_to(gate.center_x + 70, gate.center_y); walk_to(gate.center_x - 70, gate.center_y)
        d = named("Door to Glade")
        r = walk_to(d.center_x, d.center_y, frames=600)
        step(10)
        hd = window.hd2d_renderer is not None
        note("door_to_hd2d_room", room() == "glade" and hd, walk=r, room=room(), hd2d=hd,
             hd2d_error=getattr(window, "hd2d_error", None))
        if room() == "glade":
            h = hero(); x0 = h.center_x
            hold({K.RIGHT}); step(30); hold(set()); step(2)
            note("hd2d_room_walkable", hero().center_x > x0 + 20, moved=round(hero().center_x - x0, 1))
            window.dispatch_event("on_draw")
            back = named("Door to Start")
            r = walk_to(back.center_x, back.center_y, frames=900) if back else "no door back"
            step(10)
            note("door_back_from_hd2d_room", room() == "start", walk=r, room=room())
        e = named("Elder")
        if e is not None:
            walk_to(e.center_x, e.center_y - 40)
            press(K.E, 3); press(K.E, 3); step(5)
        note("once_reward_not_repaid_after_reentry", gold() == facts["steps"]["chest_grants_gold"]["gold_after"],
             gold=gold(), note="#620 if this fails")
        facts["before_save"] = snapshot()
        press(K.F5, 5)   # quick_save
        facts["saves"] = window.save_manager.list_saves()
    elif MODE == "resume":
        press(K.F9, 3); step(5)   # quick_load
        facts["after_load"] = snapshot()
    elif MODE == "export_play":
        facts["slots_at_start"] = window.save_manager.list_saves()
        h = hero(); x0 = h.center_x
        hold({K.RIGHT}); step(30); hold(set()); step(2)
        note("exported_game_walks", hero().center_x > x0 + 20, moved=round(hero().center_x - x0, 1))
        e = named("Elder")
        walk_to(e.center_x, e.center_y - 40); press(K.E, 3); press(K.E, 3); step(3)
        note("exported_elder_reward", gold() == 25.0, gold=gold())
        press(K.F5, 5)
        facts["saves"] = window.save_manager.list_saves()
        facts["before_save"] = snapshot()
    elif MODE == "export_resume":
        facts["slots_at_start"] = window.save_manager.list_saves()
        press(K.F9, 3); step(5)
        facts["after_load"] = snapshot()
    window.dispatch_event("on_draw")
    window.close()

GameWindow.run = drive
try:
    runpy.run_path(str(GAME / "main.py"), run_name="__main__")
except SystemExit:
    pass
print("MESH-CHAIN " + json.dumps(facts, default=str), flush=True)
'''


def child(mode: str, game: Path, cwd: Path, env_extra: dict[str, str], tmp: Path) -> dict[str, Any]:
    """Run the driver in a child process (one at a time; this process waits)."""
    script = tmp / "driver.py"
    script.write_text(DRIVER, encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("MESH_")}
    env["MESH_RUNTIME_SETTINGS_PATH"] = str(tmp / "settings" / "user_settings.json")
    if mode.startswith("export"):
        env.pop("PYTHONPATH", None)  # the exported game: its own engine, never this checkout's
        env.pop("MESH_RUNTIME_SETTINGS_PATH")  # (an exported game keeps the player's settings beside its saves)
    env.update(env_extra)
    proc = subprocess.run([sys.executable, str(script), mode, str(game), str(REPO / "tooling" / "hidden_windows.py")],
                          cwd=str(cwd), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=600)
    line = next((x for x in reversed(proc.stdout.splitlines()) if x.startswith("MESH-CHAIN ")), None)
    if line is None:
        tail = (proc.stdout + proc.stderr)[-3000:]
        return {"crashed": True, "code": proc.returncode, "tail": tail}
    facts = json.loads(line[len("MESH-CHAIN "):])
    facts["warnings"] = [x for x in (proc.stdout + proc.stderr).splitlines()
                         if ("Traceback" in x or "ERROR" in x or "Error" in x) and "MESH-CHAIN" not in x][:12]
    return facts


def main() -> int:
    sys.path.insert(0, str(REPO))
    os.chdir(REPO)
    import engine

    print("engine from", Path(engine.__file__).relative_to(REPO.parent).as_posix())
    tmp = Path(tempfile.mkdtemp(prefix="mesh_s1_chain_"))
    defects: list[str] = []
    results: dict[str, Any] = {}

    def check(step: str, ok: bool, detail: Any = "", issue: str = "") -> None:
        results[step] = "works" if ok else "FAILS"
        print(f"[{'ok' if ok else 'FAIL'}] {step}: {detail}")
        if not ok:
            defects.append(f"{step}{f' ({issue})' if issue else ''}")

    try:
        # ---- A. mesh new --------------------------------------------------------------------------------------
        from mesh_cli.main import main as mesh

        code = mesh(["new", "chain", "--dest", str(tmp)])
        project = tmp / "chain"
        check("A mesh new (starter)", code == 0 and (project / "config.json").is_file(), f"exit {code}")
        world_file = json.loads((project / "config.json").read_text(encoding="utf-8"))["world_file"]
        has = {rel: (project / rel).is_file() for rel in ("assets/data/items.json", "assets/data/quests.json")}
        print("   fresh project has:", has)

        # ---- B. Studio project model: imports + rooms ------------------------------------------------------------
        mine = tmp / "creator_files"
        mine.mkdir()
        from PIL import Image

        Image.new("RGBA", (32, 48), (200, 60, 60, 255)).save(mine / "Merchant Pic.png")
        Image.new("RGBA", (64, 32), (90, 90, 200, 255)).save(mine / "my tiles.png")
        with wave.open(str(mine / "hum.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes(b"\0\0" * 2205)
        shutil.copyfile(REPO / "assets/hd2d_starter/models/crate.glb", mine / "my_crate.glb")

        from engine.editor import project_ownership
        from engine.studio_project import Project

        held = project_ownership.acquire(project, project_ownership.STUDIO)
        try:
            proj = Project.open(project, world_file)
            assert proj is not None
            sprite = proj.import_sprite(mine / "Merchant Pic.png")
            tiles = proj.import_tileset(mine / "my tiles.png", 32, "My Tiles", owner=held)
            sound = proj.import_sound(mine / "hum.wav")
            model = proj.import_model(mine / "my_crate.glb", name="My Crate")
            proj.add_room("Shed")
            glade, kit = proj.add_hd2d_room("Glade", 16, 12)
            written = proj.save(owner=held)
        finally:
            held.release()
        check("B Studio imports (picture, tileset, sound, .glb)",
              all((project / p).is_file() for p in (sprite, tiles["source"], sound, model.model)),
              f"{sprite}, {tiles['source']}, {sound}, {model.model}")
        check("B Studio add 2D room + HD-2D room, save", glade == "glade" and len(written) == 3,
              f"kit installed={kit}, wrote {written}")
        catalog = json.loads((project / "assets/models/catalog.json").read_text(encoding="utf-8"))
        prov = next(m for m in catalog["models"] if m["id"] == "my_crate").get("source", {})
        print("   model provenance recorded:", {k: ("<absolute path>" if k == "file" else v) for k, v in prov.items()},
              "| absolute source path stored:", Path(str(prov.get("file", ""))).is_absolute())

        # ---- C. mesh author apply --------------------------------------------------------------------------------
        from engine import authoring_session

        border = [(c, r) for c in range(24) for r in range(16) if c in (0, 23) or r in (0, 15)]
        inner = [(14, r) for r in range(1, 15) if r not in (7, 8)]  # a wall with a two-tile gap the gate fills
        sign = "assets/sprites/starter_sign.png"

        def behaviour(n: int, name: str, **params: Any) -> list[dict[str, Any]]:
            ops = [{"op": "add_behaviour", "room": "start", "entity_id": f"@{n}", "behaviour": name}]
            return ops + [{"op": "set_behaviour_param", "room": "start", "entity_id": f"@{n}", "behaviour": name,
                           "param": k, "value": v} for k, v in params.items()]

        changes: list[dict[str, Any]] = [
            {"op": "paint_tiles", "room": "start", "layer": "walls", "cells": border + inner, "tile": 9},
            {"op": "place_prefab", "room": "start", "prefab": "person", "x": 200, "y": 320},       # 1
            {"op": "rename_entity", "room": "start", "entity_id": "@1", "name": "Elder"},
            {"op": "set_dialogue_text", "room": "start", "entity_id": "@1", "text": "Help us, and take this."},
            {"op": "add_choice", "room": "start", "entity_id": "@1", "node_id": "root", "text": "Thank you"},
            {"op": "set_choice", "room": "start", "entity_id": "@1", "node_id": "root", "index": 0, "once": True,
             "add_counters": {"gold": 25}, "set_flags": ["elder_thanked"]},
        ]
        n = len(changes)
        changes += [{"op": "place_blank", "room": "start", "name": "Merchant", "x": 300, "y": 420},
                    {"op": "set_picture", "room": "start", "entity_id": f"@{n}", "sprite": sprite}]
        changes += behaviour(n, "Vendor", stock=[{"item_id": "healing_potion", "price": 5, "quantity": 3}])
        n = len(changes)
        changes += [{"op": "place_blank", "room": "start", "name": "Lever", "x": 400, "y": 160},
                    {"op": "set_picture", "room": "start", "entity_id": f"@{n}", "sprite": sign}]
        changes += behaviour(n, "SwitchInteract", event_id="gate_open")
        n = len(changes)
        changes += [{"op": "place_blank", "room": "start", "name": "Gate", "x": 464, "y": 256},
                    {"op": "set_picture", "room": "start", "entity_id": f"@{n}", "sprite": "assets/sprites/door.png"},
                    {"op": "set_solid", "room": "start", "entity_id": f"@{n}", "solid": True}]
        changes += behaviour(n, "DoorLock", unlock_event="gate_open")
        n = len(changes)
        changes += [{"op": "place_blank", "room": "start", "name": "Chest", "x": 600, "y": 320},
                    {"op": "set_picture", "room": "start", "entity_id": f"@{n}", "sprite": sign}]
        changes += behaviour(n, "RewardChest", unlock_event="gate_open", gold=10)
        n = len(changes)
        changes += [{"op": "place_blank", "room": "start", "name": "VaultZone", "x": 620, "y": 160},
                    {"op": "set_trigger_zone", "room": "start", "entity_id": f"@{n}", "width": 96, "height": 96,
                     "set_flags": ["reached_vault"]}]
        n = len(changes)
        changes += [{"op": "place_blank", "room": "start", "name": "Wolf", "x": 330, "y": 250},
                    {"op": "set_picture", "room": "start", "entity_id": f"@{n}", "sprite": sign},
                    {"op": "set_entity_fields", "room": "start", "entity_id": f"@{n}", "fields": {"tag": "enemy"}}]
        changes += behaviour(n, "Health", max_hp=3)
        changes += behaviour(n, "EnemyAI", speed=40)
        changes += behaviour(n, "DropTable", drops=[{"gold": 5, "chance": 1.0}])
        changes += behaviour(n, "GrantExperience")
        n = len(changes)
        changes += [{"op": "place_blank", "room": "start", "name": "Potion", "x": 150, "y": 220},
                    {"op": "set_picture", "room": "start", "entity_id": f"@{n}", "sprite": sign}]
        changes += behaviour(n, "PickupCollectible", item_id="healing_potion", item_amount=1)
        changes += [{"op": "set_sound_emitter", "room": "start", "entity_id": "Merchant", "sound": sound}]
        changes += [
            {"op": "link_rooms", "key_a": "start", "at_a": [80, 440], "key_b": "shed", "at_b": [320, 240]},
            {"op": "link_rooms", "key_a": "start", "at_a": [80, 260], "key_b": "glade", "at_b": [256, 192]},
            {"op": "place_structure", "room": "glade", "model": "my_crate", "x": 320, "y": 300},
            {"op": "add_behaviour", "room": "start", "entity_id": "Player", "behaviour": "Combat"},
            {"op": "add_behaviour", "room": "start", "entity_id": "Player", "behaviour": "Health"},
            {"op": "set_behaviour_param", "room": "start", "entity_id": "Player", "behaviour": "Health",
             "param": "max_hp", "value": 50},
        ]
        result = authoring_session.apply(project, changes, source="mesh author")
        check("C mesh author apply (door, NPC+once reward, shop, lever+gate, chest, zone, enemy, HD-2D model)",
              bool(result.get("ok")), result.get("message") or f"{len(changes)} changes, wrote {result.get('written')}")
        player_cfg = json.loads((project / "assets/prefabs.json").read_text(encoding="utf-8"))[0]["entity"]
        print("   shared player behaviours now:", player_cfg.get("behaviours"))
        start_doc = json.loads((project / "packs/core_regions/scenes/start.json").read_text(encoding="utf-8"))
        wolf_hp = next(e for e in start_doc["entities"] if e.get("name") == "Wolf")["behaviour_config"]["Health"]
        print("   Wolf's authored Health after add_behaviour + max_hp=3:", wolf_hp)

        # ---- B2. Studio: reimport the placed model from a new export (provenance + placed copies kept) -----------
        shutil.copyfile(REPO / "assets/hd2d_starter/models/barrel.glb", mine / "my_crate_v2.glb")
        held = project_ownership.acquire(project, project_ownership.STUDIO)
        try:
            proj = Project.open(project, world_file)
            assert proj is not None
            plan = proj.plan_reimport("my_crate", mine / "my_crate_v2.glb")
            proj.reimport_model("my_crate", mine / "my_crate_v2.glb")
        finally:
            held.release()
        catalog = json.loads((project / "assets/models/catalog.json").read_text(encoding="utf-8"))
        prov2 = next(m for m in catalog["models"] if m["id"] == "my_crate").get("source", {})
        glade_doc = json.loads((project / "packs/core_regions/scenes/glade.json").read_text(encoding="utf-8"))
        placed = [s.get("model") for s in (glade_doc.get("settings", {}).get("hd2d", {}).get("structures") or [])]
        check("B2 Studio reimport keeps the placed copy and records the new source",
              prov2.get("sha256") != prov.get("sha256") and any("my_crate" in str(m) for m in placed),
              f"plan: {str(plan)[:160]} | sha changed: {prov2.get('sha256') != prov.get('sha256')} | placed: {placed}")

        # ---- D. quests: the CLI, then MCP -----------------------------------------------------------------------
        from engine.mcp_server import tools

        quest = {"title": "The Elder's Vault", "stages": [
            {"id": "open_gate", "title": "Open the vault gate",
             "start_on_event": {"type": "dialogue_choice", "payload": {"entity": "Elder"}},
             "complete_on": {"type": "door_unlocked"}},
            {"id": "enter_vault", "title": "Enter the vault", "requirements": {"flags": {"reached_vault": True}}}],
            "reward": {"inc_counters": {"vault_badge": 1}}}
        listed = tools.list_scenes(root=str(project))
        print(f"   MCP list_scenes on this project: {listed} (its rooms: "
              f"{sorted(authoring_session.read_project(project)['rooms'])})")
        add = [{"type": "add_quest_definition", "quest_id": "vault_quest", "quest": quest}]
        first = tools.apply_ops(operations=add, root=str(project))
        check("D MCP add_quest_definition on a fresh project", bool(first.get("ok")),
              (first.get("results") or [{}])[0].get("message"), "new")
        cwd = Path.cwd()
        os.chdir(project)
        try:
            bare_code = mesh(["new-quest", "Side Errand"])  # as its help shows it (--target optional)
            cli_code = mesh(["new-quest", "Side Errand", "--target", "assets/data/quests.json"])
        finally:
            os.chdir(cwd)
        check("D mesh new-quest NAME (no --target)", bare_code == 0, f"exit {bare_code}", "new")
        quests_file = project / "assets/data/quests.json"
        cli_file = json.loads(quests_file.read_text(encoding="utf-8")) if quests_file.is_file() else None
        # The runtime's rule (engine/quests.py load_definitions): quests = payload.get("quests") if payload is a dict.
        runtime_sees = isinstance(cli_file, dict) and isinstance(cli_file.get("quests"), (list, dict))
        second = tools.apply_ops(operations=add, root=str(project))
        check("D mesh new-quest --target assets/data/quests.json makes a file the runtime loads",
              cli_code == 0 and runtime_sees,
              f"exit {cli_code}; file root is a {type(cli_file).__name__}; runtime reads a 'quests' key: {runtime_sees}",
              "new")
        check("D MCP add_quest_definition after mesh new-quest", bool(second.get("ok")),
              (second.get("results") or [{}])[0].get("message"), "new")
        # Workaround a creator would need: an object-rooted file by hand, then MCP.
        (project / "assets/data/quests.json").write_text(json.dumps({"quests": []}), encoding="utf-8")
        third = tools.apply_ops(operations=add, root=str(project))
        check("D MCP add_quest_definition after hand-writing {\"quests\": []} (workaround)", bool(third.get("ok")),
              (third.get("results") or [{}])[0].get("message"))

        # ---- E/F. play, quicksave, reopen, quickload ----------------------------------------------------------------
        play = child("play", project, tmp, {}, tmp)
        if play.get("crashed"):
            check("E play the project (main.py)", False, play["tail"])
        else:
            print("   engine in the game:", Path(play["engine"]).relative_to(REPO.parent).as_posix())
            issues = {"elder_reward_once_in_visit": "", "quest_started_by_dialogue_choice": "",
                      "pickup_item": "new", "shop_opens_on_interact": "new", "shop_purchase": "new", "enemy_defeated": "",
                      "lever_unlocks_gate": "", "walk_through_unlocked_gate": "#639",
                      "chest_grants_gold": "#636", "zone_sets_flag_and_quest_completes": "",
                      "door_to_hd2d_room": "", "hd2d_room_walkable": "", "door_back_from_hd2d_room": "",
                      "once_reward_not_repaid_after_reentry": "#620"}
            for name, step in play["steps"].items():
                detail = {k: v for k, v in step.items() if k != "ok"}
                check(f"E {name}", bool(step["ok"]), json.dumps(detail, default=str)[:400], issues.get(name, ""))
            print("   before quicksave:", json.dumps(play.get("before_save")))
            print("   slots:", play.get("saves"), "| warnings:", play.get("warnings"))
            resume = child("resume", project, tmp, {}, tmp)
            if resume.get("crashed"):
                check("F reopen + quickload", False, resume["tail"])
            else:
                before, after = play.get("before_save") or {}, resume.get("after_load") or {}
                print("   after reopen + quickload:", json.dumps(after))
                for key in ("room", "gold", "elder_thanked", "reached_vault", "potions", "wolf_present"):
                    check(f"F reopen keeps {key}", before.get(key) == after.get(key),
                          f"{before.get(key)!r} -> {after.get(key)!r}")
                check("F reopen keeps the quest", (before.get("quest") or {}).get("status") ==
                      (after.get("quest") or {}).get("status"),
                      f"{(before.get('quest') or {}).get('status')} -> {(after.get('quest') or {}).get('status')}")
                check("F reopen keeps the gate unlocked", after.get("gate_locked") is False,
                      f"gate locked after load: {after.get('gate_locked')}", "#639")

        # ---- G. export, then the exported game -----------------------------------------------------------------
        os.chdir(project)
        try:
            code = mesh(["export", "build", "--deterministic"])
        finally:
            os.chdir(cwd)
        bundle = project / "dist" / "bundle"
        check("G mesh export build", code == 0 and (bundle / "main.py").is_file(), f"exit {code}")
        if (bundle / "main.py").is_file():
            listed = {f["path"] for f in json.loads((bundle / "bundle_manifest.json").read_text(encoding="utf-8"))["files"]}
            for rel in ("assets/data/quests.json", sprite, sound, model.model, "packs/core_regions/scenes/glade.json"):
                check(f"G export carries {rel}", rel in listed, rel in listed)
            cat = bundle / "assets/models/catalog.json"
            if cat.is_file():
                text = cat.read_text(encoding="utf-8")
                print("   exported catalog holds the creator's absolute source path:", str(mine) in text)
            player_home = tmp / "player_data"
            env = {"APPDATA": str(player_home), "XDG_DATA_HOME": str(player_home)}
            elsewhere = tmp / "launch_folder"
            elsewhere.mkdir()
            first = child("export_play", bundle, elsewhere, env, tmp)
            if first.get("crashed"):
                check("G exported game starts", False, first["tail"])
            else:
                check("G exported game starts from its own engine",
                      Path(first["engine"]).resolve().is_relative_to(bundle.resolve()), first["engine"])
                print("   exported save folder:", "<player data>" + first["save_dir"].split(str(player_home))[-1]
                      if str(player_home) in first["save_dir"] else first["save_dir"])
                print("   dev saves visible to the export:", first.get("slots_at_start"))
                for name, step in first["steps"].items():
                    check(f"G {name}", bool(step["ok"]), {k: v for k, v in step.items() if k != "ok"})
                again = child("export_resume", bundle, elsewhere, env, tmp)
                if again.get("crashed"):
                    check("G exported game reopens + loads", False, again["tail"])
                else:
                    b, a = first.get("before_save") or {}, again.get("after_load") or {}
                    check("G exported game reopens and loads its save", b.get("gold") == a.get("gold") == 25.0
                          and "quicksave" in (again.get("slots_at_start") or []),
                          f"slots {again.get('slots_at_start')}; gold {b.get('gold')} -> {a.get('gold')}")
                untouched = not (bundle / "saves").exists()
                check("G exported game writes nothing into its own folder", untouched, untouched)
    finally:
        os.chdir(REPO)
        listing = sorted(p.relative_to(tmp).as_posix() for p in tmp.iterdir())
        shutil.rmtree(tmp, ignore_errors=True)  # (the temp folder this script created)
        print("removed temp folder holding:", listing)

    print("\nSUMMARY", json.dumps(results, indent=1))
    if defects:
        print("DEFECTS:", "; ".join(defects))
        return 1
    print("chain composes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
