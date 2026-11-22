"""M1-B-1: one representative HD-2D room, the Crossing, made in Mesh Studio and walked in the game (hidden windows).

    py -3.13 tooling/hd2d_m1b_scene.py build OUT    a 2D starter project (OUT/game) given the Crossing in Studio
    py -3.13 tooling/hd2d_m1b_scene.py check OUT    the game walks it with held arrow keys: pictures + OUT/check.json
    py -3.13 tooling/hd2d_m1b_scene.py all OUT      both

``build`` works Mesh Studio only through its own window events (button clicks, typing, mouse clicks and drags in the
3D view, a right-click menu), as ``hd2d_room_studio.py`` and ``lakeside_village.py`` do, never by writing room files:

- + New room > HD-2D, 32 x 32 m, outdoors: the Crossing (its gameplay camera bounded by the room); Set as starting room;
- Models...: the starter kit's pieces placed by a click and typed to the metre: two plateaus 2 m up (three 4 m
  platforms each), the 6 m bridge between them over an open underpass, a staircase up each, a cottage (See-through in
  play: on) and two lamp posts;
- Lighting: a warm lamp at each lamp post's lantern and one under the bridge;
- a Person (the "guard") placed on the grass and dragged under the bridge, so a player on the deck stands at the
  guard's x/y 2 m above it;
- a right-click inside the cottage: Add door to a new room... > HD-2D, 16 x 12 m, indoors: Inside, with a door back;
  both doors made Passages (invisible areas: the models have their own doorways); in Inside the door dragged just
  beyond the north wall, the kit's cottage interior placed turned round so that is its doorway and Studio's arrival
  spot is on its floor, and a lamp; saved.

The geometry (ground 0 m, deck 2 m, stairs between, an underpass) is what M1-A's parity work and M3 reuse. ``check``
plays it with the game's runtime (``hd2d_demo.HiddenGame``), driving the player only with key press/release events:
ground, up the west stairs, the west plateau, the deck above the guard, the east plateau, down the east stairs, under
the bridge, behind the cottage (cutaway), through the doorway into Inside and back out; saves and loads on the deck and
under it; a fixed walk timed frame by frame (update + draw + GPU finish). Nothing is played aloud (master volume 0)."""

from __future__ import annotations

import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(1, str(REPO / "tooling"))

PX = 32.0
SCENES = "packs/core_regions/scenes"
ROOM, INSIDE = "Crossing", "Inside"
ROOM_FILE = f"{SCENES}/crossing.json"
# 10 m of grass north of the plateaus: the camera's bounds keep the ground in the picture, so a player on the 2 m deck
# near the room's north edge would be at the picture's top edge (see the review)
W_M, D_M = 32, 32
# (model's name in the Models list, x m, y m): the starter village's hills, cottage and lamps (engine.hd2d.starter_village)
PIECES = [*[("Platform (4 x 4 m)", x, 20.0) for x in (4.0, 8.0, 12.0, 20.0, 24.0, 28.0)],
          ("Bridge (6 m)", 16.0, 20.0), ("Staircase", 11.0, 15.0), ("Staircase", 26.0, 15.0),
          ("Cottage", 6.0, 8.0), ("Lamp post", 13.5, 5.0), ("Lamp post", 18.5, 5.0)]
LAMPS = [(13.5, 5.0, 2.5), (18.5, 5.0, 2.5), (16.0, 20.0, 1.4)]  # x, y, height (m): the lanterns; under the deck
# the guard: placed on the grass, dragged under the bridge (its picture's centre: its feet 0.56 m south, about the deck's
# middle line, y 20)
GUARD_ON_GRASS, GUARD = (15.5, 16.5), (15.5, 20.5)
PLAYER_START = (16.0, 4.5)  # the player's picture's centre (its feet 0.56 m south): the path south of the lamps
# m: right-clicked inside the cottage (its south wall at y 6, its floor 0.1 m): a door's area is met by the player's
# whole picture (1.3 m above its feet walking north; see the review), so 2 m in, it is met as the feet step into the
# doorway
COTTAGE_DOOR = (6.0, 8.0)
# Inside: Studio puts the door back at (8, 7) m and its arrival spot 3 m south of it, (8, 4); an arrival spot can't be
# picked in the 3D view (see the review), so the room is fitted round it: the kit's interior turned 180 degrees with its
# middle at (7, 5), so its doorway is in the north wall (y 7.5) and the arrival is on its floor, clear of the table;
# the door dragged beyond that doorway. See-through in play, so its south wall doesn't hide the player.
INSIDE_ROOM = (7.0, 5.0, 180.0)
INSIDE_DOOR = (7.0, 9.0)  # (1.5 m past the doorway's line: met as the feet step into it, as for the cottage's)


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=1, default=str) + "\n", encoding="utf-8")


def _silent(project: Path) -> None:
    config = json.loads((project / "config.json").read_text(encoding="utf-8"))
    config["master_volume"] = 0.0
    _write(project / "config.json", config)


# ---------------------------------------------------------------------------------------------------- build (Studio)
def _left(widget: Any) -> bool:
    return bool(widget.rect.left < 230)


def _right(widget: Any) -> bool:
    return bool(widget.rect.left > 900)


def _press(d: Any, text: str, where: Any = lambda w: True) -> None:
    from hd2d_room_studio import _press as press

    press(d, text, where)


def _place(d: Any, name: str, x: float, y: float, turn: float | None = None, *, see_through: bool = False) -> str:
    """Models... > search > the model > Place in scene > a click on the ground; its inspector's X and Y (and turn)
    typed; ``see_through``: its See-through in play button (the cutaway) pressed."""
    from lakeside_village import _place_model

    placed = _place_model(d, name, x, y, turn=turn)
    st = d.structure(placed["id"]) or {}
    expected = {"Platform (4 x 4 m)": "platform_4m", "Bridge (6 m)": "bridge_6m", "Staircase": "stairs",
                "Cottage": "cottage", "Lamp post": "lamp_post", "Cottage interior": "interior"}[name]
    assert str(st.get("model", "")).endswith(f"/{expected}.glb"), (name, st)
    if see_through:
        d.button("See-through in play", prefix=True)
        assert (d.structure(placed["id"]) or {}).get("cutaway") is True, d.studio.message
    return str(placed["id"])


def _add_light(d: Any, x: float, y: float, height: float, radius: float) -> None:
    import m20c_material_study as m20c
    from lakeside_village import _panel_to_top

    m20c._look_at(d, x, y, 16.0)
    _panel_to_top(d)
    d.button("+ Add light")
    d.click(*d.screen((x, y, 0.0)))
    if d.studio.expanded != "light_more":  # (it stays open from one light to the next)
        d.button("> More settings")
    d.type_into("light_radius", f"{radius:g}")
    d.type_into("light_height", f"{height:g}")


def _select(d: Any, entity_id: str) -> None:
    """Click the object as a person does: on its picture (or marker), clicking again where several are under the
    mouse (Studio cycles to the one behind)."""
    import m20c_material_study as m20c
    from lakeside_village import _entity

    e = _entity(d, entity_id)
    x, y, z = float(e["x"]) / PX, float(e["y"]) / PX, float(e.get("elevation") or 0.0) / PX
    m20c._look_at(d, x, y + 2.0, 12.0)
    for up in (1.5, 1.0, 0.6, 0.3):
        for _ in range(4):
            if d.studio.selected == entity_id:
                return
            d.click(*d.screen((x, y, z + up)))
    assert d.studio.selected == entity_id, (d.studio.selected, entity_id, d.studio.message)


def _move(d: Any, entity_id: str, to: tuple[float, float]) -> int:
    """Select it, then drag it to ``to`` (m, its x/y: on Studio's 0.5 m grid) in short hops, the view on it each time."""
    import math

    import m20c_material_study as m20c
    from lakeside_village import _entity

    _select(d, entity_id)
    hops = 0
    for hops in range(1, 30):
        e = _entity(d, entity_id)
        here, z = (float(e["x"]) / PX, float(e["y"]) / PX), float(e.get("elevation") or 0.0) / PX
        gap = math.dist(here, to)
        if gap < 0.01:
            break
        step = min(1.0, 1.5 / gap)
        nxt = (here[0] + (to[0] - here[0]) * step, here[1] + (to[1] - here[1]) * step)
        m20c._look_at(d, (here[0] + nxt[0]) / 2, (here[1] + nxt[1]) / 2, 12.0)
        d.drag(d.screen((here[0], here[1], z + 1.0)), d.screen((nxt[0], nxt[1], z + 1.0)), steps=10)
    e = _entity(d, entity_id)
    assert (float(e["x"]) / PX, float(e["y"]) / PX) == to, (entity_id, e, d.studio.message)
    return hops


def _passage(d: Any, door: str, width: int, height: int) -> dict[str, Any]:
    """The door, clicked and shown as a Passage (an invisible area: the room's own model is the doorway) of that size."""
    from lakeside_village import _entity, _right_button

    _select(d, door)
    _right_button(d, "Passage")
    d.type_into("door_width", str(width))
    d.type_into("door_height", str(height))
    return {key: _entity(d, door).get(key) for key in ("x", "y", "door_style", "behaviour_config")}


def build(out: Path, *, pictures: bool = True) -> dict[str, Any]:
    import m20c_material_study as m20c
    from hd2d_studio_demo import StudioDriver
    from lakeside_village import _entity, _panel_to_top, _save

    pics = out / "pictures"
    pics.mkdir(parents=True, exist_ok=True)
    project = out / "game"
    if project.exists():
        raise SystemExit(f"{project} exists; pick a new OUT (this never overwrites)")
    made = subprocess.run([sys.executable, "-m", "mesh_cli", "new", "game", "--dest", str(out), "--template", "starter"],
                          cwd=REPO, capture_output=True, text=True, timeout=600)
    assert made.returncode == 0, made.stdout + made.stderr
    _silent(project)
    report: dict[str, Any] = {}
    t0 = time.perf_counter()
    d = StudioDriver(project)
    k = d.arcade.key
    try:
        # -- the room
        _press(d, "+ New room", _left)
        d.type_into("room_name", ROOM)
        _press(d, "HD-2D (3D)", _right)
        d.type_into("room_width", str(W_M))
        d.type_into("room_depth", str(D_M))
        _press(d, "Outdoors", _right)
        _press(d, "Create", _right)
        d.advance(5)
        report["room"] = {"key": d.studio.project.current, "message": d.studio.message}
        d.button("Set as starting room")
        report["start_room"] = d.studio.message
        player = next(e["id"] for e in d.studio.project.scene()["entities"] if e.get("tag") == "player")
        report["player_hops"] = _move(d, player, PLAYER_START)  # (from the room's middle) to the south path
        # -- the hills, the bridge, the stairs, the cottage, the lamp posts
        report["structures"] = [_place(d, name, x, y, see_through=name == "Cottage") for name, x, y in PIECES]
        d.key(k.ESCAPE)
        # -- the lights
        d.button("Lighting")
        for x, y, h in LAMPS:
            _add_light(d, x, y, h, 224.0)
        _panel_to_top(d)
        d.button("Lighting")  # (panel closed)
        d.key(k.ESCAPE)
        report["lights"] = d.studio.project.scene().get("lights")
        # -- the guard: a Person on the grass, dragged under the bridge
        m20c._look_at(d, GUARD_ON_GRASS[0], GUARD_ON_GRASS[1], 14.0)
        d.button("Person")
        spot = d.screen((*GUARD_ON_GRASS, 0.0))
        d.window.dispatch_event("on_mouse_motion", *spot, 0, 0)
        d.advance()
        d.click(*spot)
        guard = d.studio.selected
        assert guard, d.studio.message
        d.key(k.ESCAPE)
        report["guard_hops"] = _move(d, guard, GUARD)
        report["guard"] = {key: _entity(d, guard).get(key) for key in ("id", "x", "y", "elevation")}
        # -- the doorway: a door to a new room, Inside
        m20c._look_at(d, COTTAGE_DOOR[0], COTTAGE_DOOR[1] + 2.0, 14.0)
        d.click(*d.screen((*COTTAGE_DOOR, 0.0)), button=d.arcade.MOUSE_BUTTON_RIGHT)
        d.button("Add door to a new room...")
        d.type_into("room_name", INSIDE)
        _press(d, "HD-2D (3D)", _right)
        d.type_into("room_width", "16")
        d.type_into("room_depth", "12")
        _press(d, "Indoors", _right)
        _press(d, "Create", _right)
        d.advance(3)
        report["door_message"] = d.studio.message
        scene = d.studio.project.scene()
        door = next(e["id"] for e in scene["entities"] if e.get("tag") == "door")
        report["crossing_door"] = _passage(d, door, 48, 32)
        d.key(k.ESCAPE)
        m20c._look_at(d, 15.0, 12.0, 48.0)
        if pictures:
            d.picture(pics / "studio_01_crossing.png")
        _save(d)
        # -- Inside: the door into the doorway's line (moved before the walls are there to hide it), the interior
        # round it and Studio's arrival spot, its lamp
        _press(d, INSIDE, _left)
        d.advance(5)
        report["inside_key"] = d.studio.project.current
        scene = d.studio.project.scene()
        door = next(e["id"] for e in scene["entities"] if e.get("tag") == "door")
        arrival = next(e["id"] for e in scene["entities"] if e.get("tag") == "spawn_point")
        report["inside_hops"] = _move(d, door, INSIDE_DOOR)
        report["inside_door"] = _passage(d, door, 48, 16)
        report["inside_arrival"] = {key: _entity(d, arrival).get(key) for key in ("x", "y")}
        d.key(k.ESCAPE)
        report["interior"] = _place(d, "Cottage interior", *INSIDE_ROOM, see_through=True)
        d.key(k.ESCAPE)
        d.button("Lighting")
        _add_light(d, 8.0, 7.0, 2.0, 200.0)
        _panel_to_top(d)
        d.button("Lighting")
        d.key(k.ESCAPE)
        m20c._look_at(d, 7.0, 5.5, 17.0)
        if pictures:
            d.picture(pics / "studio_02_inside.png")
        _save(d)
        report["saved"] = d.studio.message
    finally:
        d.close()
    report["studio_s"] = round(time.perf_counter() - t0, 1)
    crossing = json.loads((project / ROOM_FILE).read_text(encoding="utf-8"))
    report["saved_crossing"] = {"structures": len(crossing["settings"]["hd2d"]["structures"]),
                                "camera": crossing["settings"]["hd2d"]["camera"],
                                "doors": [{key: e.get(key) for key in ("id", "tag", "x", "y")} for e in crossing["entities"]
                                          if e.get("tag") in ("door", "spawn_point")]}
    _write(out / "build.json", report)
    return report


# ------------------------------------------------------------------------------------------------------ check (game)
def machine(window: Any) -> dict[str, Any]:
    """CPU, GPU (the GL context's own strings: vendor, renderer, version with the driver), OS, Python, picture size."""
    cpu = platform.processor()
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                cpu = str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    from pyglet.gl import gl_info

    info = window.ctx.info
    return {"cpu": cpu, "cores": os.cpu_count(), "gpu": f"{info.VENDOR} {info.RENDERER}",
            "gl_version_and_driver": gl_info.get_version_string(),
            "os": platform.platform(), "python": platform.python_version(),
            "framebuffer": list(window.get_framebuffer_size())}


def _pct(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(len(ordered) * q))], 2)


def check(out: Path, *, pictures: bool = True, timing: bool = True) -> dict[str, Any]:
    """The game (hidden window, 1280 x 720) walks the Crossing with held arrow keys. ``pictures``: save them;
    ``timing``: the fixed timed walk at the end."""
    from hd2d_demo import HiddenGame, _total_pixels
    from hd2d_floors_demo import _feet, hold_key

    from engine.hd2d.renderer import fit_view

    project, pics = out / "game", out / "pictures"
    pics.mkdir(parents=True, exist_ok=True)
    game = HiddenGame(project, size=(1280, 720))
    keys = game.arcade.key
    report: dict[str, Any] = {"legs": []}
    view_drift: list[float] = []
    last_feet: dict[str, list[float]] = {}  # the player's feet in each room at the last frame walked there
    try:
        w = game.window
        game.load(ROOM_FILE)
        game.step(60)  # (past the room's fade-in; the camera settled)
        report["hd2d_error"] = getattr(w, "hd2d_error", None)
        report["floors"] = sorted({s.floor for s in w.hd2d_world.surfaces})
        guard = next(s for s in w.scene_controller.all_sprites if getattr(s, "mesh_tag", None) == "npc")

        def hd() -> Any:
            return w.hd2d_renderer

        def room() -> str:
            return str(w.scene_controller.current_scene_path or "").replace("\\", "/").rsplit("/", 1)[-1]

        def each_frame() -> None:  # the camera never shows past the room's bounds (fit_view would move it)
            r = hd()
            bounds = tuple(v / PX for v in r.settings.camera.bounds)
            fitted = fit_view(r.camera, r.camera.target, 0.0, bounds, r._aspect)
            view_drift.append(max(abs(a - b) for a, b in zip(fitted, r.camera.target)))
            last_feet[room()] = [round(v, 3) for v in _feet(game.player())]

        def state(label: str, picture: str | None = None, **extra: Any) -> dict[str, Any]:
            p = game.player()
            fx, fy = _feet(p)
            entry = {"after": label, "room": room(), "feet_m": [round(fx, 3), round(fy, 3)],
                     "elevation_m": round(p.mesh_entity_data.get("elevation", 0.0) / PX, 3),
                     "floor": getattr(p, "mesh_hd2d_floor", None),
                     "camera_target": [round(v, 3) for v in hd().camera.target], **extra}
            if picture and pictures:
                game.draw().convert("RGB").save(pics / picture)
                entry["picture"] = picture
            report["legs"].append(entry)
            return entry

        def seen() -> dict[str, int]:
            """How much of the player the picture shows: with the cutaway, without it (as the test of the cutaway
            draws it), and unhidden (nothing built drawn)."""
            r, p = hd(), game.player()
            keep = r._cutaway
            r._cutaway = set()
            try:
                without = r.visible_pixels(p)
            finally:
                r._cutaway = keep
            return {"visible_px": r.visible_pixels(p), "without_cutaway_px": without, "total_px": _total_pixels(r, p)}

        def drive(key: str, axis: int, target: float, frames: int = 900) -> bool:
            return bool(hold_key(game, game.player(), getattr(keys, key), axis, target, frames, each_frame))

        def through_door(key: str, axis: int, target: float) -> dict[str, Any]:
            before = room()
            drive(key, axis, target, 400)
            for _ in range(120):  # (the room's fade) until the other room is there
                if room() != before:
                    break
                game.step(1)
            game.step(60)
            return {"from": before, "to": room(), "feet_when_it_fired": last_feet.get(before)}

        saves = w.save_manager
        state("start: on the ground", "01_ground.png")
        drive("LEFT", 0, 11.0)
        drive("UP", 1, 15.0)
        state("half way up the west stairs", "02_stairs.png")
        drive("UP", 1, 20.0)
        state("on the west plateau")
        drive("RIGHT", 0, GUARD[0])
        gx, gy = _feet(guard)
        gz = guard.mesh_entity_data.get("elevation", 0.0) / PX
        on_deck = state("on the deck, above the guard under it", "03_deck_above_guard.png",
                        guard={"feet_m": [round(gx, 3), round(gy, 3)], "elevation_m": round(gz, 3),
                               "stands_on": w.hd2d_world.stand(gx, gy, gz, 0.3, 0.19)})
        report["saved_deck"] = saves.save_game("m1b_deck")
        drive("RIGHT", 0, 26.0)
        state("on the east plateau")
        drive("DOWN", 1, 11.0)
        state("down the east stairs: on the ground")
        drive("LEFT", 0, 17.0)
        drive("UP", 1, 20.0)
        fx, fy = _feet(game.player())
        under = state("under the deck, beside the guard", "04_under_deck.png",
                      overhead=w.hd2d_world.stand(fx, fy, 2.0, 0.3, 0.19))  # the same x/y, 2 m up
        report["saved_under"] = saves.save_game("m1b_under")
        drive("DOWN", 1, 11.0)
        drive("LEFT", 0, 6.0)
        state("behind the cottage (see-through)", "05_behind_cottage.png", seen=seen())
        drive("RIGHT", 0, 9.5)
        drive("DOWN", 1, 5.0)
        drive("LEFT", 0, 6.0)
        state("at the cottage's doorway", "06_doorway.png")
        report["door_in"] = through_door("UP", 1, COTTAGE_DOOR[1])
        state("through the doorway: Inside (its south wall see-through)", "07_inside.png", seen=seen())
        drive("UP", 1, 6.5)
        drive("LEFT", 0, INSIDE_DOOR[0])
        report["door_out"] = through_door("UP", 1, INSIDE_DOOR[1])
        state("back out through the doorway: the Crossing")
        report["loads"] = {}
        for slot, expected in (("m1b_deck", on_deck), ("m1b_under", under)):
            ok = saves.load_game(slot)
            game.step(30)
            got = state(f"loaded '{slot}'")
            report["loads"][slot] = {"ok": ok, "expected": [expected["feet_m"], expected["elevation_m"], expected["floor"]],
                                     "got": [got["feet_m"], got["elevation_m"], got["floor"]]}
        report["camera_bounds_max_drift_m"] = round(max(view_drift), 4)
        report["camera_frames"] = len(view_drift)
        if timing:
            report["timing"] = _timed_walk(game)
        report["machine"] = machine(w)
        report["renderer"] = hd().stats()
    finally:
        game.close()
    _write(out / "check.json", report)
    return report


def _timed_walk(game: Any) -> dict[str, Any]:
    """The Crossing reloaded; from the start the player walks right for 3 s, then left for 3 s (held keys); every frame
    timed: update, draw, the GPU finished (``ctx.finish``), the frame completed (``ctx.gc``). 30 warm-up frames first."""
    w, keys = game.window, game.arcade.key
    game.load(ROOM_FILE)
    game.step(60)
    frames: list[float] = []

    def frame(record: bool) -> None:
        t = time.perf_counter()
        w.dispatch_event("on_update", 1 / 60)
        w.dispatch_event("on_draw")
        w.ctx.finish()
        w.ctx.gc()
        if record:
            frames.append((time.perf_counter() - t) * 1000)

    for _ in range(30):
        frame(False)
    for key in (keys.RIGHT, keys.LEFT):
        w.dispatch_event("on_key_press", key, 0)
        for _ in range(180):
            frame(True)
        w.dispatch_event("on_key_release", key, 0)
    return {"frames": len(frames), "median_ms": round(statistics.median(frames), 2), "p95_ms": _pct(frames, 0.95),
            "p99_ms": _pct(frames, 0.99), "max_ms": round(max(frames), 2),
            "what": "hidden 1280x720 window, vsync off; per frame: on_update(1/60) + on_draw + ctx.finish + ctx.gc"}


if __name__ == "__main__":
    command, out_dir = sys.argv[1], Path(sys.argv[2]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out_dir / "user_settings.json")  # never a checkout's own file
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    result = {}
    if command in ("build", "all"):
        result["build"] = build(out_dir)
    if command in ("check", "all"):
        result["check"] = check(out_dir)
    print(json.dumps(result, indent=1, default=str)[:8000])
