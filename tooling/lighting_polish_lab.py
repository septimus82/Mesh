"""Lighting Polish Lab (Milestone 12.1): character shadows and natural flicker, checked in the real Mesh Studio window.

A disposable project built with the engine's own operations, opened in Mesh Studio and driven with OS-level
mouse and keys (as tooling/shadow_lab.py does for the walls' shadows). Its rooms:

  Lamps    lamp L1 (white) and L2 (warm, off at first), a wall above L1, the player beside L1, two patrolling
           NPCs (Walker along the bottom, Guard up and down on the left)
  Flicker  seven lamps: steady, candle, torch A, fire / faulty, torch B, and one to make a custom flicker on

Still checks compare two screenshots of Studio's edit view, which holds still, under two settings (characters'
shadows on and off, a lamp on and off): the floor's texture cancels out and what is left is the shadow. Flicker
is checked as a time series: every few frames the Studio's dump gives each lamp's reach and colour at the
lighting clock, and each sample must be exactly what the flicker formula (engine/lighting/flicker.py) gives
for that light's settings and seed at that moment - in Studio and in Play, before and after reopening.

Run from the repo root:  py -3.13 tooling/lighting_polish_lab.py [--out DIR]
(MESH_GUI_AT / MESH_GUI_POLITE as for the other GUI tests). Writes DIR/report.json, DIR/flicker_series.png
and screenshots. A copy of Hollowmere_Trial (if present) is opened for the compatibility check; the original
is only read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import statistics
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
from shadow_lab import NIGHT, ROWS, STEP_FAILURES, world  # noqa: E402

from engine import project_ops as ops  # noqa: E402
from engine.lighting import flicker as fl  # noqa: E402
from engine.lighting.static_light_builder import _light_seed  # noqa: E402
from engine.studio_project import Project  # noqa: E402

L1, L2 = (6, 7), (14, 7)
PLAYER_AT = (336.0, 240.0)                       # beside L1, level with it: its shadow falls to the right
WALL = [(6, 4), (6, 5)]                          # above L1: its shadow runs up to the border
WALKER = [(100.0, 80.0), (330.0, 80.0)]          # along the bottom, below L1
GUARD = [(90.0, 200.0), (90.0, 380.0)]           # up and down on the left
FLICKER_LAMPS = [("steady", (3, 4)), ("candle", (8, 4)), ("torch", (13, 4)), ("fire", (17, 4)),
                 ("faulty", (3, 10)), ("torch", (8, 10)), ("steady", (13, 10))]
CUSTOM = 6                                       # the lamp made into a custom flicker in the Studio
HOLLOWMERE = Path.home() / "Documents" / "Mesh Projects" / "Hollowmere_Trial"


def build(root: Path) -> dict[str, str]:
    from engine.project_scaffold import create_project

    create_project(root, "Lighting Polish Lab", template_id="blank")
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    project = Project(root, config["world_file"])
    keys = {"lamps": project.add_room("Lamps"), "flicker": project.add_room("Flicker")}
    for key in keys.values():
        project.edit_scene(lambda s: ops.set_room_lighting(s, enabled=True, ambient=NIGHT, shadows="hard"), key)

    def lamp(key: str, cell: tuple[int, int], colour: str, radius: float, **change: Any) -> None:
        x, y = world(cell)

        def add(scene: dict[str, Any]) -> dict[str, Any]:
            scene, index = ops.add_light(scene, x, y, color=colour, radius=radius)
            return ops.set_light(scene, index, **change) if change else scene

        project.edit_scene(add, key)

    lamp(keys["lamps"], L1, "White", 300)
    lamp(keys["lamps"], L2, "Warm", 300, enabled=False)
    project.edit_scene(lambda s: ops.paint_tiles(s, ops.WALLS, WALL, ops.STARTER_WALL), keys["lamps"])
    prefab = next(p for p in json.loads((root / "assets" / "prefabs.json").read_text(encoding="utf-8"))
                  if p.get("id") == "player")["entity"]

    def people(scene: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = json.loads(json.dumps(scene))
        for entity in out.get("entities", []):
            if entity.get("prefab_id") == "player" or entity.get("tag") == "player":
                entity["x"], entity["y"] = PLAYER_AT
        for name, path in (("Walker", WALKER), ("Guard", GUARD)):
            npc = json.loads(json.dumps(prefab))
            npc.update({"id": f"lamps_{name.lower()}", "name": name, "tag": "npc", "x": path[0][0], "y": path[0][1],
                        "behaviours": ["Patrol", "Animator"]})
            npc["behaviour_config"] = {"Animator": npc["behaviour_config"]["Animator"],
                                       "Patrol": {"patrol_points": [{"x": x, "y": y} for x, y in path], "patrol_speed": 45.0}}
            npc.get("components", {}).pop("collider", None)  # walks through the player: the lab is about light
            out.setdefault("entities", []).append(npc)
        return out

    project.edit_scene(people, keys["lamps"])
    for preset, cell in FLICKER_LAMPS:
        lamp(keys["flicker"], cell, "Warm", 110, **({} if preset == "steady" else {"flicker": preset}))
    project.save()
    return keys


# ----------------------------------------------------------------------------------- flicker
def expected_flicker(lights: list[dict[str, Any]], reduced: bool = False) -> list[Callable[[float], tuple[float, float]] | None]:
    """For each enabled light (as the Studio lists them), (brightness, reach) at a clock, or None if it is steady.
    The seed as the static light builder gives it: the light's own, or one from where it is."""
    out: list[Callable[[float], tuple[float, float]] | None] = []
    flickering = 0
    for cfg in lights:
        if cfg.get("enabled", True) is False:
            continue
        profile = fl.flicker_profile(cfg)
        if profile is None or not cfg.get("flicker_enabled"):
            out.append(None)
            continue
        seed = int(cfg["flicker_seed"]) if cfg.get("flicker_seed") is not None else _light_seed(cfg, flickering)
        flickering += 1
        strength = fl.flicker_strength(cfg)
        out.append(_sampler(profile, seed, strength, reduced))
    return out


def _sampler(profile: fl.FlickerProfile, seed: int, strength: float, reduced: bool) -> Callable[[float], tuple[float, float]]:
    def sample(t: float) -> tuple[float, float]:
        return fl.flicker_sample(profile, seed, t, strength, reduced)

    return sample


def check_series(samples: list[dict[str, Any]], lights: list[dict[str, Any]], reduced: bool = False) -> dict[str, Any]:
    """Every recorded reach and colour is the formula's at the recorded clock; steady lights never move."""
    formulas = expected_flicker(lights, reduced)
    enabled = [cfg for cfg in lights if cfg.get("enabled", True) is not False]
    worst_reach = worst_bright = 0.0
    for sample in samples:
        for cfg, formula, seen in zip(enabled, formulas, sample["static"]):
            base = ops.rgb(cfg.get("color"))
            channel = max(range(3), key=lambda i: base[i])
            brightness, reach = formula(sample["clock"]) if formula else (1.0, 1.0)
            want_r, want_c = float(cfg["radius"]) * reach, round(base[channel] * min(brightness, 255.0 / base[channel]))
            worst_reach = max(worst_reach, abs(seen["radius"] - want_r))
            worst_bright = max(worst_bright, abs(seen["color"][channel] - want_c))
    assert len(samples) >= 8, f"only {len(samples)} samples"
    # One frame's clock step at most between the dump's clock and the lights' (they are read in the same frame).
    assert worst_reach <= 0.6 and worst_bright <= 1.01, f"the lights are not the formula's: reach off by {worst_reach}, " \
        f"colour by {worst_bright}"
    return {"samples": len(samples), "worst_reach_px": round(worst_reach, 3), "worst_colour_levels": worst_bright,
            "seconds": round(samples[-1]["clock"] - samples[0]["clock"], 2)}


def peak_spread(values: list[float]) -> float:
    peaks = [i for i in range(1, len(values) - 1) if values[i - 1] < values[i] >= values[i + 1]]
    gaps = [b - a for a, b in zip(peaks, peaks[1:])]
    return statistics.pstdev(gaps) / statistics.mean(gaps) if len(gaps) > 2 else 0.0


# ------------------------------------------------------------------------------------------- run
def run(out: Path) -> int:
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    shutil.rmtree(work, ignore_errors=True)
    root = work / "polish_lab"
    layout = out / "layout.json"
    env_keep = {k: os.environ.get(k) for k in ("PYTHONPATH", "MESH_STUDIO_LAYOUT", "MESH_SHADOWS_RENDERER",
                                                "MESH_LIGHTING_PROFILE", "MESH_USER_DIR", "MESH_PROJECTS_DIR")}
    os.environ.update({"PYTHONPATH": str(REPO), "MESH_STUDIO_LAYOUT": str(layout), "MESH_LIGHTING_PROFILE": "1",
                       "MESH_USER_DIR": str(work / "user"), "MESH_PROJECTS_DIR": str(work / "projects")})
    os.environ.pop("MESH_SHADOWS_RENDERER", None)
    keys = build(root)
    results: list[dict[str, Any]] = []
    holder: dict[str, Any] = {"driver": None, "page": None}
    memo: dict[str, Any] = {}

    def p() -> AuthorPage:
        return holder["page"]

    def launch(where: Path = root) -> AuthorPage:
        layout.unlink(missing_ok=True)
        driver = Driver([sys.executable, "-m", "mesh_cli", "edit"], cwd=where, shots=out / "shots")
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
        if not ok and driver and driver.proc.poll() is None:  # a failed step mustn't leave the next one in Play
            try:
                if p().state()["mode"] == "play":
                    p().d.key("F4")
                    p().wait(lambda s: s["mode"] == "edit", "editing")
            except STEP_FAILURES:
                pass
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
            except (KeyError, IndexError, TypeError, StopIteration):
                value = None
            if time.time() > deadline:
                raise AssertionError(f"timed out waiting for: {what} (message: {p().state().get('message')!r})")
            time.sleep(0.2)

    def doc() -> dict[str, Any]:
        room_doc: dict[str, Any] = p().wait(lambda s: s.get("room_doc"), "the room")["room_doc"]
        return room_doc

    def settings() -> dict[str, Any]:
        return doc().get("settings") or {}

    def live(s: dict[str, Any] | None = None) -> dict[str, Any]:
        s = s or p().fresh()
        return (s["play"]["runtime"]["lighting"] if s["mode"] == "play" else s["lighting"]) or {}

    def room(name: str) -> None:
        label = {"lamps": "Lamps", "flicker": "Flicker"}[name]
        if p().state()["mode"] == "play":
            p().d.key("F4")
            p().wait(lambda s: s["mode"] == "edit", "editing")
        if p().state().get("room") == keys[name]:
            return
        for attempt in range(3):  # a click can land while the Studio is still redrawing: try again
            p().d.key("ESC")
            p().button(label)
            try:
                p().wait(lambda s: s["room"] == keys[name] and s.get("map"), f"the {label} room", timeout=5)
                break
            except AssertionError:
                if attempt == 2:
                    raise
        time.sleep(0.6)

    def panel(open_it: bool) -> None:
        for attempt in range(3):  # a click can land while the panel is still redrawing: try again
            if (p().state()["panel"] == "lighting") == open_it:
                return
            p().button("Lighting")
            try:
                p().wait(lambda s: (s["panel"] == "lighting") == open_it, "the Lighting panel", timeout=3)
                time.sleep(0.3)
                return
            except AssertionError:
                if attempt == 2:
                    raise

    def press(text: str) -> None:
        p().reveal(text=text)
        p().button(text)

    def press_toggle(label: str, on: bool) -> None:
        """A "Label: On/Off" toggle, pressed only if it isn't already as wanted."""
        want, other = f"{label}: {'On' if on else 'Off'}", f"{label}: {'Off' if on else 'On'}"
        try:
            p().reveal(text=want)  # scrolled into view, already as wanted
            return
        except AssertionError:
            p().press(other)
        until(lambda: p()._find(text=want), want)

    def select_light(number: int) -> None:
        if p().state().get("light") != number - 1:
            p().press_prefix(f"Light {number}:")
            p().wait(lambda s: s.get("light") == number - 1, f"light {number} selected")

    def light_on(number: int, on: bool) -> None:
        panel(True)
        select_light(number)
        press_toggle("On", on)
        until(lambda: (ops.lights(doc())[number - 1].get("enabled", True) is not False) == on, f"light {number} on={on}")
        panel(False)
        time.sleep(0.5)

    def fine_tune(open_it: bool = True) -> None:
        panel(True)
        shown = p()._find(text="v Fine-tune shadows") is not None
        if shown != open_it:
            press(("> " if open_it else "v ") + "Fine-tune shadows")
            until(lambda: p()._find(text=("v " if open_it else "> ") + "Fine-tune shadows"), "fine-tune shadows")

    def room_characters(on: bool) -> None:
        fine_tune(True)
        press_toggle("Characters cast shadows", on)
        until(lambda: (settings().get("lighting_character_shadows") is not False) == on, "characters' shadows")
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

    def zoom_of(s: dict[str, Any]) -> float:
        if s["mode"] == "play":
            return float(s["play"]["runtime"]["camera"]["zoom"])
        m = s["map"]
        return float((m["screen"][2] - m["screen"][0]) / (m["width"] * m["tilewidth"]))

    def snap(name: str) -> tuple[Any, dict[str, Any]]:
        state = p().fresh()
        image = Image.open(holder["driver"].shot(name)).convert("RGB")
        return image, state

    def lum_at(shot: tuple[Any, dict[str, Any]], point: tuple[float, float], r: int = 2) -> float:
        image, state = shot
        sx, sy = screen_of(point, state)
        kx, ky = image.width / state["window"][0], image.height / state["window"][1]
        cx, cy = int(sx * kx), int(sy * ky)
        pixels = [image.getpixel((cx + dx, cy + dy)) for dx in range(-r, r + 1) for dy in range(-r, r + 1)]
        return float(sum(sum(px) / 3 for px in pixels) / len(pixels))

    def darkened(a: tuple[Any, dict[str, Any]], b: tuple[Any, dict[str, Any]], centre: tuple[float, float],
                 half: float = 90.0, threshold: float = 8.0) -> list[tuple[float, float]]:
        """World offsets from ``centre`` (within ``half`` world px) where shot a is darker than shot b."""
        (ia, sa), (ib, _sb) = a, b
        z = zoom_of(sa)
        cx, cy = screen_of(centre, sa)
        kx = ia.width / sa["window"][0]
        found = []
        step_px = max(1, int(2 * z))
        for sy in range(int(cy - half * z), int(cy + half * z), step_px):
            for sx in range(int(cx - half * z), int(cx + half * z), step_px):
                px, py = int(sx * kx), int(sy * kx)
                if not (0 <= px < ia.width and 0 <= py < ia.height):
                    continue
                if sum(ib.getpixel((px, py))) / 3 - sum(ia.getpixel((px, py))) / 3 > threshold:
                    found.append(((sx - cx) / z, -(sy - cy) / z))
        return found

    def lobe(points: list[tuple[float, float]], away: tuple[float, float]) -> dict[str, Any]:
        """Where a shadow lies around a character's feet: how much, which way, how much on the lamp's side."""
        n = len(points)
        if not n:
            return {"pixels": 0}
        mx, my = sum(x for x, _ in points) / n, sum(y for _, y in points) / n
        d = math.hypot(*away) or 1.0
        ux, uy = away[0] / d, away[1] / d
        toward = sum(1 for x, y in points if x * ux + y * uy < -6)
        return {"pixels": n, "centre": [round(mx, 1), round(my, 1)],
                "direction_agreement": round((mx * ux + my * uy) / (math.hypot(mx, my) or 1.0), 3),
                "on_the_lamps_side": round(toward / n, 3), "reach": round(max(x * ux + y * uy for x, y in points), 1)}

    def feet_of(name: str, s: dict[str, Any] | None = None) -> tuple[float, float]:
        """A character's feet as the lighting draws its shadow from them (the stats), nearest to the object."""
        s = s or p().fresh()
        if s["mode"] == "play":
            sprite = next(sp for sp in s["play"]["sprites"] if sp["name"] == name)
            at = sprite["at"]
        else:
            entity = next(e for e in s["room_doc"]["entities"] if e.get("name") == name or
                          (name == "Player" and e.get("prefab_id") == "player"))
            at = [float(entity["x"]), float(entity["y"])]
        feet = live(s)["stats"]["character_feet"]
        best = min(feet, key=lambda f: math.hypot(f[0] - at[0], f[1] - at[1] + 20))
        return float(best[0]), float(best[1])

    def away_from(lamp: tuple[int, int], feet: tuple[float, float]) -> tuple[float, float]:
        lx, ly = world(lamp)
        return feet[0] - lx, feet[1] - ly

    def edge_pixels(shot: tuple[Any, dict[str, Any]], lit: tuple[Any, dict[str, Any]], dark: tuple[Any, dict[str, Any]],
                    start: tuple[float, float], end: tuple[float, float]) -> int:
        """How many world px along a line are part-way between in shadow and lit (10-90%): the soft edges' width.
        Measured as the share of the lamp's light that arrives (against the same view unshadowed and with the lamp
        off), so the lamp's own fading with distance doesn't count as an edge."""
        n = int(math.hypot(end[0] - start[0], end[1] - start[1]))
        share = []
        for i in range(n):
            pt = (start[0] + (end[0] - start[0]) * i / n, start[1] + (end[1] - start[1]) * i / n)
            top, floor = lum_at(lit, pt, 0), lum_at(dark, pt, 0)
            if top - floor >= 6:
                share.append((lum_at(shot, pt, 0) - floor) / (top - floor))
        low = min(share)
        return sum(1 for v in share if low + 0.1 * (1 - low) < v < low + 0.9 * (1 - low))

    def record(seconds: float) -> list[dict[str, Any]]:
        """The lamps' reach and colour at the lighting clock, every dump, for ``seconds``."""
        samples, seen = [], set()
        deadline = time.time() + seconds
        while time.time() < deadline:
            lit = live()
            if lit.get("clock") in seen or not lit.get("static"):
                continue
            seen.add(lit["clock"])
            samples.append({"clock": lit["clock"], "static": lit["static"]})
        return samples

    # ------------------------------------------------------------------------------------ the checks
    def s00_gpu_pixel_tests() -> dict[str, Any]:
        """The exact-pixel GPU tests (characters' and walls' shadows), which pytest skips without MESH_GL_SMOKE."""
        import subprocess  # noqa: PLC0415

        done = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                               "tests/test_character_shadows_gpu.py", "tests/test_shadow_compositing_gpu.py",
                               "tests/test_shadow_geometry_gpu.py"],
                              cwd=REPO, env={**os.environ, "MESH_GL_SMOKE": "1"}, capture_output=True, text=True)
        tail = (done.stdout + done.stderr).strip().splitlines()[-1:]
        assert done.returncode == 0, tail
        return {"pytest": tail}

    def s00_open_the_lab() -> dict[str, Any]:
        launch()
        room("lamps")
        stats = live().get("stats") or {}
        assert stats.get("renderer") == "per_light", stats
        assert stats.get("characters") == 3, f"the player and two NPCs cast shadows: {stats}"
        return {"stats": stats}

    def s01_stationary_player_shadow() -> dict[str, Any]:
        """1: the player's shadow starts at its feet and points away from L1; never on the lamp's side, never black."""
        room("lamps")
        on = snap("player_shadow_on")
        feet = feet_of("Player", on[1])
        room_characters(False)
        off = snap("player_shadow_off")
        light_on(1, False)
        dark = snap("lamp_off")
        light_on(1, True)
        room_characters(True)
        away = away_from(L1, feet)
        found = lobe(darkened(on, off, feet), away)
        memo.update(shots={"on": on, "off": off, "dark": dark}, feet=feet)
        assert found["pixels"] > 150, f"no shadow: {found}"
        assert found["direction_agreement"] > 0.9, f"the shadow doesn't point away from the lamp: {found}"
        assert found["on_the_lamps_side"] < 0.03, f"shadow on the lamp's side: {found}"
        centre = (feet[0] + found["centre"][0], feet[1] + found["centre"][1])
        assert lum_at(on, centre) >= lum_at(dark, centre) - 2, "the shadow is never darker than the room without the lamp"
        assert abs(found["centre"][1]) < 12, f"level with a level lamp: the shadow lies along the floor, not above: {found}"
        return {"feet": feet, "lobe": found, "shadow_centre_lum": round(lum_at(on, centre), 1),
                "lamp_off_lum": round(lum_at(dark, centre), 1), "lit_lum": round(lum_at(off, centre), 1)}

    def s07_npcs_have_shadows_too() -> dict[str, Any]:
        """7 (still): the NPCs' shadows, each away from L1 (they patrol in Play: step 2_3_7)."""
        found = {}
        for name in ("Walker", "Guard"):
            feet = feet_of(name, memo["shots"]["on"][1])
            found[name] = lobe(darkened(memo["shots"]["on"], memo["shots"]["off"], feet, half=70), away_from(L1, feet))
            assert found[name]["pixels"] > 60 and found[name]["direction_agreement"] > 0.85, (name, found[name])
        return found

    def s05_contact_shadow_under_the_feet() -> dict[str, Any]:
        """5: the shadow under the feet (Look tab, "Under feet"), separate from the lamps'."""
        room("lamps")
        panel(False)
        p().select("Player")
        p().tab("Look")
        press_toggle("Under feet", False)
        until(lambda: p().entity("Player").get("shadow_enabled") is False, "no shadow under the feet")
        without = snap("contact_off")
        press_toggle("Under feet", True)
        until(lambda: p().entity("Player").get("shadow_enabled", True) is not False, "a shadow under the feet")
        with_it = snap("contact_on")
        feet = memo["feet"]
        under = [(feet[0] + dx, feet[1] + dy) for dx in (-6, 0, 6) for dy in (-2, 2)]
        drop = statistics.mean(lum_at(without, pt) - lum_at(with_it, pt) for pt in under)
        memo["contact"] = {"with": with_it, "without": without}
        assert drop > 4, f"no shadow under the feet ({drop:.1f})"
        return {"darker_under_the_feet_by": round(drop, 1)}

    def s06_cast_off_contact_kept() -> dict[str, Any]:
        """6: "From lamps" off for the player: its lamp shadow goes, the one under its feet stays."""
        press_toggle("From lamps", False)
        until(lambda: not ops.casts_shadow(p().entity("Player")), "no lamp shadow")
        cast_off = snap("cast_off")
        feet = memo["feet"]
        left = lobe(darkened(cast_off, memo["shots"]["off"], feet), away_from(L1, feet))
        press_toggle("Under feet", False)  # the same view without the contact shadow either: what is left of it
        until(lambda: p().entity("Player").get("shadow_enabled") is False, "no shadow under the feet")
        neither = snap("cast_off_contact_off")
        press_toggle("Under feet", True)
        until(lambda: p().entity("Player").get("shadow_enabled", True) is not False, "a shadow under the feet")
        under = [(feet[0] + dx, feet[1] + dy) for dx in (-6, 0, 6) for dy in (-2, 2)]
        kept = statistics.mean(lum_at(neither, pt) - lum_at(cast_off, pt) for pt in under)
        press_toggle("From lamps", True)
        until(lambda: ops.casts_shadow(p().entity("Player")), "the lamp shadow back")
        assert left["pixels"] < 15, f"a lamp shadow is left: {left}"
        assert kept > 4, f"the shadow under the feet went too ({kept:.1f})"
        return {"lamp_shadow_left": left, "under_the_feet_darker_by": round(kept, 1)}

    def s04_two_lights_independent() -> dict[str, Any]:
        """4: with L2 on there are two shadows; each goes with its own lamp; neither takes the other's light."""
        p().d.key("ESC")
        light_on(2, True)
        both = snap("two_lamps")
        feet = feet_of("Player", both[1])
        room_characters(False)
        both_plain = snap("two_lamps_no_characters")
        light_on(1, False)
        only_l2_plain = snap("only_l2_no_characters")
        room_characters(True)
        only_l2 = snap("only_l2")
        light_on(1, True)
        light_on(2, False)
        shadow_1 = lobe(darkened(both, both_plain, feet, half=110), away_from(L1, feet))
        lobes = {"both_lamps_right": shadow_1,
                 "both_lamps_left": lobe(darkened(both, both_plain, feet, half=110), away_from(L2, feet)),
                 "only_l2": lobe(darkened(only_l2, only_l2_plain, feet, half=110), away_from(L2, feet))}
        right = [pt for pt in darkened(both, both_plain, feet, half=110) if pt[0] > 12]
        left = [pt for pt in darkened(both, both_plain, feet, half=110) if pt[0] < -12]
        gone = [pt for pt in darkened(only_l2, only_l2_plain, feet, half=110) if pt[0] > 12]
        assert len(right) > 100 and len(left) > 100, f"two shadows, one from each lamp: {len(right)} right, {len(left)} left"
        assert len(gone) < 15, f"L1 off: its shadow (to the right) goes: {len(gone)} pixels left"
        # In L1's shadow, L2's light is all there: no darker than L2 alone lights it.
        mid = (feet[0] + shadow_1["centre"][0], feet[1] + shadow_1["centre"][1])
        in_l1_shadow, l2_alone = lum_at(both, mid), lum_at(only_l2_plain, mid)
        assert in_l1_shadow >= l2_alone - 3, f"L1's shadow took L2's light: {in_l1_shadow} vs {l2_alone}"
        return {"lobes": lobes, "pixels": {"right": len(right), "left": len(left), "right_after_L1_off": len(gone)},
                "in_L1_shadow": round(in_l1_shadow, 1), "L2_alone": round(l2_alone, 1)}

    def s08_sharp_soft_softer() -> dict[str, Any]:
        """8: the three edge presets on the wall's shadow and on the player's."""
        room("lamps")
        feet = memo["feet"]
        lx, ly = world(L1)
        wall_y = (ROWS - 1) * 32 - 16.0  # the row below the top border: the wall's shadow crosses it
        widths: dict[str, dict[str, int]] = {}
        panel(True)
        press("Shadows off")
        until(lambda: settings().get("lighting_shadows_mode") == "none", "shadows off")
        panel(False)
        time.sleep(0.4)
        unshadowed = snap("unshadowed")
        panel(True)
        press("Shadows on")
        until(lambda: settings().get("lighting_shadows_mode") == "hard", "shadows on")
        memo["unshadowed"] = unshadowed
        dark = memo["shots"]["dark"]
        for name in ("Sharp", "Soft", "Softer"):
            panel(True)
            press(name)
            until(lambda: settings().get("lighting_shadow_softness", "sharp") == name.lower(), f"{name} edges")
            panel(False)
            time.sleep(0.4)
            shot = snap(f"edges_{name.lower()}")
            widths[name] = {"wall": edge_pixels(shot, unshadowed, dark, (lx - 150, wall_y), (lx + 150, wall_y)),
                            "character": edge_pixels(shot, unshadowed, dark, (feet[0] + 45, feet[1] - 40),
                                                     (feet[0] + 45, feet[1] + 40))}
        assert widths["Sharp"]["wall"] < widths["Soft"]["wall"] < widths["Softer"]["wall"], widths
        assert widths["Sharp"]["character"] < widths["Softer"]["character"], widths
        panel(True)
        press("Sharp")
        until(lambda: settings().get("lighting_shadow_softness", "sharp") == "sharp", "sharp edges")
        return {"edge_width_px": widths, "light_at": [lx, ly]}

    def s09_fine_tune_keeps_the_presets() -> dict[str, Any]:
        """9: Fine-tune shadows: edge width, strength, quality; the presets stay and choosing one clears the edge."""
        lx, _ly = world(L1)
        wall_y = (ROWS - 1) * 32 - 16.0
        fine_tune(True)
        p().fill("shadow_edge", "24")
        until(lambda: settings().get("lighting_shadow_edge") == 24.0, "edge width 24")
        panel(False)
        wide = edge_pixels(snap("edge_24"), memo["unshadowed"], memo["shots"]["dark"], (lx - 150, wall_y), (lx + 150, wall_y))
        fine_tune(True)
        p().fill("shadow_strength_room", "0.5")
        until(lambda: settings().get("lighting_shadow_strength") == 0.5, "strength 0.5")
        press("High")
        until(lambda: settings().get("lighting_shadow_quality") == "high", "quality high")
        panel(False)
        half = snap("strength_half")
        stats = live(half[1])["stats"]
        inside = (lx, wall_y)
        full, lamp_off = lum_at(memo["shots"]["on"], inside), lum_at(memo["shots"]["dark"], inside)
        lit = lum_at(memo["shots"]["on"], (lx + 120, wall_y))
        weaker = lum_at(half, inside)
        panel(True)
        presets = [p().reveal(text=t)["text"] for t in ("Sharp", "Soft", "Softer")]  # still there beside the fine-tuning
        press("Soft")
        until(lambda: settings().get("lighting_shadow_softness") == "soft" and "lighting_shadow_edge" not in settings(),
              "a preset chosen: its own edge")
        fine_tune(True)
        p().fill("shadow_strength_room", "1")
        press("Normal")
        until(lambda: settings().get("lighting_shadow_strength", 1.0) == 1.0
                    and settings().get("lighting_shadow_quality", "normal") == "normal",
              "back to full strength, normal quality")
        press("Sharp")
        until(lambda: settings().get("lighting_shadow_softness") == "sharp", "sharp")
        panel(False)
        assert wide > 20, f"a 24 px edge is wide: {wide}"
        assert full - 2 <= weaker and weaker > full + 6 and weaker <= lit, (full, weaker, lit)
        assert full >= lamp_off - 2, "full strength: down to the room light, never below"
        assert stats.get("shadow_passes", 0) > 8 and stats.get("shadow_strength") == 0.5, stats
        assert presets == ["Sharp", "Soft", "Softer"], presets
        return {"edge_24_width": wide, "behind_wall": {"full": full, "strength_0_5": weaker, "lit": lit, "lamp_off": lamp_off},
                "stats": {k: stats.get(k) for k in ("shadow_edge_px", "shadow_passes", "shadow_strength")}}

    def s10_to_16_flicker_presets() -> dict[str, Any]:
        """10-14, 16: steady, candle, torch, fire, faulty, two torches; the Studio's lights against the formula."""
        room("flicker")
        lights = ops.lights(doc())
        samples = record(10.0)
        result = check_series(samples, lights)
        series = {i: [s["static"][i]["color"][0] for s in samples] for i in range(len(lights))}
        reach = {i: [s["static"][i]["radius"] for s in samples] for i in range(len(lights))}
        names = [name for name, _cell in FLICKER_LAMPS]
        spread = {f"{i}_{names[i]}": round(statistics.pstdev(series[i]), 2) for i in series}
        assert spread["0_steady"] == 0 and statistics.pstdev(reach[0]) == 0, "a steady lamp never moves"
        assert spread["1_candle"] < spread["2_torch"] < spread["3_fire"], spread
        assert series[2] != series[5], "two torches flicker on their own"
        # No beat: on the formula's 60 Hz series for these very lights (the dump samples a few times a second).
        formulas = expected_flicker(lights)
        beats = {names[i]: round(peak_spread([f(t / 60)[0] for t in range(1200)]), 2)
                 for i, f in enumerate(formulas) if f and names[i] != "faulty"}
        assert all(v > 0.35 for v in beats.values()), beats
        # On screen: beside each lamp, the floor's brightness over a few frames.
        shots = []
        for i in range(12):
            shots.append(snap(f"flicker_{i:02d}"))
        beside = {i: [lum_at(shot, (world(cell)[0] + 40, world(cell)[1]), 3) for shot in shots]
                  for i, (_n, cell) in enumerate(FLICKER_LAMPS)}
        on_screen = {f"{i}_{names[i]}": round(max(v) - min(v), 1) for i, v in beside.items()}
        assert on_screen["0_steady"] <= 2 and on_screen["2_torch"] > 4 and on_screen["3_fire"] > 4, on_screen
        memo["flicker"] = {"samples": samples, "lights": lights, "steady_custom_lamp": statistics.mean(beside[CUSTOM])}
        plot(out / "flicker_series.png", samples, names)
        return {**result, "colour_spread": spread, "peak_gap_spread": beats, "on_screen_range": on_screen,
                "plot": "flicker_series.png"}

    def s15_torch_then_adjust_custom() -> dict[str, Any]:
        """15: a lamp made Torch, then livelier, then its own speed and reach: a custom flicker, shown as Custom."""
        room("flicker")
        panel(True)
        select_light(CUSTOM + 1)
        press("Torch")
        until(lambda: ops.lights(doc())[CUSTOM].get("flicker_preset") == "torch", "the lamp is a torch")
        press("Livelier")
        until(lambda: ops.lights(doc())[CUSTOM].get("flicker_strength") == 1.33, "a livelier torch")
        press("> More settings")
        p().fill("light_flicker_speed", "3.5")
        until(lambda: ops.flicker_name(ops.lights(doc())[CUSTOM]) == "custom", "a custom flicker")
        p().fill("light_flicker_reach", "0.12")
        light = until(lambda: ops.lights(doc())[CUSTOM] if ops.lights(doc())[CUSTOM].get("flicker_reach") == 0.12 else None,
                      "reach 0.12")
        press("v More settings")
        panel(False)
        samples = record(5.0)
        result = check_series(samples, ops.lights(doc()))
        reach = [s["static"][CUSTOM]["radius"] for s in samples]
        assert light["flicker_speed"] == 3.5 and light["flicker_brightness"] == 0.2, f"made from the torch: {light}"
        assert max(reach) - min(reach) > 6, f"the reach moves more: {min(reach)}-{max(reach)}"
        panel(True)
        custom_active = p()._find(text="Custom") is not None
        panel(False)
        memo["custom_light"] = light
        return {**result, "light": light, "reach_range": [min(reach), max(reach)], "custom_button": custom_active}

    def s17_flicker_off_leaves_nothing() -> dict[str, Any]:
        """17: back to Steady: the lamp's reach and colour are its own again, exactly, and it looks as before."""
        panel(True)
        select_light(CUSTOM + 1)
        press("Steady")
        until(lambda: not ops.lights(doc())[CUSTOM].get("flicker_enabled"), "steady")
        panel(False)
        time.sleep(0.4)
        samples = record(3.0)
        base = ops.lights(doc())[CUSTOM]
        moved = {(s["static"][CUSTOM]["radius"], tuple(s["static"][CUSTOM]["color"][:3])) for s in samples}
        assert moved == {(float(base["radius"]), tuple(ops.rgb(base["color"])[:3]))}, moved
        now = statistics.mean(lum_at(snap(f"steady_again_{i}"), (world(FLICKER_LAMPS[CUSTOM][1])[0] + 40,
                                                                 world(FLICKER_LAMPS[CUSTOM][1])[1]), 3) for i in range(3))
        before = memo["flicker"]["steady_custom_lamp"]
        assert abs(now - before) <= 2, f"the lamp looks as it did before it flickered: {now} vs {before}"
        return {"reach_and_colour": sorted(moved), "beside_lamp": [round(before, 1), round(now, 1)]}

    def s19_undo_redo() -> dict[str, Any]:
        """19: undo brings the custom flicker back (as it was), redo makes it steady again."""
        p().d.key("ctrl+z")
        light = until(lambda: ops.lights(doc())[CUSTOM] if ops.lights(doc())[CUSTOM].get("flicker_enabled") else None,
                      "flicker undone")
        assert {k: light.get(k) for k in memo["custom_light"]} == memo["custom_light"], (light, memo["custom_light"])
        samples = record(3.0)
        check_series(samples, ops.lights(doc()))
        p().d.key("ctrl+y")
        until(lambda: not ops.lights(doc())[CUSTOM].get("flicker_enabled"), "redone: steady")
        p().d.key("ctrl+z")  # leave it custom: the save and reopen check keeps it
        until(lambda: ops.lights(doc())[CUSTOM].get("flicker_enabled"), "custom again")
        return {"undone_to": light}

    def s18_play_matches_studio() -> dict[str, Any]:
        """18: in Play the flicker room's lamps are the same formula, seeds and settings as in the Studio."""
        room("flicker")
        lights = ops.lights(doc())
        p().d.key("F4")
        p().wait(lambda s: s["mode"] == "play" and s["play"] and s["play"]["player"], "playing", timeout=30)
        time.sleep(1.5)
        samples = record(5.0)
        result = check_series(samples, lights)
        stats = live().get("stats") or {}
        p().d.key("F4")
        p().wait(lambda s: s["mode"] == "edit", "editing")
        assert stats.get("renderer") == "per_light", stats
        return {**result, "stats": stats}

    def s02_03_07_22_play_walk_patrol() -> dict[str, Any]:
        """2, 3, 7, 22: in Play the player walks round L1 (four ways, animating) while the NPCs patrol. Every
        dump: each character's shadow starts at its feet (inside its picture, at the bottom), never jumps, and
        the floor just past the player's feet, away from the lamp, is darker than the floor beside it."""
        room("lamps")
        light_on(1, True)
        p().d.key("F4")
        p().wait(lambda s: s["mode"] == "play" and s["play"] and s["play"]["player"], "playing", timeout=30)
        time.sleep(1.5)
        lx, ly = world(L1)
        stops = [(336.0, 170.0), (230.0, 150.0), (150.0, 160.0), (150.0, 250.0), (300.0, 300.0), (340.0, 240.0)]
        checks: list[dict[str, Any]] = []
        worst_off = worst_jump = 0.0
        last: dict[str, tuple[float, float]] = {}
        darker: list[dict[str, Any]] = []
        start = time.time()
        for i, stop in enumerate(stops):
            try:
                p().go_to(*stop, tol=12)
            except AssertionError:  # a key-up lost to another window leaves the player walking: clear the keys, retry
                for key in "WASD":
                    p().d.hold(key, 0.02)
                p().go_to(*stop, tol=12)
            time.sleep(0.3)
            shot = snap(f"walk_{i}")
            s = shot[1]
            feet = live(s)["stats"]["character_feet"]
            for sprite in s["play"]["sprites"]:
                if sprite["name"] not in ("Player", "Walker", "Guard"):
                    continue
                cx, cy = sprite["at"]
                w, h = sprite["size"]
                near = min(feet, key=lambda f: math.hypot(f[0] - cx, f[1] - (cy - h / 2)))
                off = max(abs(near[0] - cx) - w / 2, abs(near[1] - (cy - h / 2)) - 6, 0.0)
                worst_off = max(worst_off, off)
                if sprite["name"] in last:
                    moved = math.hypot(cx - last[sprite["name"]][0], cy - last[sprite["name"]][1])
                    jump = math.hypot(near[0] - cx - last[sprite["name"] + "_f"][0], near[1] - cy - last[sprite["name"] + "_f"][1])
                    worst_jump = max(worst_jump, jump) if moved < 1 else worst_jump
                last[sprite["name"]], last[sprite["name"] + "_f"] = (cx, cy), (near[0] - cx, near[1] - cy)
            pf = feet_of("Player", s)
            d = math.hypot(pf[0] - lx, pf[1] - ly)
            ux, uy = (pf[0] - lx) / d, (pf[1] - ly) / d
            shadow_pt = (pf[0] + ux * 22, pf[1] + uy * 22)
            angle = math.atan2(uy, ux) + 0.6
            beside_pt = (lx + math.cos(angle) * (d + 22), ly + math.sin(angle) * (d + 22))
            darker.append({"stop": stop, "shadow": round(lum_at(shot, shadow_pt, 3), 1), "beside": round(lum_at(shot, beside_pt, 3), 1)})
            checks.append({"stop": stop, "characters": live(s)["stats"].get("characters"),
                           "character_shadows": live(s)["stats"].get("character_shadows")})
        walked = time.time() - start
        patrolled = {sp["name"]: sp["at"] for sp in p().fresh()["play"]["sprites"] if sp["name"] in ("Walker", "Guard")}
        profile = live().get("profile")
        p().d.key("F4")
        p().wait(lambda s: s["mode"] == "edit", "editing")
        assert worst_off <= 2.0, f"a shadow started away from its character's feet by {worst_off} px"
        assert worst_jump <= 3.0, f"a shadow jumped {worst_jump} px against its standing character"
        assert all(c["character_shadows"] and c["character_shadows"] >= 1 for c in checks), checks
        assert sum(1 for x in darker if x["shadow"] < 0.8 * x["beside"]) >= len(darker) - 1, darker
        assert {n: at for n, at in patrolled.items()} != {"Walker": list(WALKER[0]), "Guard": list(GUARD[0])}, "the NPCs patrol"
        return {"stops": checks, "floor_past_the_feet": darker, "feet_off_by_at_most": worst_off,
                "largest_jump": worst_jump, "walked_seconds": round(walked, 1), "npcs_now": patrolled, "profile": profile}

    def s20_save_close_reopen() -> dict[str, Any]:
        """20: saved and reopened: the flicker presets, the custom flicker, the room's settings, the player's."""
        p().d.key("ctrl+s")
        p().wait(lambda s: not s["dirty"], "saved")
        room("flicker")
        before_lights = ops.lights(doc())
        room("lamps")
        before_settings, before_player = settings(), p().entity("Player")
        close()
        launch()
        room("flicker")
        lights = ops.lights(doc())
        assert lights == before_lights, (before_lights, lights)
        result = check_series(record(4.0), lights)
        room("lamps")
        assert settings() == before_settings and p().entity("Player") == before_player
        stats = live()["stats"]
        assert stats.get("character_shadows", 0) >= 3, stats
        return {**result, "lights": lights, "room_settings": before_settings}

    def s21_compatibility_copy() -> dict[str, Any]:
        """21: a copy of Hollowmere_Trial (lamps from before presets): opened, played; the original only read."""
        if not HOLLOWMERE.is_dir():
            return {"skipped": f"{HOLLOWMERE} not on this computer"}

        def digest(folder: Path) -> dict[str, str]:
            return {str(f.relative_to(folder)): hashlib.sha1(f.read_bytes()).hexdigest()
                    for f in sorted(folder.rglob("*")) if f.is_file()}

        original = digest(HOLLOWMERE)
        copy = work / "Hollowmere_copy"
        shutil.copytree(HOLLOWMERE, copy)
        def rooms(folder: Path) -> dict[str, str]:  # .mesh holds the Studio's session marker; saves are the game's
            return {k: v for k, v in digest(folder).items() if k.endswith(".json") and not k.startswith((".mesh", "saves"))}

        scenes_before = rooms(copy)
        close()
        launch(copy)
        start = p().state()
        lights = ops.lights(doc())
        names = [ops.flicker_name(light) for light in lights]
        samples = record(4.0)
        result = check_series(samples, lights) if any(light.get("flicker_enabled") for light in lights) else {}
        p().d.key("F4")
        p().wait(lambda s: s["mode"] == "play" and s["play"] and s["play"]["player"], "playing", timeout=30)
        time.sleep(1.5)
        play_stats = live().get("stats") or {}
        p().d.key("F4")
        p().wait(lambda s: s["mode"] == "edit", "editing")
        close()
        scenes_after = rooms(copy)
        assert digest(HOLLOWMERE) == original, "the original project was changed"
        assert scenes_after == scenes_before, "opening and playing the copy rewrote its rooms"
        assert "flicker_preset" not in json.dumps(lights), "older lights keep their own settings"
        assert play_stats.get("renderer") == "per_light", play_stats
        return {"room": start.get("room"), "flicker": names, **result, "play_stats": play_stats}

    def s21_then_back() -> dict[str, Any]:
        try:
            return s21_compatibility_copy()
        finally:  # the lab's own project again, for the last check, however the copy went
            close()
            launch()

    def s22_performance() -> dict[str, Any]:
        """22, P4: the lighting pass with three moving casters and two lamps (one a torch), Sharp / Soft / Softer,
        and zoomed in; the budget holds and nothing is dropped silently."""
        room("lamps")
        light_on(2, True)
        panel(True)
        select_light(1)
        press("Torch")
        until(lambda: ops.lights(doc())[0].get("flicker_preset") == "torch", "L1 a torch")
        figures: dict[str, Any] = {}
        for edges in ("Sharp", "Soft", "Softer"):
            panel(True)
            press(edges)
            until(lambda: settings().get("lighting_shadow_softness", "sharp") == edges.lower(), f"{edges} edges")
            panel(False)
            p().d.key("F4")
            p().wait(lambda s: s["mode"] == "play" and s["play"] and s["play"]["player"], "playing", timeout=30)
            p().d.hold("A", 1.2)
            p().d.hold("D", 1.2)
            time.sleep(2.5)  # the profile keeps the last 240 frames
            lit = live()
            figures[edges.lower()] = {"profile": lit.get("profile"), "stats": lit.get("stats")}
            p().d.key("F4")
            p().wait(lambda s: s["mode"] == "edit", "editing")
        feet = feet_of("Player")
        x, y = screen_of(feet, p().fresh())
        p().d.scroll(x, y, 4)
        zoom = p().wait(lambda s: s["zoom"] > 1.3, "zoomed in")["zoom"]
        time.sleep(1.5)
        zoomed = snap("zoomed")
        room_characters(False)
        zoomed_off = snap("zoomed_no_characters")
        room_characters(True)
        # L2 is on too: the player has a shadow each side. L1's is the one to the right of the feet.
        found = lobe([pt for pt in darkened(zoomed, zoomed_off, feet_of("Player", zoomed[1])) if pt[0] > 12],
                     away_from(L1, feet))
        figures["zoomed"] = {"zoom": zoom, "profile": live().get("profile"), "lobe": found}
        p().d.scroll(x, y, -4)
        panel(True)
        select_light(1)  # opening the panel clears the selected light
        press("Steady")
        press("Sharp")
        panel(False)
        light_on(2, False)
        for name, figure in figures.items():
            stats = figure.get("stats") or {}
            assert not stats.get("lights_over_budget") and not stats.get("shadows_unavailable"), (name, stats)
        assert found["pixels"] > 100 and found["direction_agreement"] > 0.85, f"zoomed in, the shadow is where it was: {found}"
        return figures

    steps = [("gpu_pixel_tests", s00_gpu_pixel_tests), ("open_the_lab", s00_open_the_lab),
             ("1_stationary_player_shadow", s01_stationary_player_shadow), ("7_npc_shadows", s07_npcs_have_shadows_too),
             ("5_contact_shadow", s05_contact_shadow_under_the_feet), ("6_cast_off_contact_kept", s06_cast_off_contact_kept),
             ("4_two_lights_independent", s04_two_lights_independent), ("8_sharp_soft_softer", s08_sharp_soft_softer),
             ("9_fine_tune_keeps_presets", s09_fine_tune_keeps_the_presets),
             ("10_to_14_16_flicker_presets", s10_to_16_flicker_presets), ("15_torch_then_custom", s15_torch_then_adjust_custom),
             ("17_flicker_off_no_residue", s17_flicker_off_leaves_nothing), ("19_undo_redo", s19_undo_redo),
             ("18_play_matches_studio", s18_play_matches_studio),
             ("2_3_7_walk_turn_patrol", s02_03_07_22_play_walk_patrol), ("20_save_close_reopen", s20_save_close_reopen),
             ("21_compatibility_copy", s21_then_back), ("22_performance", s22_performance)]
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
    (out / "report.json").write_text(json.dumps({"passed": passed == len(results), "steps": results}, indent=2, default=str),
                                     encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)  # the disposable project and the copy go; report and screenshots stay
    print(f"{passed}/{len(results)} checks passed; report: {out / 'report.json'}")
    return 0 if passed == len(results) else 1


def plot(path: Path, samples: list[dict[str, Any]], names: list[str]) -> None:
    """The recorded brightness (orange: the colour's channels summed) and reach (blue) of each lamp over the run, each
    scaled to its own range: the time series, not a still. A flat line is a lamp that doesn't move."""
    from PIL import Image, ImageDraw

    width, row_h = 900, 70
    image = Image.new("RGB", (width, row_h * len(names) + 20), (250, 250, 250))
    draw = ImageDraw.Draw(image)
    t0, t1 = samples[0]["clock"], samples[-1]["clock"]
    for i, name in enumerate(names):
        top = 10 + i * row_h
        draw.text((6, top + 2), f"{i + 1} {name}", fill=(40, 40, 40))
        for key, colour in (("color", (200, 80, 40)), ("radius", (40, 90, 200))):
            values = [float(sum(s["static"][i][key][:3])) if key == "color" else s["static"][i][key] for s in samples]
            mid = statistics.mean(values)
            low, high = mid * 0.8, mid * 1.2  # +/-20% of its mean: the same scale for every lamp
            pts = [(110 + (s["clock"] - t0) / max(1e-6, t1 - t0) * (width - 120),
                    top + row_h - 8 - (v - low) / max(1e-6, high - low) * (row_h - 16)) for s, v in zip(samples, values)]
            draw.line(pts, fill=colour, width=1)
    image.save(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO / "artifacts" / "lighting_polish_lab")
    args = parser.parse_args()
    raise SystemExit(run(args.out))
