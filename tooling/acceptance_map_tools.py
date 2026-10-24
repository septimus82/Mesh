"""Acceptance test, Milestone 3: map tools in Mesh Studio, through the real window.

On a fresh `mesh new` project, with OS-level mouse and keyboard input only (the
layout dump is read to find things and check state, never to act):

 1 open the Studio                       9 text-field clipboard (Ctrl+A/X/C/V)
 2 import a 16 px tileset (file dialog)  10 save
 3 rectangle on the ground; undo/redo    11 close and reopen
 4 rectangle of walls (a house)          12 tiles, tileset, objects persisted
 5 eraser: a doorway                     13 play: walk under the canopy (drawn over the
 6 fill the yard; undo/redo                 player, never blocking)
 7 a 2-tile stamp above the player       14 the imported walls block
 8 copy and paste an object              15 stop: editor unchanged

Run from the repo root:  py -3.13 tooling/acceptance_map_tools.py [--out DIR]
Exit code 0 only if every step passed. Writes DIR/report.json and a screenshot per step.
Keep hands off the mouse while it runs: the driver stops if the cursor moves under it.
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
from acceptance_map_building import MapPage  # noqa: E402
from gui_driver import Driver  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from engine.schema_validation import validate  # noqa: E402

# The imported tileset: 4 x 3 tiles of 16 px, plus a 4 px strip that isn't a whole tile.
DIRT, STONE, WALL, WATER, CANOPY = (140, 100, 60), (150, 150, 160), (90, 60, 40), (40, 90, 200), (20, 200, 90)
YARD = ((2, 2), (10, 8))
HOUSE = ((4, 3), (8, 5))
DOOR = (6, 5)
CANOPY_AT = (14, 6)
GRASS = 1  # the starter tileset's grass (its palette is not on screen once Meadow is shown)


def make_tileset(path: Path) -> None:
    image = Image.new("RGBA", (64, 52), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    colours = [DIRT, STONE, WALL, WATER, CANOPY, CANOPY, (200, 60, 60), (230, 210, 80),
               (120, 80, 160), (60, 160, 160), (200, 120, 40), (90, 90, 90)]
    for i, colour in enumerate(colours):
        x, y = (i % 4) * 16, (i // 4) * 16
        if i in (4, 5):  # treetops (a 2-tile pair on the second row): round, transparent around the edges
            draw.ellipse([x, y, x + 15, y + 15], fill=(*colour, 255))
            draw.rectangle([x + 3, y + 3, x + 12, y + 12], fill=(*colour, 255))
        else:
            draw.rectangle([x, y, x + 15, y + 15], fill=(*colour, 255))
    draw.rectangle([0, 48, 63, 51], fill=(255, 0, 0, 255))  # the leftover strip
    image.save(path)


def cells(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    return [(c, r) for r in range(a[1], b[1] + 1) for c in range(a[0], b[0] + 1)]


def run(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    layout = out / "layout.json"
    env = {**os.environ, "PYTHONPATH": str(REPO), "MESH_STUDIO_LAYOUT": str(layout)}
    os.environ.update(env)
    project = work / "village"
    sheet = work / "my art" / "meadow_tiles.png"  # outside the project, with a space in the path
    results: list[dict[str, Any]] = []
    holder: dict[str, Any] = {"driver": None, "page": None}
    memo: dict[str, Any] = {}

    def launch() -> MapPage:
        layout.unlink(missing_ok=True)
        driver = Driver([sys.executable, "-m", "mesh_cli", "edit"], cwd=project, shots=out)
        holder["driver"], holder["page"] = driver, MapPage(driver, layout)
        return holder["page"]

    def p() -> MapPage:
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

    def gid(label: str) -> int:
        value: int = p().gid(label)
        return value

    def layer_is(layer: str, where: list[tuple[int, int]], value: int) -> bool:
        return all(p().at(layer, c, r) == value for c, r in where)

    def drag_cells(a: tuple[int, int], b: tuple[int, int]) -> None:
        before = p().map()["layers"]
        p().d.drag(*p().cell_xy(*a), *p().cell_xy(*b), steps=16)
        p().wait(lambda s: s["map"]["layers"] != before, "the shape to apply")

    def click_cell_and_wait(cell: tuple[int, int]) -> None:
        before = p().map()["layers"]
        p().click_cell(*cell)
        p().wait(lambda s: s["map"]["layers"] != before, "the click to apply")

    def tile_xy(label: str) -> tuple[float, float]:
        found = [w for w in p().state()["widgets"] if w["type"] == "tile" and w["text"] == label]
        if not found:
            raise AssertionError(f"no '{label}' tile on the palette")
        value: tuple[float, float] = p()._xy(found[0]["rect"])
        return value

    def field_click(key: str) -> None:
        field = p().field(key)
        x, y = p()._xy(field["rect"])
        p().d.click(x + field["rect"][2] / 2 - 6, y)
        p().wait(lambda s: p().field(key)["active"], f"the {key} field to take the keyboard")

    # --- the steps ------------------------------------------------------------------------
    def s01_open() -> None:
        sheet.parent.mkdir(parents=True)
        make_tileset(sheet)
        subprocess.run([sys.executable, "-m", "mesh_cli", "new", "village"], cwd=work, env=env, check=True, capture_output=True)
        launch().wait(lambda s: s["mode"] == "edit" and s.get("map") and s["tilesets"] == ["Starter"], "the Studio")

    def s02_import_tileset() -> dict[str, Any]:
        p().button("Import...")
        p().wait(lambda s: s["panel"] == "import_tileset", "the import form")
        p().button("Browse...")
        p().d.file_dialog(str(sheet))
        p().wait(lambda s: Path(p().field("tileset_path")["text"]) == sheet, "the chosen file in the form")
        assert p().field("tile_size")["text"] == "32", "52 px high fits no common size, so the guess is 32"
        p().set_field("tile_size", "16")
        p().wait(lambda s: p().field("tile_size")["text"] == "16", "the tile size")
        p().set_field("tileset_name", "Meadow")
        p().wait(lambda s: any(w["type"] == "preview" for w in s["widgets"]), "the preview")
        p().d.shot(f"{len(results) + 1:02d}_import_form_filled")
        p().button("Import")
        s = p().wait(lambda s: s["tilesets"] == ["Starter", "Meadow"] and s["sheet"] == "Meadow", "the imported tileset")
        with Image.open(project / "assets/tilesets/meadow.png") as img:
            assert img.size == (128, 96), f"12 tiles scaled to 32 px, strip cut off: {img.size}"
            assert img.getpixel((0, 32))[3] == 0, "transparency kept (treetop corners are see-through)"
            assert img.getpixel((16, 16))[:3] == DIRT
        tileset = json.loads((project / "assets/tilesets/meadow.json").read_text(encoding="utf-8"))
        assert (tileset["tilecount"], tileset["columns"], tileset["tilewidth"]) == (12, 4, 32), tileset
        start_map = json.loads((project / "packs/core_regions/maps/start.json").read_text(encoding="utf-8"))
        assert start_map["tilesets"][1] == {"firstgid": 17, "source": "../../../assets/tilesets/meadow.json"}
        assert gid("Meadow 1") == 17 and len([w for w in s["widgets"] if w.get("tileset") == "Meadow"]) == 12
        return {"tilesets": s["tilesets"]}

    def s03_rect_ground_undo_redo() -> None:
        p().button("Ground")
        p().tile("Meadow 1")
        p().button("Rect")
        p().wait(lambda s: s["shape"] == "rect" and s["layer"] == "ground", "the rectangle tool on the ground")
        drag_cells(*YARD)
        yard = cells(*YARD)
        assert layer_is("ground", yard, 17), "every cell of the rectangle is dirt"
        assert p().at("ground", 11, 2) == GRASS, "nothing outside the rectangle"
        p().d.key("CTRL+Z")
        p().wait(lambda s: layer_is("ground", yard, GRASS), "one undo taking back the whole rectangle")
        p().d.key("CTRL+Y")
        p().wait(lambda s: layer_is("ground", yard, 17), "redo")

    def s04_rect_walls() -> None:
        p().button("Walls")
        p().tile("Meadow 3")
        p().wait(lambda s: s["layer"] == "walls" and s["shape"] == "rect", "walls, rectangle")
        drag_cells(*HOUSE)
        assert layer_is("walls", cells(*HOUSE), 19)
        assert layer_is("ground", cells(*HOUSE), 17), "walls go on their own layer; the ground stays"

    def s05_eraser_doorway() -> None:
        p().button("Brush")
        p().button("Eraser")
        p().wait(lambda s: s["tool"] == "erase" and s["shape"] == "brush", "the eraser brush")
        click_cell_and_wait(DOOR)
        assert p().at("walls", *DOOR) == 0 and p().at("ground", *DOOR) == 17, "erased the wall only"

    def s06_fill_yard_undo_redo() -> dict[str, Any]:
        p().button("Ground")
        p().tile("Meadow 2")
        p().button("Fill")
        p().wait(lambda s: s["shape"] == "fill" and s["layer"] == "ground", "the fill tool on the ground")
        click_cell_and_wait((3, 7))
        under_walls = [c for c in cells(*HOUSE) if c != DOOR]
        open_yard = [c for c in cells(*YARD) if c not in under_walls]
        assert layer_is("ground", open_yard, 18), "the whole yard, including the doorway"
        assert layer_is("ground", under_walls, 17), "the fill stops at walls"
        assert p().at("ground", 11, 2) == GRASS and p().at("ground", 0, 0) == GRASS, "and at other tiles"
        message = p().state()["message"]
        p().d.key("CTRL+Z")
        p().wait(lambda s: layer_is("ground", open_yard, 17), "one undo taking back the whole fill")
        p().d.key("CTRL+Y")
        p().wait(lambda s: layer_is("ground", open_yard, 18), "redo")
        return {"message": message, "filled": len(open_yard)}

    def s07_stamp_above() -> None:
        p().button("Above")
        p().d.drag(*tile_xy("Meadow 5"), *tile_xy("Meadow 6"), steps=6)
        p().wait(lambda s: s["stamp"] == [[21, 22]] and s["layer"] == "overhead", "a 2-tile stamp on the layer above")
        p().button("Brush")
        click_cell_and_wait(CANOPY_AT)
        right = (CANOPY_AT[0] + 1, CANOPY_AT[1])
        assert p().at("overhead", *CANOPY_AT) == 21 and p().at("overhead", *right) == 22
        assert p().at("walls", *CANOPY_AT) == 0 and p().at("ground", *CANOPY_AT) == GRASS

    def s08_copy_paste_object() -> dict[str, Any]:
        p().d.key("ESC")
        p().wait(lambda s: s["tool"] == "select", "the Select tool")
        p().click_obj("Guide")
        p().wait(lambda s: s["selected"] == p().obj("Guide")["id"], "the Guide selected")
        p().d.key("CTRL+C")
        p().wait(lambda s: s["clipboard"] == "Guide", "the Guide copied")
        p().click_cell(18, 12)  # an empty spot: deselects, and puts the mouse there
        p().d.key("CTRL+V")
        s = p().wait(lambda s: any(o["name"] == "Guide 2" for o in s["objects"]), "the pasted copy")
        pasted = p().obj("Guide 2")
        assert s["selected"] == pasted["id"], "the copy is selected"
        assert abs(pasted["x"] - (18 * 32 + 16)) <= 16 and abs(pasted["y"] - (512 - 12.5 * 32)) <= 16, pasted
        return {"pasted_at": [pasted["x"], pasted["y"]]}

    def s09_text_clipboard() -> dict[str, Any]:
        original = p().field("says")["text"]
        field_click("says")
        p().d.key("CTRL+A")
        p().d.key("CTRL+X")
        p().wait(lambda s: p().field("says")["text"] == "", "cut emptying the field")
        p().d.type_text("Hi! ")
        p().d.key("CTRL+V")
        flat = " ".join(original.splitlines())  # text fields are one line: pasted line breaks become spaces
        p().wait(lambda s: p().field("says")["text"] == "Hi! " + flat, "paste after the typed text")
        p().d.key("ENTER")
        p().wait(lambda s: s["message"] == "Dialogue updated.", "the line saved")
        field_click("name")
        p().d.key("CTRL+A")
        p().d.key("CTRL+C")
        p().d.key("ESC")
        field_click("says")
        p().d.key("CTRL+A")
        p().d.key("CTRL+V")
        p().d.key("ENTER")
        s = p().wait(lambda s: p().field("says")["text"] == "Guide 2", "the copied name pasted over the line")
        assert s["clipboard"] == "Guide", "Ctrl+C in a text field copies text, not the object"
        assert any(o["name"] == "Guide 2" for o in s["objects"]), "Ctrl+X/Ctrl+C in a field never touch objects"
        return {"says": p().field("says")["text"]}

    def s10_save() -> None:
        p().d.key("CTRL+S")
        memo["layers"] = p().wait(lambda s: not s["dirty"], "everything saved")["map"]["layers"]

    def s11_close_and_reopen() -> None:
        holder["driver"].close()
        launch().wait(lambda s: s["mode"] == "edit" and s.get("map") and s["tilesets"] == ["Starter", "Meadow"], "the Studio")

    def s12_persisted() -> None:
        s = p().state()
        assert s["map"]["layers"] == memo["layers"], "tiles changed across save and reopen"
        start = json.loads((project / "packs/core_regions/scenes/start.json").read_text(encoding="utf-8"))
        validate(start, "scene.schema.json", "start.json")
        copy = next(e for e in start["entities"] if e.get("name") == "Guide 2")
        assert copy["behaviour_config"]["Dialogue"]["dialogue"]["nodes"]["root"]["text"] == "Guide 2"
        overhead = next(la for la in start["tilemap"]["tile_layers"] if la["id"] == "overhead")
        assert overhead["collision"] is False and overhead["z"] >= 0

    def s13_play_under_the_canopy() -> dict[str, Any]:
        p().d.key("F4")
        p().wait(lambda s: s["mode"] == "play", "play mode")
        x, y = (CANOPY_AT[0] + 0.5) * 32, 512 - (CANOPY_AT[1] + 0.5) * 32
        p().walk_to((x, p().player()[1]), tolerance=6)
        p().walk_to((x, y), tolerance=6)
        time.sleep(0.5)
        screen = p().state()["play"]["player_screen"]
        sx, sy = screen[0], p().state()["window"][1] - screen[1]
        on_player, beside = p().d.pixel(sx, sy), p().d.pixel(sx + 40, sy)  # +40: canopy, clear of the 64 px player
        assert beside[1] > beside[0] + 40 and beside[1] > beside[2] + 40, f"the canopy should be green: {beside}"
        assert all(abs(a - b) <= 8 for a, b in zip(on_player, beside)), f"the canopy should cover the player: {on_player} vs {beside}"
        colour = on_player
        p().d.shot(f"{len(results) + 1:02d}_player_under_the_canopy")
        p().walk_to((x, y + 112), tolerance=8)  # and it never blocks: walk on through
        return {"under_canopy_pixel": colour, "walked_to": p().player()}

    def s14_imported_walls_block() -> dict[str, Any]:
        p().walk_to((p().player()[0], 240), tolerance=8)
        p().walk_to((176, 240), tolerance=6)  # below the house's left part
        p().d.hold("W", 1.4)
        stopped = p().player()
        wall_bottom = 512 - (HOUSE[1][1] + 1) * 32
        # The player collides with its feet (Milestone 11): the top of the feet box meets the wall's bottom edge.
        h = next(sp["size"][1] for sp in p().state()["play"]["sprites"] if sp["name"] == "Player")
        feet_top = -h / 2 + max(8.0, h * 0.25)  # physics_runtime.footprint, relative to the centre
        expected = wall_bottom - feet_top
        assert expected - 6 <= stopped[1] <= expected + 4, f"should stop with its feet at the wall: {stopped}, expected {expected}"
        return {"stopped_at": stopped}

    def s15_stop_unchanged() -> None:
        p().d.key("F4")
        s = p().wait(lambda s: s["mode"] == "edit" and s.get("map"), "back to editing")
        assert not s["dirty"] and s["map"]["layers"] == memo["layers"]

    steps = [s01_open, s02_import_tileset, s03_rect_ground_undo_redo, s04_rect_walls, s05_eraser_doorway,
             s06_fill_yard_undo_redo, s07_stamp_above, s08_copy_paste_object, s09_text_clipboard, s10_save,
             s11_close_and_reopen, s12_persisted, s13_play_under_the_canopy, s14_imported_walls_block,
             s15_stop_unchanged]
    try:
        for fn in steps:
            if not step(fn.__name__.split("_", 1)[1], fn):
                break
    finally:
        if holder["driver"] is not None:
            holder["driver"].close()
    passed = len(results) == len(steps) and all(r["ok"] for r in results)
    (out / "report.json").write_text(json.dumps({"passed": passed, "steps": results}, indent=2, default=str), encoding="utf-8")
    print(f"{sum(r['ok'] for r in results)}/{len(steps)} steps passed; report: {out / 'report.json'}")
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO / "artifacts" / "acceptance_map_tools")
    raise SystemExit(run(parser.parse_args().out))
