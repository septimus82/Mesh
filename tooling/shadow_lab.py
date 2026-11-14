"""Shadow Quality Lab (Milestone 12): lighting and shadows checked in the real Mesh Studio window.

A disposable project built with the engine's own operations (project_ops through studio_project), then
opened in Mesh Studio and driven with OS-level mouse and keys. Its rooms:

  Two lamps  lamp A and lamp B, wall W1 between A and point R, wall W2 between B and point S
  Shapes     one lamp, an L-shaped corner, a short block, walls running past its reach, a slanted wall
  Open       one lamp, no walls (and a door to Two lamps, for the room-change check)
  Dark       lighting on, no lamps

Every visual check compares pixels of the window at the same place under two settings (a lamp on and off,
shadows on and off): Studio's edit view holds still, so the floor's texture cancels out. Where a check
needs to know where shadows belong, it classes points by a ray test against the walls, as the GPU test
(tests/test_shadow_geometry_gpu.py) does.

Run from the repo root:  py -3.13 tooling/shadow_lab.py [--out DIR] [--renderer new|legacy]
(MESH_GUI_AT / MESH_GUI_POLITE as for the other GUI tests). ``--renderer legacy`` runs the same checks on
the pre-Milestone-12 shadow overlay, for the before/after record. Writes DIR/report.json and screenshots.
"""

from __future__ import annotations

import argparse
import json
import math
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

from engine import project_ops as ops  # noqa: E402
from engine.studio_project import Project  # noqa: E402

ROWS = 15
NIGHT = [60, 70, 110, 255]
# Laid out so that each probe point is well inside both lamps' reach and clear of every shadow edge.
W1 = [(3, r) for r in range(3, 6)]             # between lamp A and R
W2 = [(5, r) for r in range(6, 9)]             # between the lamps: hides S from lamp B
LAMP_A, LAMP_B = (5, 4), (5, 9)
R, S = (1, 7), (7, 5)                          # R: A blocked, B lights it.  S: B blocked, A lights it.
BORDER = [(c, 0) for c in range(20)] + [(c, 14) for c in range(20)] + [(0, r) for r in range(15)] + [(19, r) for r in range(15)]
SHAPES_LAMP = (8, 7)
L_CORNER = [(11, r) for r in range(3, 7)] + [(c, 6) for c in range(11, 15)]
SHORT_BLOCK = [(5, 10)]
LONG_WALL = [(c, 12) for c in range(2, 18)]    # runs past the lamp's reach at both ends
SLANT = [[0.0, 0.0], [20.0, 0.0], [100.0, 150.0], [80.0, 150.0]]  # a slanted wall (entity occluder_poly)
SLANT_AT = (440.0, 220.0)
STEP_FAILURES = (AssertionError, AttributeError, KeyError, IndexError, TypeError, ValueError, OSError, RuntimeError,
                 StopIteration)


def world(cell: tuple[float, float]) -> tuple[float, float]:
    """The middle of a map cell (column, row from the top) in world units (y up)."""
    return cell[0] * 32 + 16.0, (ROWS - cell[1]) * 32 - 16.0


def build(root: Path) -> dict[str, str]:
    from engine.project_scaffold import create_project

    create_project(root, "Shadow Lab", template_id="blank")
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    project = Project(root, config["world_file"])
    keys = {name: project.add_room(label) for name, label in
            (("two", "Two lamps"), ("shapes", "Shapes"), ("open", "Open"), ("dark", "Dark"))}

    def lit(key: str, shadows: str = "hard") -> None:
        project.edit_scene(lambda s: ops.set_room_lighting(s, enabled=True, ambient=NIGHT, shadows=shadows), key)

    def lamp(key: str, cell: tuple[int, int], colour: str, radius: float) -> None:
        x, y = world(cell)
        project.edit_scene(lambda s: ops.add_light(s, x, y, color=colour, radius=radius)[0], key)

    def walls(key: str, cells: list[tuple[int, int]]) -> None:
        project.edit_scene(lambda s: ops.paint_tiles(s, ops.WALLS, cells, ops.STARTER_WALL), key)

    for key in keys.values():
        lit(key)
    lamp(keys["two"], LAMP_A, "White", 260)
    lamp(keys["two"], LAMP_B, "Cold", 260)
    walls(keys["two"], W1 + W2)
    lamp(keys["shapes"], SHAPES_LAMP, "White", 260)
    walls(keys["shapes"], L_CORNER + SHORT_BLOCK + LONG_WALL)

    def slant(scene: dict[str, Any]) -> dict[str, Any]:
        # A slanted wall as an object's outline (occluder_poly): Studio has no tool for it yet; the engine reads it.
        out: dict[str, Any] = json.loads(json.dumps(scene))
        out.setdefault("entities", []).append({"id": "shapes_slanted_wall", "name": "Slanted wall", "x": SLANT_AT[0],
                                               "y": SLANT_AT[1], "occluder_poly": SLANT})
        return out

    project.edit_scene(slant, keys["shapes"])
    lamp(keys["open"], (10, 7), "Warm", 260)
    project.link_rooms(keys["two"], (592.0, 400.0), keys["open"], (80.0, 400.0))
    project.save()
    return keys


# ------------------------------------------------------------------------------------- geometry
def _cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _crosses(p: tuple[float, float], q: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> bool:
    return (_cross(a, b, p) > 0) != (_cross(a, b, q) > 0) and (_cross(p, q, a) > 0) != (_cross(p, q, b) > 0)


def cell_poly(cell: tuple[int, int]) -> list[tuple[float, float]]:
    x, y = cell[0] * 32.0, (ROWS - cell[1] - 1) * 32.0
    return [(x, y), (x + 32, y), (x + 32, y + 32), (x, y + 32)]


def blocked(light: tuple[float, float], point: tuple[float, float], shapes: list[list[tuple[float, float]]]) -> bool:
    return any(_crosses(light, point, a, b) for poly in shapes for a, b in zip(poly, [*poly[1:], poly[0]]))


def near_boundary(light: tuple[float, float], point: tuple[float, float], shapes: list[list[tuple[float, float]]],
                  margin: float) -> bool:
    def seg(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        t = max(0.0, min(1.0, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1]))
                         / max(1e-9, (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)))
        return math.hypot(p[0] - a[0] - t * (b[0] - a[0]), p[1] - a[1] - t * (b[1] - a[1]))

    for poly in shapes:
        for a, b in zip(poly, [*poly[1:], poly[0]]):
            if seg(point, a, b) < margin:
                return True
        for c in poly:
            d = math.hypot(c[0] - light[0], c[1] - light[1]) or 1.0
            far = (light[0] + (c[0] - light[0]) / d * 4000, light[1] + (c[1] - light[1]) / d * 4000)
            if seg(point, c, far) < margin:
                return True
    return False


# ------------------------------------------------------------------------------------------- run
def run(out: Path, renderer: str) -> int:
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    shutil.rmtree(work, ignore_errors=True)
    root = work / "shadow_lab"
    layout = out / "layout.json"
    env_keep = {k: os.environ.get(k) for k in ("PYTHONPATH", "MESH_STUDIO_LAYOUT", "MESH_SHADOWS_RENDERER",
                                                "MESH_LIGHTING_PROFILE", "MESH_USER_DIR", "MESH_PROJECTS_DIR")}
    os.environ.update({"PYTHONPATH": str(REPO), "MESH_STUDIO_LAYOUT": str(layout), "MESH_LIGHTING_PROFILE": "1",
                       "MESH_USER_DIR": str(work / "user"), "MESH_PROJECTS_DIR": str(work / "projects")})
    if renderer == "legacy":
        os.environ["MESH_SHADOWS_RENDERER"] = "legacy"
    else:
        os.environ.pop("MESH_SHADOWS_RENDERER", None)
    keys = build(root)
    world_file = json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"]
    results: list[dict[str, Any]] = []
    holder: dict[str, Any] = {"driver": None, "page": None}
    memo: dict[str, Any] = {}

    def p() -> AuthorPage:
        return holder["page"]

    def launch() -> AuthorPage:
        layout.unlink(missing_ok=True)
        driver = Driver([sys.executable, "-m", "mesh_cli", "edit"], cwd=root, shots=out / "shots")
        page = AuthorPage(driver, layout)
        holder["driver"], holder["page"] = driver, page
        page.wait(lambda s: s["mode"] == "edit", "the Studio", timeout=60)
        return page

    def close() -> None:
        if holder["driver"] is not None:
            holder["driver"].close()  # only the Studio this lab started
            holder["driver"] = None

    def step(name: str, action: Callable[[], Any]) -> bool:
        started = time.time()
        try:
            detail, ok, error = action(), True, None
        except STEP_FAILURES as exc:
            ok, error, detail = False, f"{type(exc).__name__}: {exc}", traceback.format_exc(limit=4)
        driver = holder["driver"]
        shot = driver.shot(f"{len(results) + 1:02d}_{name}").name if driver and driver.proc.poll() is None else None
        results.append({"step": name, "ok": ok, "error": error, "detail": detail,
                        "seconds": round(time.time() - started, 1), "screenshot": shot})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {error}" if error else ""), flush=True)
        return ok

    # ------------------------------------------------------------------ the Studio, read and driven
    def until(test: Callable[[], Any], what: str, timeout: float = 10.0) -> Any:
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

    def doc() -> dict[str, Any]:
        room: dict[str, Any] = p().wait(lambda s: s.get("room_doc"), "the room")["room_doc"]
        return room

    def live() -> dict[str, Any]:
        s = p().fresh()
        return (s["play"]["runtime"]["lighting"] if s["mode"] == "play" else s["lighting"]) or {}

    def room(name: str) -> None:
        label = {"two": "Two lamps", "shapes": "Shapes", "open": "Open", "dark": "Dark"}[name]
        if p().state()["mode"] == "play":  # a failed play check must not strand the rest
            p().d.key("F4")
            p().wait(lambda s: s["mode"] == "edit", "editing")
        p().d.key("ESC")
        p().button(label)
        p().wait(lambda s: s["room"] == keys[name] and s.get("map"), f"the {label} room")
        time.sleep(0.6)

    def panel(open_it: bool) -> None:
        state = p().state()
        if (state["panel"] == "lighting") != open_it:
            p().button("Lighting")
            p().wait(lambda s: (s["panel"] == "lighting") == open_it, "the Lighting panel " + ("open" if open_it else "closed"))
            time.sleep(0.3)

    def press(text: str) -> None:
        p().reveal(text=text)
        p().button(text)

    def select_light(number: int) -> None:
        if p().state().get("light") != number - 1:
            p().press_prefix(f"Light {number}:")
            p().wait(lambda s: s.get("light") == number - 1, f"light {number} selected")

    def light_on(number: int, on: bool) -> None:
        panel(True)
        select_light(number)
        current = ops.lights(doc())[number - 1].get("enabled", True) is not False
        if current != on:
            p().press_prefix("On: ")
            until(lambda: (ops.lights(doc())[number - 1].get("enabled", True) is not False) == on,
                  f"light {number} {'on' if on else 'off'}")
        panel(False)
        time.sleep(0.5)

    def room_shadows(on: bool) -> None:
        panel(True)
        press("Shadows on" if on else "Shadows off")
        until(lambda: (doc().get("settings") or {}).get("lighting_shadows_mode") == ("hard" if on else "none"), "shadows")
        panel(False)
        time.sleep(0.5)

    def screen_of(point: tuple[float, float], s: dict[str, Any]) -> tuple[float, float]:
        height = s["window"][1]
        if s["mode"] == "play":
            play = s["play"]
            zoom = play["runtime"]["camera"]["zoom"]
            return (play["player_screen"][0] + (point[0] - play["player"][0]) * zoom,
                    height - (play["player_screen"][1] + (point[1] - play["player"][1]) * zoom))
        m = s["map"]
        x0, y0, x1, y1 = m["screen"]
        mw, mh = m["width"] * m["tilewidth"], m["height"] * m["tileheight"]
        return x0 + point[0] / mw * (x1 - x0), height - (y0 + point[1] / mh * (y1 - y0))

    def snap(name: str) -> tuple[Any, dict[str, Any]]:
        """A screenshot and the state it was taken in (one frame, nothing moving)."""
        state = p().fresh()
        image = Image.open(holder["driver"].shot(name)).convert("RGB")
        return image, state

    def rgb(shot: tuple[Any, dict[str, Any]], point: tuple[float, float], r: int = 2) -> tuple[float, float, float]:
        image, state = shot
        sx, sy = screen_of(point, state)
        kx, ky = image.width / state["window"][0], image.height / state["window"][1]
        cx, cy = int(sx * kx), int(sy * ky)
        pixels = [image.getpixel((cx + dx, cy + dy)) for dx in range(-r, r + 1) for dy in range(-r, r + 1)]
        r_, g_, b_ = (round(sum(px[i] for px in pixels) / len(pixels), 1) for i in range(3))
        return r_, g_, b_

    def same(a: tuple[float, ...], b: tuple[float, ...], tol: float = 4.0) -> bool:
        return all(abs(x - y) <= tol for x, y in zip(a, b))

    def lum(c: tuple[float, ...]) -> float:
        return round(sum(c[:3]) / 3, 1)

    def wall_shapes(cells: list[tuple[int, int]]) -> list[list[tuple[float, float]]]:
        """The given walls and the room's stone border, which casts shadows too."""
        return [cell_poly(c) for c in [*cells, *BORDER]]

    def reset_two() -> None:
        """Both lamps on, steady, shadows on: each check starts from the same room."""
        room("two")
        for number in (1, 2):
            light = ops.lights(doc())[number - 1]
            if light.get("enabled", True) is False:
                light_on(number, True)
            if light.get("flicker_enabled"):
                panel(True)
                select_light(number)
                press("Steady")
                until(lambda: not ops.lights(doc())[number - 1].get("flicker_enabled"), "steady")
                panel(False)
        if (doc().get("settings") or {}).get("lighting_shadows_mode") != "hard":
            room_shadows(True)

    def classify(light: tuple[float, float], radius: float, shapes: list[list[tuple[float, float]]],
                 on: Any, unshadowed: Any, light_off: Any, skip: list[tuple[float, float]]) -> dict[str, Any]:
        """Grid points: blocked ones must look like the lamp off, seen ones like shadows off."""
        wrong, checked = [], 0
        for col in range(1, 19):
            for row in range(1, 14):
                for ox, oy in ((-7, -7), (7, 7)):
                    pt = (col * 32 + 16.0 + ox, (ROWS - row) * 32 - 16.0 + oy)
                    d = math.hypot(pt[0] - light[0], pt[1] - light[1])
                    if d < 24 or d > radius * 0.95 or any(math.hypot(pt[0] - q[0], pt[1] - q[1]) < 40 for q in skip):
                        continue
                    if any(_point_in(pt, s) for s in shapes) or near_boundary(light, pt, shapes, 5.0):
                        continue
                    expect = light_off if blocked(light, pt, shapes) else unshadowed
                    got, want = rgb(on, pt, 1), rgb(expect, pt, 1)
                    checked += 1
                    if not same(got, want, 5.0):
                        wrong.append({"at": pt, "should_be": "blocked" if expect is light_off else "lit", "got": got, "want": want})
        return {"checked": checked, "wrong": len(wrong), "examples": wrong[:5]}

    # ------------------------------------------------------------------------------------ steps
    def s00_open_the_lab() -> dict[str, Any]:
        launch()
        room("two")
        lit = until(lambda: (lambda x: x if x.get("enabled") and len(x["static"]) == 2 else None)(live()), "two lamps lit")
        return {"renderer": renderer, "lighting": {k: lit.get(k) for k in ("shadows_mode", "ambient", "occluders", "stats")}}

    def s01_one_light_no_walls() -> dict[str, Any]:
        room("open")
        shot = snap("open_room")
        lamp = world((10, 7))
        ring = [lum(rgb(shot, (lamp[0] + dx, lamp[1] + dy))) for dx, dy in ((60, 0), (-60, 0), (0, 60), (0, -60))]
        falls = [lum(rgb(shot, (lamp[0] + d, lamp[1] + 7))) for d in (30, 90, 150, 210, 290)]
        assert max(ring) - min(ring) <= 8, f"a lamp with nothing near shines evenly all round: {ring}"
        assert all(a >= b - 2 for a, b in zip(falls, falls[1:])) and falls[0] > falls[-1] + 25, f"falls off: {falls}"
        return {"same_distance_all_round": ring, "brightness_by_distance": falls}

    def both_reach() -> tuple[float, float]:
        """A floor point both lamps light, with no wall in the way of either."""
        shapes, a, b = wall_shapes(W1 + W2), world(LAMP_A), world(LAMP_B)
        for col in range(1, 19):
            for row in range(1, 14):
                pt = world((col, row))
                if (math.hypot(pt[0] - a[0], pt[1] - a[1]) < 200 and math.hypot(pt[0] - b[0], pt[1] - b[1]) < 200
                        and not blocked(a, pt, shapes) and not blocked(b, pt, shapes)
                        and not near_boundary(a, pt, shapes, 12) and not near_boundary(b, pt, shapes, 12)):
                    return pt
        raise AssertionError("the lab room has no point both lamps light")

    def s02_to_07_two_lamps() -> dict[str, Any]:
        reset_two()
        a, b = world(LAMP_A), world(LAMP_B)
        r, s_ = world(R), world(S)
        shapes = wall_shapes(W1 + W2)
        assert blocked(a, r, shapes) and not blocked(b, r, shapes), "R: behind W1 from A, open to B"
        assert blocked(b, s_, shapes) and not blocked(a, s_, shapes), "S: behind W2 from B, open to A"
        near_a = (a[0] + 48, a[1] + 40)
        both_pt = both_reach()
        shots = {}
        light_on(1, True)
        light_on(2, True)
        shots["both"] = snap("two_both_on")
        light_on(2, False)
        shots["a_only"] = snap("two_a_only")
        light_on(1, False)
        shots["none"] = snap("two_none")
        light_on(2, True)
        shots["b_only"] = snap("two_b_only")
        light_on(1, True)
        memo["two_shots"] = shots
        v = {name: {"R": rgb(sh, r), "S": rgb(sh, s_), "near_A": rgb(sh, near_a), "both": rgb(sh, both_pt)}
             for name, sh in shots.items()}
        # Lamp B's own light where both reach: what it adds with A on, and with A off.
        b_with_a = [x - y for x, y in zip(v["both"]["both"], v["a_only"]["both"])]
        b_alone = [x - y for x, y in zip(v["b_only"]["both"], v["none"]["both"])]
        checks = {
            "2_wall_casts_a_shadow": lum(v["a_only"]["near_A"]) > lum(v["a_only"]["R"]) + 30,
            "3_room_light_stays_in_it": same(v["a_only"]["R"], v["none"]["R"]),
            "4_both_lamps_light_one_place": lum(v["both"]["both"]) > lum(v["a_only"]["both"]) + 5
            and lum(v["both"]["both"]) > lum(v["b_only"]["both"]) + 5,
            "5_wall_W1_blocks_only_lamp_A": same(v["both"]["R"], v["b_only"]["R"]),
            "6_wall_W2_blocks_only_lamp_B": same(v["both"]["S"], v["a_only"]["S"]),
            "7_lamp_A_off_leaves_lamp_B_as_it_was": all(abs(x - y) <= 5 for x, y in zip(b_with_a, b_alone)),
        }
        memo["checks_2_7"] = checks
        assert all(checks.values()), {"checks": checks, "pixels": v}
        return {"checks": checks, "pixels": v, "both_lamps_point": both_pt}

    def s08_move_a_light() -> dict[str, Any]:
        reset_two()
        panel(True)
        select_light(1)
        before = dict(ops.lights(doc())[0])
        zoom = p().state()["zoom"]
        p().drag_handle("light_move", 96 * zoom, 0)  # three tiles right: now the walls hide other places
        after = until(lambda: ops.lights(doc())[0] if ops.lights(doc())[0]["x"] != before["x"] else None, "lamp A moved")
        panel(False)
        light_on(2, False)
        on = snap("moved_a_on")
        light_on(1, False)
        off = snap("moved_a_off")
        room_shadows(False)
        light_on(1, True)
        unshadowed = snap("moved_a_unshadowed")
        room_shadows(True)
        light_on(2, True)
        result = classify((after["x"], after["y"]), float(after["radius"]), wall_shapes(W1 + W2), on, unshadowed, off,
                          skip=[world(LAMP_B)])
        assert result["wrong"] == 0 and result["checked"] > 80, result
        panel(True)
        select_light(1)
        p().drag_handle("light_move", -96 * zoom, 0)  # back where it was
        until(lambda: abs(ops.lights(doc())[0]["x"] - before["x"]) <= 3, "lamp A back")
        panel(False)
        return {"moved_from": [before["x"], before["y"]], "to": [after["x"], after["y"]], **result}

    def s09_flicker_keeps_the_shadow() -> dict[str, Any]:
        reset_two()
        light_on(2, False)
        panel(True)
        select_light(1)
        press("Torch")
        until(lambda: ops.lights(doc())[0].get("flicker_enabled"), "lamp A flickers")
        panel(False)
        r, lit_pt = world(R), (world(LAMP_A)[0] + 120, world(LAMP_A)[1])
        none_r = rgb(memo["two_shots"]["none"], r)
        behind: list[tuple[float, float, float]] = []
        lit_side: list[float] = []
        for i in range(8):
            shot = snap(f"flicker_{i}")
            behind.append(rgb(shot, r))
            lit_side.append(lum(rgb(shot, lit_pt)))
            time.sleep(0.11)
        for seen in behind:
            assert same(seen, none_r, 5), f"a flickering lamp's light got behind the wall: {seen} vs {none_r}"
        varies = max(lit_side) - min(lit_side)
        samples = [{"R": seen, "lit": lit} for seen, lit in zip(behind, lit_side)]
        panel(True)
        select_light(1)
        press("Steady")
        until(lambda: not ops.lights(doc())[0].get("flicker_enabled"), "lamp A steady")
        panel(False)
        light_on(2, True)
        return {"behind_wall": [x["R"] for x in samples], "room_light_alone": none_r, "lit_side_varies_by": varies}

    def s10_to_12_shapes() -> dict[str, Any]:
        room("shapes")
        on = snap("shapes_on")
        light_on(1, False)
        off = snap("shapes_lamp_off")
        light_on(1, True)
        room_shadows(False)
        unshadowed = snap("shapes_unshadowed")
        room_shadows(True)
        lamp = world(SHAPES_LAMP)
        slant = [[(SLANT_AT[0] + x, SLANT_AT[1] + y) for x, y in SLANT]]
        shapes = wall_shapes(L_CORNER + SHORT_BLOCK + LONG_WALL) + [[(float(x), float(y)) for x, y in poly] for poly in slant]
        result = classify(lamp, 260.0, shapes, on, unshadowed, off, skip=[])
        # Beyond the lamp's reach (behind the long wall), only the room light: no beams.
        beyond = [(c * 32 + 16.0, (ROWS - 13) * 32 - 16.0) for c in range(1, 19)]
        beams = [pt for pt in beyond if not same(rgb(on, pt), rgb(off, pt))]
        assert not beams, f"shadow or light beyond the reach: {beams}"
        assert result["wrong"] == 0 and result["checked"] > 120, result
        return {**result, "points_beyond_reach_checked": len(beyond)}

    def ratios(shot: tuple[Any, dict[str, Any]]) -> dict[str, float]:
        """Brightness at R (only lamp B), S (only lamp A) and beside lamp A, averaged over a few pixels."""
        return {"R": lum(rgb(shot, world(R), 6)), "S": lum(rgb(shot, world(S), 6)),
                "near_A": lum(rgb(shot, (world(LAMP_A)[0] + 48, world(LAMP_A)[1] + 40), 6))}

    def close_enough(a: dict[str, float], b: dict[str, float]) -> bool:
        """The same places at another size or scroll. The planks and the light's slope average a little differently
        over a 13-pixel square when the sample lands a pixel or two away: up to 15%, or 8 levels when dim."""
        return all(abs(a[k] - b[k]) <= max(8.0, 0.15 * b[k]) for k in b)

    def s14_zoom_in_studio() -> dict[str, Any]:
        reset_two()
        before = ratios(snap("zoom_before"))
        x, y = screen_of(world((10, 7)), p().fresh())
        p().d.scroll(x, y, 3)
        zoom = p().wait(lambda s: s["zoom"] > 1.15, "zoomed in")["zoom"]
        time.sleep(0.5)
        zoomed = snap("zoomed")
        after = ratios(zoomed)
        # Same places, bigger on screen: R still lamp B's light only, S still lamp A's.
        assert close_enough(after, before), (before, after)
        p().d.scroll(x, y, -3)
        p().wait(lambda s: s["zoom"] < zoom - 0.1, "zoomed back")
        memo["edit_ratios"] = before
        return {"zoom": zoom, "before": before, "zoomed": after}

    def s16_lighting_off_and_on() -> dict[str, Any]:
        reset_two()
        panel(True)
        press("Off")
        until(lambda: (doc().get("settings") or {}).get("lighting_enabled") is False and not live().get("enabled"), "lighting off")
        panel(False)
        off = snap("lighting_off")
        panel(True)
        press("On")
        until(lambda: (doc().get("settings") or {}).get("lighting_enabled") is True and live().get("enabled"), "lighting on")
        panel(False)
        on = snap("lighting_on_again")
        r_off, r_on = lum(rgb(off, world(R))), lum(rgb(on, world(R)))
        assert r_off > r_on + 20, f"unlit, the floor shows as drawn ({r_off}); lit, it is darker away from lamps ({r_on})"
        assert same(rgb(on, world(R)), rgb(memo["two_shots"]["both"], world(R))), "lighting back on: the same as before"
        return {"R_unlit": r_off, "R_lit": r_on}

    def s19_no_lamps_no_darkening() -> dict[str, Any]:
        room("dark")
        on = snap("dark_shadows_on")
        room_shadows(False)
        off = snap("dark_shadows_off")
        room_shadows(True)
        points = [world((c, r)) for c in range(2, 18, 3) for r in range(2, 13, 3)]
        diff = max(max(abs(x - y) for x, y in zip(rgb(on, pt), rgb(off, pt))) for pt in points)
        assert diff <= 2, f"shadows on darkened a room with no lamps by up to {diff}"
        return {"points": len(points), "largest_difference": diff}

    def s18_and_13_play_matches_studio() -> dict[str, Any]:
        reset_two()
        edit = ratios(snap("edit_view"))
        p().d.key("F4")
        p().wait(lambda s: s["mode"] == "play" and s["play"] and s["play"]["player"], "playing", timeout=30)
        time.sleep(2.0)  # past the room's fade-in
        play = ratios(snap("play_view"))
        start = p().fresh()["play"]["player"]
        p().go_to(start[0] + 96, start[1] - 64, tol=10)  # the camera follows the player
        time.sleep(0.4)
        moved = p().fresh()["play"]["player"]
        scrolled = ratios(snap("play_scrolled"))
        result: dict[str, Any] = {"edit": edit, "play": play, "scrolled": scrolled, "player": [start, moved]}
        memo["play"] = result
        assert close_enough(play, edit), result
        assert close_enough(scrolled, play), result
        return result

    def s15_room_change_and_back() -> dict[str, Any]:
        def door_of(key: str) -> tuple[float, float]:
            scene = json.loads((root / Project(root, world_file).path(keys[key])).read_text(encoding="utf-8"))
            door = next(e for e in scene["entities"] if e.get("tag") == "door")
            return float(door["x"]), float(door["y"])

        def through(key: str, lamps: int, what: str) -> None:
            x, y = door_of(key)
            p().go_to(x, y - 80, tol=10)
            p().d.hold("W", 0.9)
            p().wait(lambda s: s["play"] and len(s["play"]["runtime"]["lighting"]["static"]) == lamps, what, timeout=10)
            time.sleep(1.8)  # the fade-in
            p().d.hold("S", 0.4)  # step off the arrival spot, away from the door

        through("two", 1, "the Open room (one lamp)")
        other = live()
        own = list(world((10, 7)))
        assert [x["at"] for x in other["static"]] == [own], f"the Open room shows only its own lamp: {other['static']}"
        through("open", 2, "back in Two lamps")
        p().go_to(*memo["play"]["player"][1], tol=10)  # where the scrolled view was taken
        time.sleep(0.4)
        back = ratios(snap("back_in_two_lamps"))
        p().d.key("F4")
        p().wait(lambda s: s["mode"] == "edit", "editing")
        before = memo["play"]["scrolled"]
        assert close_enough(back, before), (before, back)
        return {"open_room": {"lamps": len(other["static"]), "stats": other.get("stats")}, "back": back, "before": before}

    def s17_save_and_reopen() -> dict[str, Any]:
        reset_two()
        panel(True)
        press("Soft")
        until(lambda: (doc().get("settings") or {}).get("lighting_shadow_softness") == "soft", "soft edges")
        panel(False)
        select_off = snap("soft_edges")
        p().d.key("ctrl+s")
        p().wait(lambda s: not s["dirty"], "saved")
        saved = {k: ops.lights(json.loads((root / Project(root, world_file).path(keys[k])).read_text(encoding="utf-8")))
                 for k in ("two", "shapes")}
        close()
        launch()
        room("two")
        reopened = snap("reopened")
        assert (doc().get("settings") or {}).get("lighting_shadow_softness") == "soft"
        assert live().get("stats", {}).get("shadow_softness") in ("soft", None) or renderer == "legacy"
        diff = max(max(abs(a - b) for a, b in zip(rgb(select_off, world(pt)), rgb(reopened, world(pt)))) for pt in (R, S, (6, 9)))
        assert diff <= 4, f"the reopened room looks different by up to {diff}"
        return {"lights_saved": saved, "largest_difference": diff}

    def s20_performance() -> dict[str, Any]:
        """The lighting pass's CPU and GPU time (MESH_LIGHTING_PROFILE), each room as it is, Two lamps sharp and soft."""
        def measure() -> dict[str, Any]:
            time.sleep(4.5)  # the profile keeps the last 240 frames: let it fill with this setting
            lit = live()
            return {"profile": lit.get("profile"), "stats": lit.get("stats")}

        figures = {}
        for name in ("shapes", "open", "dark"):
            room(name)
            figures[name] = measure()
        room("two")
        for edges in ("Sharp", "Soft", "Softer"):
            panel(True)
            press(edges)
            until(lambda: (doc().get("settings") or {}).get("lighting_shadow_softness") == edges.lower(), f"{edges} edges")
            panel(False)
            figures[f"two_{edges.lower()}"] = measure()
        return {"renderer": renderer, "lighting_pass": figures}

    def s00_gpu_pixel_tests() -> dict[str, Any]:
        """The exact-pixel GPU tests (flat floor, every pixel classed by a ray test), which pytest skips without MESH_GL_SMOKE."""
        import subprocess  # noqa: PLC0415

        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                               "tests/test_shadow_compositing_gpu.py", "tests/test_shadow_geometry_gpu.py"],
                              cwd=REPO, env={**os.environ, "MESH_GL_SMOKE": "1"}, capture_output=True, text=True)
        tail = (done.stdout + done.stderr).strip().splitlines()[-1:]
        assert done.returncode == 0, tail
        return {"pytest": tail}

    steps = [("gpu_pixel_tests", s00_gpu_pixel_tests), ("open_the_lab", s00_open_the_lab), ("1_one_light_no_walls", s01_one_light_no_walls),
             ("2_to_7_two_lamps_two_walls", s02_to_07_two_lamps), ("8_move_a_light", s08_move_a_light),
             ("9_flicker_keeps_the_shadow", s09_flicker_keeps_the_shadow),
             ("10_to_12_corner_reach_slant", s10_to_12_shapes), ("14_zoom_in_studio", s14_zoom_in_studio),
             ("16_lighting_off_and_on", s16_lighting_off_and_on), ("19_no_lamps_no_darkening", s19_no_lamps_no_darkening),
             ("18_13_play_matches_studio_and_scrolls", s18_and_13_play_matches_studio),
             ("15_room_change_and_back", s15_room_change_and_back), ("17_soft_save_and_reopen", s17_save_and_reopen),
             ("20_performance", s20_performance)]
    try:
        for name, action in steps:
            if not step(name, action) and name == "open_the_lab":
                break
    finally:
        close()
        for k, v in env_keep.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    passed = sum(r["ok"] for r in results)
    (out / "report.json").write_text(json.dumps({"renderer": renderer, "passed": passed == len(results), "steps": results},
                                                indent=2, default=str), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)  # the disposable project goes; report and screenshots stay
    print(f"{passed}/{len(results)} checks passed; report: {out / 'report.json'}")
    return 0 if passed == len(results) else 1


def _point_in(pt: tuple[float, float], poly: list[tuple[float, float]]) -> bool:
    inside = False
    for (x0, y0), (x1, y1) in zip(poly, [*poly[1:], poly[0]]):
        if (y0 > pt[1]) != (y1 > pt[1]) and pt[0] < x0 + (pt[1] - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO / "artifacts" / "shadow_lab")
    parser.add_argument("--renderer", choices=("new", "legacy"), default="new")
    args = parser.parse_args()
    raise SystemExit(run(args.out, args.renderer))
