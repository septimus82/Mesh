"""R4 evidence (scratch only): real 1280x720 hidden-window frames of the Lakeside brook entering the lake, its free
upstream end and its shoreline, with the same cameras before (f552d6f: R3) and after (R4A).

    python r4_evidence.py before|after

A fresh scratch copy of D:\\Games\\Lakeside Village (read only) per phase; the narrow lake arm ("Puddle 2") removed,
the brook added ending inside the lake at its level, its bed carved and its plants cleared with the ops, as Studio's
buttons do. After: the same course with ``mouth: "auto"`` and ``ends: "round_source"``.
"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

PHASE = sys.argv[1]
assert PHASE in ("before", "after"), PHASE
REPO = Path(r"D:\Games\Mesh-rivers")
LAKESIDE = Path(r"D:\Games\Lakeside Village")
HERE = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\river4")
sys.path.insert(0, str(HERE))
from scratch_guard import inside_scratch  # noqa: E402

ROOT = inside_scratch(HERE / PHASE)
OUT = inside_scratch(ROOT / "frames")
PROJECT = inside_scratch(ROOT / "lakeside")
if PROJECT.exists():
    shutil.rmtree(inside_scratch(PROJECT))  # (this script's own copy from an earlier run)
OUT.mkdir(parents=True, exist_ok=True)
shutil.copytree(LAKESIDE, PROJECT, ignore=shutil.ignore_patterns("saves", "artifacts"))
sys.path[:0] = [str(REPO), str(REPO / "tooling")]
os.environ.update({"MESH_USER_DIR": str(ROOT / "user"), "MESH_PROJECTS_DIR": str(ROOT / "userprojects"),
                   "APPDATA": str(ROOT / "appdata"), "XDG_DATA_HOME": str(ROOT / "xdg"),
                   "MESH_STUDIO_NO_AI_BRIDGE": "1"})
from hd2d_demo import HiddenGame  # noqa: E402
from hd2d_studio_demo import StudioDriver  # noqa: E402

from engine import project_ops as ops  # noqa: E402

COURSE = [[700, 960, 56, -4.0], [800, 930, 60, -5.0], [900, 905, 64, -6.0], [990, 870, 66, -7.5],
          [1060, 852, 68, -9.0], [1130, 860, 70, -10.5], [1190, 890, 74, -12.0], [1250, 935, 84, -13.25]]
# cameras (target m, distance m, pitch deg): the same before and after
CAMERAS = {
    "mouth_top_down": ((37.6, 29.0, -0.4), 14.0, 89.0),
    "mouth_angled": ((37.6, 29.0, -0.4), 16.0, 40.0),
    "source_end_top_down": ((22.0, 30.0, 0.0), 9.0, 89.0),
    "brook_overview": ((31.0, 28.5, -0.3), 30.0, 48.0),
}
report: dict = {"phase": PHASE}


def make_scene() -> None:
    scenes = PROJECT / "packs" / "core_regions" / "scenes"
    world_path = PROJECT / "packs" / "core_regions" / "worlds" / "main.json"
    scene = json.loads((scenes / "lakeside.json").read_text(encoding="utf-8"))
    arm = next(e for e in scene["entities"] if e.get("name") == "Puddle 2")
    scene = ops.remove_entity(scene, arm["id"])
    scene = ops.add_river(scene, "brook", COURSE)
    if PHASE == "after":
        scene = ops.set_river(scene, "brook", mouth="auto", ends="round_source")
    t = time.perf_counter()
    scene = ops.carve_river_bed(scene, "brook")
    report["carve_ms"] = round((time.perf_counter() - t) * 1000, 1)
    try:
        scene = ops.clear_scatter_in_rivers(scene, "brook")
    except ops.OpError as err:
        report["clear"] = str(err)
    report["brook"] = next(r for r in scene["settings"]["hd2d"]["rivers"] if r["id"] == "brook")
    (scenes / "lakeside_r4.json").write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    world = json.loads(world_path.read_text(encoding="utf-8"))
    world["scenes"]["lakeside_r4"] = {"label": "Lakeside R4", "path": "packs/core_regions/scenes/lakeside_r4.json",
                                      "tags": []}
    world_path.write_text(json.dumps(world, indent=2) + "\n", encoding="utf-8")


def studio() -> None:
    d = StudioDriver(PROJECT)
    try:
        d.button("Rooms")
        d.button("Lakeside R4", prefix=True)
        v = d.studio.hd2d
        for name, (target, distance, pitch) in CAMERAS.items():
            v.camera.target, v.camera.distance, v.camera.pitch = target, distance, pitch
            d.advance(3)
            d.picture(OUT / f"studio_{name}.png")
        # the flow into the lake: three frames 0.5 s apart, the same camera (time advanced by Studio's own clock)
        target, distance, pitch = CAMERAS["mouth_angled"]
        v.camera.target, v.camera.distance, v.camera.pitch = target, distance, pitch
        d.advance(3)
        from PIL import Image
        vx, vy, vw, vh = v.viewport()
        for i in range(3):  # the renderer itself, the camera held exactly, the water's clock half a second on each
            d.window.water_time = 20.0 + 0.5 * i
            data = bytes(d.renderer.draw(camera=v.camera, viewport=v.viewport(), read=True))
            Image.frombytes("RGB", (vw, vh), data).transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(
                OUT / f"studio_mouth_flow_{i}.png")
    finally:
        d.close()


def play() -> None:
    game = HiddenGame(PROJECT, size=(1280, 720))
    try:
        game.load("packs/core_regions/scenes/lakeside_r4.json")
        game.step(3)
        player = game.player()
        player.center_x, player.center_y = 1175.0, 830.0  # on the bank above the mouth
        player.mesh_entity_data["elevation"] = 0.0
        game.step(30)
        game.draw().convert("RGB").save(OUT / "play_mouth_gameplay_camera.png")
        frames = []
        for _ in range(60):
            t = time.perf_counter()
            game.step(1)
            game.draw()
            frames.append((time.perf_counter() - t) * 1000)
        report["play_frame_ms_median"] = round(sorted(frames)[len(frames) // 2], 2)
    finally:
        game.close()


make_scene()
studio()
play()
(OUT / "report.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
print(json.dumps({k: v for k, v in report.items() if k != "brook"}, indent=1, default=str))
