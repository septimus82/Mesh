"""Real-window acceptance: game state persists across rooms, saves and a restart.

A disposable two-room project is built with Mesh's own authoring operations, then played in Mesh
Studio's real window with OS-level keys:

  Hall: a coin to pick up (PickupCollectible), a lamp zone that sets the flag `lamp_lit`, a gate
        shown only while that flag is set, and a dummy (Health) that a turret keeps hitting, so its
        HP is object state that changes over time. A door to the Yard.
  Yard: a door back.

The steps follow the Milestone 8 brief: collect the coin and light the lamp, go to the Yard and back
(the coin must stay gone, the flag set, the gate shown), save, change things, load, and then close
Mesh Studio, start it again and load the save. Nothing works around a failure.

Run from the repo root:  py -3.13 tooling/acceptance_persistence.py [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO))
from acceptance_event_authoring import AuthorPage  # noqa: E402
from gui_driver import Driver  # noqa: E402

from engine import authoring  # noqa: E402
from engine.studio_project import Project  # noqa: E402

COIN, LAMP, GATE = (320.0, 128.0), (480.0, 224.0), (480.0, 352.0)


def build(root: Path) -> dict[str, str]:
    from PIL import Image

    from engine.project_scaffold import create_project

    create_project(root, "Persistence Test", template_id="blank")
    sprites = root / "assets" / "sprites"
    sprites.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (20, 20), (250, 210, 40, 255)).save(sprites / "coin.png")
    Image.new("RGBA", (32, 32), (120, 120, 140, 255)).save(sprites / "gate.png")
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    project = Project(root, config["world_file"])
    hall = project.current
    yard = project.add_room("Yard")
    project.link_rooms(hall, (544.0, 48.0), yard, (128.0, 48.0))
    authoring.apply(project, [
        {"op": "place_blank", "room": hall, "name": "Coin", "x": COIN[0], "y": COIN[1]},
        {"op": "set_picture", "room": hall, "entity_id": "@0", "sprite": "assets/sprites/coin.png"},
        {"op": "add_behaviour", "room": hall, "entity_id": "@0", "behaviour": "PickupCollectible"},
        {"op": "place_blank", "room": hall, "name": "Lamp switch", "x": LAMP[0], "y": LAMP[1]},
        {"op": "set_trigger_zone", "room": hall, "entity_id": "@3", "width": 64, "height": 64, "once": True,
         "set_flags": ["lamp_lit"]},
        {"op": "place_blank", "room": hall, "name": "Gate", "x": GATE[0], "y": GATE[1]},
        {"op": "set_picture", "room": hall, "entity_id": "@5", "sprite": "assets/sprites/gate.png"},
        {"op": "set_show_when", "room": hall, "entity_id": "@5", "require": ["lamp_lit"], "forbid": []},
    ])

    def target_practice(scene: dict[str, Any]) -> dict[str, Any]:  # keys Studio has no control for yet
        out = json.loads(json.dumps(scene))
        out["entities"] += [
            {"id": "dummy", "name": "Dummy", "tag": "dummy", "x": 64.0, "y": 400.0, "sprite": "assets/sprites/gate.png",
             "behaviours": ["Health"], "behaviour_config": {"Health": {"max_hp": 1000, "hp": 1000}}},
            {"id": "turret", "name": "Turret", "x": 256.0, "y": 400.0, "sprite": "assets/sprites/coin.png",
             "behaviours": ["RangedEnemyAI", "Shooter"], "behaviour_config": {
                 "RangedEnemyAI": {"target_tag": "dummy", "detect_radius": 400, "attack_radius": 300, "flee_radius": 0,
                                   "speed": 0},
                 "Shooter": {"target_tag": "dummy", "cooldown": 0.6, "range": 400, "damage": 1}}},
        ]
        return out

    project.edit_scene(target_practice, hall)
    project.save()
    return {"hall": hall, "yard": yard}


def run(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    shutil.rmtree(work, ignore_errors=True)
    root = work / "persistence"
    layout = out / "layout.json"
    os.environ.update({"PYTHONPATH": str(REPO), "MESH_STUDIO_LAYOUT": str(layout)})
    keys = build(root)
    results: list[dict[str, Any]] = []
    holder: dict[str, Any] = {"driver": None, "page": None}
    memo: dict[str, Any] = {}

    def p() -> AuthorPage:
        return holder["page"]

    def launch() -> AuthorPage:
        layout.unlink(missing_ok=True)
        driver = Driver([sys.executable, "-m", "mesh_cli", "edit"], cwd=root, shots=out)
        page = AuthorPage(driver, layout)
        page.memo_positions = {}
        holder["driver"], holder["page"] = driver, page
        page.wait(lambda s: s["mode"] == "edit" and s["objects"], "the Studio", timeout=60)
        return page

    def close() -> None:
        if holder["driver"] is not None:
            holder["driver"].close()
            holder["driver"] = None

    def step(name: str, action: Callable[[], Any]) -> bool:
        started = time.time()
        try:
            detail, ok, error = action(), True, None
        except (AssertionError, AttributeError, KeyError, IndexError, TypeError, ValueError, OSError, RuntimeError) as exc:
            # record every failure in the report, then go on
            ok, error, detail = False, f"{type(exc).__name__}: {exc}", traceback.format_exc(limit=4)
        driver = holder["driver"]
        shot = driver.shot(f"{len(results) + 1:02d}_{name}").name if driver and driver.proc.poll() is None else None
        results.append({"step": name, "ok": ok, "error": error, "detail": detail,
                        "seconds": round(time.time() - started, 1), "screenshot": shot})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {error}" if error else ""), flush=True)
        return ok

    def play() -> dict[str, Any]:
        return p().fresh()["play"]

    def names() -> list[str]:
        return [s["name"] for s in play()["sprites"] if s["visible"]]

    def scene_doc(key: str) -> dict[str, Any]:
        return json.loads((root / project_path(key)).read_text(encoding="utf-8"))

    def project_path(key: str) -> str:
        return Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]).path(key)

    def tagged(key: str, tag: str) -> tuple[float, float]:
        entity = next(e for e in scene_doc(key)["entities"] if e.get("tag") == tag)
        return float(entity["x"]), float(entity["y"])

    def through_door(here: str, there: str) -> None:
        door = tagged(here, "door")
        p().go_to(door[0], door[1] + 90, tol=10)  # just outside the door's reach, then step in
        p().d.hold("S", 0.6)
        p().wait(lambda s: s["play"] and project_path(there).split("/")[-1] in str(s["play"]["scene"]),
                 f"arriving in {there}", timeout=8)
        time.sleep(1.2)  # a held key must not carry the player on through the next door

    def state() -> dict[str, Any]:
        s = play()
        return {"scene": s["scene"], "player": [round(v, 1) for v in s["player"]], "flags": s["flags"],
                "coin": "Coin" in names(), "gate": "Gate" in names(),
                "dummy_hp": next((x["hp"] for x in s["sprites"] if x["name"] == "Dummy"), None)}

    def hp_problems(now: dict[str, Any], saved: dict[str, Any]) -> list[str]:
        """The dummy's HP after a load: the saved value, less the few hits landed since (one per 0.6 s)."""
        if now["dummy_hp"] is None or saved["dummy_hp"] is None:
            return [f"no dummy HP to compare: {now['dummy_hp']} vs saved {saved['dummy_hp']}"]
        if not saved["dummy_hp"] - 6 <= now["dummy_hp"] <= saved["dummy_hp"]:
            return [f"dummy HP {now['dummy_hp']} after load, saved at {saved['dummy_hp']}"]
        return []

    # ------------------------------------------------------------------ steps
    def s01_play_the_hall() -> dict[str, Any]:
        launch()
        # Studio opens on the start room: the Hall
        p().d.key("F4")
        p().wait(lambda s: s["mode"] == "play" and s["play"] and s["play"]["player"], "playing", timeout=30)
        time.sleep(0.8)
        now = state()
        assert now["coin"] and not now["gate"] and not now["flags"].get("lamp_lit"), now
        return now

    def s02_collect_the_coin() -> dict[str, Any]:
        p().go_to(COIN[0] - 40, COIN[1], tol=6)
        p().face("D")
        p().tap("E", 0.6)
        p().wait(lambda s: "Coin" not in [x["name"] for x in s["play"]["sprites"] if x["visible"]], "the coin picked up")
        return state()

    def s03_light_the_lamp() -> dict[str, Any]:
        p().go_to(LAMP[0], LAMP[1], tol=12)
        p().wait(lambda s: s["play"]["flags"].get("lamp_lit"), "lamp_lit set")
        time.sleep(0.5)
        now = state()
        assert now["gate"], f"the gate should show once lamp_lit is set: {now}"
        return now

    def s04_to_the_yard_and_back() -> dict[str, Any]:
        through_door(keys["hall"], keys["yard"])
        yard = state()
        through_door(keys["yard"], keys["hall"])
        back = state()
        memo["back"] = back
        return {"in_yard": yard, "back_in_hall": back}

    def s05_coin_stays_gone() -> dict[str, Any]:
        now = state()
        assert not now["coin"], f"the collected coin came back after leaving the room: {now}"
        return now

    def s06_flag_and_gate_kept() -> dict[str, Any]:
        now = state()
        assert now["flags"].get("lamp_lit") and now["gate"], now
        return now

    def s07_save() -> dict[str, Any]:
        p().go_to(400.0, 160.0, tol=10)
        p().d.key("F5")
        memo["saved"] = state()  # read right after the key: the dummy may take a hit in between
        time.sleep(1.2)
        assert (root / "saves" / "quicksave.json").is_file(), "no quicksave written"
        hp = memo["saved"]["dummy_hp"]
        assert hp is not None and hp < 1000, f"the turret should have hit the dummy by now: {memo['saved']}"
        return memo["saved"]

    def s08_change_things() -> dict[str, Any]:
        through_door(keys["hall"], keys["yard"])
        return state()

    def s09_load_restores() -> dict[str, Any]:
        p().d.key("F9")
        time.sleep(2.0)
        now = state()
        saved = memo["saved"]
        problems = []
        if abs(now["player"][0] - saved["player"][0]) > 4 or abs(now["player"][1] - saved["player"][1]) > 4:
            problems.append(f"player at {now['player']}, saved at {saved['player']}")
        if now["coin"]:
            problems.append("the collected coin is back")
        if not (now["flags"].get("lamp_lit") and now["gate"]):
            problems.append(f"lamp/gate lost: flags {now['flags']}, gate {now['gate']}")
        problems += hp_problems(now, saved)
        assert not problems, "; ".join(problems) + f" -- {now}"
        return now

    def s10_after_load_rooms_still_right() -> dict[str, Any]:
        through_door(keys["hall"], keys["yard"])
        through_door(keys["yard"], keys["hall"])
        now = state()
        assert not now["coin"] and now["gate"], f"after load, leaving and coming back: {now}"
        return now

    def s11_restart_and_load() -> dict[str, Any]:
        p().d.key("F4")
        close()
        launch()
        p().d.key("F4")
        p().wait(lambda s: s["mode"] == "play" and s["play"] and s["play"]["player"], "playing", timeout=30)
        time.sleep(0.8)
        fresh_game = state()
        assert fresh_game["coin"] and not fresh_game["flags"].get("lamp_lit"), f"a new play-test is a new game: {fresh_game}"
        p().d.key("F9")
        time.sleep(2.0)
        now = state()
        saved = memo["saved"]
        problems = []
        if abs(now["player"][0] - saved["player"][0]) > 4 or abs(now["player"][1] - saved["player"][1]) > 4:
            problems.append(f"player at {now['player']}, saved at {saved['player']}")
        if now["coin"]:
            problems.append("the collected coin is back")
        if not (now["flags"].get("lamp_lit") and now["gate"]):
            problems.append("lamp/gate lost")
        problems += hp_problems(now, saved)
        assert not problems, "; ".join(problems) + f" -- {now}"
        return {"new_game": fresh_game, "loaded": now}

    def s12_restarted_rooms_still_right() -> dict[str, Any]:
        through_door(keys["hall"], keys["yard"])
        through_door(keys["yard"], keys["hall"])
        now = state()
        assert not now["coin"] and now["gate"] and now["flags"].get("lamp_lit"), now
        return now

    try:
        for name, action in (
            ("play_the_hall", s01_play_the_hall), ("collect_the_coin", s02_collect_the_coin),
            ("light_the_lamp", s03_light_the_lamp), ("to_the_yard_and_back", s04_to_the_yard_and_back),
            ("coin_stays_gone", s05_coin_stays_gone), ("flag_and_gate_kept", s06_flag_and_gate_kept),
            ("save", s07_save), ("change_things", s08_change_things), ("load_restores", s09_load_restores),
            ("after_load_rooms_still_right", s10_after_load_rooms_still_right),
            ("restart_and_load", s11_restart_and_load), ("restarted_rooms_still_right", s12_restarted_rooms_still_right),
        ):
            step(name, action)
    finally:
        close()
    passed = sum(r["ok"] for r in results)
    (out / "report.json").write_text(json.dumps({"passed": passed == len(results), "steps": results}, indent=2,
                                                default=str), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)  # the disposable project goes; report and screenshots stay
    print(f"{passed}/{len(results)} steps passed; report: {out / 'report.json'}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO / "artifacts" / "acceptance_persistence")
    raise SystemExit(run(parser.parse_args().out))
