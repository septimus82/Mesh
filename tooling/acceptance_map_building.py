"""Acceptance test, Milestone 2: building playable maps in Mesh Studio through the real window.

The owner's sequence, on a fresh `mesh new` project, using OS-level mouse and keyboard
only (the Studio's MESH_STUDIO_LAYOUT dump is read to find things and to check state,
never to act):

 1 open Mesh Studio            7 place an NPC in the room          13 close and reopen
 2 open the starting map       8 give it a Dialogue behaviour      14 everything persisted
 3 paint a floor               9 create a second room              15 play through both rooms
 4 paint walls and obstacles  10 paint a different layout there    16 walls block, doors work
 5 erase tiles and repaint    11 connect the rooms with a door     17 stop: editor unchanged
 6 undo/redo a brush stroke   12 save

Run from the repo root:  py -3.13 tooling/acceptance_map_building.py [--out DIR]
Exit code 0 only if every step passed. Writes DIR/report.json and a screenshot per step.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO))
from acceptance_first_workflow import Page  # noqa: E402
from gui_driver import Driver  # noqa: E402

from engine.schema_validation import validate  # noqa: E402

FLOOR, STONE_WALL, ROCK, FLOWERS, GRASS = "Wood floor", "Stone wall", "Rock", "Flowers", "Grass"
ROOM_COLS, ROOM_ROWS = range(3, 15), range(2, 10)  # outer walls of the room painted in the start map
ENTRANCE = range(7, 10)  # a 3-tile gap in the bottom wall: wide enough for the 64px player


class MapPage(Page):
    def map(self) -> dict[str, Any]:
        return self.wait(lambda s: s.get("map"), "a map on screen")["map"]

    def cell_xy(self, col: int, row: int) -> tuple[float, float]:
        m = self.map()
        x0, y0, x1, y1 = m["screen"]
        sx = x0 + (col + 0.5) / m["width"] * (x1 - x0)
        sy = y0 + (m["height"] - row - 0.5) / m["height"] * (y1 - y0)
        return sx, self.state()["window"][1] - sy

    def tile(self, label: str) -> None:
        found = [w for w in self.state()["widgets"] if w["type"] == "tile" and w["text"] == label]
        if not found:
            raise AssertionError(f"no '{label}' tile in the palette")
        self.d.click(*self._xy(found[0]["rect"]))
        self.wait(lambda s: s["tool"] == "paint" and s["brush"] == found[0]["gid"], f"brush {label}")

    def gid(self, label: str) -> int:
        return next(w["gid"] for w in self.state()["widgets"] if w["type"] == "tile" and w["text"] == label)

    def stroke(self, a: tuple[int, int], b: tuple[int, int]) -> None:
        before = self.map()["layers"]  # every stroke in this test changes at least one tile
        self.d.drag(*self.cell_xy(*a), *self.cell_xy(*b), steps=16)
        self.wait(lambda s: s["map"]["layers"] != before, "the stroke to apply")

    def click_cell(self, col: int, row: int, *, right: bool = False) -> None:
        self.d.click(*self.cell_xy(col, row), right=right)

    def at(self, layer: str, col: int, row: int) -> int:
        m = self.map()
        return m["layers"][layer][row * m["width"] + col]


def run(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    layout = out / "layout.json"
    env = {**os.environ, "PYTHONPATH": str(REPO), "MESH_STUDIO_LAYOUT": str(layout)}
    os.environ.update(env)
    project = work / "village"
    results: list[dict[str, Any]] = []
    holder: dict[str, Any] = {"driver": None, "page": None}
    memo: dict[str, Any] = {}

    def launch() -> MapPage:
        layout.unlink(missing_ok=True)
        driver = Driver([sys.executable, "-m", "mesh_cli", "edit"], cwd=project, shots=out)
        holder["driver"], holder["page"] = driver, MapPage(driver, layout)
        return holder["page"]

    def step(name: str, action: Callable[[], Any]) -> bool:
        started = time.time()
        try:
            detail, ok, error = action(), True, None
        except Exception as exc:  # noqa: BLE001  # REASON: record every failure in the report, then stop
            ok, error, detail = False, f"{type(exc).__name__}: {exc}", traceback.format_exc(limit=4)
        driver = holder["driver"]
        shot = driver.shot(f"{len(results) + 1:02d}_{name}").name if driver and driver.proc.poll() is None else None
        results.append({"step": name, "ok": ok, "error": error, "detail": detail,
                        "seconds": round(time.time() - started, 1), "screenshot": shot})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {error}" if error else ""), flush=True)
        return ok

    def p() -> MapPage:
        return holder["page"]

    def s01_open() -> None:
        subprocess.run([sys.executable, "-m", "mesh_cli", "new", "village"], cwd=work, env=env, check=True, capture_output=True)
        page = launch()
        page.wait(lambda s: s["mode"] == "edit" and s["objects"], "the Studio")

    def s02_starting_map() -> dict[str, Any]:
        m = p().map()
        assert (m["width"], m["height"]) == (24, 16), m
        assert set(m["layers"]["ground"]) == {p().gid(GRASS)}, "the starting map is a grass field"
        return {"size": [m["width"], m["height"]], "tile": m["tilewidth"]}

    def s03_paint_floor() -> None:
        p().tile(FLOOR)
        for row in range(ROOM_ROWS.start + 1, ROOM_ROWS.stop - 1):
            p().stroke((ROOM_COLS.start + 1, row), (ROOM_COLS.stop - 2, row))
        floor = p().gid(FLOOR)
        bad = [(c, r) for r in range(ROOM_ROWS.start + 1, ROOM_ROWS.stop - 1)
               for c in range(ROOM_COLS.start + 1, ROOM_COLS.stop - 1) if p().at("ground", c, r) != floor]
        assert not bad, f"unpainted floor cells: {bad[:5]}"

    def s04_walls_and_obstacles() -> None:
        p().tile(STONE_WALL)
        top, bottom, left, right = ROOM_ROWS.start, ROOM_ROWS.stop - 1, ROOM_COLS.start, ROOM_COLS.stop - 1
        p().stroke((left, top), (right, top))
        p().stroke((left, bottom), (right, bottom))
        p().stroke((left, top), (left, bottom))
        p().stroke((right, top), (right, bottom))
        p().tile(ROCK)
        p().click_cell(11, 4)
        p().wait(lambda s: p().at("walls", 11, 4) == p().gid(ROCK), "the rock")
        wall = p().gid(STONE_WALL)
        assert all(p().at("walls", c, top) == wall and p().at("walls", c, bottom) == wall for c in ROOM_COLS)
        assert all(p().at("walls", left, r) == wall and p().at("walls", right, r) == wall for r in ROOM_ROWS)

    def s05_erase_and_repaint() -> None:
        bottom = ROOM_ROWS.stop - 1
        p().d.click(*p()._xy(next(w for w in p().state()["widgets"] if w.get("text") == "Eraser")["rect"]))
        p().wait(lambda s: s["tool"] == "erase", "the eraser")
        p().stroke((ENTRANCE.start - 1, bottom), (ENTRANCE.stop, bottom))
        assert all(p().at("walls", c, bottom) == 0 for c in range(ENTRANCE.start - 1, ENTRANCE.stop + 1))
        p().tile(STONE_WALL)
        p().click_cell(ENTRANCE.start - 1, bottom)
        p().click_cell(ENTRANCE.stop, bottom)
        p().wait(lambda s: p().at("walls", ENTRANCE.stop, bottom) == p().gid(STONE_WALL), "the repainted wall")
        assert all(p().at("walls", c, bottom) == 0 for c in ENTRANCE), "the entrance stays open"

    def s06_undo_redo_stroke() -> dict[str, Any]:
        p().tile(FLOWERS)
        cells = [(c, 13) for c in range(15, 21)]
        p().stroke(cells[0], cells[-1])
        flowers, grass = p().gid(FLOWERS), p().gid(GRASS)
        assert all(p().at("ground", c, r) == flowers for c, r in cells)
        p().d.key("CTRL+Z")
        p().wait(lambda s: all(p().at("ground", c, r) == grass for c, r in cells), "undo removing the whole stroke at once")
        p().d.key("CTRL+Y")
        p().wait(lambda s: all(p().at("ground", c, r) == flowers for c, r in cells), "redo restoring the whole stroke")
        return {"stroke_cells": len(cells)}

    def s07_place_npc() -> None:
        p().d.key("ESC")  # back to Select
        p().wait(lambda s: s["tool"] == "select", "the Select tool")
        p().button("Person")
        p().click_cell(11, 7)
        p().wait(lambda s: s["selected"] and any(o["name"].startswith("Person") for o in s["objects"]), "the NPC")
        p().set_field("name", "Elder")
        p().wait(lambda s: any(o["name"] == "Elder" for o in s["objects"]), "the NPC named Elder")

    def s08_dialogue_behaviour() -> None:
        # Take the Person's Dialogue off (Behaviours tab), then add it back through the right-click menu.
        p().button("Behaviours")
        p().wait(lambda s: s["tab"] == "behaviours", "the Behaviours tab")
        p().button("Remove", nth=0)
        p().wait(lambda s: s["message"] == "Removed Dialogue.", "Dialogue removed")
        p().click_obj("Elder", right=True)
        p().wait(lambda s: any(w["text"] == "Add behaviour..." for w in s["widgets"]), "the context menu")
        p().button("Add behaviour...")
        p().wait(lambda s: s["panel"] == "add_behaviour", "the behaviour picker")
        p().d.type_text("Dialogue")
        p().wait(lambda s: any(w["type"] == "button" and w["text"] == "Dialogue" for w in s["widgets"]), "Dialogue listed")
        p().button("Dialogue")
        p().wait(lambda s: s["message"] == "Added Dialogue.", "Dialogue added")
        p().button("Dialogue")  # what they say is on the Dialogue tab
        p().wait(lambda s: s["tab"] == "dialogue", "the Dialogue tab")
        p().set_field("says", "Welcome to my room!")
        p().wait(lambda s: s["message"] == "Dialogue updated.", "the line saved")

    def s09_second_room() -> dict[str, Any]:
        p().button("+ New room")
        p().wait(lambda s: s["panel"] == "new_room", "the new-room form")
        p().d.type_text("Cabin")
        p().button("Create")
        s = p().wait(lambda s: s["room"] == "cabin" and s.get("map"), "the new room open for editing")
        m = s["map"]
        assert set(m["layers"]["ground"]) == {p().gid(FLOOR)}, "a new room starts with a floor"
        assert m["layers"]["walls"][0] == p().gid(STONE_WALL), "and a wall around it"
        return {"size": [m["width"], m["height"]]}

    def s10_paint_second_room() -> None:
        p().tile("Carpet")
        for row in range(3, 6):
            p().stroke((3, row), (6, row))
        p().tile("Water")
        for row in range(3, 6):
            p().stroke((13, row), (16, row))
        p().tile("Tree")
        p().click_cell(14, 10)
        p().click_cell(15, 10)
        p().wait(lambda s: p().at("walls", 15, 10) == p().gid("Tree"), "the trees")
        assert p().at("ground", 4, 4) == p().gid("Carpet") and p().at("walls", 14, 4) == p().gid("Water")

    def s11_connect_rooms() -> None:
        p().d.key("ESC")
        p().button("Start")
        p().wait(lambda s: s["room"] == "start", "back in the start room")
        p().click_cell(8, 4, right=True)  # inside the room, under its top wall
        p().wait(lambda s: any(w["text"] == "Add door to Cabin" for w in s["widgets"]), "the map context menu")
        p().button("Add door to Cabin")
        p().wait(lambda s: any(o["tag"] == "door" for o in s["objects"]), "a door in the start room")

    def s12_save() -> None:
        p().d.key("CTRL+S")
        memo["start_tiles"] = p().wait(lambda s: not s["dirty"], "everything saved")["map"]["layers"]

    def s13_close_and_reopen() -> None:
        holder["driver"].close()
        launch().wait(lambda s: s["mode"] == "edit" and s["objects"] and s.get("map"), "the Studio reopened")

    def s14_persisted() -> dict[str, Any]:
        s = p().state()
        assert s["map"]["layers"] == memo["start_tiles"], "the start map's tiles changed across save and reopen"
        names = {o["name"] for o in s["objects"]}
        assert {"Elder", "Door to Cabin"} <= names, names
        start = json.loads((project / "packs/core_regions/scenes/start.json").read_text(encoding="utf-8"))
        elder = next(e for e in start["entities"] if e.get("name") == "Elder")
        assert "Dialogue" in elder["behaviours"]
        assert elder["behaviour_config"]["Dialogue"]["dialogue"]["nodes"]["root"]["text"] == "Welcome to my room!"
        cabin = json.loads((project / "packs/core_regions/scenes/cabin.json").read_text(encoding="utf-8"))
        assert any(e.get("tag") == "door" for e in cabin["entities"])
        validate(start, "scene.schema.json", "start.json")  # the saved rooms are valid scenes
        validate(cabin, "scene.schema.json", "cabin.json")
        carpet = p().gid("Carpet")
        assert carpet in cabin["tilemap"]["tile_layers"][0]["tiles"]
        p().button("Cabin")
        s = p().wait(lambda s: s["room"] == "cabin" and s.get("map"), "the Cabin")
        assert p().at("walls", 14, 10) == p().gid("Tree") and p().at("ground", 4, 4) == carpet
        p().button("Start")
        p().wait(lambda s: s["room"] == "start", "the start room")
        return {"objects": sorted(names)}

    def door_and_arrival(scene_file: str) -> tuple[dict[str, Any], dict[str, Any]]:
        scene = json.loads((project / scene_file).read_text(encoding="utf-8"))
        door = next(e for e in scene["entities"] if e.get("tag") == "door")
        arrival = next(e for e in scene["entities"] if e.get("tag") == "spawn_point")
        return door, arrival

    def s15_play_both_rooms() -> dict[str, Any]:
        p().d.key("F4")
        p().wait(lambda s: s["mode"] == "play", "play mode")
        door, _ = door_and_arrival("packs/core_regions/scenes/start.json")
        entrance_x = (ENTRANCE.start + ENTRANCE.stop - 1) / 2 * 32 + 16
        p().walk_to((entrance_x, p().player()[1]), tolerance=6)  # line up with the entrance
        p().walk_to((door["x"], door["y"] - 64), tolerance=8)   # through the entrance, up to the door
        p().d.hold("W", 0.7)
        p().wait(lambda s: s["play"]["scene"].endswith("cabin.json"), "arriving in the Cabin")
        time.sleep(1.0)
        s = p().state()
        cabin_door, cabin_arrival = door_and_arrival("packs/core_regions/scenes/cabin.json")
        arrived = s["play"]["player"]
        assert s["play"]["scene"].endswith("cabin.json"), "bounced back out of the Cabin"
        assert abs(arrived[0] - cabin_arrival["x"]) < 40 and abs(arrived[1] - cabin_arrival["y"]) < 40, arrived
        p().walk_to((cabin_door["x"], cabin_door["y"] - 64), tolerance=8)
        p().d.hold("W", 0.7)
        p().wait(lambda s: s["play"]["scene"].endswith("start.json"), "back in the start room")
        time.sleep(1.0)
        return {"arrived_in_cabin_at": arrived, "back_at": p().player()}

    def s16_walls_block() -> dict[str, Any]:
        before = p().player()
        p().d.hold("A", 1.6)  # walk at the room's left wall
        after = p().player()
        wall_inner_edge = (ROOM_COLS.start + 1) * 32
        assert after[0] < before[0] - 20, f"the player should have walked left: {before} -> {after}"
        assert after[0] >= wall_inner_edge + 24, f"the player walked into the wall: x={after[0]:.0f}"
        p().d.hold("W", 1.6)  # and at the top wall
        top = p().player()
        top_wall_inner_edge = (16 - ROOM_ROWS.start) * 32 - 32
        assert top[1] <= top_wall_inner_edge - 24, f"the player walked into the top wall: y={top[1]:.0f}"
        return {"from": before, "stopped_at_left_wall": after, "stopped_at_top_wall": top}

    def s17_stop_unchanged() -> None:
        p().d.key("F4")
        s = p().wait(lambda s: s["mode"] == "edit" and s.get("map"), "back to editing")
        assert not s["dirty"], "play must not change the documents"
        assert s["map"]["layers"] == memo["start_tiles"], "play must not change the map"

    # --- the surrounding interactions (after the owner's 17 steps, same window) --------------
    def x_drag_object_paints_nothing() -> dict[str, Any]:
        tiles = p().map()["layers"]
        guide = p().obj("Guide")
        x, y = p()._xy(guide["rect"])
        p().d.drag(x, y, x + 96, y, steps=10)
        moved = p().wait(lambda s: p().obj("Guide")["x"] != guide["x"], "the Guide to move")
        assert moved["map"]["layers"] == tiles, "dragging an object must not paint"
        to = p().obj("Guide")["x"]
        p().d.key("CTRL+Z")
        p().wait(lambda s: p().obj("Guide")["x"] == guide["x"], "undo moving it back")
        return {"from_x": guide["x"], "to_x": to}

    def x_painting_over_an_object_leaves_it() -> None:
        elder = p().obj("Elder")
        col, row = int(elder["x"] // 32), 15 - int(elder["y"] // 32)
        p().tile(GRASS)
        p().stroke((col, row), (col + 1, row))
        s = p().state()
        assert p().at("ground", col, row) == p().gid(GRASS)
        assert (p().obj("Elder")["x"], p().obj("Elder")["y"]) == (elder["x"], elder["y"]), "painting moved the Elder"
        assert s["selected"] != elder["id"], "painting selected the Elder"
        p().d.key("CTRL+Z")
        p().wait(lambda s: p().at("ground", col, row) == p().gid(FLOOR), "undo of the stroke")

    def x_typing_never_triggers_shortcuts() -> None:
        p().d.key("ESC")
        p().click_obj("Elder")
        p().wait(lambda s: s["selected"] == p().obj("Elder")["id"], "the Elder selected")
        screen, count = p().map()["screen"], len(p().state()["objects"])
        field = p().field("name")
        x, y = p()._xy(field["rect"])
        p().d.click(x + field["rect"][2] / 2 - 6, y)
        p().d.type_text(" wasd")  # would pan the view if it reached the map
        for combo in ("DELETE", "CTRL+Z", "CTRL+S", "F4"):
            p().d.key(combo)
        p().d.key("ENTER")
        s = p().wait(lambda s: any(o["name"] == "Elder wasd" for o in s["objects"]), "the rename")
        assert s["mode"] == "edit" and s["dirty"], "F4/Ctrl+S in a text field must not play or save"
        assert s["map"]["screen"] == screen and len(s["objects"]) == count

    def x_zoom_pan_then_paint() -> dict[str, Any]:
        before = p().map()["screen"]
        cx, cy = p().cell_xy(12, 8)
        p().d.scroll(cx, cy, 3)
        zoomed = p().wait(lambda s: s["map"]["screen"][2] - s["map"]["screen"][0] > before[2] - before[0] + 50, "zoom in")
        p().d.drag(cx, cy, cx - 120, cy - 60, steps=8, button="middle")
        panned = p().wait(lambda s: s["map"]["screen"][0] < zoomed["map"]["screen"][0] - 60, "the view to pan")
        p().tile("Sand")
        p().click_cell(12, 8)
        p().wait(lambda s: p().at("ground", 12, 8) == p().gid("Sand"), "the tile under the cursor painted")
        p().d.key("CTRL+Z")
        p().wait(lambda s: p().at("ground", 12, 8) != p().gid("Sand"), "undo of the sand")
        return {"zoom": [before, zoomed["map"]["screen"], panned["map"]["screen"]]}

    def x_right_click_with_a_brush_opens_the_menu() -> None:
        tiles = p().map()["layers"]
        p().click_cell(20, 2, right=True)
        s = p().wait(lambda s: any(w["text"].startswith("Add door to") for w in s["widgets"]), "the map menu")
        assert s["map"]["layers"] == tiles, "a right-click must not paint"
        p().d.key("ESC")
        p().wait(lambda s: s["tool"] == "select" and not any(w["text"].startswith("Add door to") for w in s["widgets"]), "Esc closing it")

    def x_switching_rooms_keeps_unsaved_paint() -> None:
        p().button("Cabin")
        p().wait(lambda s: s["room"] == "cabin", "the Cabin")
        p().tile("Sand")
        p().click_cell(10, 12)
        p().wait(lambda s: p().at("ground", 10, 12) == p().gid("Sand"), "the sand")
        p().button("Start")
        p().wait(lambda s: s["room"] == "start", "the start room")
        p().button("Cabin")
        s = p().wait(lambda s: s["room"] == "cabin" and s.get("map"), "the Cabin again")
        assert p().at("ground", 10, 12) == p().gid("Sand") and s["dirty"]

    steps = [s01_open, s02_starting_map, s03_paint_floor, s04_walls_and_obstacles, s05_erase_and_repaint,
             s06_undo_redo_stroke, s07_place_npc, s08_dialogue_behaviour, s09_second_room, s10_paint_second_room,
             s11_connect_rooms, s12_save, s13_close_and_reopen, s14_persisted, s15_play_both_rooms,
             s16_walls_block, s17_stop_unchanged,
             x_drag_object_paints_nothing, x_painting_over_an_object_leaves_it, x_typing_never_triggers_shortcuts,
             x_zoom_pan_then_paint, x_right_click_with_a_brush_opens_the_menu, x_switching_rooms_keeps_unsaved_paint]
    try:
        for fn in steps:
            if not step(fn.__name__.split("_", 1)[1] if fn.__name__[0] == "s" else fn.__name__, fn):
                break
    finally:
        if holder["driver"] is not None:
            holder["driver"].close()
    passed = len(results) == len(steps) and all(r["ok"] for r in results)
    (out / "report.json").write_text(json.dumps({"passed": passed, "steps": results}, indent=2, default=str), encoding="utf-8")
    print(f"{sum(r['ok'] for r in results)}/{len(steps)} steps passed (17 owner steps + {len(steps) - 17} interaction checks); report: {out / 'report.json'}")
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO / "artifacts" / "acceptance_map_building")
    raise SystemExit(run(parser.parse_args().out))
