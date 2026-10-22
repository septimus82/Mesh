"""Acceptance test: the first creation workflow, driven through the real window.

New project -> Studio -> place a person, give them dialogue, rename them, add a behaviour,
undo/redo -> create a second room with a linked door -> put a person in it -> save ->
play: talk, walk through the door and back -> save, move, load -> stop -> check the
saved files.

Input is OS-level (tooling/gui_driver.py). The Studio's MESH_STUDIO_LAYOUT dump tells the
script where things are on screen and what state the game is in; every check below is
made against that dump, the window, or the files on disk.

Run from the repo root:  py -3.13 tooling/acceptance_first_workflow.py [--out DIR]
Exit code 0 only if every step passed. Results: DIR/report.json plus a screenshot per step.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gui_driver import Driver  # noqa: E402


class Page:
    """Reads the Studio's layout dump and acts on what it describes."""

    def __init__(self, driver: Driver, layout: Path) -> None:
        self.d = driver
        self.layout = layout

    def state(self) -> dict[str, Any]:
        for _ in range(50):
            try:
                return json.loads(self.layout.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                time.sleep(0.1)
        raise AssertionError("the Studio never wrote its layout dump")

    def wait(self, test: Callable[[dict[str, Any]], Any], what: str, timeout: float = 8.0) -> dict[str, Any]:
        deadline = time.time() + timeout
        state = self.state()
        while time.time() < deadline:
            state = self.state()
            if test(state):
                return state
            time.sleep(0.2)
        raise AssertionError(f"timed out waiting for: {what} (last message: {state.get('message')!r})")

    def _xy(self, rect: list[float]) -> tuple[float, float]:
        height = self.state()["window"][1]
        return rect[0] + rect[2] / 2, height - (rect[1] + rect[3] / 2)

    def button(self, text: str, *, nth: int = 0) -> None:
        matches = [w for w in self.state()["widgets"] if w["type"] == "button" and w["text"] == text]
        if len(matches) <= nth:
            raise AssertionError(f"no button '{text}' on screen")
        if matches[nth]["disabled"]:
            raise AssertionError(f"button '{text}' is disabled")
        self.d.click(*self._xy(matches[nth]["rect"]))

    def field(self, key: str) -> dict[str, Any]:
        found = [w for w in self.state()["widgets"] if w["type"] == "field" and w["key"] == key]
        if not found:
            raise AssertionError(f"no '{key}' field on screen")
        return found[0]

    def set_field(self, key: str, text: str) -> None:
        current = self.field(key)
        x, y = self._xy(current["rect"])
        self.d.click(x + current["rect"][2] / 2 - 6, y)  # click near the right end: caret at the end
        for _ in range(len(current["text"]) + 2):
            self.d.key("BACKSPACE", hold=0.02, settle=0.02)
        self.d.type_text(text)
        self.d.key("ENTER")

    def obj(self, name: str) -> dict[str, Any]:
        found = [o for o in self.state()["objects"] if o["name"] == name]
        if not found:
            raise AssertionError(f"no object '{name}' in the room")
        return found[0]

    def click_obj(self, name: str, *, right: bool = False) -> None:
        self.d.click(*self._xy(self.obj(name)["rect"]), right=right)

    def click_near(self, name: str, dx: float, dy: float, *, right: bool = False) -> None:
        """Click ``(dx, dy)`` world units from an object (map at zoom 1; +dy is up)."""
        x, y = self._xy(self.obj(name)["rect"])
        self.d.click(x + dx, y - dy, right=right)

    # --- play mode ---------------------------------------------------------------------------
    def player(self) -> tuple[float, float]:
        play = self.wait(lambda s: s.get("play") and s["play"].get("player"), "a player in the game")["play"]
        return tuple(play["player"])  # type: ignore[return-value]

    def walk_to(self, target: tuple[float, float], tolerance: float = 20.0, timeout: float = 20.0) -> None:
        deadline = time.time() + timeout
        for axis, (neg, pos) in ((0, ("A", "D")), (1, ("S", "W"))):
            while time.time() < deadline:
                gap = target[axis] - self.player()[axis]
                if abs(gap) <= tolerance:
                    break
                self.d.hold(pos if gap > 0 else neg, min(0.4, max(0.05, abs(gap) / 300)))
            else:
                raise AssertionError(f"could not walk to {target}; player at {self.player()}")


def run(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    if work.exists():
        import shutil

        shutil.rmtree(work)
    work.mkdir()
    env = {**os.environ, "PYTHONPATH": str(REPO), "MESH_STUDIO_LAYOUT": str(out / "layout.json")}
    os.environ.update(env)
    results: list[dict[str, Any]] = []
    driver: Driver | None = None
    page: Page | None = None

    def step(name: str, action: Callable[[], Any]) -> bool:
        started = time.time()
        try:
            detail = action()
            ok, error = True, None
        except Exception as exc:  # noqa: BLE001  # REASON: record every failure in the report, then stop
            ok, error, detail = False, f"{type(exc).__name__}: {exc}", traceback.format_exc(limit=3)
        shot = None
        if driver is not None and driver.proc.poll() is None:
            shot = str(driver.shot(f"{len(results) + 1:02d}_{name}").name)
        results.append({"step": name, "ok": ok, "error": error, "detail": detail, "seconds": round(time.time() - started, 1),
                        "screenshot": shot})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {error}" if error else ""), flush=True)
        return ok

    project = work / "village"
    try:
        if not step("create_project", lambda: subprocess.run(
                [sys.executable, "-m", "mesh_cli", "new", "village"], cwd=work, env=env, check=True, capture_output=True)):
            return _finish(out, results)
        driver = Driver([sys.executable, "-m", "mesh_cli", "edit"], cwd=project, shots=out)
        page = Page(driver, out / "layout.json")
        p = page

        def opened() -> None:
            s = p.wait(lambda s: s["mode"] == "edit" and s["objects"], "the Studio showing the start room")
            names = sorted(o["name"] for o in s["objects"])
            assert names == ["Guide", "Player"], names

        def place_person() -> None:
            p.button("Person")
            p.click_near("Player", -128, 0)  # left of the player
            s = p.wait(lambda s: len(s["objects"]) == 3 and s["selected"], "the new person placed and selected")
            assert any(o["name"].startswith("Person") for o in s["objects"])

        def give_dialogue() -> None:
            p.set_field("says", "Welcome, traveller!")
            p.wait(lambda s: s["message"] == "Dialogue updated.", "dialogue saved to the document")
            assert p.field("says")["text"] == "Welcome, traveller!"

        def rename() -> None:
            p.set_field("name", "Elder")
            p.wait(lambda s: any(o["name"] == "Elder" for o in s["objects"]), "the person renamed to Elder")

        def undo_redo() -> None:
            p.d.key("CTRL+Z")
            p.wait(lambda s: not any(o["name"] == "Elder" for o in s["objects"]), "undo reverting the rename")
            p.d.key("CTRL+Y")
            p.wait(lambda s: any(o["name"] == "Elder" for o in s["objects"]), "redo restoring the rename")

        def add_behaviour_via_right_click() -> None:
            p.click_obj("Elder", right=True)
            p.wait(lambda s: any(w["text"] == "Add behaviour..." for w in s["widgets"]), "the context menu")
            p.button("Add behaviour...")
            p.wait(lambda s: s["panel"] == "add_behaviour", "the behaviour picker")
            p.d.type_text("Health")
            p.wait(lambda s: any(w["type"] == "button" and w["text"] == "Health" for w in s["widgets"]), "Health in the picker")
            p.button("Health")
            s = p.wait(lambda s: s["message"] == "Added Health.", "Health added")
            assert any(w["type"] == "field" for w in s["widgets"]), "Health's settings should be editable fields"

        def new_room_with_door() -> None:
            p.click_near("Player", 0, 160, right=True)  # empty spot above the player
            p.wait(lambda s: any(w["text"] == "Add door to a new room..." for w in s["widgets"]), "the map context menu")
            p.button("Add door to a new room...")
            p.wait(lambda s: s["panel"] == "new_room", "the new-room form")
            p.d.type_text("House")
            p.button("Create")
            s = p.wait(lambda s: any(o["tag"] == "door" for o in s["objects"]), "a door in the start room")
            assert any(w["text"] == "House" for w in s["widgets"]), "House should be listed under Rooms"

        def furnish_house() -> None:
            p.button("House")
            p.wait(lambda s: s["room"] == "house", "switched to House")
            p.button("Person")
            p.click_near("Player", 0, -128)  # below the house's player
            p.wait(lambda s: s["selected"] and len([o for o in s["objects"] if o["tag"] == "npc"]) == 1, "a person in House")
            p.set_field("says", "Welcome to my house!")
            p.wait(lambda s: s["message"] == "Dialogue updated.", "house dialogue saved")

        def save() -> None:
            p.d.key("CTRL+S")
            p.wait(lambda s: not s["dirty"], "everything saved")

        def files_on_disk() -> None:
            world = json.loads((project / "packs/core_regions/worlds/main.json").read_text(encoding="utf-8"))
            assert "house" in world["scenes"], world["scenes"].keys()
            start = json.loads((project / "packs/core_regions/scenes/start.json").read_text(encoding="utf-8"))
            elder = next(e for e in start["entities"] if e.get("name") == "Elder")
            assert "Health" in elder["behaviours"]
            assert elder["behaviour_config"]["Dialogue"]["dialogue"]["nodes"]["root"]["text"] == "Welcome, traveller!"
            house = json.loads((project / world["scenes"]["house"]["path"]).read_text(encoding="utf-8"))
            assert any(e.get("tag") == "player" for e in house["entities"])
            assert any(e.get("tag") == "door" for e in house["entities"])

        def play_and_talk() -> None:
            p.button("Start")
            p.wait(lambda s: s["room"] == "start", "back in the start room")
            p.d.key("F4")
            p.wait(lambda s: s["mode"] == "play", "play mode")
            start = json.loads((project / "packs/core_regions/scenes/start.json").read_text(encoding="utf-8"))
            ex, ey = next((e["x"], e["y"]) for e in start["entities"] if e.get("name") == "Elder")
            p.walk_to((ex + 48, ey), tolerance=10)  # overlapping, as interaction needs
            p.d.key("E")
            s = p.wait(lambda s: s["play"] and s["play"]["dialogue"], "a dialogue box")
            assert s["play"]["dialogue"]["text"] == "Welcome, traveller!", s["play"]["dialogue"]
            assert s["play"]["dialogue"]["speaker"] == "Elder", s["play"]["dialogue"]
            p.d.shot("12b_dialogue_open")
            p.d.key("E")
            p.wait(lambda s: not s["play"]["dialogue"], "the dialogue closing")

        def through_the_door_and_back() -> None:
            start = json.loads((project / "packs/core_regions/scenes/start.json").read_text(encoding="utf-8"))
            door = next(e for e in start["entities"] if e.get("tag") == "door")
            p.walk_to((door["x"], door["y"] - 60))
            p.d.hold("W", 0.6)
            p.wait(lambda s: s["play"]["scene"].endswith("house.json"), "arriving in House")
            time.sleep(1.2)  # a held key must not carry the player on through House's own door
            s = p.state()
            assert s["play"]["scene"].endswith("house.json"), f"bounced back out: now in {s['play']['scene']}"
            house = json.loads((project / "packs/core_regions/scenes/house.json").read_text(encoding="utf-8"))
            arrival = next(e for e in house["entities"] if e.get("tag") == "spawn_point")
            px, py = s["play"]["player"]
            assert abs(px - arrival["x"]) < 40 and abs(py - arrival["y"]) < 40, ((px, py), arrival)
            hdoor = next(e for e in house["entities"] if e.get("tag") == "door")
            p.walk_to((hdoor["x"], hdoor["y"] - 60))
            p.d.hold("W", 0.6)
            p.wait(lambda s: s["play"]["scene"].endswith("start.json"), "back in the start room")
            time.sleep(1.2)
            s = p.state()
            assert s["play"]["scene"].endswith("start.json"), f"bounced back out: now in {s['play']['scene']}"
            back = next(e for e in start["entities"] if e.get("tag") == "spawn_point")
            px, py = s["play"]["player"]
            assert abs(px - back["x"]) < 40 and abs(py - back["y"]) < 40, ((px, py), back)

        def save_move_load() -> None:
            before = p.player()
            p.d.key("F5")
            p.d.wait(0.8)
            p.d.hold("D", 0.6)
            moved = p.player()
            assert abs(moved[0] - before[0]) > 30, "the player should have moved before loading"
            p.d.key("F9")
            s = p.wait(lambda s: s["play"] and s["play"]["player"]
                       and abs(s["play"]["player"][0] - before[0]) < 12 and abs(s["play"]["player"][1] - before[1]) < 12,
                       "loading the save putting the player back", timeout=6)
            return {"saved_at": before, "moved_to": moved, "loaded_at": s["play"]["player"]}

        def stop_returns_to_edit() -> None:
            p.d.key("F4")
            s = p.wait(lambda s: s["mode"] == "edit", "back to editing")
            assert not s["dirty"], "play must not change the documents"

        for name, action in [
            ("studio_opens", opened), ("place_person", place_person), ("give_dialogue", give_dialogue),
            ("rename", rename), ("undo_redo", undo_redo), ("add_behaviour_via_right_click", add_behaviour_via_right_click),
            ("new_room_with_door", new_room_with_door), ("furnish_house", furnish_house), ("save", save),
            ("files_on_disk", files_on_disk), ("play_and_talk", play_and_talk),
            ("through_the_door_and_back", through_the_door_and_back), ("save_move_load", save_move_load),
            ("stop_returns_to_edit", stop_returns_to_edit),
        ]:
            if not step(name, action) and name not in ("save_move_load",):
                break
    finally:
        if driver is not None:
            driver.close()  # the app's own output is already in OUT/app.log
    return _finish(out, results)


def _finish(out: Path, results: list[dict[str, Any]]) -> int:
    passed = all(r["ok"] for r in results)
    (out / "report.json").write_text(json.dumps({"passed": passed, "steps": results}, indent=2, default=str), encoding="utf-8")
    print(f"{sum(r['ok'] for r in results)}/{len(results)} steps passed; report: {out / 'report.json'}")
    return 0 if passed else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO / "artifacts" / "acceptance_first_workflow")
    raise SystemExit(run(parser.parse_args().out))
