"""Acceptance test, Milestone 5: authoring a small conditional, animated, dialogue-driven scene
entirely in Mesh Studio, through the real window, then playing it.

The cemetery scene (a shovel, a grave you can only dig with it, a gravekeeper who appears
once it's dug) is built on a fresh Blank project with OS-level mouse and keyboard only.
The Studio's MESH_STUDIO_LAYOUT dump is read to find things on screen and to check state;
saved files are read only to check what was written, never to write anything. The art is
generated here (small coloured fixtures), so the test runs anywhere.

 1 import and assign a character sprite        10 the gravekeeper appears when the grave is dug
 2 a four-direction walking animation           11 ... with a conversation that has a choice
 3 place a shovel you can take                  12 size a collider and a trigger zone by dragging
 4 a flag for having the shovel                 13 save and close
 5 place a grave                                14 reopen: everything persisted
 6 examining it says something                  15 play it through
 7 digging needs the shovel                     16 quick-save, change things, quick-load
 8 digging changes how the grave looks          17 stop: the editor is unchanged
 9 digging is counted

Run from the repo root:  py -3.13 tooling/acceptance_event_authoring.py [--out DIR]
Set MESH_GUI_AT="x,y" to put the Studio window there (e.g. on a second monitor) and
MESH_GUI_POLITE=3 to wait for the mouse to be still for 3 s whenever someone uses it.
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
from acceptance_map_building import MapPage  # noqa: E402
from gui_driver import Driver  # noqa: E402

from engine.schema_validation import validate  # noqa: E402

SCENE = "packs/core_regions/scenes/start.json"
# Where things go (map cells; the Blank map is 24 x 16 tiles of 32 px, row 0 at the top).
SHOVEL_CELL, GRAVE_CELL, KEEPER_CELL, ZONE_CELL = (4, 6), (12, 6), (18, 6), (12, 11)


# ------------------------------------------------------------------------------------ art
def make_fixtures(folder: Path) -> dict[str, Path]:
    """Small generated pictures: a 3x4 walking character (rows: down, left, right, up), a shovel,
    a grave (closed and dug open) and a gravekeeper."""
    from PIL import Image, ImageDraw

    folder.mkdir(parents=True, exist_ok=True)
    fw, fh = 32, 48
    hero = Image.new("RGBA", (fw * 3, fh * 4), (0, 0, 0, 0))
    draw = ImageDraw.Draw(hero)
    for row, facing in enumerate(("down", "left", "right", "up")):
        for col in range(3):
            x, y = col * fw, row * fh
            draw.rectangle([x + 9, y + 16, x + 23, y + 38], fill=(60, 90, 200, 255))  # coat
            draw.ellipse([x + 9, y + 2, x + 23, y + 16], fill=(240, 205, 170, 255))  # head
            step = (-3, 0, 3)[col]
            draw.rectangle([x + 10 + step, y + 38, x + 14 + step, y + 46], fill=(40, 40, 50, 255))  # legs
            draw.rectangle([x + 18 - step, y + 38, x + 22 - step, y + 46], fill=(40, 40, 50, 255))
            eye = {"down": [(13, 8), (18, 8)], "left": [(11, 8)], "right": [(20, 8)], "up": []}[facing]
            for ex, ey in eye:
                draw.rectangle([x + ex, y + ey, x + ex + 1, y + ey + 1], fill=(20, 20, 20, 255))
    paths = {"hero": folder / "hero.png"}
    hero.save(paths["hero"])

    shovel = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(shovel)
    d.line([(8, 4), (22, 22)], fill=(140, 90, 50, 255), width=3)
    d.polygon([(19, 19), (28, 24), (25, 30), (17, 27)], fill=(170, 175, 185, 255))
    paths["shovel"] = folder / "shovel.png"
    shovel.save(paths["shovel"])

    for name, dug in (("grave_closed", False), ("grave_open", True)):
        grave = Image.new("RGBA", (32, 48), (0, 0, 0, 0))
        d = ImageDraw.Draw(grave)
        d.rounded_rectangle([8, 2, 24, 24], radius=6, fill=(150, 150, 160, 255))
        d.line([(16, 7), (16, 18)], fill=(90, 90, 100, 255), width=2)
        d.line([(12, 11), (20, 11)], fill=(90, 90, 100, 255), width=2)
        d.rounded_rectangle([3, 26, 29, 46], radius=5, fill=(120, 85, 55, 255))
        if dug:
            d.rectangle([7, 30, 25, 43], fill=(25, 18, 15, 255))
        paths[name] = folder / f"{name}.png"
        grave.save(paths[name])

    keeper = Image.new("RGBA", (32, 48), (0, 0, 0, 0))
    d = ImageDraw.Draw(keeper)
    d.rectangle([9, 16, 23, 38], fill=(60, 120, 60, 255))
    d.ellipse([9, 2, 23, 16], fill=(230, 195, 160, 255))
    d.rectangle([8, 0, 24, 5], fill=(70, 50, 40, 255))  # hat
    d.rectangle([10, 38, 14, 46], fill=(40, 40, 50, 255))
    d.rectangle([18, 38, 22, 46], fill=(40, 40, 50, 255))
    paths["keeper"] = folder / "keeper.png"
    keeper.save(paths["keeper"])
    return paths


# ------------------------------------------------------------------------------------ page
class AuthorPage(MapPage):
    """Acting in the Studio's inspector, which scrolls: find a field or button, scrolling to it."""

    def panel_x(self) -> float:
        width = self.state()["window"][0]
        return width - 160

    def fresh(self) -> dict[str, Any]:
        """The Studio's state as drawn after now (its dump is written every few frames)."""
        tick = self.state().get("tick")
        return self.wait(lambda s: s.get("tick") != tick, "a fresh frame", timeout=5)

    def _find(self, *, key: str | None = None, text: str | None = None) -> dict[str, Any] | None:
        for widget in self.fresh()["widgets"]:
            if key is not None and widget["type"] == "field" and widget["key"] == key:
                return widget
            if text is not None and widget["type"] == "button" and widget["text"] == text:
                return widget
        return None

    def reveal(self, *, key: str | None = None, text: str | None = None) -> dict[str, Any]:
        """Scroll the inspector until the field ``key`` or button ``text`` is on screen."""
        deadline = time.time() + 2.5  # the last click may still be redrawing the panel
        while time.time() < deadline:
            found = self._find(key=key, text=text)
            if found is not None:
                return found
        height = self.state()["window"][1]
        for _ in range(20):  # back to the top first
            if not self.fresh()["panel_more"][0]:
                break
            self.d.scroll(self.panel_x(), height / 2, 3)
        for _ in range(40):
            found = self._find(key=key, text=text)
            if found is not None:
                return found
            if not self.fresh()["panel_more"][1]:
                break
            self.d.scroll(self.panel_x(), height / 2, -2)
        found = self._find(key=key, text=text)
        if found is None:
            raise AssertionError(f"no {'field ' + key if key else 'button ' + repr(text)} in the inspector")
        return found

    def press(self, text: str) -> None:
        self.reveal(text=text)
        self.button(text)

    def press_prefix(self, prefix: str) -> None:
        """Press the inspector button whose label starts with ``prefix`` (long labels are shortened)."""
        def match() -> str | None:
            return next((w["text"] for w in self.fresh()["widgets"] if w["type"] == "button" and w["text"].startswith(prefix)), None)

        deadline, text = time.time() + 2.5, None
        while text is None and time.time() < deadline:
            text = match()
        if text is None:
            height = self.state()["window"][1]
            for _ in range(20):
                if not self.fresh()["panel_more"][0]:
                    break
                self.d.scroll(self.panel_x(), height / 2, 3)
            for _ in range(40):
                text = match()
                if text is not None or not self.fresh()["panel_more"][1]:
                    break
                self.d.scroll(self.panel_x(), height / 2, -2)
        if text is None:
            raise AssertionError(f"no button starting {prefix!r} in the inspector")
        self.button(text)

    def open_line(self, number: int) -> None:
        """Show line ``number``'s editor (clicking an open line would close it)."""
        node = self.state()["dlg_order"][number - 1]
        if self.state()["dlg_line"] != node:
            self.press_prefix(f"{number}. ")
            self.wait(lambda s: s["dlg_line"] == node, f"line {number} open")

    def open_choice(self, index: int) -> None:
        if self.state()["dlg_choice"] != index:
            self.press_prefix(f"  {chr(97 + index)}) ")
            self.wait(lambda s: s["dlg_choice"] == index, f"choice {chr(97 + index)} open")

    def entity(self, name: str) -> dict[str, Any]:
        """The object as the Studio holds it now, unsaved edits included (read from the dump)."""
        doc = self.wait(lambda s: s.get("room_doc"), "the room")["room_doc"]
        return next(e for e in doc["entities"] if e.get("name") == name)

    def fill(self, key: str, text: str, expect: str | None = None) -> None:
        """Type into a field and press Enter; wait until the Studio shows the value."""
        self.reveal(key=key)
        before = self.state()["message"]
        self.set_field(key, text)
        want = text if expect is None else expect
        state = self.wait(lambda s: (self._find(key=key) or {}).get("text") == want or (not s["ok"] and s["message"] != before),
                          f"{key} = {want!r}")
        if not state["ok"] and (self._find(key=key) or {}).get("text") != want:
            raise AssertionError(f"the Studio refused {key} = {text!r}: {state['message']}")

    def pick_flag(self, key: str, flag: str) -> None:
        """Use the "Pick" button beside a flag box: choose a flag the project already uses."""
        field = self.reveal(key=key)
        pick = [w for w in self.state()["widgets"]
                if w["type"] == "button" and w["text"] == "Pick" and abs(w["rect"][1] - field["rect"][1]) < 8]
        assert pick, f"no Pick button beside {key}"
        self.d.click(*self._xy(pick[0]["rect"]))
        self.wait(lambda s: any(w["type"] == "button" and w["text"] == flag for w in s["widgets"]), f"{flag} in the menu")
        self.button(flag)
        self.wait(lambda s: flag in ((self._find(key=key) or {}).get("text") or ""), f"{key} has {flag}")

    def tab(self, name: str) -> None:
        self.reveal(text=name)
        self.button(name)
        self.wait(lambda s: s["tab"] == name.lower(), f"the {name} tab")

    def obj(self, name: str) -> dict[str, Any]:
        found = [o for o in self.state()["objects"] if o["name"] == name]
        if not found:
            raise AssertionError(f"no object '{name}' in the room")
        return found[0]

    def place(self, palette: str, cell: tuple[int, int]) -> str:
        before = {o["id"] for o in self.state()["objects"]}
        self.button(palette)
        self.click_cell(*cell)
        state = self.wait(lambda s: s["selected"] and s["selected"] not in before, f"a new {palette}")
        return state["selected"]

    def select(self, name: str) -> None:
        self.click_obj(name)
        self.wait(lambda s: s["selected"] == self.obj(name)["id"], f"{name} selected")

    def import_picture(self, path: Path, button: str = "Import PNG...") -> None:
        self.press(button)
        self.d.file_dialog(str(path))

    def drag_handle(self, name: str, dx: float, dy: float) -> None:
        state = self.wait(lambda s: any(h["name"] == name for h in s["handles"]), f"the {name} handle")
        handle = next(h for h in state["handles"] if h["name"] == name)
        height = state["window"][1]
        x, y = handle["screen"][0], height - handle["screen"][1]
        self.d.drag(x, y, x + dx, y - dy, steps=10)

    # --- play ---------------------------------------------------------------------------------
    def play_state(self) -> dict[str, Any]:
        return self.state()["play"]

    def flags(self) -> dict[str, bool]:
        return self.play_state().get("flags") or {}

    def dialogue(self) -> dict[str, Any] | None:
        return self.play_state()["dialogue"]

    def wait_dialogue(self, part: str, timeout: float = 8.0) -> dict[str, Any]:
        state = self.wait(lambda s: s["play"] and s["play"]["dialogue"] and part in s["play"]["dialogue"]["text"],
                          f"dialogue containing {part!r}", timeout=timeout)
        return state["play"]["dialogue"]

    def tap(self, key: str, pause: float = 0.45) -> None:
        self.d.key(key)
        time.sleep(pause)

    def close_dialogue(self, limit: int = 8) -> None:
        for _ in range(limit):
            if not self.dialogue():
                return
            self.tap("E")
        assert not self.dialogue(), f"the dialogue didn't close: {self.dialogue()}"

    def choose(self, text: str) -> None:
        names = [c["text"] for c in self.dialogue()["choices"]]
        assert text in names, f"no choice {text!r} in {names}"
        target = names.index(text)
        for _ in range(len(names) + 1):
            if self.dialogue()["cursor"] == target:
                break
            self.tap("S", 0.3)
        assert self.dialogue()["cursor"] == target, f"couldn't move to {text!r}: {self.dialogue()}"
        self.tap("E", 0.6)

    def go_to(self, x: float, y: float, tol: float = 6.0) -> None:
        start = self.play_state()["player"]
        try:
            self.walk_to((x, y), tolerance=tol, timeout=25)
        except AssertionError as err:
            play = self.play_state()
            raise AssertionError(f"{err}; started at {start}; dialogue {play['dialogue']}; flags {play['flags']}") from None

    def face(self, key: str) -> None:
        self.d.hold(key, 0.12)
        time.sleep(0.2)

    def talk_to(self, name: str, *, below: float = 60.0) -> None:
        """Stand just below an object, face it, press E."""
        target = self.obj_world(name)
        clear = target[1] - below - 40  # walk across below everything, then up to it (facing moves you a little)
        self.go_to(self.play_state()["player"][0], clear)
        self.go_to(target[0], clear)
        self.go_to(target[0], target[1] - below)
        self.face("W")
        self.tap("E", 0.6)

    def obj_world(self, name: str) -> tuple[float, float]:
        return self.memo_positions[name]


# ------------------------------------------------------------------------------------ run
def run(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    art = make_fixtures(out / "fixtures")
    layout = out / "layout.json"
    env = {**os.environ, "PYTHONPATH": str(REPO), "MESH_STUDIO_LAYOUT": str(layout)}
    os.environ.update(env)
    project = work / "graveyard"
    results: list[dict[str, Any]] = []
    holder: dict[str, Any] = {"driver": None, "page": None}
    memo: dict[str, Any] = {}

    def launch() -> AuthorPage:
        layout.unlink(missing_ok=True)
        driver = Driver([sys.executable, "-m", "mesh_cli", "edit"], cwd=project, shots=out)
        page = AuthorPage(driver, layout)
        page.memo_positions = memo.setdefault("positions", {})
        holder["driver"], holder["page"] = driver, page
        page.wait(lambda s: s["mode"] == "edit" and s["objects"], "the Studio", timeout=60)
        at = os.environ.get("MESH_GUI_AT")
        if at:
            driver.move_window(*(int(v) for v in at.split(",")))
            time.sleep(0.8)
        return page

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

    def p() -> AuthorPage:
        return holder["page"]

    def scene_on_disk() -> dict[str, Any]:
        return json.loads((project / SCENE).read_text(encoding="utf-8"))

    def entity_on_disk(name: str) -> dict[str, Any]:
        return next(e for e in scene_on_disk()["entities"] if e.get("name") == name)

    def remember(name: str) -> None:
        o = p().obj(name)
        memo["positions"][name] = (float(o["x"]), float(o["y"]))

    # --------------------------------------------------------------------------- authoring
    def s01_character_sprite() -> dict[str, Any]:
        subprocess.run([sys.executable, "-m", "mesh_cli", "new", "graveyard", "--template", "blank"], cwd=work, env=env,
                       check=True, capture_output=True)
        launch()
        p().select("Player")
        p().fill("name", "Ezekiel")
        p().tab("Look")
        p().import_picture(art["hero"])
        state = p().wait(lambda s: p().obj("Ezekiel")["sprite"] == "assets/sprites/hero.png", "the new picture")
        assert (project / "assets/sprites/hero.png").is_file(), "the PNG was copied into the project"
        remember("Ezekiel")
        return {"sprite": p().obj("Ezekiel")["sprite"], "message": state["message"]}

    def s02_walking_animation() -> dict[str, Any]:
        p().tab("Animation")
        for key, value in (("anim_fw", "32"), ("anim_fh", "48"), ("anim_down", "0"), ("anim_up", "3"), ("anim_left", ""),
                           ("anim_right", "2"), ("anim_walk_first", "0"), ("anim_walk_count", "3"),
                           ("anim_idle_first", "1"), ("anim_idle_count", "1"), ("anim_fps", "8")):
            p().reveal(key=key)
            p().set_field(key, value)
        p().press("Set up walking")
        p().wait(lambda s: s["clip_sel"] == "walk_down", "the clips")
        p().press("walk_left: row 2, 3 frame(s)  (mirrored)")  # Left mirrors Right
        p().wait(lambda s: s["clip_sel"] == "walk_left", "walk_left selected")
        p().d.shot("02b_walk_left_preview")
        return {"message": p().state()["message"]}

    def s03_shovel() -> dict[str, Any]:
        p().place("Empty object", SHOVEL_CELL)
        p().fill("name", "Shovel")
        p().tab("Look")
        p().press("Choose picture...")
        p().wait(lambda s: s["panel"] == "pick_image", "the picture browser")
        p().import_picture(art["shovel"])
        p().wait(lambda s: p().obj("Shovel")["sprite"] == "assets/sprites/shovel.png", "the shovel's picture")
        remember("Shovel")
        return {"at": memo["positions"]["Shovel"]}

    def s04_shovel_flag() -> dict[str, Any]:
        p().tab("Dialogue")
        p().press("+ First line")
        p().fill("line_text", "A rusty shovel, left against the wall.")
        p().press("+ Choice")
        p().fill("choice_text", "Take it")
        p().fill("choice_sets", "has_shovel")
        p().press("+ Choice")
        p().fill("choice_text", "Leave it")
        p().tab("Conditions")
        p().fill("show_forbid", "has_shovel")  # taken: gone from the world
        p().press("Flags")
        p().wait(lambda s: s["panel"] == "flags", "the flags list")
        p().d.shot("04b_flags_panel")
        p().button("Close")
        return {"behaviours": p().obj("Shovel")["behaviours"]}

    def s05_grave() -> dict[str, Any]:
        p().place("Empty object", GRAVE_CELL)
        p().fill("name", "Grave")
        p().tab("Look")
        p().press("Choose picture...")
        p().wait(lambda s: any(w["type"] == "button" and w["text"] == "sprites/hero.png" for w in s["widgets"]),
                 "the project's pictures listed")
        p().d.shot("05b_picture_browser")
        p().import_picture(art["grave_closed"])
        p().wait(lambda s: p().obj("Grave")["sprite"] == "assets/sprites/grave_closed.png", "the grave's picture")
        p().tab("Collision")
        p().press("Blocks movement: Off")
        p().wait(lambda s: p().obj("Grave")["solid"], "the grave blocking")
        remember("Grave")
        return {"solid": True}

    def s06_examine() -> dict[str, Any]:
        p().tab("Dialogue")
        p().press("+ First line")
        p().fill("line_text", "I cannot dig with my bare hands.")
        p().press("+ Line")  # line 2
        p().fill("line_text", "Elara Vance. Shall I dig?")
        p().press("+ Line")  # line 3
        p().fill("line_text", "The coffin is empty.")
        p().press("+ Line")  # line 4
        p().fill("line_text", "The grave is already open.")
        # Lines 1 and 3 end the conversation instead of running on into the next line.
        for number in (1, 3):
            p().open_line(number)
            p().fill("line_next", "")
        p().press("Test conversation")
        p().wait(lambda s: s["panel"] == "preview", "the conversation tester")
        p().d.shot("06b_test_without_shovel")
        p().button("Back to editing")
        return {"lines": 4}

    def s07_dig_needs_shovel() -> dict[str, Any]:
        p().open_line(2)
        p().press("+ Choice")
        p().fill("choice_text", "Dig")
        p().fill("choice_req", "has_shovel")
        p().fill("choice_next", "3")
        p().press("+ Choice")
        p().fill("choice_text", "Leave her be")
        p().fill("choice_next", "")
        p().press("+ Opening")
        p().fill("open_node_0", "4")
        p().fill("open_req_0", "grave_open")
        p().press("+ Opening")
        p().fill("open_node_1", "2")
        p().fill("open_req_1", "has_shovel")
        p().press("Test conversation")
        p().fill("preview_flags", "has_shovel")
        p().wait(lambda s: s["preview"] and s["preview"]["flags"] == ["has_shovel"], "pretend shovel")
        p().wait(lambda s: any(w["type"] == "button" and w["text"] == "Dig" for w in s["widgets"]), "the Dig choice")
        p().d.shot("07b_test_with_shovel")
        p().button("Back to editing")
        return {"openings": 2}

    def s08_dig_changes_look() -> dict[str, Any]:
        p().tab("Dialogue")
        p().open_line(2)
        p().open_choice(0)
        p().fill("choice_sets", "grave_open")
        p().tab("Conditions")
        p().press("+ Picture change...")
        p().import_picture(art["grave_open"])
        p().wait(lambda s: "PictureByFlags" in p().obj("Grave")["behaviours"], "the picture change")
        p().fill("pic_req_0", "grave_open")
        return {"behaviours": p().obj("Grave")["behaviours"]}

    def s09_count_digging() -> dict[str, Any]:
        p().tab("Dialogue")
        p().open_line(2)
        p().open_choice(0)
        p().fill("choice_counters", "graves_dug")
        return {"counter": "graves_dug"}

    def s10_keeper_appears() -> dict[str, Any]:
        p().place("Person", KEEPER_CELL)
        p().fill("name", "Gravekeeper")
        p().tab("Look")
        p().press("Choose picture...")
        p().import_picture(art["keeper"])
        p().wait(lambda s: p().obj("Gravekeeper")["sprite"] == "assets/sprites/keeper.png", "the keeper's picture")
        p().tab("Conditions")
        p().pick_flag("show_req", "grave_open")
        p().fill("talk_req", "grave_open")
        remember("Gravekeeper")
        return {"behaviours": p().obj("Gravekeeper")["behaviours"]}

    def s11_keeper_conversation() -> dict[str, Any]:
        p().tab("Dialogue")
        p().fill("says", "Who's there? Grave robber!")
        p().press("Starts by itself: Off")
        p().press("+ Line")
        p().fill("line_text", "Easy, old man. I didn't come to steal.")
        p().fill("line_speaker", "Ezekiel")
        p().press("+ Line")
        p().fill("line_text", "Then what did you find down there?")
        p().press("+ Choice")
        p().fill("choice_text", "Nothing. It was empty.")
        p().press("+ Choice")
        p().fill("choice_text", "Say nothing")
        p().press("+ Line")
        p().fill("line_text", "Empty? Then God help us both.")
        p().open_line(3)
        p().open_choice(0)
        p().fill("choice_next", "4")
        return {"lines": 4}

    def s12_collider_and_zone() -> dict[str, Any]:
        p().select("Grave")
        p().tab("Collision")
        p().press("Footprint")
        p().wait(lambda s: any(h["name"] == "collider_size" for h in s["handles"]), "the footprint's handles")
        before = dict(_collider(p().entity("Grave")))
        p().drag_handle("collider_size", 10, -6)  # wider and taller
        p().wait(lambda s: _collider(p().entity("Grave")) != before, "the resized footprint")
        sized = dict(_collider(p().entity("Grave")))
        p().drag_handle("collider_move", 0, -4)  # nudge it down
        p().wait(lambda s: _collider(p().entity("Grave")) != sized, "the moved footprint")
        after = _collider(p().entity("Grave"))
        assert after != before and after["kind"] == "box", (before, after)
        p().select("Ezekiel")
        p().tab("Collision")
        p().press("Circle")
        p().wait(lambda s: _collider(p().entity("Ezekiel"))["kind"] == "circle", "Ezekiel's feet collider")
        p().place("Trigger zone", ZONE_CELL)
        p().fill("name", "Cemetery gate")
        p().drag_handle("zone_size", 16, -8)
        p().wait(lambda s: p().entity("Cemetery gate")["behaviour_config"]["TriggerVolume"]["width"] > 96, "the bigger zone")
        p().fill("zone_flags", "entered_cemetery")
        remember("Cemetery gate")
        zone = p().entity("Cemetery gate")["behaviour_config"]["TriggerVolume"]
        assert zone["width"] > 96 and zone["height"] > 96, zone
        return {"collider": after, "zone": [zone["width"], zone["height"]]}

    def s13_save_and_close() -> None:
        assert p().state()["dirty"], "there should be unsaved work to ask about"
        p().d.click_close_button(wait=False)
        p().wait(lambda s: s["modal"] == "close", "the Save / Discard / Cancel question")
        p().d.shot("13a_close_question")
        p().button("Save")
        p().d.proc.wait(timeout=20)
        memo["saved"] = scene_on_disk()
        validate(memo["saved"], "scene.schema.json", "scene")
        assert _collider(entity_on_disk("Ezekiel"))["kind"] == "circle", "the feet collider was saved"

    def s14_reopen_persisted() -> dict[str, Any]:
        page = launch()
        assert scene_on_disk() == memo["saved"], "opening changed the file"
        names = {o["name"] for o in page.state()["objects"]}
        assert {"Ezekiel", "Shovel", "Grave", "Gravekeeper", "Cemetery gate"} <= names, names
        page.select("Grave")
        page.tab("Dialogue")
        page.press_prefix("2. Elara Vance. Shall I dig? ?")
        page.select("Ezekiel")
        page.tab("Animation")
        page.press_prefix("walk_left: row 2, 3 frame(s)  (mirrored)")
        grave = entity_on_disk("Grave")
        talk = grave["behaviour_config"]["Dialogue"]["dialogue"]
        return {"objects": sorted(names), "grave_lines": len(talk["nodes"]), "openings": talk["starts"],
                "clips": sorted(entity_on_disk("Ezekiel")["behaviour_config"]["Animator"]["animations"])}

    # --------------------------------------------------------------------------- playing
    def s15_play_through() -> dict[str, Any]:
        p().d.key("F4")
        p().wait(lambda s: s["mode"] == "play" and s["play"] and s["play"]["player"], "the game", timeout=30)
        time.sleep(1.0)
        start = tuple(p().play_state()["player"])
        p().d.hold("D", 0.4)
        moved = tuple(p().play_state()["player"])
        assert moved[0] > start[0] + 20, (start, moved)
        assert abs(moved[1] - start[1]) < 0.5, f"walking right moved Ezekiel up or down: {start} -> {moved}"
        assert _visible(p(), "Shovel") and not _visible(p(), "Gravekeeper"), p().play_state()["sprites"]
        gx, gy = p().obj_world("Cemetery gate")
        p().go_to(gx, gy)  # walking into the zone
        p().wait(lambda s: s["play"]["flags"].get("entered_cemetery"), "the zone's flag")
        memo["after_zone"] = {"player": p().play_state()["player"], "visible": _visible(p(), "Shovel")}
        p().talk_to("Grave")
        p().wait_dialogue("bare hands")
        p().close_dialogue()
        p().talk_to("Shovel")
        p().wait_dialogue("rusty shovel")
        p().choose("Take it")
        p().close_dialogue()
        p().wait(lambda s: s["play"]["flags"].get("has_shovel"), "has_shovel")
        p().talk_to("Grave")
        p().wait_dialogue("Shall I dig?")
        return {"flags": p().flags()}

    def s16_quick_save_and_load() -> dict[str, Any]:
        p().choose("Leave her be")
        p().close_dialogue()
        p().d.key("F5")
        time.sleep(1.0)
        saved_at = tuple(p().play_state()["player"])
        p().talk_to("Grave")
        p().wait_dialogue("Shall I dig?")
        p().choose("Dig")
        p().wait_dialogue("coffin is empty")
        p().wait(lambda s: s["play"]["flags"].get("grave_open"), "grave_open")
        p().tap("E")  # once: the keeper starts talking as soon as this line closes
        p().wait_dialogue("Grave robber", timeout=8)  # the keeper appears and speaks
        p().d.shot("16a_keeper_confronts")
        p().tap("E")
        p().wait_dialogue("Easy, old man")
        p().tap("E")
        p().wait_dialogue("what did you find")
        p().choose("Nothing. It was empty.")
        p().wait_dialogue("God help us")
        p().close_dialogue()
        dug = dict(p().flags())
        p().d.key("F9")
        p().wait(lambda s: not s["play"]["flags"].get("grave_open"), "the quick-load")
        time.sleep(1.0)
        restored = dict(p().flags())
        assert restored.get("has_shovel") and restored.get("entered_cemetery") and not restored.get("grave_open"), restored
        loaded_at = tuple(p().play_state()["player"])
        assert max(abs(a - b) for a, b in zip(loaded_at, saved_at)) < 1.0, f"saved at {saved_at}, loaded at {loaded_at}"
        assert _visible(p(), "Grave") and not _visible(p(), "Gravekeeper") and not _visible(p(), "Shovel")
        p().talk_to("Grave")
        p().wait_dialogue("Shall I dig?")  # not "already open": the dig was undone by the load
        p().choose("Leave her be")
        p().close_dialogue()
        p().button("Flags")  # the flags while playing, to see and change
        p().wait(lambda s: s["play_flags_open"] and any(w["type"] == "button" and w["text"] == "has_shovel: On"
                                                        for w in s["widgets"]), "the play-mode flags")
        p().d.shot("16b_play_flags")
        return {"after_digging": dug, "after_loading": restored}

    def s17_stop_unchanged() -> None:
        p().d.key("F4")
        s = p().wait(lambda s: s["mode"] == "edit", "back to editing")
        assert not s["dirty"], "playing must not change the project"
        assert scene_on_disk() == memo["saved"], "playing must not change the saved room"

    steps = [s01_character_sprite, s02_walking_animation, s03_shovel, s04_shovel_flag, s05_grave, s06_examine,
             s07_dig_needs_shovel, s08_dig_changes_look, s09_count_digging, s10_keeper_appears, s11_keeper_conversation,
             s12_collider_and_zone, s13_save_and_close, s14_reopen_persisted, s15_play_through, s16_quick_save_and_load,
             s17_stop_unchanged]
    try:
        for action in steps:
            if not step(action.__name__.split("_", 1)[1], action):
                break
    finally:
        if holder["driver"] is not None:
            holder["driver"].close()
    passed = sum(r["ok"] for r in results)
    (out / "report.json").write_text(json.dumps({"passed": passed, "total": len(steps), "steps": results}, indent=2),
                                     encoding="utf-8")
    print(f"{passed}/{len(steps)} steps passed; report: {out / 'report.json'}")
    return 0 if passed == len(steps) else 1


def _visible(page: AuthorPage, name: str) -> bool:
    return any(s["name"] == name and s["visible"] for s in page.play_state()["sprites"])


def _collider(entity: dict[str, Any]) -> dict[str, Any]:
    return (entity.get("components") or {}).get("collider") or {"kind": "picture"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO / "artifacts" / "acceptance_event_authoring")
    raise SystemExit(run(parser.parse_args().out))
