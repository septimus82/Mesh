"""Real-window acceptance: lighting a game in Mesh Studio, through its own controls.

A disposable two-room project (Cellar and Garden, joined by doors; the Cellar has a stone pillar)
is lit entirely through Mesh Studio's Lighting panel and map, with OS-level mouse and keys:
lighting on, room light, two coloured lights, move and resize one, flicker, shadows behind the
pillar, undo/redo, a second room lit differently, play through the doors repeatedly (nothing may
leak between rooms), the map zoomed, save / close / reopen, and Play/Stop leaving the authored
lighting alone. Pixels are read from the window's own surface to see the light and the shadow.

Run from the repo root:  py -3.13 tooling/acceptance_lighting.py [--out DIR]
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
from capability_lab import brightness  # noqa: E402
from gui_driver import Driver  # noqa: E402

from engine import project_ops as ops  # noqa: E402
from engine.studio_project import Project  # noqa: E402

PILLAR = [(10, r) for r in range(4, 10)]  # map cells (column, row from the top) of the Cellar's pillar
CAVE, DUSK = [30, 30, 40, 255], [150, 120, 140, 255]


def world(cell: tuple[int, int], rows: int = 15) -> tuple[float, float]:
    """The middle of a map cell in world units (y up)."""
    return cell[0] * 32 + 16.0, (rows - cell[1]) * 32 - 16.0


def build(root: Path) -> dict[str, str]:
    from engine.project_scaffold import create_project

    create_project(root, "Lighting Test", template_id="blank")
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    project = Project(root, config["world_file"])
    cellar, garden = project.add_room("Cellar"), project.add_room("Garden")
    project.link_rooms(cellar, (560.0, 48.0), garden, (80.0, 48.0))
    project.edit_scene(lambda s: ops.paint_tiles(s, ops.WALLS, PILLAR, ops.STARTER_WALL), cellar)
    project.save()
    return {"cellar": cellar, "garden": garden}


def run(out: Path) -> int:
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    shutil.rmtree(work, ignore_errors=True)
    root = work / "lighting"
    layout = out / "layout.json"
    os.environ.update({"PYTHONPATH": str(REPO), "MESH_STUDIO_LAYOUT": str(layout)})
    keys = build(root)
    world_file = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    files = {name: Project(root, world_file).path(key).split("/")[-1] for name, key in keys.items()}  # as play reports
    results: list[dict[str, Any]] = []
    holder: dict[str, Any] = {"driver": None, "page": None}
    memo: dict[str, Any] = {}

    def p() -> AuthorPage:
        return holder["page"]

    def launch() -> AuthorPage:
        layout.unlink(missing_ok=True)
        driver = Driver([sys.executable, "-m", "mesh_cli", "edit"], cwd=root, shots=out)
        page = AuthorPage(driver, layout)
        holder["driver"], holder["page"] = driver, page
        page.wait(lambda s: s["mode"] == "edit", "the Studio", timeout=60)
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
            ok, error, detail = False, f"{type(exc).__name__}: {exc}", traceback.format_exc(limit=4)
        driver = holder["driver"]
        shot = driver.shot(f"{len(results) + 1:02d}_{name}").name if driver and driver.proc.poll() is None else None
        results.append({"step": name, "ok": ok, "error": error, "detail": detail,
                        "seconds": round(time.time() - started, 1), "screenshot": shot})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {error}" if error else ""), flush=True)
        return ok

    # ------------------------------------------------------------------ reading the Studio
    def doc() -> dict[str, Any]:
        room: dict[str, Any] = p().wait(lambda s: s.get("room_doc"), "the room")["room_doc"]
        return room

    def settings() -> dict[str, Any]:
        return doc().get("settings") or {}

    def lights() -> list[dict[str, Any]]:
        return ops.lights(doc())

    def live() -> dict[str, Any]:
        s = p().fresh()
        return (s["play"]["runtime"]["lighting"] if s["mode"] == "play" else s["lighting"]) or {}

    def on_disk(key: str) -> dict[str, Any]:
        path = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]).path(key)
        scene: dict[str, Any] = json.loads((root / path).read_text(encoding="utf-8"))
        return scene

    def lighting_of(scene: dict[str, Any]) -> dict[str, Any]:
        keep = ("lighting_enabled", "lighting_ambient_color", "lighting_shadows_mode")
        return {"lights": ops.lights(scene), "settings": {k: v for k, v in (scene.get("settings") or {}).items() if k in keep}}

    def press(text: str) -> None:
        """A button in the right-hand panel, scrolled into view."""
        p().reveal(text=text)
        p().button(text)

    def until(test: Callable[[], Any], what: str, timeout: float = 8.0) -> Any:
        deadline = time.time() + timeout
        while True:
            try:
                value = test()
                if value:
                    return value
            except (KeyError, IndexError, TypeError):
                value = None
            if time.time() > deadline:
                raise AssertionError(f"timed out waiting for: {what} (message: {p().state().get('message')!r})")
            time.sleep(0.2)

    def screen_of(point: tuple[float, float]) -> tuple[float, float]:
        """Where a world point is in the window (logical pixels, y down), edit or play."""
        s = p().fresh()
        height = s["window"][1]
        if s["mode"] == "play":
            play = s["play"]
            zoom = play["runtime"]["camera"]["zoom"]
            sx = play["player_screen"][0] + (point[0] - play["player"][0]) * zoom
            sy = play["player_screen"][1] + (point[1] - play["player"][1]) * zoom
            return sx, height - sy
        m = s["map"]
        x0, y0, x1, y1 = m["screen"]
        mw, mh = m["width"] * m["tilewidth"], m["height"] * m["tileheight"]
        return x0 + point[0] / mw * (x1 - x0), height - (y0 + point[1] / mh * (y1 - y0))

    def bright(points: list[tuple[float, float]], frames: int = 6) -> list[float]:
        """Mean brightness at each world point, averaged over a few frames (flicker moves the light)."""
        s = p().fresh()
        totals = [0.0] * len(points)
        for i in range(frames):
            image = Image.open(holder["driver"].shot(f"sample_{len(results):02d}_{i}"))
            scale_x, scale_y = image.width / s["window"][0], image.height / s["window"][1]
            for n, point in enumerate(points):
                x, y = screen_of(point)
                totals[n] += brightness(image, x * scale_x, y * scale_y, r=4) / frames
            time.sleep(0.12)
        for leftover in out.glob(f"sample_{len(results):02d}_*.png"):
            leftover.unlink()
        return [round(t, 1) for t in totals]

    def select_light(number: int) -> None:
        if p().state().get("light") != number - 1:
            p().press_prefix(f"Light {number}:")
            p().wait(lambda s: s.get("light") == number - 1, f"light {number} selected")

    def add_light(cell: tuple[int, int], colour: str) -> int:
        before = len(lights())
        press("+ Add light")
        p().wait(lambda s: s["tool"] == "light", "the light tool")
        p().click_cell(*cell)
        until(lambda: len(lights()) == before + 1, "a new light")
        press(colour)
        until(lambda: ops.rgb(lights()[before]["color"]) == ops.rgb(ops.LIGHT_COLOURS[colour]), f"a {colour} light")
        return before

    def play_and_wait(room: str) -> None:
        p().d.key("F4")
        p().wait(lambda s: s["mode"] == "play" and s["play"] and s["play"]["player"], "playing", timeout=30)
        p().wait(lambda s: files[room] in str(s["play"]["scene"]), f"playing in {room}")
        time.sleep(2.0)  # past the room's fade-in, which covers the whole screen evenly

    def through_door(here: str, there: str) -> None:
        door = next(e for e in on_disk(keys[here])["entities"] if e.get("tag") == "door")
        p().go_to(float(door["x"]), float(door["y"]) + 90, tol=10)
        p().d.hold("S", 0.6)
        p().wait(lambda s: s["play"] and files[there] in str(s["play"]["scene"]), f"arriving in {there}", timeout=8)
        time.sleep(1.2)  # a held key must not carry the player on through the next door

    def room_lighting() -> dict[str, Any]:
        lit = live()
        return {"room": p().state()["play"]["scene"].split("/")[-1], "enabled": lit["enabled"], "ambient": lit["ambient"],
                "shadows": lit["shadows_mode"], "static": len(lit["static"]), "dynamic": len(lit["dynamic"]),
                "occluders": lit["occluders"], "radii": [round(x["radius"], 1) for x in lit["static"]]}

    # ------------------------------------------------------------------ the steps
    def s01_open_room_1() -> dict[str, Any]:
        launch()
        p().button("Cellar")
        p().wait(lambda s: s["room"] == keys["cellar"] and s.get("map"), "the Cellar")
        assert not live().get("enabled"), f"a new project starts unlit: {live()}"
        return {"room": p().state()["room"]}

    def s02_enable_lighting() -> dict[str, Any]:
        p().button("Lighting")
        p().wait(lambda s: s["panel"] == "lighting", "the Lighting panel")
        press("On")
        until(lambda: settings().get("lighting_enabled") is True and live()["enabled"], "lighting on")
        return {"settings": settings(), "live": live()}

    def s03_change_ambient() -> dict[str, Any]:
        press("Cave")
        until(lambda: settings().get("lighting_ambient_color") == CAVE and live()["ambient"] == CAVE, "cave light")
        return {"settings": settings(), "ambient": live()["ambient"]}

    def s04_two_coloured_lights() -> dict[str, Any]:
        add_light((6, 7), "Red")
        add_light((16, 12), "Cold")
        lit = until(lambda: (lambda x: x if len(x["static"]) == 2 else None)(live()), "two lights drawn")
        reds = [c for c in lit["static"] if c["color"][0] > 200 and c["color"][2] < 120]
        colds = [c for c in lit["static"] if c["color"][2] > 200 and c["color"][0] < 160]
        assert reds and colds, f"expected a red and a cold light: {lit['static']}"
        return {"lights": lights(), "live": lit["static"]}

    def s05_move_and_resize() -> dict[str, Any]:
        select_light(1)
        before = dict(lights()[0])
        zoom = p().state()["zoom"]
        p().drag_handle("light_move", 32 * zoom, 0)
        until(lambda: lights()[0]["x"] != before["x"], "light 1 moved")
        p().drag_handle("light_size", 120 * zoom, 0)
        after = until(lambda: lights()[0] if lights()[0]["radius"] > before["radius"] + 60 else None, "light 1 bigger")
        moved = abs(after["x"] - (before["x"] + 32)) <= 3 and abs(after["y"] - before["y"]) <= 3
        assert moved, f"moved to {after['x']},{after['y']} from {before['x']},{before['y']} (wanted +32 x)"
        drawn = until(lambda: next((c for c in live()["static"] if abs(c["radius"] - after["radius"]) < 1), None), "drawn as authored")
        assert abs(drawn["at"][0] - after["x"]) < 1, drawn
        return {"before": before, "after": after, "drawn": drawn}

    def s06_flicker() -> dict[str, Any]:
        select_light(2)
        press("Flicker: Off")
        light = until(lambda: lights()[1] if lights()[1].get("flicker_enabled") else None, "light 2 flickers")
        assert light.get("flicker_amount", 0) > 0 and light.get("flicker_speed", 0) > 0, light
        return {"light": light}

    def s07_shadows() -> dict[str, Any]:
        press("Shadows on")
        until(lambda: settings().get("lighting_shadows_mode") == "hard" and live()["shadows_mode"] == "hard", "hard shadows")
        light = (lights()[0]["x"], lights()[0]["y"])
        behind, open_side, far = (light[0] + 160, light[1]), (light[0], light[1] - 160), (light[0] - 200, light[1] + 200)
        b = bright([behind, open_side, far])
        memo["edit_shadow"] = {"behind_pillar": b[0], "open_same_distance": b[1], "far_dark": b[2], "light": light}
        assert b[1] - b[0] > 10, f"no shadow behind the pillar: {memo['edit_shadow']}"
        return dict(memo["edit_shadow"])

    def s08_undo_redo() -> dict[str, Any]:
        full = lighting_of(doc())
        p().d.key("ctrl+z")
        until(lambda: "lighting_shadows_mode" not in settings(), "shadows undone")
        p().d.key("ctrl+z")
        until(lambda: not lights()[1].get("flicker_enabled"), "flicker undone")
        p().d.key("ctrl+y")
        p().d.key("ctrl+y")
        until(lambda: lighting_of(doc()) == full, "both redone")
        until(lambda: live()["shadows_mode"] == "hard" and len(live()["static"]) == 2, "redone and drawn")
        return full

    def s09_second_room() -> dict[str, Any]:
        p().button("Garden")
        p().wait(lambda s: s["room"] == keys["garden"] and s["panel"] == "lighting", "the Garden, Lighting still open")
        press("On")
        press("Dusk")
        until(lambda: settings().get("lighting_ambient_color") == DUSK and live()["ambient"] == DUSK, "dusk")
        add_light((10, 7), "Green")
        p().d.key("ctrl+s")
        p().wait(lambda s: not s["dirty"], "saved")
        memo["authored"] = {k: lighting_of(on_disk(keys[k])) for k in ("cellar", "garden")}
        assert memo["authored"]["cellar"]["settings"]["lighting_ambient_color"] == CAVE
        return dict(memo["authored"])

    def s10_play_between_rooms() -> dict[str, Any]:
        p().button("Cellar")
        p().wait(lambda s: s["room"] == keys["cellar"], "the Cellar")
        play_and_wait("cellar")
        visits, radii = [], []
        for i in range(8):
            radii.append(live()["static"][1]["radius"])
            time.sleep(0.15)
        light = (memo["authored"]["cellar"]["lights"][0]["x"], memo["authored"]["cellar"]["lights"][0]["y"])
        b = bright([(light[0] + 160, light[1]), (light[0], light[1] - 160)])
        memo["play_shadow"] = {"behind_pillar": b[0], "open_same_distance": b[1]}
        assert b[1] - b[0] > 10, f"no shadow behind the pillar while playing: {memo['play_shadow']}"
        assert max(radii) - min(radii) > 1, f"light 2 doesn't flicker while playing: {radii}"
        for _ in range(3):
            visits.append(room_lighting())
            through_door("cellar", "garden")
            visits.append(room_lighting())
            through_door("garden", "cellar")
        visits.append(room_lighting())
        memo["visits"] = visits
        for visit in visits:
            cellar = visit["room"] == files["cellar"]
            want = (CAVE, "hard", 2) if cellar else (DUSK, None, 1)
            assert visit["enabled"] and visit["ambient"] == want[0] and visit["static"] == want[2], visit
            if want[1]:
                assert visit["shadows"] == want[1], visit
        return {"visits": visits, "flicker_radii": [round(r, 1) for r in radii], "shadow": memo["play_shadow"]}

    def s11_no_leaks() -> dict[str, Any]:
        visits = memo["visits"]
        by_room: dict[str, set[Any]] = {}
        for visit in visits:
            by_room.setdefault(visit["room"], set()).add((visit["static"], visit["dynamic"], visit["occluders"]))
        assert all(len(v) == 1 for v in by_room.values()), f"a room's light count changed between visits: {by_room}"
        return {room: sorted(v) for room, v in by_room.items()}

    def s12_zoomed_map() -> dict[str, Any]:
        p().d.key("F4")
        p().wait(lambda s: s["mode"] == "edit", "back to editing")
        if p().state()["panel"] != "lighting":
            p().button("Lighting")
        p().wait(lambda s: s["panel"] == "lighting", "the Lighting panel")
        light = lights()[0]
        x, y = screen_of((light["x"], light["y"]))
        p().d.scroll(x, y, 4)
        zoom = p().wait(lambda s: s["zoom"] > 1.2, "zoomed in")["zoom"]
        select_light(1)
        before = dict(lights()[0])
        p().drag_handle("light_move", 40, 0)
        after = until(lambda: lights()[0] if lights()[0]["x"] != before["x"] else None, "light 1 moved at zoom")
        moved = after["x"] - before["x"]
        assert abs(moved - 40 / zoom) <= 3, f"40 screen px at zoom {zoom:.2f} moved the light {moved} world px"
        b = bright([(after["x"], after["y"]), (after["x"] - 200, after["y"] + 200)], frames=3)
        assert b[0] > b[1] + 20, f"the glow isn't where the light is at zoom {zoom:.2f}: {b}"
        p().d.key("ctrl+z")
        until(lambda: lights()[0]["x"] == before["x"], "move undone")
        return {"zoom": zoom, "moved_world_px": moved, "glow_vs_dark": b}

    def s13_save_close_reopen() -> dict[str, Any]:
        p().d.key("ctrl+s")
        p().wait(lambda s: not s["dirty"], "saved")
        memo["saved"] = {k: lighting_of(on_disk(keys[k])) for k in ("cellar", "garden")}
        close()
        launch()
        return dict(memo["saved"])

    def s14_preserved() -> dict[str, Any]:
        assert memo["saved"] == memo["authored"], "what was saved differs from what was authored"
        p().button("Cellar")
        p().wait(lambda s: s["room"] == keys["cellar"] and s.get("room_doc"), "the Cellar")
        assert lighting_of(doc()) == memo["authored"]["cellar"], lighting_of(doc())
        until(lambda: live()["enabled"] and live()["ambient"] == CAVE and len(live()["static"]) == 2, "the Cellar lit as saved")
        p().button("Lighting")
        p().wait(lambda s: s["panel"] == "lighting", "the Lighting panel")
        return {"cellar": lighting_of(doc()), "live": live()}

    def s15_play_stop_keeps_authoring() -> dict[str, Any]:
        for _ in range(2):
            play_and_wait("cellar")
            through_door("cellar", "garden")
            p().d.key("F4")
            p().wait(lambda s: s["mode"] == "edit", "back to editing")
        state = p().wait(lambda s: s.get("room_doc"), "the room")
        assert not state["dirty"], "Play/Stop marked the project changed"
        now = {k: lighting_of(on_disk(keys[k])) for k in ("cellar", "garden")}
        assert now == memo["authored"], "the files changed"
        assert lighting_of(doc()) == memo["authored"][next(k for k in keys if keys[k] == state["room"])]
        until(lambda: live()["ambient"] == (CAVE if state["room"] == keys["cellar"] else DUSK), "the edited room's lighting back")
        return {"room": state["room"], "live": live()}

    try:
        for name, action in (
            ("open_room_1", s01_open_room_1), ("enable_lighting", s02_enable_lighting),
            ("change_ambient", s03_change_ambient), ("two_coloured_lights", s04_two_coloured_lights),
            ("move_and_resize", s05_move_and_resize), ("flicker", s06_flicker), ("shadows", s07_shadows),
            ("undo_redo", s08_undo_redo), ("second_room", s09_second_room),
            ("play_between_rooms", s10_play_between_rooms), ("no_leaks", s11_no_leaks), ("zoomed_map", s12_zoomed_map),
            ("save_close_reopen", s13_save_close_reopen), ("preserved", s14_preserved),
            ("play_stop_keeps_authoring", s15_play_stop_keeps_authoring),
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
    parser.add_argument("--out", type=Path, default=REPO / "artifacts" / "acceptance_lighting")
    raise SystemExit(run(parser.parse_args().out))
