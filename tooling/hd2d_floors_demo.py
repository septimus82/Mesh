"""The developer-only HD-2D floors scene (Milestone 16 Stage 3) and its checks, in a hidden window.

    py -3.13 tooling/hd2d_floors_demo.py build PROJECT_DIR         # a blank-template project, start room = the crossing
    py -3.13 tooling/hd2d_floors_demo.py check PROJECT_DIR OUT_DIR  # both routes with real key events; pictures + JSON

``build`` makes an ordinary Mesh project (the blank template: its player, animation and controls) whose start room is
the stone crossing (``tooling/hd2d_assets/stone_crossing.glb``, built by ``build_crossing.py`` with its collision
authored in Blender): ground, two platforms 2 m up with a staircase each, a railed bridge between them over an open
underpass, and a hut. A warden (the template's person) walks with ``FloorRoute`` from the east platform down its stairs, under the
bridge and back. Lit (Stage 4) by a sun, the sky's ambient tint and two lamps, from the scene's ordinary
``lights``. Not a template.

``check`` drives the player only by holding arrow keys (key press / release events into the hidden window, as the
OS would send them) until a spot is reached or the player is blocked: never by setting positions. It records each
leg's position, elevation, floor, animation, the camera, and how much of the player is visible; tries the walls,
ledges and railings; saves and loads on the bridge and under it; and follows the warden. Set MESH_USER_DIR /
MESH_PROJECTS_DIR to keep runs out of the owner's recent-projects list.
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
from hd2d_demo import SCENES, HiddenGame, _total_pixels  # noqa: E402  # the Stage 2 hidden-window harness

ASSETS = REPO / "tooling" / "hd2d_assets"
LAB = REPO / "tooling" / "hd2d_lab" / "assets"
CENTRE = (512.0, 384.0)  # the crossing's origin on the 32 x 24 map (px): 16 m, 12 m
WIDTH, HEIGHT = 32, 24
PX = 32.0


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def build(project: Path) -> Path:
    from engine.project_scaffold import create_project

    if project.exists():
        raise SystemExit(f"{project} exists; pick a new folder (this never overwrites)")
    create_project(project, "HD-2D floors", "blank")
    (project / "assets/models").mkdir(parents=True)
    (project / "assets/textures").mkdir(parents=True)
    shutil.copy2(ASSETS / "stone_crossing.glb", project / "assets/models/stone_crossing.glb")
    shutil.copy2(LAB / "grass.png", project / "assets/textures/grass.png")
    start = project / SCENES / "start.json"
    scene = json.loads(start.read_text(encoding="utf-8"))
    scene["name"] = "HD-2D Crossing"
    tm = scene["tilemap"]
    tm["width"], tm["height"] = WIDTH, HEIGHT
    for layer in tm["tile_layers"]:  # all ground: the crossing's collision comes from its GLB, not tiles
        layer["tiles"] = [1 if layer["id"] == "ground" else 0] * (WIDTH * HEIGHT)
    scene.setdefault("settings", {}).update({
        "world_width": WIDTH * 32, "world_height": HEIGHT * 32,
        "hd2d": {
            "structures": [{"id": "crossing", "model": "assets/models/stone_crossing.glb", "x": CENTRE[0], "y": CENTRE[1]}],
            "ground": {"texture": "assets/textures/grass.png", "from": [0, 0], "to": [WIDTH * 32, HEIGHT * 32]},
            "camera": {"pitch": 32, "fov": 30, "distance": 15, "follow": "player"},
            # Stage 4: a warm sun from the north-east (shadows fall towards the camera), a dim bluish sky light
            "sun": {"direction": [0.35, 0.5, 0.79], "color": "#fff0d8", "intensity": 1.0}, "ambient": 0.35,
        },
        "lighting_shadow_softness": "soft",
    })
    # The room's ordinary lights (as a 2D room has them; HD-2D adds their height): the sky's tint, a warm lamp at
    # the foot of the west stairs, and a blue lamp on the east platform whose light the hut blocks.
    scene["lights"] = [
        {"id": "sky", "type": "ambient", "color": "#8a96c8", "mode": "soft"},
        {"id": "stairs_lamp", "x": 288.0, "y": 128.0, "elevation": 48.0, "radius": 224.0, "color": "#ffb060",
         "intensity": 1.6, "mode": "soft"},
        {"id": "hut_lamp", "x": 624.0, "y": 432.0, "elevation": 102.4, "radius": 224.0, "color": "#5a8cff",
         "intensity": 1.8, "mode": "soft"},
    ]
    # Positions are sprite centres; a 48 px character's feet (its movement box) are 18 px below its centre.
    scene["entities"] = [
        {"id": "start_player_128_128_0_0", "prefab_id": "player", "x": 512.0, "y": 96.0 + 18.0},
        {"id": "warden", "prefab_id": "person", "mesh_name": "Warden", "x": 784.0, "y": 336.0 + 18.0, "elevation": 64.0,
         "behaviours": ["Dialogue", "Animator", "FloorRoute"],
         # feet points: on the east platform (2 m up), then on the ground south of its stairs
         "behaviour_config": {"FloorRoute": {"route": [[704.0, 96.0, 0.0], [512.0, 384.0, 0.0],
                                                                       [784.0, 336.0, 64.0]], "speed": 70.0,
                                             "wait": 0.5}}},
    ]
    _write(start, scene)
    return project


def _feet(sprite: Any) -> tuple[float, float]:
    from engine.physics_runtime import _sprite_to_aabb

    box = _sprite_to_aabb(sprite)
    return box.x / PX, box.y / PX


def hold_key(game: Any, player: Any, key: int, axis: int, target: float, max_frames: int = 900,
             each_frame: Any = None) -> bool:
    """Hold ``key`` (press and release events, as the OS sends them) until the player's feet reach ``target`` (m) on
    ``axis``, or it stops moving (blocked). True if reached."""
    keys = game.arcade.key
    sign = 1 if key in (keys.RIGHT, keys.UP) else -1
    game.window.dispatch_event("on_key_press", key, 0)
    reached, stalled = False, 0
    for _ in range(max_frames):
        before = _feet(player)[axis]
        if (before - target) * sign >= 0:
            reached = True
            break
        game.step(1)
        if each_frame is not None:
            each_frame()
        stalled = stalled + 1 if abs(_feet(player)[axis] - before) < 1e-4 else 0
        if stalled > 12:
            break
    game.window.dispatch_event("on_key_release", key, 0)
    game.step(2)
    return reached


def check(project: Path, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    game = HiddenGame(project)
    keys = game.arcade.key
    report: dict[str, Any] = {"legs": [], "blocked": {}}
    camera_z: list[float] = []
    clips: set[str] = set()
    move_times: list[float] = []
    try:
        t0 = time.perf_counter()
        game.load(f"{SCENES}/start.json")
        report["load_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        world, hd = game.window.hd2d_world, game.window.hd2d_renderer
        report["world"] = {"surfaces": len(world.surfaces), "walls": len(world.walls),
                           "floors": sorted({s.floor for s in world.surfaces})}
        original_move = world.move

        def timed_move(*args: Any, **kwargs: Any) -> None:
            t = time.perf_counter()
            original_move(*args, **kwargs)
            move_times.append((time.perf_counter() - t) * 1e6)

        world.move = timed_move  # measure the height-aware move (player and warden)
        game.step(60)
        player = game.player()

        def state(label: str, picture: str | None = None) -> dict[str, Any]:
            fx, fy = _feet(player)
            entry = {"after": label, "feet_m": [round(fx, 2), round(fy, 2)],
                     "elevation_m": round(player.mesh_entity_data.get("elevation", 0.0) / PX, 3),
                     "floor": getattr(player, "mesh_hd2d_floor", None),
                     "camera_target_z": round(hd.camera.target[2], 3),
                     "visible_px": hd.visible_pixels(player), "total_px": _total_pixels(hd, player)}
            if picture:
                game.draw().convert("RGB").save(out / picture)
                entry["picture"] = picture
            report["legs"].append(entry)
            return entry

        def each_frame() -> None:
            camera_z.append(hd.camera.target[2])
            clips.add(_clip(player) or "")

        def drive(key: int, axis: int, target: float, max_frames: int = 900) -> bool:
            return hold_key(game, player, key, axis, target, max_frames, each_frame)

        state("start: on the ground", "01_ground.png")
        # -- the upper route: ground -> west stairs -> west platform -> bridge -> east platform -> east stairs -> ground
        drive(keys.LEFT, 0, 10.0)
        state("west to the foot of the west stairs")
        drive(keys.UP, 1, 6.5)
        state("half way up the west stairs", "02_stairs.png")
        drive(keys.UP, 1, 11.5)
        state("on the west platform", "03_platform.png")
        drive(keys.RIGHT, 0, 16.0)
        state("mid-bridge", "04_bridge.png")
        report["blocked"]["railing"] = not drive(keys.UP, 1, 13.5, 120)
        state("pushed north on the bridge (railing)")
        drive(keys.DOWN, 1, 11.5)
        drive(keys.RIGHT, 0, 22.0)
        state("on the east platform", "05_east_platform.png")
        report["blocked"]["platform_edge"] = not drive(keys.RIGHT, 0, 27.0, 200)
        state("pushed east off the platform (edge)")
        drive(keys.LEFT, 0, 22.0)
        drive(keys.DOWN, 1, 3.0)
        state("down the east stairs: on the ground", "06_descended.png")
        # -- the lower route: under the same bridge
        drive(keys.LEFT, 0, 16.0)
        drive(keys.UP, 1, 12.0)
        state("under the bridge", "07_under_bridge.png")
        report["blocked"]["platform_side"] = not drive(keys.RIGHT, 0, 21.0, 200)
        state("under the bridge, pushed east into the east platform's side")
        drive(keys.LEFT, 0, 16.0)
        drive(keys.UP, 1, 18.0)
        state("north of the bridge, through the underpass", "08_north.png")
        report["animation_clips_seen"] = sorted(c for c in clips if c)  # while the keys were held
        steps = [abs(b - a) for a, b in zip(camera_z, camera_z[1:])]  # walking only (a load re-centres the camera)
        report["camera"] = {"frames": len(camera_z), "z_min": round(min(camera_z), 3), "z_max": round(max(camera_z), 3),
                            "largest_frame_step": round(max(steps), 4)}
        # -- save and load, on the bridge and under it
        saves = game.window.save_manager
        drive(keys.LEFT, 0, 16.0)
        drive(keys.DOWN, 1, 12.0)
        under = state("back under the bridge: save 'under'")
        report["saved_under"] = saves.save_game("hd2d_under")
        drive(keys.DOWN, 1, 3.0)
        drive(keys.LEFT, 0, 10.0)
        drive(keys.UP, 1, 11.5)
        drive(keys.RIGHT, 0, 16.0)
        on = state("on the bridge again: save 'bridge'")
        report["saved_bridge"] = saves.save_game("hd2d_bridge")
        report["loads"] = {}
        for slot, expected in (("hd2d_under", under), ("hd2d_bridge", on)):
            drive(keys.RIGHT, 0, 18.5)  # move away first
            ok = saves.load_game(slot)
            game.step(20)
            player, world, hd = game.player(), game.window.hd2d_world, game.window.hd2d_renderer
            after = state(f"loaded '{slot}'", f"09_loaded_{slot}.png")
            report["loads"][slot] = {"ok": ok, "expected": [expected["feet_m"], expected["elevation_m"], expected["floor"]],
                                     "got": [after["feet_m"], after["elevation_m"], after["floor"]]}
        # -- the warden: walks platform <-> ground by the stairs (FloorRoute over the navigation grid)
        warden = game.sprite("Warden")
        track = []
        valid, pictured = True, False
        for frame in range(60 * 30):
            game.step(1)
            fx, fy = _feet(warden)
            z = warden.mesh_entity_data.get("elevation", 0.0) / PX
            track.append((round(fx, 2), round(fy, 2), round(z, 3)))
            from engine.physics_runtime import _sprite_to_aabb

            box = _sprite_to_aabb(warden)
            if world.stand(fx, fy, z, box.w / 2 / PX, box.h / 2 / PX) is None:
                valid = False
            if 0.6 < z < 1.4 and not pictured:
                pictured = True
                hd.camera.target = (fx, fy, z + 0.8)  # for this picture only: look at the warden (it re-follows)
                game.draw().convert("RGB").save(out / "10_warden_on_stairs.png")
        zs = [t[2] for t in track]
        report["warden"] = {"frames": len(track), "elevation_min": min(zs), "elevation_max": max(zs),
                            "trips_down": sum(1 for a, b in zip(zs, zs[1:]) if a > 0.05 >= b),
                            "trips_up": sum(1 for a, b in zip(zs, zs[1:]) if a < 1.95 <= b),
                            "always_standable": valid, "track_every_30": track[::30]}
        # -- performance: the move, the navigation grid, a frame
        t = time.perf_counter()
        world._nav = None
        world._nav_grid()
        nav_ms = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        route = world.path((16.0, 3.0, 0.0), (24.0, 11.0, 2.0))
        path_ms = (time.perf_counter() - t) * 1000
        frames = []
        for _ in range(120):
            t = time.perf_counter()
            game.window.dispatch_event("on_update", 1 / 60)
            game.window.dispatch_event("on_draw")
            game.window.ctx.finish()
            frames.append((time.perf_counter() - t) * 1000)
        report["performance"] = {
            "move_us_median": round(statistics.median(move_times), 1), "move_us_p95": round(sorted(move_times)[int(len(move_times) * 0.95)], 1),
            "moves_measured": len(move_times), "nav_grid_ms": round(nav_ms, 1), "nav_cells": len(world._nav or {}),
            "path_ms": round(path_ms, 2), "path_waypoints": len(route),
            "frame_ms_median": round(statistics.median(frames), 2), "frame_ms_p95": round(sorted(frames)[int(len(frames) * 0.95)], 2),
            "renderer": hd.stats()}
    finally:
        game.close()
    _write(out / "check.json", report)
    return report


def _clip(sprite: Any) -> str | None:
    clips = [getattr(b, "_current_clip_name", None) for b in getattr(sprite, "mesh_behaviours_runtime", None) or []]
    return next((c for c in clips if c), None)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["build", "check"])
    parser.add_argument("project", type=Path)
    parser.add_argument("out", type=Path, nargs="?")
    args = parser.parse_args()
    if args.command == "build":
        print(build(args.project.resolve()))
    else:
        if args.out is None:
            parser.error("check needs OUT_DIR")
        print(json.dumps(check(args.project.resolve(), args.out.resolve()), indent=1, default=str))
