"""Acceptance test, Milestone 4: from double-clicking Mesh to playing a new game.

The real windows only, driven by OS-level mouse and keyboard input; the launcher's and
the Studio's opt-in layout dumps are read to find things and check state, never to act.

 1 launch Mesh with "Mesh Engine.bat"        11 close the Studio (its X button)
 2 the launcher appears                       12 launch Mesh again
 3 New Project                                13 open the game from Recent projects
 4 pick Top-down Adventure                    14 every change persisted
 5 name it; choose a folder outside the       15 create a Blank Project
   engine (Browse..., the OS folder picker;   16 it has no monster or demo content
   spaces and non-ASCII letters in the path)  17 add a room and an object; play it
 6 Create & Open: Mesh Studio opens           18 open older projects (copies) in the Studio
 7 the village, player and Guide are there    19 bad and missing paths: clear errors,
 8 change the map and the Guide's line           nothing on disk changed
 9 play, talk to the Guide                    20 the engine folder is unchanged
10 save and stop

Run from the repo root:  py -3.13 tooling/acceptance_launcher.py [--out DIR] [--old PROJECT ...]
``--old`` names older projects to open (each is copied first; the original is never touched).
Keep hands off the mouse while it runs.
"""

from __future__ import annotations

import argparse
import hashlib
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

GAME, BLANK = "Village Quest", "Empty Canvas"
NEW_LINE = "Have you met my grandma? She lives in the house."


def tree_digest(folder: Path) -> str:
    """A fingerprint of every file's path and contents under ``folder``."""
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        digest.update(path.relative_to(folder).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def repo_status() -> str:
    return subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=REPO,
                          capture_output=True, text=True, check=True).stdout


def run(out: Path, old_projects: list[Path]) -> int:
    out.mkdir(parents=True, exist_ok=True)
    # The games it creates go outside the engine folder: the launcher refuses a location inside it, and --out
    # (artifacts/ by default) is inside it. One reused folder; the report and pictures stay in --out.
    work = Path(tempfile.gettempdir()) / "mesh_acceptance_launcher"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    dest = work / "Mina spel – Åäö"  # where the games go: a space, a dash and non-ASCII letters
    dest.mkdir()
    launcher_layout, studio_layout = out / "launcher.json", out / "studio.json"
    env = {**os.environ, "MESH_USER_DIR": str(work / "user"), "MESH_PROJECTS_DIR": str(work / "default games"),
           "MESH_LAUNCHER_LAYOUT": str(launcher_layout), "MESH_STUDIO_LAYOUT": str(studio_layout)}
    env.pop("MESH_PROJECTS_PATH", None)
    results: list[dict[str, Any]] = []
    held: dict[str, Any] = {"launcher": None, "studio": None, "L": None, "S": None}
    memo: dict[str, Any] = {}

    # --- helpers ---------------------------------------------------------------------------
    def launch() -> Page:
        """Double-click equivalent: run the .bat the way Explorer does, then find its window."""
        launcher_layout.unlink(missing_ok=True)
        subprocess.Popen(["cmd", "/c", str(REPO / "Mesh Engine.bat")], cwd=str(REPO), env=env,
                         creationflags=subprocess.CREATE_NO_WINDOW)
        driver = Driver.attach("Mesh Studio", out / "shots", logical_size=(960, 640))  # the launcher (Milestone 15: "Mesh Studio")
        held["launcher"], held["L"] = driver, Page(driver, launcher_layout)
        held["L"].wait(lambda s: s["screen"] == "home", "the launcher's home screen", timeout=30)
        return held["L"]

    def studio_opens() -> MapPage:
        driver = Driver.attach("Mesh Studio - ", out / "shots", timeout=90)  # Studio itself: "Mesh Studio - <room>"
        held["studio"], held["S"] = driver, MapPage(driver, studio_layout)
        held["S"].wait(lambda s: s["mode"] == "edit" and s["objects"], "Mesh Studio", timeout=30)
        launcher = held["launcher"]
        if launcher is not None:
            launcher.proc.wait(timeout=20)  # the launcher steps aside once the Studio is up
            held["launcher"] = None
        return held["S"]

    def close_studio() -> None:
        held["studio"].click_close_button()
        held["studio"].proc.wait(timeout=20)
        held["studio"] = None
        studio_layout.unlink(missing_ok=True)

    def close_launcher() -> None:
        held["launcher"].click_close_button()
        held["launcher"].proc.wait(timeout=20)
        held["launcher"] = None

    def L() -> Page:
        return held["L"]

    def S() -> MapPage:
        return held["S"]

    def card(template_id: str) -> None:
        found = next(w for w in L().state()["widgets"] if w["type"] == "card" and w["text"] == template_id)
        L().d.click(*L()._xy(found["rect"]))
        L().wait(lambda s: s["template"] == template_id, f"the {template_id} template chosen")

    def step(name: str, action: Callable[[], Any]) -> bool:
        started = time.time()
        try:
            detail, ok, error = action(), True, None
        except Exception as exc:  # noqa: BLE001  # REASON: record every failure in the report, then stop
            ok, error, detail = False, f"{type(exc).__name__}: {exc}", traceback.format_exc(limit=5)
        driver = held["studio"] or held["launcher"]
        shot = None
        if driver is not None and driver.proc.poll() is None:
            try:
                shot = driver.shot(f"{len(results) + 1:02d}_{name}").name
            except Exception:  # noqa: BLE001  # REASON: a window closing mid-capture must not hide the step's result
                shot = None
        results.append({"step": name, "ok": ok, "error": error, "detail": detail,
                        "seconds": round(time.time() - started, 1), "screenshot": shot})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {error}" if error else ""), flush=True)
        return ok

    # --- the steps --------------------------------------------------------------------------
    def s01_launch_mesh() -> None:
        memo["repo_before"] = repo_status()
        launch()

    def s02_launcher_appears() -> dict[str, Any]:
        s = L().state()
        assert held["launcher"].title() == "Mesh Engine"
        buttons = {w["text"] for w in s["widgets"] if w["type"] == "button"}
        assert {"New Project", "Open Project..."} <= buttons, buttons
        assert s["recent"] == [], "a fresh user has no recent projects"
        return {"buttons": sorted(buttons)}

    def s03_new_project() -> None:
        L().button("New Project")
        s = L().wait(lambda s: s["screen"] == "new", "the New Project screen")
        assert {w["text"] for w in s["widgets"] if w["type"] == "card"} == {"blank", "adventure"}

    def s04_choose_top_down_adventure() -> None:
        card("blank")
        card("adventure")

    def s05_name_and_destination() -> dict[str, Any]:
        L().set_field("name", GAME)
        L().wait(lambda s: L().field("name")["text"] == GAME, "the name")
        L().button("Browse...")
        L().d.file_dialog(str(dest))  # the OS folder picker
        s = L().wait(lambda s: Path(L().field("location")["text"]) == dest, "the chosen folder")
        assert s["problem"] == "" and Path(s["target"]) == dest / GAME, s
        return {"target": s["target"]}

    def s06_create_and_open() -> None:
        L().button("Create & Open")
        studio_opens()
        assert (dest / GAME / "config.json").is_file()

    def s07_example_content() -> dict[str, Any]:
        s = S().state()
        rooms = [w["text"] for w in s["widgets"] if w["type"] == "button" and w["text"] in ("Village", "House")]
        names = {o["name"] for o in s["objects"]}
        assert sorted(rooms) == ["House", "Village"] and {"Player", "Guide", "Door to House"} <= names, (rooms, names)
        walls = sum(1 for gid in s["map"]["layers"]["walls"] if gid)
        assert (s["map"]["width"], s["map"]["height"]) == (24, 16) and walls > 30
        return {"objects": sorted(names), "wall_tiles": walls}

    def s08_change_map_and_dialogue() -> None:
        S().tile("Flowers")
        S().stroke((3, 14), (6, 14))
        assert all(S().at("ground", c, 14) == S().gid("Flowers") for c in range(3, 7))
        S().d.key("ESC")
        S().click_obj("Guide")
        S().wait(lambda s: s["selected"] == S().obj("Guide")["id"], "the Guide selected")
        S().set_field("says", NEW_LINE)
        S().wait(lambda s: s["message"] == "Dialogue updated.", "the new line")

    def s09_play_and_talk() -> dict[str, Any]:
        S().d.key("F4")
        S().wait(lambda s: s["mode"] == "play", "play mode")
        village = json.loads((dest / GAME / "packs/core_regions/scenes/start.json").read_text(encoding="utf-8"))
        gx, gy = next((e["x"], e["y"]) for e in village["entities"] if e.get("name") == "Guide")
        S().walk_to((gx - 48, gy), tolerance=10)
        S().d.key("E")
        s = S().wait(lambda s: s["play"] and s["play"]["dialogue"], "the Guide's dialogue")
        S().d.shot(f"{len(results) + 1:02d}_talking_to_the_guide")
        assert s["play"]["dialogue"]["text"] == NEW_LINE and s["play"]["dialogue"]["speaker"] == "Guide", s["play"]["dialogue"]
        S().d.key("E")
        S().wait(lambda s: not s["play"]["dialogue"], "the dialogue closing")
        return {"dialogue": s["play"]["dialogue"]}

    def s10_save_and_stop() -> None:
        S().d.key("F4")
        S().wait(lambda s: s["mode"] == "edit", "back to editing")
        S().d.key("CTRL+S")
        memo["layers"] = S().wait(lambda s: not s["dirty"], "everything saved")["map"]["layers"]

    def s11_close_the_application() -> None:
        close_studio()
        assert find_window_by_title("Mesh Studio") == 0  # neither Studio nor the launcher

    def s12_launch_again() -> None:
        launch()

    def s13_open_from_recent() -> dict[str, Any]:
        s = L().state()
        assert [r["path"] for r in s["recent"]] == [str((dest / GAME).resolve())], s["recent"]
        row = s["recent"][0]
        assert row["name"] == GAME and not row["missing"]
        L().button(GAME)
        studio_opens()
        return {"recent": s["recent"]}

    def s14_changes_persisted() -> None:
        s = S().state()
        assert s["map"]["layers"] == memo["layers"], "tiles changed across close and reopen"
        S().click_obj("Guide")
        S().wait(lambda s: s["selected"] == S().obj("Guide")["id"]
                 and any(w["type"] == "field" and w["key"] == "says" for w in s["widgets"]), "the Guide's inspector")
        S().wait(lambda s: S().field("says")["text"] == " ".join(NEW_LINE.split()), "the Guide's new line")

    def s15_create_blank_project() -> None:
        close_studio()
        launch()
        L().button("New Project")
        L().wait(lambda s: s["screen"] == "new", "the New Project screen")
        card("blank")
        L().set_field("name", BLANK)
        L().set_field("location", str(dest))  # typed this time, not browsed
        L().wait(lambda s: s["target"] and Path(s["target"]) == dest / BLANK, "the target folder")
        L().button("Create & Open")
        studio_opens()

    def s16_blank_has_no_monster_or_demo_content() -> dict[str, Any]:
        root = dest / BLANK
        files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
        unwanted = [f for f in files if any(word in f.lower() for word in ("monster", "sproutling", "shelltide", "quest", "battle"))]
        assert not unwanted, unwanted
        s = S().state()
        assert [o["tag"] for o in s["objects"]] == ["player"], s["objects"]
        assert set(s["map"]["layers"]["ground"]) == {1} and not any(s["map"]["layers"]["walls"])
        world = json.loads((root / "packs/core_regions/worlds/main.json").read_text(encoding="utf-8"))
        assert list(world["scenes"]) == ["start"]
        return {"files": files}

    def s17_add_room_and_object_then_play() -> dict[str, Any]:
        S().button("+ New room")
        S().wait(lambda s: s["panel"] == "new_room", "the new-room form")
        S().d.type_text("Cave")
        S().button("Create")
        S().wait(lambda s: s["room"] == "cave", "the new Cave room")
        S().button("Start")
        S().wait(lambda s: s["room"] == "start", "back to the start room")
        S().button("Person")
        S().click_cell(12, 8)
        S().wait(lambda s: any(o["name"].startswith("Person") for o in s["objects"]), "the placed Person")
        S().d.key("CTRL+S")
        S().wait(lambda s: not s["dirty"], "saved")
        S().d.key("F4")
        S().wait(lambda s: s["mode"] == "play", "play mode")
        start = S().player()
        S().d.hold("D", 0.8)
        moved = S().player()
        assert moved[0] > start[0] + 40, f"the player should walk: {start} -> {moved}"
        S().d.key("F4")
        S().wait(lambda s: s["mode"] == "edit" and not s["dirty"], "stopped, nothing changed")
        return {"walked": [start, moved]}

    def s18_open_older_projects() -> dict[str, Any]:
        close_studio()
        opened = {}
        for index, original in enumerate(old_projects):
            before = tree_digest(original)
            copy = work / "older" / f"{index}_{original.name}"
            shutil.copytree(original, copy, ignore=shutil.ignore_patterns("__pycache__", "artifacts"))
            launch()
            L().button("Open Project...")
            L().d.file_dialog(str(copy))
            s = studio_opens().state()
            held["studio"].shot(f"18_{index}_older_project_{original.name}")
            assert s.get("map") and s["objects"], f"{original.name}: nothing to edit"
            opened[str(original)] = {"tilesets": s["tilesets"], "objects": len(s["objects"]), "message": s["message"]}
            if s["dirty"]:
                # Milestone 11: a project from before one shared player is migrated on open (and says so), so
                # closing asks whether to save. Discard: the copy stays as it was.
                held["studio"].click_close_button(wait=False)
                held["S"].wait(lambda s: s["modal"] == "close", "the save-before-closing question")
                held["S"].button("Discard")
                held["studio"].proc.wait(timeout=20)
                held["studio"] = None
                studio_layout.unlink(missing_ok=True)
            else:
                close_studio()
            assert tree_digest(original) == before, f"{original} was modified"
        if not old_projects:
            raise AssertionError("no older projects given (--old)")
        return opened

    def s19_bad_and_missing_paths() -> dict[str, Any]:
        game_before = tree_digest(dest / GAME)
        (dest / BLANK).rename(dest / f"{BLANK} moved")  # a recent project that has gone
        launch()
        seen: dict[str, str] = {}
        L().button("Open Project...")
        L().d.file_dialog(str(dest))  # a folder, but not a project
        seen["not a project"] = L().wait(lambda s: "no config.json" in s["message"], "the not-a-project error")["message"]
        L().d.shot("19c_not_a_project")
        s = L().state()
        missing = next(r for r in s["recent"] if Path(r["path"]).name == BLANK)
        assert missing["missing"], s["recent"]
        L().button(BLANK)
        seen["moved"] = L().wait(lambda s: "isn't there any more" in s["message"], "the moved-project error")["message"]
        L().d.shot("19a_moved_project")
        L().button("Remove")
        L().wait(lambda s: all(Path(r["path"]).name != BLANK for r in s["recent"]), "the entry removed")
        assert (dest / f"{BLANK} moved" / "config.json").is_file(), "removing from the list must not delete anything"
        L().button("New Project")
        L().wait(lambda s: s["screen"] == "new", "the New Project screen")
        L().set_field("location", str(dest))
        for name, expect in ((GAME, "already a Mesh project"), ("What?", "can't contain")):
            L().set_field("name", name)
            seen[name] = L().wait(lambda s: expect in s["problem"], f"the '{expect}' warning")["problem"]
        L().set_field("name", GAME)
        L().button("Create & Open")
        L().wait(lambda s: "already a Mesh project" in s["message"], "the refusal")
        L().d.shot("19b_refused_existing_project")
        L().set_field("location", str(REPO))
        L().set_field("name", "Inside")
        seen["engine folder"] = L().wait(lambda s: "outside the Mesh engine folder" in s["problem"], "the engine-folder warning")["problem"]
        close_launcher()
        assert tree_digest(dest / GAME) == game_before, "a refused create changed the existing game"
        assert not (REPO / "Inside").exists()
        return seen

    def s20_engine_folder_unchanged() -> dict[str, Any]:
        after = repo_status()
        assert after == memo["repo_before"], f"the engine folder changed:\n{after}"
        assert (work / "user" / "projects.json").is_file(), "recent projects are kept in the user folder"
        assert not (work / "default games").exists() or not any((work / "default games").iterdir())
        return {"git_status_lines": len(after.splitlines())}

    steps = [s01_launch_mesh, s02_launcher_appears, s03_new_project, s04_choose_top_down_adventure,
             s05_name_and_destination, s06_create_and_open, s07_example_content, s08_change_map_and_dialogue,
             s09_play_and_talk, s10_save_and_stop, s11_close_the_application, s12_launch_again,
             s13_open_from_recent, s14_changes_persisted, s15_create_blank_project,
             s16_blank_has_no_monster_or_demo_content, s17_add_room_and_object_then_play, s18_open_older_projects,
             s19_bad_and_missing_paths, s20_engine_folder_unchanged]
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
    parser.add_argument("--out", type=Path, default=REPO / "artifacts" / "acceptance_launcher")
    parser.add_argument("--old", type=Path, nargs="*", default=[], help="older projects to open (copied first)")
    args = parser.parse_args()
    raise SystemExit(run(args.out, [p.resolve() for p in args.old]))
