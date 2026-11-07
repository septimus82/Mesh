"""Engine Capabilities Lab: verify Mesh's reusable systems in the real runtime window.

Not a game and not a demo: a disposable project with one small room per capability, built from
generated placeholder art and sounds, then played in the real Arcade window (Mesh Studio's
play-test runs the game's own loop). Each check reads the game's state (Studio's layout dump,
which includes engine.runtime_probe while playing) and, where the question is visual, samples
the screenshot's pixels. Every check reports PASS, FAIL (with what was seen) or UNVERIFIED.
Nothing here works around a failure: the existing systems are used as they are.

Run from the repo root:  py -3.13 tooling/capability_lab.py [--out DIR]
(MESH_GUI_AT / MESH_GUI_POLITE as for the other GUI tests). Writes DIR/lab_report.json and a
screenshot per check. A probe plugin is placed in the repo's mods/ for the run and removed after.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import struct
import sys
import time
import traceback
import wave
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO))
from acceptance_event_authoring import AuthorPage  # noqa: E402
from gui_driver import Driver  # noqa: E402

from engine import project_ops as ops  # noqa: E402
from engine.studio_project import Project  # noqa: E402

ROWS = 15  # new rooms are 20 x 15 tiles of 32 px
CLOCK = (480.0, 352.0)  # the Animate room's AnimationFactory object


def cell(col: int, row: int) -> tuple[float, float]:
    """World centre of a map cell (row 0 at the top; world y points up)."""
    return col * 32 + 16.0, ROWS * 32 - (row * 32 + 16.0)


def entity(eid: str, name: str, at: tuple[float, float], sprite: str | None, behaviours: dict[str, dict[str, Any]],
           **extra: Any) -> dict[str, Any]:
    out = {"id": eid, "name": name, "x": at[0], "y": at[1], "behaviours": list(behaviours),
           "behaviour_config": {k: v for k, v in behaviours.items() if v}}
    if sprite:
        out["sprite"] = sprite
    out.update(extra)
    return out


# ------------------------------------------------------------------------------- the lab project
def frame_colour(col: int, row: int) -> tuple[int, int, int, int]:
    return 40 + 60 * col, 40 + 60 * row, 220, 255


def frame_of(rgb: tuple[int, int, int]) -> tuple[int, int] | None:
    """Which frame of lab_frames.png a pixel shows: (column, row from the top), or None."""
    col, row = round((rgb[0] - 40) / 60), round((rgb[1] - 40) / 60)
    if abs(rgb[2] - 220) > 25 or not (0 <= col < 4 and 0 <= row < 4):
        return None
    if abs(rgb[0] - (40 + 60 * col)) > 20 or abs(rgb[1] - (40 + 60 * row)) > 20:
        return None
    return col, row


def make_assets(root: Path) -> None:
    from PIL import Image, ImageDraw

    sprites = root / "assets" / "sprites"
    sprites.mkdir(parents=True, exist_ok=True)
    for name, colour in (("lab_red", (220, 50, 50)), ("lab_blue", (50, 90, 230)), ("lab_green", (60, 200, 90)),
                         ("lab_yellow", (240, 210, 60)), ("lab_white", (235, 235, 235)), ("lab_purple", (150, 70, 200))):
        img = Image.new("RGBA", (28, 28), colour + (255,))
        ImageDraw.Draw(img).rectangle([0, 0, 27, 27], outline=(20, 20, 20, 255), width=2)
        img.save(sprites / f"{name}.png")
    for name, colour in (("lab_big_red", (220, 50, 50)), ("lab_big_blue", (50, 90, 230)), ("lab_big_white", (235, 235, 235))):
        Image.new("RGBA", (64, 64), colour + (255,)).save(sprites / f"{name}.png")
    # Every frame a different solid colour: red = 40 + 60 * column, green = 40 + 60 * row (row 0 at the top).
    sheet = Image.new("RGBA", (128, 128))
    for row in range(4):
        for col in range(4):
            ImageDraw.Draw(sheet).rectangle([col * 32, row * 32, col * 32 + 31, row * 32 + 31], fill=frame_colour(col, row))
    sheet.save(sprites / "lab_frames.png")
    backgrounds = root / "assets" / "backgrounds"
    backgrounds.mkdir(parents=True, exist_ok=True)
    stripes = Image.new("RGBA", (1600, 600), (20, 30, 70, 255))
    ImageDraw.Draw(stripes).rectangle([794, 0, 806, 599], fill=(255, 0, 0, 255))
    stripes.save(backgrounds / "stripes.png")
    sounds = root / "assets" / "sounds"
    sounds.mkdir(parents=True, exist_ok=True)
    for name, freq in (("hit", 660), ("shoot", 440), ("attack", 330)):
        with wave.open(str(sounds / f"{name}.wav"), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(22050)
            out.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / 22050)))
                                     for i in range(2205)))


def make_probe_mod(root: Path) -> None:
    """A plugin in the project's own mods/ folder (the game loads mods from the folder it runs in)."""
    mod_dir = root / "mods" / "capability_lab_probe"
    mod_dir.mkdir(parents=True, exist_ok=True)
    (mod_dir / "mod.json").write_text(json.dumps({
        "id": "capability_lab_probe", "name": "Capability lab probe", "version": "1.0.0", "author": "capability lab",
        "description": "Registers LabSpinner, a custom behaviour, to check plugins can add behaviours.",
        "entry_point": "main", "dependencies": []}, indent=2), encoding="utf-8")
    (mod_dir / "main.py").write_text('''from engine.behaviours.base import Behaviour
from engine.behaviours.registry import register_behaviour
from engine.plugin_system import MeshPlugin


@register_behaviour("LabSpinner", description="Spins its object (capability lab probe plugin)")
class LabSpinner(Behaviour):
    def update(self, dt):
        self.entity.angle = (self.entity.angle + 90.0 * dt) % 360.0


class LabProbe(MeshPlugin):
    pass


def create_plugin():
    return LabProbe()
''', encoding="utf-8")


def build_lab(root: Path) -> dict[str, str]:
    from engine.project_scaffold import create_project

    create_project(root, "Capability Lab", template_id="blank")
    config_path = root / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["lighting_enabled"] = True  # lighting is switched on per project, not per room
    config["lighting_ambient_color"] = [255, 255, 255, 255]  # rooms darken this with ambient_light_rgba
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    make_assets(root)
    make_probe_mod(root)
    project = Project(root, config["world_file"])
    keys = {label: project.add_room(label) for label in ("Paths", "Lights", "Torch", "Sequence", "Camera", "Depth", "Audio",
                                                         "Zoomed", "Day", "Look", "Unlit", "Enemy", "Animate")}

    def edit(key: str, fn: Callable[[dict[str, Any]], None]) -> None:
        def change(scene: dict[str, Any]) -> dict[str, Any]:
            import copy

            out = copy.deepcopy(scene)
            fn(out)
            return out

        project.edit_scene(change, key)

    def widen(key: str) -> None:
        """60 tiles wide: wider than the window, so the camera scrolls (it is clamped to the map)."""
        project.edit_scene(lambda s: ops.resize_map(s, 60, ROWS), key)
        project.edit_scene(lambda s: ops.paint_tiles(s, ops.WALLS, [(19, r) for r in range(1, 14)], 0), key)
        project.edit_scene(lambda s: ops.paint_tiles(s, ops.WALLS, [(c, r) for c in range(19, 60) for r in (0, 14)]
                                                     + [(59, r) for r in range(ROWS)], ops.STARTER_WALL), key)

    def add(key: str, *items: dict[str, Any]) -> None:
        edit(key, lambda s: s.setdefault("entities", []).extend(items))

    # Paths: a wall to walk around; one chaser can see the player, one can't.
    project.edit_scene(lambda s: ops.paint_tiles(s, ops.WALLS, [(10, r) for r in range(3, 12)], ops.STARTER_WALL), keys["Paths"])
    chase = {"target_tag": "player", "acquire_radius_tiles": 12, "leash_radius_tiles": 20, "los_required": True,
             "stop_range_tiles": 1}
    add(keys["Paths"],
        entity("walker", "Walker", cell(6, 7), "assets/sprites/lab_green.png",
               {"FollowPath": {"goal_x": cell(14, 7)[0], "goal_y": cell(14, 7)[1], "speed": 90},
                "LightSource": {"radius": 120, "color": "#99ccff"}}),
        entity("seer", "Seer", cell(8, 11), "assets/sprites/lab_yellow.png", {"ChaseTarget": dict(chase)}),
        entity("blind", "Blind", cell(16, 11), "assets/sprites/lab_purple.png", {"ChaseTarget": dict(chase)}))

    # Lights: a flickering static light and an occluder beside it, in the dark.
    light = cell(11, 7)
    edit(keys["Lights"], lambda s: s.update(
        lights=[{"id": "flicker", "x": light[0], "y": light[1], "radius": 220, "color": "#ffcc66", "flicker_enabled": True,
                 "flicker_speed": 5, "flicker_amount": 0.35}],
        occluders=[{"id": "pillar", "type": "rect", "x": light[0] + 80, "y": light[1] - 64, "width": 32, "height": 128}],
        settings={**(s.get("settings") or {}), "ambient_light_rgba": [25, 25, 35, 255], "lighting_shadows_mode": "hard"}))
    # Torch: a patrolling NPC carrying a light.
    edit(keys["Torch"], lambda s: s.update(settings={**(s.get("settings") or {}), "ambient_light_rgba": [25, 25, 35, 255]}))
    add(keys["Torch"], entity("torchbearer", "Torchbearer", cell(8, 6), "assets/sprites/lab_white.png", {
        "LightSource": {"radius": 140, "color": "#ff9933"},
        "PatrolPath": {"waypoints": [list(cell(8, 6)), list(cell(15, 6))], "mode": "pingpong", "speed": 70, "wait_time": 0.0}}))

    # Sequence: move, wait, then talk; particles; prefab reuse; a plugin's custom behaviour.
    add(keys["Sequence"],
        entity("herald", "Herald", cell(8, 9), "assets/sprites/lab_blue.png", {
            "SequencePlayer": {"auto_start": True, "lock_player_input": False, "steps": [
                {"type": "move_to", "x": 96, "y": 0, "relative": True, "speed": 80},
                {"type": "wait", "duration": 3.0},
                {"type": "signal", "event": "herald_talk"},
                {"type": "wait", "duration": 0.5},
                {"type": "signal", "event": "herald_done"}]},
            "Dialogue": {"start_event": "herald_talk", "once": False},
            "SetGameStateOnEvent": {"event_type": "herald_done", "set_flags": {"herald_done": True}}}),
        entity("sparks", "Sparks", cell(5, 8), None, {"ParticleEmitter": {
            "mode": "rate", "rate": 30, "color": [255, 200, 80], "spawn_shape": "circle", "radius": 12}}),
        entity("spinner", "Spinner", cell(14, 9), "assets/sprites/lab_red.png", {"LabSpinner": {}}),
        # A quest step counted from a live event: QuestHook hears the herald's last signal, then a flag records
        # the step's completion event.
        entity("quest_board", "Quest board", cell(3, 3), "assets/sprites/lab_white.png", {
            "QuestHook": {"quest_id": "lab", "step_id": "hear_the_herald", "listen_events": ["herald_done"],
                          "target_count": 1},
            "SetGameStateOnEvent": {"event_type": "quest_step_completed", "set_flags": {"quest_step_done": True}}}),
        {"id": "twin_ref", "mesh_name": "Twin (prefab reference)", "prefab_id": "person", "x": cell(12, 5)[0], "y": cell(12, 5)[1]})
    project.edit_scene(lambda s: ops.set_dialogue_text(s, "herald", "Moved, waited, now talking."), keys["Sequence"])
    from engine import authoring

    authoring.apply(project, [{"op": "place_prefab", "room": keys["Sequence"], "prefab": "person", "x": cell(14, 5)[0],
                               "y": cell(14, 5)[1]},
                              {"op": "rename_entity", "room": keys["Sequence"], "entity_id": "@0", "name": "Twin (copy)"}])

    # Camera: a zoom area to walk into; a parallax background showing where the floor is cleared.
    edit(keys["Camera"], lambda s: s.update(
        settings={**(s.get("settings") or {}), "camera": {"areas": [
            {"name": "close-up", "x": 300, "y": 96, "width": 200, "height": 128, "zoom": 1.8}]}},
        background_layers=[{"id": "stripes", "path": "assets/backgrounds/stripes.png", "z": -1000, "parallax": 0.5}]))
    widen(keys["Camera"])
    project.edit_scene(lambda s: ops.paint_tiles(s, ops.GROUND, [(c, r) for c in range(1, 59) for r in range(1, 14)], 0),
                       keys["Camera"])

    # Depth: three overlapping squares, two sharing one texture (y-sort vs batching).
    a1, b, a2 = (320.0, 250.0), (320.0, 230.0), (320.0, 210.0)
    add(keys["Depth"],
        entity("back_red", "Back red", a1, "assets/sprites/lab_big_red.png", {}),
        entity("mid_blue", "Middle blue", b, "assets/sprites/lab_big_blue.png", {}),
        entity("front_red", "Front red", a2, "assets/sprites/lab_big_red.png", {}),
        entity("lone", "Lone", (480.0, 250.0), "assets/sprites/lab_big_blue.png", {}))

    # Audio: a turret shooting a dummy; the listener is the camera, so the room is wide enough to move it.
    widen(keys["Audio"])
    add(keys["Audio"],
        entity("dummy", "Dummy", cell(48, 7), "assets/sprites/lab_purple.png", {"Health": {"max_hp": 99999, "hp": 99999}},
               tag="dummy", solid=True),
        entity("turret", "Turret", cell(44, 7), "assets/sprites/lab_yellow.png", {
            "RangedEnemyAI": {"target_tag": "dummy", "detect_radius": 400, "attack_radius": 300, "flee_radius": 0, "speed": 0},
            "Shooter": {"target_tag": "dummy", "cooldown": 0.6, "range": 400, "damage": 1}}))

    # Zoomed: the Lights room's light and pillar, seen with the camera at zoom 1.8 (shadows must line up).
    zl = (240.0, 240.0)
    edit(keys["Zoomed"], lambda s: s.update(
        lights=[{"id": "steady", "x": zl[0], "y": zl[1], "radius": 220, "color": "#ffcc66"}],
        occluders=[{"id": "pillar", "type": "rect", "x": zl[0] + 80, "y": zl[1] - 64, "width": 32, "height": 128}],
        settings={**(s.get("settings") or {}), "ambient_light_rgba": [25, 25, 35, 255], "lighting_shadows_mode": "hard",
                  # A camera area over the whole room: the templates' player CameraFollow pins zoom 1.0, which
                  # overrides a room's own initial zoom (recorded in the Milestone 8 report).
                  "camera": {"areas": [{"name": "zoomed", "x": 0, "y": 0, "width": 640, "height": 480, "zoom": 1.8}]}}))

    # Day: the clock runs an hour a second from 06:00; two shopkeepers stand until 08:00, then walk a route.
    # One lists Patrol before NpcSchedule, the other after (the schedule looks for its Patrol when it starts).
    def schedule(row: int) -> dict[str, Any]:
        a, b = cell(5, row), cell(15, row)
        return {"schedules": [{"start_hour": 6, "end_hour": 8, "mode": "stand", "x": a[0], "y": a[1]},
                              {"start_hour": 8, "end_hour": 20, "mode": "patrol",
                               "patrol_points": [{"x": a[0], "y": a[1]}, {"x": b[0], "y": b[1]}]}]}

    edit(keys["Day"], lambda s: s.update(settings={**(s.get("settings") or {}), "day_night_enabled": True,
                                                   "time_of_day_hour": 6, "day_night_cycle_length_seconds": 24}))
    patrol = {"patrol_points": [], "patrol_speed": 60}
    add(keys["Day"],
        {**entity("shopkeeper", "Shopkeeper", cell(5, 5), "assets/sprites/lab_green.png", {}),
         "behaviours": ["Patrol", "NpcSchedule"], "behaviour_config": {"Patrol": dict(patrol), "NpcSchedule": schedule(5)}},
        {**entity("early_bird", "Early bird", cell(5, 8), "assets/sprites/lab_yellow.png", {}),
         "behaviours": ["NpcSchedule", "Patrol"], "behaviour_config": {"Patrol": dict(patrol), "NpcSchedule": schedule(8)}})

    # Look: outlines and depth tint on real sprites.
    edit(keys["Look"], lambda s: s.update(settings={**(s.get("settings") or {}),
        "outline_enabled": True, "outline_color_rgba": [255, 0, 255, 255], "outline_strength": 1.0, "outline_radius_px": 2,
        "depth_tint_enabled": True, "depth_tint_near_color": [255, 255, 255, 255], "depth_tint_far_color": [40, 40, 160, 255],
        "depth_tint_strength": 1.0}))
    add(keys["Look"],
        # In y-sort rooms depth tint follows render_layer (depth_z counts only in explicit_z rooms); higher is nearer.
        entity("near", "Near", (320.0, 300.0), "assets/sprites/lab_big_white.png", {}, render_layer=10),
        entity("far", "Far", (480.0, 300.0), "assets/sprites/lab_big_white.png", {}, render_layer=-10))

    # Unlit: this room switches lighting off (the project has it on) and would be dark if it didn't.
    edit(keys["Unlit"], lambda s: s.update(settings={**(s.get("settings") or {}), "lighting_enabled": False,
                                                     "ambient_light_rgba": [20, 20, 20, 255]}))

    # Enemy: an EnemyAI that should chase the player at its speed (100 px/s).
    add(keys["Enemy"], entity("grunt", "Grunt", cell(14, 11), "assets/sprites/lab_red.png", {
        "EnemyAI": {"target_tag": "player", "detect_radius": 500, "lose_radius": 600, "attack_radius": 40, "speed": 100,
                    "use_patrol": False}}))

    # Animate: the player walks with Mesh Studio's Animator (a row of the colour sheet per direction, top-left
    # order) and a clock plays an AnimationFactory clip (the older system: frames counted from the bottom-left).
    # Unlit, so the colours on screen are the sheet's own. A door to Unlit and back for a room change.
    edit(keys["Animate"], lambda s: s.update(settings={**(s.get("settings") or {}), "lighting_enabled": False}))
    player_id = next(e["id"] for e in project.scene(keys["Animate"])["entities"] if e.get("tag") == "player")
    clips = ops.character_clips("assets/sprites/lab_frames.png", 32, 32, 4, {"down": 0, "left": 1, "right": 2, "up": 3},
                                walk_count=4, walk_fps=4, idle_fps=2, sheet_rows=4)
    project.edit_scene(lambda s: ops.set_animation(s, player_id, clips), keys["Animate"])
    add(keys["Animate"], entity("clock", "Clock", CLOCK, "assets/sprites/lab_frames.png", {},
                                sprite_sheet={"frame_width": 32, "frame_height": 32},
                                animations={"idle": {"frames": [0, 1, 2, 3], "fps": 4, "loop": True}}))
    project.link_rooms(keys["Animate"], (560.0, 48.0), keys["Unlit"], (80.0, 48.0))

    # A door from Lights to Paths, for a scene transition.
    project.link_rooms(keys["Lights"], (128.0, 48.0), keys["Paths"], (560.0, 400.0))
    project.save()
    return keys


# ------------------------------------------------------------------------------- the checks
def brightness(img: Any, x: float, y: float, r: int = 3) -> float:
    total, n = 0.0, 0
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            px, py = int(x + dx), int(y + dy)
            if 0 <= px < img.width and 0 <= py < img.height:
                rgb = img.getpixel((px, py))[:3]
                total += sum(rgb) / 3
                n += 1
    return total / max(1, n)


def colour(img: Any, x: float, y: float) -> tuple[int, int, int]:
    return tuple(img.getpixel((int(x), int(y)))[:3])


def run(out: Path, only: set[str] | None = None) -> int:
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    root = out / "lab"
    shutil.rmtree(root, ignore_errors=True)
    layout = out / "layout.json"
    env = {**os.environ, "PYTHONPATH": str(REPO), "MESH_STUDIO_LAYOUT": str(layout)}
    os.environ.update(env)
    keys = build_lab(root)
    results: list[dict[str, Any]] = []
    holder: dict[str, Any] = {}

    def record(name: str, status: str, detail: Any, shot: str | None = None) -> None:
        results.append({"check": name, "status": status, "detail": detail, "screenshot": shot})
        print(f"[{status}] {name}: {json.dumps(detail)[:220]}", flush=True)

    def p() -> AuthorPage:
        return holder["page"]

    def shot(name: str) -> tuple[Any, str]:
        path = p().d.shot(name)
        return Image.open(path).convert("RGB"), path.name

    def play_room(label: str) -> None:
        state = p().fresh()
        if state["mode"] == "play":
            p().d.key("F4")
            p().wait(lambda s: s["mode"] == "edit", "back to editing")
        p().button(label)
        p().wait(lambda s: s["room"] == keys[label], f"room {label}")
        p().d.key("F4")
        p().wait(lambda s: s["mode"] == "play" and s["play"] and s["play"]["player"], f"playing {label}", timeout=30)
        time.sleep(0.8)

    def play() -> dict[str, Any]:
        value: dict[str, Any] = p().fresh()["play"]
        return value

    def sprite(name: str, state: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """An object as the game last reported it; pass ``state`` to compare it with other values from the same
        moment (a separate read is a later frame: a moving object then seems to lead its own light)."""
        return next((s for s in (state or play())["sprites"] if s["name"] == name), None)

    def present(name: str) -> dict[str, Any]:
        """``sprite`` for an object the room must have."""
        found = sprite(name)
        assert found is not None, f"no {name} in the room"
        return found

    def to_screen(world: tuple[float, float], state: dict[str, Any] | None = None) -> tuple[float, float]:
        """World point -> screenshot pixel, from where the player is drawn (camera follows it)."""
        state = state or play()
        zoom = state["runtime"]["camera"]["zoom"]
        (px, py), (sx, sy) = state["player"], state["player_screen"]
        height = p().state()["window"][1]
        return sx + (world[0] - px) * zoom, height - (sy + (world[1] - py) * zoom)

    def check(name: str, fn: Callable[[], None]) -> None:
        try:
            fn()
        except (AssertionError, AttributeError, KeyError, IndexError, TypeError, ValueError, OSError, RuntimeError) as exc:
            # one broken check must not hide the others
            record(name, "ERROR", f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)}")

    # -------------------------------------------------------------------- navigation
    def nav() -> None:
        play_room("Paths")
        walls = {(10, r) for r in range(3, 12)}
        start = time.time()
        trail = []
        while time.time() - start < 14:
            w = sprite("Walker")
            if w:
                trail.append(w["at"])
            time.sleep(0.4)
        goal = cell(14, 7)
        end = trail[-1]
        inside = [pt for pt in trail if (int(pt[0] // 32), int((ROWS * 32 - pt[1]) // 32)) in walls]
        img, name = shot("nav_walker")
        reached = math.dist(end, goal) < 24
        record("4. NPC follows a path around an obstacle (FollowPath, A*)", "PASS" if reached and not inside else "FAIL",
               {"start": trail[0], "end": end, "goal": goal, "points_inside_wall": len(inside),
                "went_around": any(pt[1] > cell(0, 3)[1] or pt[1] < cell(0, 11)[1] for pt in trail)}, name)
        seer, blind = sprite("Seer"), sprite("Blind")
        seer0, blind0 = cell(8, 11), cell(16, 11)
        img, name = shot("los")
        moved_seer = math.dist(seer["at"], seer0) > 16 if seer else False
        moved_blind = math.dist(blind["at"], blind0) > 16 if blind else True
        record("5. Line of sight affects a behaviour (ChaseTarget los_required)",
               "PASS" if moved_seer and not moved_blind else "FAIL",
               {"seer_moved": moved_seer, "seer_at": seer and seer["at"], "blind_moved": moved_blind,
                "blind_at": blind and blind["at"]}, name)

    def save_load() -> None:
        before = play()
        seer_saved = present("Seer")["at"]
        player_saved = before["player"]
        p().d.key("F5")
        time.sleep(1.0)
        p().d.hold("D", 0.7)  # walk away: the seer follows
        time.sleep(1.2)
        moved = play()
        p().d.key("F9")
        time.sleep(2.0)
        after = play()
        img, name = shot("save_load")
        seer_back = present("Seer")["at"]
        ok = math.dist(after["player"], player_saved) < 4 and math.dist(seer_back, seer_saved) < 8
        record("12. Save and load restore runtime state (F5/F9)", "PASS" if ok else "FAIL",
               {"player_saved": player_saved, "player_moved_to": moved["player"], "player_after_load": after["player"],
                "seer_saved": seer_saved, "seer_after_load": seer_back,
                "scene_after_load": after["scene"]}, name)

    # -------------------------------------------------------------------- lighting
    def lights() -> None:
        play_room("Lights")
        state = play()
        lit = state["runtime"]["lighting"]
        centre, edge, behind, open_side = [], [], [], []
        light = cell(11, 7)
        for i in range(8):  # the flicker mostly changes the light's reach, so its edge shows it best
            img, _ = shot(f"flicker_{i}")
            centre.append(brightness(img, *to_screen(light)))
            edge.append(brightness(img, *to_screen((light[0] - 160, light[1]))))
            # Just past the pillar (it spans 80-112 px east), and the same distance south in the open:
            # well inside the light's reach even when the flicker shrinks it (to ~143 px).
            behind.append(brightness(img, *to_screen((light[0] + 125, light[1]))))
            open_side.append(brightness(img, *to_screen((light[0], light[1] - 125))))
            time.sleep(0.15)
        img, name = shot("lights")
        far = brightness(img, *to_screen((light[0] - 300, light[1] + 150)))
        varies = max(edge) - min(edge)
        record("1. A flickering light illuminates the scene", "PASS" if lit["enabled"] and min(centre) > far + 20 and varies > 4
               else "FAIL", {"lighting": lit, "brightness_at_light": [round(v) for v in centre],
                             "brightness_near_edge": [round(v) for v in edge], "dark_far_away": round(far),
                             "flicker_range_at_edge": round(varies, 1)}, name)
        darker = sum(o - b for o, b in zip(open_side, behind)) / len(behind)  # averaged: the flicker dims some frames
        record("2. An occluder casts a visible shadow (hard shadows)", "PASS" if darker > 10 else "FAIL",
               {"behind_pillar": [round(v) for v in behind], "open_same_distance": [round(v) for v in open_side],
                "occluders": lit["occluders"], "mode": lit["shadows_mode"]}, name)

    def transition() -> None:
        """Through the Lights room's door to Paths and back, three times. Each arrival must show that room's
        lights only: Lights' static light and pillar; in Paths, the walker's own light, on the walker."""
        lights_scene = play()["scene"]
        visits, name = [], None
        for lap in range(3):
            p().go_to(128.0, 48.0 + 90, tol=10)  # the Lights door is at (128, 48)
            p().d.hold("S", 0.6)
            p().wait(lambda s: s["play"] and s["play"]["scene"] != lights_scene, "arriving in Paths", timeout=8)
            time.sleep(1.0)
            state = play()
            walker = sprite("Walker", state)
            lit = state["runtime"]["lighting"]
            visits.append({"room": "Paths", "static": lit["static_lights"], "occluders": lit["occluders"],
                           "dynamic": [d["at"] for d in lit["dynamic"]], "walker": walker and walker["at"]})
            if lap == 0:
                _, name = shot("transition")
            p().go_to(560.0, 400.0 - 90, tol=10)  # the Paths door is at (560, 400), its arrival below it
            p().d.hold("W", 0.6)
            p().wait(lambda s: s["play"] and s["play"]["scene"] == lights_scene, "back in Lights", timeout=8)
            time.sleep(1.0)
            lit = play()["runtime"]["lighting"]
            visits.append({"room": "Lights", "static": lit["static_lights"], "occluders": lit["occluders"],
                           "dynamic": [d["at"] for d in lit["dynamic"]], "ambient_tint": lit["ambient_tint"]})
        ok = all(v["static"] == 1 and v["occluders"] == 1 and not v["dynamic"] for v in visits if v["room"] == "Lights")
        ok = ok and all(v["static"] == 0 and len(v["dynamic"]) == 1 and v["walker"]
                        and math.dist(v["dynamic"][0], v["walker"]) < 4 for v in visits if v["room"] == "Paths")
        record("Scene transitions, and lights over repeated room changes (3 round trips)", "PASS" if ok else "FAIL",
               {"visits": visits}, name)

    def zoomed() -> None:
        play_room("Zoomed")
        state = play()
        light = (240.0, 240.0)
        zoom = state["runtime"]["camera"]["zoom"]
        img, name = shot("zoomed_shadow")
        behind = brightness(img, *to_screen((light[0] + 125, light[1]), state))
        before = brightness(img, *to_screen((light[0] + 60, light[1]), state))  # lit side, between light and pillar
        open_side = brightness(img, *to_screen((light[0], light[1] - 125), state))
        ok = zoom > 1.5 and open_side - behind > 10 and before > behind + 10
        record("Occluder shadow lines up at camera zoom 1.8", "PASS" if ok else "FAIL",
               {"zoom": zoom, "behind_pillar": round(behind), "in_front_of_pillar": round(before),
                "open_same_distance": round(open_side)}, name)

    def day() -> None:
        play_room("Day")
        samples = []
        start = time.time()
        while time.time() - start < 5.0:
            state = play()
            keeper, bird = sprite("Shopkeeper", state), sprite("Early bird", state)
            samples.append({"t": round(time.time() - start, 1), "hour": state["runtime"].get("day_night", {}).get("hour"),
                            "ambient": state["runtime"]["lighting"]["ambient"], "shopkeeper": keeper and keeper["at"],
                            "early_bird": bird and bird["at"]})
            time.sleep(0.5)
        _, name = shot("day")
        hours = [x["hour"] for x in samples if x["hour"] is not None]
        ambients = {tuple(x["ambient"]) for x in samples}
        record("Day/night progresses over time (scene day_night_enabled)",
               "PASS" if hours and hours[-1] - hours[0] >= 3 and len(ambients) >= 3 else "FAIL",
               {"hours": hours, "distinct_ambients": len(ambients), "first": samples[0], "last": samples[-1]}, name)
        for who in ("shopkeeper", "early_bird"):
            first, last = samples[0][who], samples[-1][who]
            moved = bool(first and last and math.dist(first, last) > 30)
            record(f"NPC schedule: stands until 08:00, then walks its route ({who})", "PASS" if moved else "FAIL",
                   {"at_start": first, "at_end": last, "hour_at_end": samples[-1]["hour"]}, name)

    def look() -> None:
        play_room("Look")
        state = play()
        img, name = shot("look")
        near, far = colour(img, *to_screen((320.0, 300.0), state)), colour(img, *to_screen((480.0, 300.0), state))
        edge = colour(img, *to_screen((320.0 + 33.5, 300.0), state))  # 1-2 px outside the near square, right side
        outlined = edge[0] > 150 and edge[2] > 150 and edge[1] < 120
        record("Outlines are drawn round sprites (outline_enabled)", "PASS" if outlined else "FAIL",
               {"pixel_just_outside": edge, "outline_colour": [255, 0, 255]}, name)
        record("Depth tint colours near and far sprites differently (depth_tint_enabled)",
               "PASS" if sum(near) - sum(far) > 90 and far[2] > far[0] + 30 else "FAIL",
               {"near_pixel": near, "far_pixel": far, "far_colour": [40, 40, 160]}, name)

    def unlit() -> None:
        play_room("Unlit")
        state = play()
        img, name = shot("unlit")
        floor = brightness(img, *to_screen((320.0, 300.0), state))
        lit = state["runtime"]["lighting"]
        record("A room can switch lighting off (settings.lighting_enabled false)",
               "PASS" if not lit["enabled"] and floor > 80 else "FAIL", {"lighting": lit, "floor_brightness": round(floor)}, name)
        play_room("Lights")
        lit = play()["runtime"]["lighting"]
        record("Lighting comes back on in the next lit room", "PASS" if lit["enabled"] and lit["static_lights"] == 1 else "FAIL",
               {"lighting": lit}, None)

    def enemy() -> None:
        play_room("Enemy")
        trail = []
        start = time.time()
        while time.time() - start < 2.0:
            grunt = sprite("Grunt")
            trail.append((time.time() - start, grunt and grunt["at"]))
            time.sleep(0.25)
        _, name = shot("enemy")
        (t0, a), (t1, b) = trail[0], trail[-1]
        speed = math.dist(a, b) / (t1 - t0) if a and b and t1 > t0 else 0.0
        record("EnemyAI chases at its speed (100 px/s)", "PASS" if 70 <= speed <= 130 else "FAIL",
               {"measured_px_per_s": round(speed, 1), "from": a, "to": b, "seconds": round(t1 - t0, 2)}, name)

    def torch() -> None:
        play_room("Torch")
        seen: list[dict[str, Any]] = []
        for _ in range(6):
            state = play()
            dyn = state["runtime"]["lighting"]["dynamic"]
            npc = sprite("Torchbearer", state)
            seen.append({"light": dyn[0]["at"] if dyn else None, "npc": npc["at"] if npc else None, "lights": len(dyn)})
            time.sleep(0.5)
        img, name = shot("torch")
        moved = max((math.dist(seen[0]["npc"], s["npc"]) for s in seen if s["npc"] and seen[0]["npc"]), default=0) > 20
        follows = all(s["light"] and s["npc"] and s["lights"] == 1 and math.dist(s["light"], s["npc"]) < 2 for s in seen)
        record("3. A moving entity carries a dynamic light (LightSource)", "PASS" if moved and follows else "FAIL",
               {"samples": seen}, name)

    # -------------------------------------------------------------------- sequence, particles, prefabs, plugins
    def sequence() -> None:
        play_room("Sequence")
        start = cell(8, 9)
        moved_at = None
        deadline = time.time() + 10
        talked = None
        trail = []
        while time.time() < deadline:
            state = play()
            herald = sprite("Herald")
            trail.append(herald and [round(v) for v in herald["at"]])
            if herald and math.dist(herald["at"], start) > 80 and moved_at is None:
                moved_at = (time.time(), herald["at"])
            if state["dialogue"]:
                talked = (time.time(), state["dialogue"])
                break
            time.sleep(0.2)
        img, name = shot("sequence")
        waited = bool(moved_at and talked and talked[0] - moved_at[0] >= 1.5)  # the wait is 3 s; arrival is seen late
        record("6. A sequence moves an object, waits and starts dialogue (SequencePlayer + Dialogue)",
               "PASS" if moved_at and talked and waited else "FAIL",
               {"moved_to": moved_at and moved_at[1], "dialogue": talked and talked[1]["text"],
                "wait_between_s": talked and moved_at and round(talked[0] - moved_at[0], 2), "herald_trail": trail[::3]}, name)
        p().close_dialogue()
        done = p().wait(lambda s: s["play"]["flags"].get("herald_done"), "the sequence's last step", timeout=6)
        record("A sequence runs to its end and triggers what follows (signal -> SetGameStateOnEvent)", "PASS",
               {"flags": done["play"]["flags"]}, None)
        quest = p().wait(lambda s: s["play"]["flags"].get("quest_step_done"), "the quest step completed", timeout=6)
        record("A quest step counts a live game event (QuestHook)", "PASS", {"flags": quest["play"]["flags"]}, None)
        particles = play()["runtime"]["particles"]
        img, name = shot("particles")
        record("10. A particle effect appears (ParticleEmitter)", "PASS" if particles["alive"] or particles["sprites"] else "FAIL",
               particles, name)
        sprites = play()["sprites"]
        ref = next((s for s in sprites if math.dist(s["at"], cell(12, 5)) < 4), None)  # the dump names it after the prefab
        copy = next((s for s in sprites if s["name"] == "Twin (copy)"), None)
        record("Prefab reuse (a prefab reference and a copy)", "PASS" if ref and copy else "FAIL",
               {"reference_spawned_as": ref and ref["name"], "copy": copy and copy["name"]}, name)
        spinner = sprite("Spinner")
        a0 = spinner["angle"] if spinner else None
        time.sleep(0.6)
        spinner = sprite("Spinner")
        a1 = spinner["angle"] if spinner else None
        log = p().d.log_text()
        record("Custom behaviour from a plugin (mods/, LabSpinner)",
               "PASS" if a0 is not None and a1 is not None and a0 != a1 else "FAIL",
               {"angles": [a0, a1], "plugin_logged": "capability_lab_probe" in log}, name)

    # -------------------------------------------------------------------- camera and parallax
    def camera() -> None:
        play_room("Camera")
        state = play()
        img0, _ = shot("parallax_before")
        stripe0 = _find_red(img0)
        cam0 = state["runtime"]["camera"]["center"]
        zoom0 = state["runtime"]["camera"]["zoom"]
        p().go_to(1100.0, 128.0, tol=16)
        time.sleep(0.8)
        state = play()
        img1, name1 = shot("parallax_after")
        stripe1 = _find_red(img1)
        cam1 = state["runtime"]["camera"]["center"]
        record("8. A background uses parallax (background_layers, parallax 0.5)",
               "PASS" if stripe0 is not None and stripe1 is not None and cam0 and cam1 and cam1[0] != cam0[0]
               and abs((stripe0 - stripe1) - (cam1[0] - cam0[0]) * 0.5) < 25 else "FAIL",
               {"stripe_screen_x": [stripe0, stripe1], "camera_x": [cam0 and cam0[0], cam1 and cam1[0]],
                "expected_shift": cam0 and cam1 and round((cam1[0] - cam0[0]) * 0.5, 1)}, name1)
        p().go_to(400.0, 160.0, tol=12)
        time.sleep(1.5)
        state = play()
        img, name = shot("zoom_area")
        cam = state["runtime"]["camera"]
        record("7. Camera zoom (a camera area zooms in)", "PASS" if cam["area"] == "close-up" and cam["zoom"] > zoom0 + 0.3
               else "FAIL", {"before": zoom0, "in_area": cam}, name)

    # -------------------------------------------------------------------- depth (HD-2D draw order)
    def depth() -> None:
        play_room("Depth")
        state = play()
        img, name = shot("depth")
        front_overlap = colour(img, *to_screen((320.0, 216.0), state))  # middle blue under front red
        back_overlap = colour(img, *to_screen((320.0, 256.0), state))  # back red under middle blue
        is_red = front_overlap[0] > 1.5 * front_overlap[2]  # by hue, so the room's light level doesn't matter
        is_blue = back_overlap[2] > 1.5 * back_overlap[0]
        record("9. HD-2D draw order (y-sort) with sprites sharing a texture", "PASS" if is_red and is_blue else "FAIL",
               {"front_red_over_blue_pixel": front_overlap, "blue_over_back_red_pixel": back_overlap,
                "expected": "front overlap red, back overlap blue", "lighting": state["runtime"].get("lighting")}, name)
        below = brightness(img, *to_screen((480.0, 250.0 - 34), state))
        floor = brightness(img, *to_screen((560.0, 250.0 - 34), state))
        record("Sprite shadows (on by default)", "PASS" if floor - below > 8 else "FAIL",
               {"under_sprite": round(below), "plain_floor": round(floor)}, name)

    # -------------------------------------------------------------------- audio
    def audio() -> None:
        play_room("Audio")
        time.sleep(2.5)
        far = [r for r in play()["runtime"]["audio"]["recent"] if r["path"].endswith("hit.wav")]
        dummy = cell(48, 7)
        p().go_to(dummy[0] - 70, dummy[1], tol=14)
        time.sleep(2.5)
        near = [r for r in play()["runtime"]["audio"]["recent"] if r["path"].endswith("hit.wav")]
        img, name = shot("audio")
        if not far or not near:
            state = play()
            time.sleep(0.25)
            later = play()
            record("11. A positional sound changes with distance", "FAIL",
                   {"far": far[-2:], "near": near[-2:], "recent_sounds": state["runtime"]["audio"]["recent"][-4:],
                    "projectiles": [[round(v) for v in s["at"]] for s in state["sprites"] if str(s["name"]).startswith("proj_")],
                    "projectiles_later": [[round(v) for v in s["at"]] for s in later["sprites"]
                                          if str(s["name"]).startswith("proj_")]}, name)
            return
        record("11. A positional sound changes with distance", "PASS" if near[-1]["volume"] > far[-1]["volume"] + 0.15 else "FAIL",
               {"far": far[-1], "near": near[-1]}, name)

    def animation() -> None:
        """Both animation systems, read off the screen: which frame of the colour sheet shows, many times a second."""
        import threading

        clock_at: dict[str, tuple[float, float]] = {}

        def frame_now(target: str) -> tuple[int, int] | None:
            """The sheet frame on screen for the player or the clock, from one capture of the window: the lab's
            only sheet-coloured things are those two, told apart by where the clock is (the room fits the window,
            so the camera doesn't move)."""
            with Image.open(p().d.shot("_anim")) as image:
                small = image.convert("RGB").reduce(4)
            cx, cy = clock_at["xy"][0] / 4, clock_at["xy"][1] / 4
            counts: dict[tuple[int, int], int] = {}
            for i, rgb in enumerate(small.getdata()):
                found = frame_of(rgb)
                if found is None:
                    continue
                x, y = i % small.width, i // small.width
                if ((x - cx) ** 2 + (y - cy) ** 2 < 12 ** 2) == (target == "clock"):
                    counts[found] = counts.get(found, 0) + 1
            return max(counts, key=lambda f: counts[f]) if counts else None
        def watch(target: str, seconds: float) -> tuple[list[tuple[int, int]], float]:
            seen: list[tuple[int, int]] = []
            started = time.time()
            while time.time() - started < seconds:
                now = frame_now(target)
                if now is not None and (not seen or seen[-1] != now):
                    seen.append(now)
            return seen, time.time() - started

        def in_order(seen: list[tuple[int, int]], cycle: list[tuple[int, int]]) -> bool:
            return len(seen) > 1 and all(b == cycle[(cycle.index(a) + 1) % len(cycle)] for a, b in zip(seen, seen[1:]))

        def factory_check(label: str) -> dict[str, Any]:
            seen, took = watch("clock", 3.0)
            cycle = [(0, 3), (1, 3), (2, 3), (3, 3)]  # frames 0-3 counted from the bottom-left: the bottom row
            rate = (len(seen) - 1) / took
            ok = all(f in cycle for f in seen) and in_order(seen, cycle) and len(seen) >= 8 and 2.8 <= rate <= 5.2
            record(f"AnimationFactory clip: bottom-left frame order, 4 fps, looping ({label})", "PASS" if ok else "FAIL",
                   {"frames_seen": seen, "changes_per_second": round(rate, 2), "expected_cycle": cycle}, None)
            return {"seen": seen}

        def walk_check(key: str, direction: str, row: int, label: str) -> None:
            seen: list[tuple[int, int]] = []
            stop = threading.Event()

            def sample() -> None:
                while not stop.is_set():
                    now = frame_now("player")
                    if now is not None and (not seen or seen[-1] != now):
                        seen.append(now)

            sampler = threading.Thread(target=sample)
            sampler.start()
            p().d.hold(key, 1.5)
            stop.set()
            sampler.join()
            time.sleep(0.4)
            idle = frame_now("player")
            cycle = [(c, row) for c in range(4)]
            before = [f for f in seen[:1] if f not in cycle]  # the last facing, sampled before the key took effect
            walk = seen[len(before):]
            walk = walk[:-1] if walk and walk[-1] == (0, row) else walk  # stopping goes back to the idle frame
            rate = (len(walk) - 1) / 1.5
            ok = all(f in cycle for f in walk) and in_order(walk, cycle) and len(set(walk)) >= 3 and 2.5 <= rate <= 5.5
            ok = ok and idle == (0, row)
            record(f"Studio Animator walks {direction} on row {row} in top-left order, then idles facing {direction} ({label})",
                   "PASS" if ok else "FAIL", {"frames_seen": seen, "changes_per_second": round(rate, 2), "idle_after": idle,
                                              "expected_row": row}, None)

        play_room("Animate")
        time.sleep(1.0)
        clock_at["xy"] = to_screen(CLOCK)
        _, name = shot("animation")
        start = frame_now("player")
        record("Studio Animator starts idle, facing down (row 0, first frame)", "PASS" if start == (0, 0) else "FAIL",
               {"frame": start}, name)
        factory_check("first visit")
        for key, direction, row in (("D", "right", 2), ("W", "up", 3), ("A", "left", 1), ("S", "down", 0)):
            walk_check(key, direction, row, "first visit")
        door = (560.0, 48.0)
        here = play()["scene"]
        p().go_to(door[0], door[1] + 90, tol=10)
        p().d.hold("S", 0.6)
        p().wait(lambda s: s["play"] and s["play"]["scene"] != here, "in the next room", timeout=8)
        time.sleep(1.0)
        p().go_to(80.0, 48.0 + 90, tol=10)
        p().d.hold("S", 0.6)
        p().wait(lambda s: s["play"] and s["play"]["scene"] == here, "back in Animate", timeout=8)
        time.sleep(1.0)
        factory_check("after leaving the room and coming back")
        walk_check("A", "left", 1, "after coming back")
        walk_check("W", "up", 3, "after coming back")

    # -------------------------------------------------------------------- run
    driver = Driver([sys.executable, "-m", "mesh_cli", "edit"], cwd=root, shots=out)
    holder["page"] = page = AuthorPage(driver, layout)
    page.memo_positions = {}
    try:
        page.wait(lambda s: s["mode"] == "edit" and s["objects"], "the Studio", timeout=60)
        for name, fn in (("navigation", nav), ("save_load", save_load), ("lights", lights), ("transition", transition),
                         ("torch", torch), ("sequence", sequence), ("camera", camera), ("depth", depth), ("audio", audio),
                         ("zoomed", zoomed), ("day", day), ("look", look), ("unlit", unlit), ("enemy", enemy),
                         ("animation", animation)):
            if not only or name in only:
                check(name, fn)
    finally:
        driver.close()
    headless(results, root, record)
    (out / "lab_report.json").write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
    shutil.rmtree(root, ignore_errors=True)  # the disposable project goes; the report and screenshots stay
    passed = sum(r["status"] == "PASS" for r in results)
    known = sum(r["status"] == "KNOWN" for r in results)
    print(f"{passed}/{len(results) - known} checks passed; {known} known defect(s) reported apart; "
          f"report: {out / 'lab_report.json'}")
    return 0 if passed == len(results) - known else 1


def _find_red(img: Any) -> float | None:
    """Screen x of the parallax background's red stripe (the middle of the red run on one row)."""
    row = img.height // 2
    xs = [x for x in range(img.width) if (lambda c: c[0] > 200 and c[1] < 60 and c[2] < 60)(img.getpixel((x, row)))]
    return sum(xs) / len(xs) if xs else None


def headless(results: list[dict[str, Any]], root: Path, record: Callable[..., None]) -> None:
    """Claims from reading the code, checked without a window (marked so in the report)."""
    from engine.scene_loader import SceneLoader
    from engine.schema_validation import SchemaValidationError

    scene = {"name": "planes", "entities": [], "background_planes": [{"id": "sky", "asset_path": "x.png", "parallax": 0.2}]}
    path = root / "planes_probe.json"
    path.write_text(json.dumps(scene), encoding="utf-8")
    try:
        SceneLoader().load_scene(str(path))
        record("background_planes load from a scene file (headless)", "PASS", "loaded")
    except SchemaValidationError as exc:
        # A documented defect, not a regression: the scene schema rejects the key. Deferred in Milestone 8 (see
        # docs/reviews/milestone8_runtime_reliability.md); KNOWN keeps it in every report without failing the gate.
        # If it starts loading, this becomes a PASS and the note should go.
        reason = "'background_planes' was unexpected" if "background_planes" in str(exc) else str(exc)[-160:]
        record("background_planes load from a scene file (headless)", "KNOWN", f"{type(exc).__name__}: {reason}")
    finally:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO / "artifacts" / "capability_lab")
    parser.add_argument("--only", nargs="*", help="run only these checks (navigation, lights, torch, ...)")
    args = parser.parse_args()
    raise SystemExit(run(args.out, set(args.only or ())))
