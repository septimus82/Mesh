"""Milestone 22A.1: a flat HD-2D room's ground expanded in Mesh Studio, checked in hidden windows.

    py -3.13 tooling/hd2d_room_expand_studio.py studio OUT        a fresh starter project: + New room > HD-2D 40 x 30 m,
                                                                a cottage and a villager put in it; Camera and sun...
                                                                > Room size 48 x 36 > Expand room; undo / redo;
                                                                Save, reopen; walked east in the game
    py -3.13 tooling/hd2d_room_expand_studio.py lakeside OUT LAKE  a copy of Lakeside Village (LAKE: only read): its
                                                                Village (45 structures, 8 objects) expanded 40 x 44 ->
                                                                48 x 52 m; refusals (shrinking, the sculpted Lakeside,
                                                                the Cottage with no ground); Save, reopen, Play; walked
                                                                east in the game, against an unexpanded copy; export

Everything in Studio is done with its own input events (clicks, typing), never by writing room files. Nothing is played
aloud (the projects' master volume is 0); the player's settings file is OUT's own."""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(1, str(REPO / "tooling"))
from hd2d_room_studio import SCENES, _hd2d, _left, _press, _right, _silent, _write  # noqa: E402

MAPS = "packs/core_regions/maps"


def _content(scene: dict[str, Any]) -> dict[str, Any]:
    """The room without what expanding changes (its size): everything that must stay as it was."""
    out = copy.deepcopy(scene)
    out.pop("tilemap", None)
    settings = out.get("settings") or {}
    for key in ("world_width", "world_height"):
        settings.pop(key, None)
    hd2d = settings.get("hd2d") or {}
    (hd2d.get("ground") or {}).pop("to", None)
    (hd2d.get("camera") or {}).pop("bounds", None)
    return out


def _sizes(project: Path, room: str) -> dict[str, Any]:
    scene = json.loads((project / SCENES / f"{room}.json").read_text(encoding="utf-8"))
    map_file = json.loads((project / MAPS / f"{room}.json").read_text(encoding="utf-8"))
    hd2d = scene["settings"]["hd2d"]
    return {"ground_to": hd2d["ground"]["to"], "bounds": hd2d["camera"].get("bounds"),
            "world": [scene["settings"]["world_width"], scene["settings"]["world_height"]],
            "tilemap": [scene["tilemap"]["width"], scene["tilemap"]["height"]],
            "map_file": [map_file["width"], map_file["height"]],
            "map_file_layers": sorted({(la["width"], la["height"], len(la["data"])) for la in map_file["layers"]})}


def _expand(d: Any, width: int, depth: int) -> str:
    d.type_into("grow_width", str(width))
    d.type_into("grow_depth", str(depth))
    _press(d, "Expand room", _right)
    d.frame(3)
    return str(d.studio.message)


def _labels(d: Any) -> list[str]:
    return [str(t) for t in d.labels() if "m (1 m is a tile)" in str(t) or "can't be expanded" in str(t)]


def walk_east(project: Path, room: str, *, start_x: float, frames: int = 300) -> dict[str, Any]:
    """The game itself (not Studio): the player put at ``start_x`` on a lane clear of structures, holding Right."""
    from hd2d_demo import HiddenGame

    from engine.hd2d.settings import PIXELS_PER_METRE
    from engine.physics_runtime import _sprite_to_aabb

    game = HiddenGame(project)
    try:
        game.load(f"{SCENES}/{room}.json")
        game.step(10)
        window, player = game.window, game.player()
        world = window.hd2d_world
        box = _sprite_to_aabb(player)
        hw, hh = box.w / 2 / PIXELS_PER_METRE, box.h / 2 / PIXELS_PER_METRE
        depth_px = float(window.hd2d_renderer.settings.ground.hi[1])
        lane = None
        for y in range(96, int(depth_px) - 96, 16):  # the first lane where every step east of start_x can be stood on
            if world is None or all(world.stand(x / PIXELS_PER_METRE, y / PIXELS_PER_METRE, 0.0, hw, hh) is not None
                                    for x in range(int(start_x), int(start_x) + 64, 8)):
                lane = y
                break
        assert lane is not None, "a clear lane east"
        player.center_x, player.center_y = start_x, lane + (player.center_y - box.y)
        game.step(2)
        game.hold(game.arcade.key.RIGHT, frames)
        r = window.hd2d_renderer
        return {"world_bounds_walking": world is not None, "lane_y": lane, "start_x": start_x,
                "end_x": round(_sprite_to_aabb(player).x, 1), "half_width": round(box.w / 2, 1),
                "ground_east_edge": float(r.settings.ground.hi[0]), "tilemap_size": list(window.scene_controller.tilemap_instance.map_size),
                "camera_bounds": list(r.settings.camera.bounds) if r.settings.camera.bounds else None,
                "camera_target_x": round(r.camera.target[0] * PIXELS_PER_METRE, 1)}
    finally:
        game.close()


def studio(out: Path) -> dict[str, Any]:
    """A fresh starter project's HD-2D room, with a cottage and a villager in it, expanded in Studio."""
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops

    pics = out / "pictures"
    pics.mkdir(exist_ok=True)
    project = out / "game"
    if project.exists():
        shutil.rmtree(project)
    made = subprocess.run([sys.executable, "-m", "mesh_cli", "new", "game", "--dest", str(out), "--template", "starter"],
                          cwd=REPO, capture_output=True, text=True, timeout=600)
    assert made.returncode == 0, made.stdout + made.stderr
    _silent(project)
    report: dict[str, Any] = {}
    d = StudioDriver(project)
    try:
        _press(d, "+ New room", _left)
        d.type_into("room_name", "Meadow")
        _press(d, "HD-2D (3D)", _right)
        d.type_into("room_width", "40")
        d.type_into("room_depth", "30")
        _press(d, "Create", _right)
        d.frame(5)
        d.studio._edit(lambda s: ops.place_structure(s, "assets/models/cottage.glb", 1000.0, 600.0)[0], "A cottage.")  # (Studio's
        d.studio._edit(lambda s: ops.paste_entity(s, "meadow", {"name": "Villager"}, 1150.0, 820.0)[0], "A villager.")
        _press(d, "Save")  # own edit path: its Models browser and Objects list are M20/M21's, checked there)
        before = d.studio.project.scene()
        _press(d, "Camera and sun...", _left)
        report["panel_before"] = _labels(d)
        report["expanded_message"] = _expand(d, 48, 36)
        after = d.studio.project.scene()
        report["content_kept"] = _content(after) == _content(before)
        report["panel_after"] = _labels(d)
        report["map_file_before_save"] = _sizes(project, "meadow")["map_file"]
        _press(d, "Undo")
        report["undone"] = ops.hd2d_room_size(d.studio.project.scene())
        _press(d, "Redo")
        report["redone"] = ops.hd2d_room_size(d.studio.project.scene())
        d.picture(pics / "01_expanded_48x36.png")
        _press(d, "Save")
        report["saved"] = d.studio.message
    finally:
        d.close()
    report["on_disk"] = _sizes(project, "meadow")
    d = StudioDriver(project)
    try:
        _press(d, "Meadow", _left)
        report["reopened"] = {"size": ops.hd2d_room_size(d.studio.project.scene()), "unsaved": sorted(d.studio.project.dirty)}
    finally:
        d.close()
    report["walk"] = walk_east(project, "meadow", start_x=1200.0)
    return report


def lakeside(out: Path, original: str) -> dict[str, Any]:
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops

    pics = out / "pictures"
    pics.mkdir(exist_ok=True)
    project, control = out / "lake", out / "lake_unexpanded"
    for target in (project, control):
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(original, target, ignore=shutil.ignore_patterns("saves", "artifacts", ".mesh", "*.bak"))
        _silent(target)
    report: dict[str, Any] = {}
    d = StudioDriver(project)
    try:
        _press(d, "Village", _left)
        before = d.studio.project.scene()
        report["village_before"] = {"structures": len(_hd2d(d).get("structures") or []),
                                    "objects": len(before.get("entities") or []), "lights": len(before.get("lights") or []),
                                    "size": ops.hd2d_room_size(before)}
        _press(d, "Camera and sun...", _left)
        report["panel_before"] = _labels(d)
        report["shrink_refused"] = _expand(d, 40, 40)
        report["unchanged_after_refusal"] = d.studio.project.scene() == before
        report["expanded_message"] = _expand(d, 48, 52)
        after = d.studio.project.scene()
        report["content_kept"] = _content(after) == _content(before)
        report["panel_after"] = _labels(d)
        d.picture(pics / "02_lakeside_village_expanded.png")
        _press(d, "Undo")
        report["undone_equal_before"] = d.studio.project.scene() == before
        _press(d, "Redo")
        report["redone_equal_after"] = d.studio.project.scene() == after
        for room in ("Lakeside", "Cottage"):  # sculpted ground; a room with no ground of its own
            _press(d, room, _left)
            if d.studio.panel != "environment":
                _press(d, "Camera and sun...", _left)
            report[f"{room.lower()}_panel"] = _labels(d)
            report[f"{room.lower()}_has_expand"] = d.has_button("Expand room")
        _press(d, "Save")
        report["saved"] = d.studio.message
    finally:
        d.close()
    report["on_disk"] = _sizes(project, "start")
    d = StudioDriver(project)
    try:
        report["reopened"] = {"size": ops.hd2d_room_size(d.studio.project.scene()), "unsaved": sorted(d.studio.project.dirty),
                              "same_content": _content(d.studio.project.scene()) == _content(after)}
        k = d.arcade.key
        d.key(k.F4)
        d.frame(30)
        r = d.window.hd2d_renderer
        report["studio_play"] = {"mode": d.studio.mode, "ground_hi": list(r.settings.ground.hi),
                                 "bounds": list(r.settings.camera.bounds or ()),
                                 "tilemap_size": list(d.window.scene_controller.tilemap_instance.map_size)}
        d.picture(pics / "03_lakeside_village_play.png")
        d.key(k.F4)
        d.frame(3)
    finally:
        d.close()
    report["walk_unexpanded"] = walk_east(control, "start", start_x=1200.0)
    report["walk_expanded"] = walk_east(project, "start", start_x=1200.0)
    report["export"] = _export(project, out)
    return report


def _export(project: Path, out: Path) -> dict[str, Any]:
    bundle = out / "export"
    if bundle.exists():
        shutil.rmtree(bundle)
    built = subprocess.run([sys.executable, "-m", "mesh_cli", "export", "build", "--out", str(bundle)], cwd=project,
                           capture_output=True, text=True, timeout=900, env={**os.environ, "PYTHONPATH": str(REPO)})
    code = f"""
import json, sys
sys.path.insert(0, {str(bundle)!r})
import engine
sys.path.insert(1, {str(REPO / "tooling")!r})
from pathlib import Path
import hd2d_room_expand_studio as t
print(json.dumps({{"engine_from": engine.__file__, **t.walk_east(Path({str(bundle)!r}), "start", start_x=1200.0)}}))
"""
    ran = subprocess.run([sys.executable, "-c", code], cwd=bundle, capture_output=True, text=True, timeout=900,
                         env={k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "MESH_REPO_ROOT")})
    try:
        run = json.loads(ran.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        run = {"failed": ran.stdout[-600:] + ran.stderr[-1500:]}
    return {"code": built.returncode, "bundle_sizes": _sizes(bundle, "start"), "bundle_walk": run}


def main() -> None:
    phase, out = sys.argv[1], Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")  # never a checkout's own file
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    report = {"studio": lambda: studio(out), "lakeside": lambda: lakeside(out, sys.argv[3])}[phase]()
    _write(out / f"{phase}.json", report)
    print(json.dumps(report, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
