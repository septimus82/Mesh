"""Acceptance test, Milestone 11: a first-time creator's game, from the launcher to a loaded save.

Real windows only ("Mesh Engine.bat"), driven by OS-level mouse and keyboard. The launcher's and the
Studio's layout dumps are read to find things and check state, never to act; files on disk are only read.

 1 new project from the launcher             12 a conversation that sets a flag
 2 the player and an NPC look different      13 a one-tile gap: the player walks through
 3 the player's size and footprint           14 Esc opens the game menu
 4 three rooms joined by doors               15 Save Game says "Game saved"
 5 one player in every room                  16 change room and a flag
 6 change the player once: every room        17 Load Game: room, place and flags come back
 7 an NPC in the second room                 18 Exit Play-Test
 8 find "Walk between points" by name        19 save and close the Studio
 9 click its route on the map                20 reopen from the launcher: player, route and rooms kept
10 a point in a wall: a plain warning        21 play again; the save loads
11 move it; the NPC patrols in play

Run from the repo root:  py -3.13 tooling/acceptance_creator.py [--out DIR]
Keep hands off the mouse while it runs. Exit code 0 only if every step passed.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO))
from acceptance_first_workflow import Page  # noqa: E402
from acceptance_map_building import MapPage  # noqa: E402
from gui_driver import Driver, find_window_by_title  # noqa: E402

GAME = "Lantern Vale"
# What a step raises when it fails: its own checks, the GUI driver (RuntimeError, timeouts), files and the dumps.
STEP_FAILURES = (AssertionError, RuntimeError, OSError, ValueError, KeyError, IndexError, TypeError, StopIteration,
                 subprocess.SubprocessError)
FLAG = "asked_about_ranger"


def run(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    # The games it creates go outside the engine folder: the launcher refuses a location inside it, and --out
    # (artifacts/ by default) is inside it. One reused folder; the report and pictures stay in --out.
    work = Path(tempfile.gettempdir()) / "mesh_acceptance_creator"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    dest = work / "games"
    dest.mkdir()
    root = dest / GAME
    launcher_layout, studio_layout = out / "launcher.json", out / "studio.json"
    env = {**os.environ, "MESH_USER_DIR": str(work / "user"), "MESH_PROJECTS_DIR": str(work / "default games"),
           "MESH_LAUNCHER_LAYOUT": str(launcher_layout), "MESH_STUDIO_LAYOUT": str(studio_layout)}
    env.pop("MESH_PROJECTS_PATH", None)
    results: list[dict[str, Any]] = []
    held: dict[str, Any] = {"launcher": None, "studio": None, "L": None, "S": None}
    memo: dict[str, Any] = {}

    # --- helpers ---------------------------------------------------------------------------
    def launch() -> Page:
        launcher_layout.unlink(missing_ok=True)
        subprocess.Popen(["cmd", "/c", str(REPO / "Mesh Engine.bat")], cwd=str(REPO), env=env,
                         creationflags=subprocess.CREATE_NO_WINDOW)
        driver = Driver.attach("Mesh Engine", out / "shots", logical_size=(960, 640))
        held["launcher"], held["L"] = driver, Page(driver, launcher_layout)
        held["L"].wait(lambda s: s["screen"] == "home", "the launcher's home screen", timeout=30)
        return held["L"]

    def studio_opens() -> MapPage:
        driver = Driver.attach("Mesh Studio", out / "shots", timeout=90)
        held["studio"], held["S"] = driver, MapPage(driver, studio_layout)
        held["S"].wait(lambda s: s["mode"] == "edit" and s["objects"], "Mesh Studio", timeout=30)
        if held["launcher"] is not None:
            held["launcher"].proc.wait(timeout=20)
            held["launcher"] = None
        return held["S"]

    def L() -> Page:
        return held["L"]

    def S() -> MapPage:
        return held["S"]

    def step(name: str, action: Callable[[], Any]) -> bool:
        started = time.time()
        try:
            detail, ok, error = action(), True, None
        except STEP_FAILURES as exc:  # record the failure in the report, then stop
            ok, error, detail = False, f"{type(exc).__name__}: {exc}", traceback.format_exc(limit=5)
        driver = held["studio"] or held["launcher"]
        shot = None
        if driver is not None and driver.proc.poll() is None:
            try:
                shot = driver.shot(f"{len(results) + 1:02d}_{name}").name
            except (OSError, RuntimeError, ValueError):  # a window closing mid-capture must not hide the step's result
                shot = None
        results.append({"step": name, "ok": ok, "error": error, "detail": detail,
                        "seconds": round(time.time() - started, 1), "screenshot": shot})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {error}" if error else ""), flush=True)
        return ok

    def room(label: str) -> None:
        S().button(label)
        S().wait(lambda s: s["room"] == label.lower(), f"the {label} room")  # rooms are keyed by their slugged name

    def select(name: str) -> Any:
        S().d.key("ESC")
        S().click_obj(name)
        return S().wait(lambda s: s["selected"] == S().obj(name)["id"], f"{name} selected")

    def tab(title: str) -> None:
        S().button(title)
        S().wait(lambda s: s["tab"] == title.lower(), f"the {title} tab open")

    def player_doc(state: dict[str, Any]) -> dict[str, Any]:
        return next(e for e in state["room_doc"]["entities"] if e.get("tag") == "player")

    def new_room_from(col: int, row: int, label: str) -> None:
        S().d.key("ESC")
        S().click_cell(col, row, right=True)
        S().wait(lambda s: any(w["type"] == "button" and w["text"] == "Add door to a new room..." for w in s["widgets"]),
                 "the map's right-click menu")
        S().button("Add door to a new room...")
        S().wait(lambda s: s["panel"] == "new_room", "the new-room form")
        S().d.type_text(label)  # the name box has the keyboard already: no click first
        S().wait(lambda s: S().field("room_name")["text"] == label, "the typed room name")
        S().button("Create")
        S().wait(lambda s: any(w["type"] == "button" and w["text"] == label for w in s["widgets"]), f"the {label} room")

    def menu(state: dict[str, Any] | None = None) -> Any:
        play = (state or S().state()).get("play") or {}
        return play.get("menu")

    def menu_item(prefix: str) -> None:
        found = [i for i in (menu() or {}).get("items", []) if str(i["text"] or "").startswith(prefix)]
        if not found:
            raise AssertionError(f"no '{prefix}' in the game menu: {menu()}")
        S().d.click(*S()._xy(found[0]["rect"]))

    def walk(target: tuple[float, float], order: tuple[int, ...] = (0, 1), tolerance: float = 8.0,
             timeout: float = 25.0) -> tuple[float, float]:
        """Hold the movement keys until the player is near ``target``, one axis at a time."""
        deadline = time.time() + timeout
        for axis in order:
            neg, pos = ("A", "D") if axis == 0 else ("S", "W")
            stuck = 0
            while time.time() < deadline:
                before = S().player()
                gap = target[axis] - before[axis]
                if abs(gap) <= tolerance:
                    break
                S().d.hold(pos if gap > 0 else neg, min(0.35, max(0.04, abs(gap) / 320)))
                stuck = stuck + 1 if abs(S().player()[axis] - before[axis]) < 0.5 else 0
                if stuck >= 4:
                    raise AssertionError(f"blocked walking to {target}: the player is stuck at {S().player()}")
            else:
                raise AssertionError(f"could not walk to {target}; the player is at {S().player()}")
        at = S().player()
        return float(at[0]), float(at[1])

    def sprite_at(state: dict[str, Any], name: str) -> tuple[float, float]:
        found = [s for s in state["play"]["sprites"] if s["name"] == name]
        if not found:
            raise AssertionError(f"no {name} in the game")
        return float(found[0]["at"][0]), float(found[0]["at"][1])

    def mean_colour(shot: Path, rect: list[float], height: int) -> tuple[float, float, float]:
        from PIL import Image  # noqa: PLC0415

        image = Image.open(shot).convert("RGB")
        scale = image.width / S().state()["window"][0]
        x0, y0 = rect[0] * scale, (height - rect[1] - rect[3]) * scale
        box = image.crop((int(x0), int(y0), int(x0 + rect[2] * scale), int(y0 + rect[3] * scale)))
        r, g, b = (list(band.getdata()) for band in box.split())
        return sum(r) / len(r), sum(g) / len(g), sum(b) / len(b)

    # --- the steps --------------------------------------------------------------------------
    def s01_new_project() -> dict[str, Any]:
        launch()
        L().button("New Project")
        L().wait(lambda s: s["screen"] == "new", "the New Project screen")
        found = next(w for w in L().state()["widgets"] if w["type"] == "card" and w["text"] == "blank")
        L().d.click(*L()._xy(found["rect"]))
        L().wait(lambda s: s["template"] == "blank", "the Blank template chosen")
        L().set_field("name", GAME)
        L().set_field("location", str(dest))
        L().wait(lambda s: s["target"] and Path(s["target"]) == root, "the target folder")
        L().button("Create & Open")
        s = studio_opens().state()
        return {"objects": [o["name"] for o in s["objects"]]}

    def s02_player_and_npc_look_different() -> dict[str, Any]:
        S().button("Person")
        S().click_cell(3, 6)
        s = S().wait(lambda s: any(o["name"] == "Person" for o in s["objects"]), "the placed Person")
        player, person = S().obj("Player"), S().obj("Person")
        assert player["sprite"] != person["sprite"], (player["sprite"], person["sprite"])
        assert "animated_player" not in str(player["sprite"]) + str(person["sprite"]), "the old placeholder art"
        S().d.key("ESC")
        S().wait(lambda s: s["selected"] is None, "nothing selected")
        shot = S().d.shot("02_compare")
        height = s["window"][1]
        a, b = mean_colour(shot, player["rect"], height), mean_colour(shot, person["rect"], height)
        difference = sum(abs(x - y) for x, y in zip(a, b))
        assert difference > 30, f"the player and the Person look alike: {a} vs {b}"
        return {"player": player["sprite"], "person": person["sprite"], "colour_difference": round(difference, 1)}

    def s03_player_size_and_footprint() -> dict[str, Any]:
        select("Player")
        S().wait(lambda s: any("The game's player" in str(w.get("text")) for w in s["widgets"]), "the shared-player note")
        tab("Look")
        S().set_field("look_scale", "1.25")
        S().wait(lambda s: player_doc(s).get("scale") == 1.25, "the player's new size")
        tab("Collision")
        S().button("Whole picture")
        S().wait(lambda s: "collider" not in (player_doc(s).get("components") or {}), "whole picture (no collider shape)")
        S().button("Footprint")
        s = S().wait(lambda s: (player_doc(s).get("components") or {}).get("collider") == {"kind": "box", "auto": True},
                     "the feet footprint")
        return {"player": {k: player_doc(s).get(k) for k in ("scale", "components")}}

    def s04_three_connected_rooms() -> dict[str, Any]:
        new_room_from(2, 3, "Forest")  # a door in the start room's top-left corner
        room("Forest")
        new_room_from(16, 3, "Cave")
        s = S().state()
        rooms = [w["text"] for w in s["widgets"] if w["type"] == "button" and w["text"] in ("Start", "Forest", "Cave")]
        assert sorted(rooms) == ["Cave", "Forest", "Start"], rooms
        doors = {o["name"] for o in s["objects"] if o["tag"] == "door"}
        assert {"Door to Start", "Door to Cave"} <= doors, doors
        return {"rooms": rooms, "forest_doors": sorted(doors)}

    def s05_one_player_everywhere() -> dict[str, Any]:
        seen = {}
        for label in ("Start", "Forest", "Cave"):
            room(label)
            s = S().state()
            p = player_doc(s)
            seen[label] = {"scale": p.get("scale"), "sprite": p.get("sprite"), "collider": (p.get("components") or {}).get("collider")}
        assert len({json.dumps(v, sort_keys=True) for v in seen.values()}) == 1, seen
        return seen

    def s06_change_once_every_room() -> dict[str, Any]:
        room("Cave")
        select("Player")
        tab("Look")
        S().set_field("look_scale", "0.9")
        S().wait(lambda s: player_doc(s).get("scale") == 0.9, "the player's size in the Cave")
        sizes = {}
        for label in ("Start", "Forest"):
            room(label)
            s = S().state()
            assert player_doc(s).get("scale") == 0.9, (label, player_doc(s).get("scale"))
            sizes[label] = S().obj("Player")["rect"][2:]
        return {"player_size_on_screen": sizes}

    def s07_npc_in_the_forest() -> None:
        room("Forest")
        S().button("Person")
        S().click_cell(9, 7)
        S().wait(lambda s: any(o["name"] == "Person" for o in s["objects"]), "the placed Person")
        S().set_field("name", "Ranger")
        S().wait(lambda s: any(o["name"] == "Ranger" for o in s["objects"]), "the Ranger")

    def s08_find_patrol_by_name() -> dict[str, Any]:
        select("Ranger")
        tab("Behaviours")
        S().button("+ Add behaviour")
        S().wait(lambda s: s["panel"] == "add_behaviour", "the behaviour picker")
        S().d.type_text("walk")
        s = S().wait(lambda s: any(w["type"] == "button" and w["text"] == "Walk between points" for w in s["widgets"]),
                     "'Walk between points' in the search results")
        S().button("Walk between points")
        S().wait(lambda s: "Patrol" in S().obj("Ranger")["behaviours"], "the Ranger's new behaviour")
        return {"offered": [w["text"] for w in s["widgets"] if w["type"] == "button"][:12]}

    def s09_click_the_route() -> dict[str, Any]:
        S().button("Edit route on the map")
        S().wait(lambda s: s["panel"] == "route", "the route editor")
        for cell in ((13, 7), (13, 11), (9, 11)):
            S().click_cell(*cell)
        s = S().wait(lambda s: len((s.get("route") or {}).get("points", [])) == 3, "three route points")
        assert not s["route"]["problems"], s["route"]["problems"]
        return {"points": s["route"]["points"]}

    def s10_unreachable_point_warns() -> dict[str, Any]:
        S().click_cell(19, 9)  # the room's stone border: inside a wall
        s = S().wait(lambda s: (s.get("route") or {}).get("problems"), "a warning about the new point")
        texts = [p["text"] for p in s["route"]["problems"]]
        shown = {w.get("text") for w in s["widgets"]}
        assert any(t in shown for t in texts), f"the warning isn't on screen: {texts}"
        memo["warning"] = texts
        return {"warnings": texts}

    def s11_fix_it_and_patrol() -> dict[str, Any]:
        s = S().state()
        bad = s["route"]["screen"][3]
        height = s["window"][1]
        x1, y1 = S().cell_xy(16, 9)
        S().d.drag(bad[0], height - bad[1], x1, y1)  # drag the point off the wall
        s = S().wait(lambda s: len(s["route"]["points"]) == 4 and not s["route"]["problems"]
                     and any(w["type"] == "label" and w["text"] == "It can walk this route." for w in s["widgets"]),
                     "a route it can walk, said in the panel")  # the panel has settled: Done is where it's shown
        S().button("Done")
        S().wait(lambda s: s["panel"] != "route", "the route editor closed")
        S().d.key("CTRL+S")
        S().wait(lambda s: not s["dirty"], "saved")
        S().d.key("F4")
        S().wait(lambda s: s["mode"] == "play" and s["play"] and s["play"]["sprites"], "play mode")
        trail = [sprite_at(S().state(), "Ranger")]
        for _ in range(6):
            time.sleep(0.5)
            trail.append(sprite_at(S().state(), "Ranger"))
        S().d.key("F4")
        S().wait(lambda s: s["mode"] == "edit", "back to editing")
        moved = max(abs(a[0] - trail[0][0]) + abs(a[1] - trail[0][1]) for a in trail)
        assert moved > 40, f"the Ranger didn't walk its route: {trail}"
        return {"route": s["route"]["points"], "ranger_trail": trail}

    def s12_dialogue_with_a_flag() -> None:
        room("Start")
        select("Person")
        tab("Dialogue")
        S().set_field("says", "Have you seen the ranger? They walk the forest.")
        S().wait(lambda s: s["message"] == "Dialogue updated.", "the new line")
        S().button(next(w["text"] for w in S().state()["widgets"] if w["type"] == "button" and w["text"].startswith("1. ")))
        S().button("+ Choice")
        S().wait(lambda s: any(w["type"] == "field" and w["key"] == "choice_text" for w in s["widgets"]), "the new choice")
        S().set_field("choice_text", "I'll look for them.")
        # Wait for the commit's rebuild: clicking the next box before it activated the box being replaced, and the
        # flag typed into it was lost (intermittent; more often as the panel grew).
        S().wait(lambda s: s["message"] == "Choice changed.", "the choice's text saved")
        S().set_field("choice_sets", FLAG)
        S().wait(lambda s: FLAG in json.dumps(s["room_doc"]), "the choice setting the flag")

    def s13_narrow_gap() -> dict[str, Any]:
        S().d.key("ESC")
        wall = next(w["text"] for w in S().state()["widgets"] if w["type"] == "tile" and "wall" in w["text"].lower())
        S().tile(wall)
        S().stroke((8, 0), (8, 7))
        S().stroke((8, 9), (8, 15))  # one tile open at row 8
        S().d.key("ESC")
        S().d.key("F4")
        S().wait(lambda s: s["mode"] == "play" and s["play"] and s["play"]["player"], "play mode")
        gap_y = 512 - 8.5 * 32
        start = walk((200.0, gap_y + 14), order=(1, 0), tolerance=5)  # line up with the gap, feet in it
        through = walk((340.0, gap_y + 14), order=(0,), tolerance=10)
        assert through[0] > 300, f"the player didn't get through the gap: {start} -> {through}"
        S().d.key("F4")
        S().wait(lambda s: s["mode"] == "edit", "back to editing")
        return {"before_gap": start, "after_gap": through, "wall_tile": wall}

    def s14_esc_opens_the_menu() -> dict[str, Any]:
        S().d.key("CTRL+S")
        S().wait(lambda s: not s["dirty"], "saved")
        S().d.key("F4")
        S().wait(lambda s: s["mode"] == "play" and s["play"] and s["play"]["player"], "play mode")
        memo["saved_at"] = S().player()
        S().d.key("ESC")
        s = S().wait(lambda s: menu(s) and menu(s)["screen"] == "main", "the game menu")
        items = [i["text"] for i in menu(s)["items"]]
        for wanted in ("Resume", "Save Game", "Load Game", "Exit Play-Test"):
            assert wanted in items, items
        return {"menu": items}

    def s15_save_with_confirmation() -> dict[str, Any]:
        menu_item("Save Game")
        S().wait(lambda s: menu(s) and menu(s)["screen"] == "save", "the save list")
        menu_item("New save")
        s = S().wait(lambda s: "Game saved" in (s["play"] or {}).get("toasts", []), "'Game saved'")
        saves = sorted(p.name for p in (root / "saves").glob("*.json"))
        assert saves, "no save file written"
        menu_item("Resume")
        S().wait(lambda s: not menu(s), "the menu closed")
        return {"toasts": s["play"]["toasts"], "save_files": saves}

    def s16_change_room_and_state() -> dict[str, Any]:
        person = sprite_at(S().state(), "Person")
        walk((person[0] + 44, person[1]), order=(1, 0), tolerance=6)
        S().d.key("E")
        # The line and its choice show together; E picks the highlighted choice.
        S().wait(lambda s: s["play"]["dialogue"] and s["play"]["dialogue"]["choices"], "the Person's line and choice")
        S().d.key("E")
        S().wait(lambda s: s["play"]["flags"].get(FLAG), f"the {FLAG} flag")
        S().wait(lambda s: not s["play"]["dialogue"], "the conversation over")
        door = sprite_at(S().state(), "Door to Forest")
        walk((door[0], door[1]), order=(1, 0), tolerance=6, timeout=30)
        s = S().wait(lambda s: "forest" in str(s["play"]["scene"]).lower(), "the Forest", timeout=15)
        return {"scene": s["play"]["scene"], "flags": s["play"]["flags"]}

    def s17_load_and_verify() -> dict[str, Any]:
        S().d.key("ESC")
        S().wait(lambda s: menu(s) and menu(s)["screen"] == "main", "the game menu")
        menu_item("Load Game")
        s = S().wait(lambda s: menu(s) and menu(s)["screen"] == "load", "the load list")
        labels = [i["text"] for i in menu(s)["items"]]
        menu_item("Saved ")
        s = S().wait(lambda s: "Game loaded" in (s["play"] or {}).get("toasts", []), "'Game loaded'")
        # A save loads as a scene (its path is the save file): the start room is the one with the door to the Forest.
        s = S().wait(lambda s: s["play"]["player"] and {x["name"] for x in s["play"]["sprites"]} >= {"Person", "Door to Forest"}
                     and "Ranger" not in {x["name"] for x in s["play"]["sprites"]}, "back in the start room")
        assert not s["play"]["flags"].get(FLAG), f"the flag set after saving survived the load: {s['play']['flags']}"
        at, saved = s["play"]["player"], memo["saved_at"]
        assert abs(at[0] - saved[0]) < 24 and abs(at[1] - saved[1]) < 24, f"the player is at {at}, saved at {saved}"
        return {"load_list": labels, "player": at, "saved_at": saved, "flags": s["play"]["flags"]}

    def s18_exit_play_test() -> None:
        S().d.key("ESC")
        S().wait(lambda s: menu(s) and menu(s)["screen"] == "main", "the game menu")
        menu_item("Exit Play-Test")
        S().wait(lambda s: s["mode"] == "edit", "back to editing")
        assert held["studio"].proc.poll() is None, "Exit Play-Test closed the Studio"

    def s19_save_and_close() -> None:
        S().d.key("CTRL+S")
        S().wait(lambda s: not s["dirty"], "saved")
        held["studio"].click_close_button()
        held["studio"].proc.wait(timeout=20)
        held["studio"] = None
        studio_layout.unlink(missing_ok=True)
        assert find_window_by_title("Mesh Studio") == 0

    def s20_reopen_everything_kept() -> dict[str, Any]:
        launch()
        L().button(GAME)
        studio_opens()
        prefabs = {p["id"]: p for p in json.loads((root / "assets/prefabs.json").read_text(encoding="utf-8"))}
        player = prefabs["player"]["entity"]
        assert player.get("scale") == 0.9 and player["components"]["collider"] == {"kind": "box", "auto": True}, player
        world = json.loads((root / "packs/core_regions/worlds/main.json").read_text(encoding="utf-8"))
        labels = sorted(v.get("label") for v in world["scenes"].values())
        assert labels == ["Cave", "Forest", "Start"], labels
        room("Forest")
        ranger = next(e for e in S().state()["room_doc"]["entities"] if e.get("name") == "Ranger")
        points = ranger["behaviour_config"]["Patrol"]["patrol_points"]
        assert len(points) == 4, points
        for label in ("Start", "Forest", "Cave"):
            room(label)
            assert player_doc(S().state()).get("scale") == 0.9
        return {"player": player, "rooms": labels, "route": points}

    def s21_play_again_and_load() -> dict[str, Any]:
        room("Start")
        S().d.key("F4")
        S().wait(lambda s: s["mode"] == "play" and s["play"] and s["play"]["player"], "play mode")
        S().d.key("ESC")
        S().wait(lambda s: menu(s) and menu(s)["screen"] == "main", "the game menu")
        menu_item("Load Game")
        s = S().wait(lambda s: menu(s) and menu(s)["screen"] == "load", "the load list")
        labels = [i["text"] for i in menu(s)["items"]]
        menu_item("Saved ")
        s = S().wait(lambda s: "Game loaded" in (s["play"] or {}).get("toasts", []), "'Game loaded'")
        s = S().wait(lambda s: s["play"]["player"] and "Door to Forest" in {x["name"] for x in s["play"]["sprites"]},
                     "the saved room")
        at, saved = s["play"]["player"], memo["saved_at"]
        assert abs(at[0] - saved[0]) < 24 and abs(at[1] - saved[1]) < 24, f"the player is at {at}, saved at {saved}"
        S().d.key("F4")
        S().wait(lambda s: s["mode"] == "edit", "back to editing")
        return {"load_list": labels, "player": at}

    steps = [s01_new_project, s02_player_and_npc_look_different, s03_player_size_and_footprint,
             s04_three_connected_rooms, s05_one_player_everywhere, s06_change_once_every_room, s07_npc_in_the_forest,
             s08_find_patrol_by_name, s09_click_the_route, s10_unreachable_point_warns, s11_fix_it_and_patrol,
             s12_dialogue_with_a_flag, s13_narrow_gap, s14_esc_opens_the_menu, s15_save_with_confirmation,
             s16_change_room_and_state, s17_load_and_verify, s18_exit_play_test, s19_save_and_close,
             s20_reopen_everything_kept, s21_play_again_and_load]
    try:
        for fn in steps:
            if not step(fn.__name__.split("_", 1)[1], fn):
                break
    finally:
        for key in ("studio", "launcher"):
            if held[key] is not None:
                held[key].close()
    passed = len(results) == len(steps) and all(r["ok"] for r in results)
    (out / "report.json").write_text(json.dumps({"passed": passed, "steps": results}, indent=2, default=str), encoding="utf-8")
    print(f"{sum(r['ok'] for r in results)}/{len(steps)} steps passed; report: {out / 'report.json'}")
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO / "artifacts" / "acceptance_creator")
    args = parser.parse_args()
    raise SystemExit(run(args.out))
