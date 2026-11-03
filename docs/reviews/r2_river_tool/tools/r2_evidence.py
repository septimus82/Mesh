"""R2 evidence (scratch only): Mesh Studio's River tool in real hidden windows, through Studio's own input events.

1. Lakeside (scratch copy): the bed under the footbridge already sculpted (R1's demo bed, scatter cleared), no
   river. Draw the brook with clicks, drag a point, a refused drag (mid-gesture and after), insert and remove, undo
   and redo, save, reopen in a new Studio, then Play near the bridge: screenshots at each step, the saved data.
2. Cost: dragging a point of the short Lakeside brook and of a moderately long river (~200 m) in the template
   village: per-move check and preview (ms), whole Studio frames during the drag (ms), committed save (ms), river
   buffers made and shader programs alive (before/after the drag).
"""
import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO = Path(r"D:\Games\Mesh-rivers")
M17 = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\D--Games-Mesh\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\m17")
OUT = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\D--Games-Mesh\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\river\r2_evidence")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scratch_guard import inside_scratch  # noqa: E402

OUT, M17 = inside_scratch(OUT), inside_scratch(M17)
OUT.mkdir(parents=True, exist_ok=True)
sys.path[:0] = [str(REPO), str(REPO / "tooling")]
os.environ.update({"MESH_USER_DIR": str(M17 / "user"), "MESH_PROJECTS_DIR": str(M17 / "userprojects"),
                   "APPDATA": str(M17 / "appdata"), "XDG_DATA_HOME": str(M17 / "xdg"), "MESH_STUDIO_NO_AI_BRIDGE": "1"})
import r1_river_study as r1  # noqa: E402
from hd2d_studio_demo import StudioDriver  # noqa: E402

from engine import project_ops as ops  # noqa: E402
from engine.studio_project import Project  # noqa: E402

LAKESIDE = M17 / "projects" / "lakeside"
SCENES = LAKESIDE / "packs" / "core_regions" / "scenes"
WORLD = LAKESIDE / "packs" / "core_regions" / "worlds" / "main.json"
BED = "lakeside_bed"
# the R1 demo's course (px): where the bed was flattened, under the bridge, to the lake
COURSE = [(700, 960), (800, 930), (900, 905), (990, 870), (1060, 852), (1130, 860), (1190, 890), (1250, 935)]
report: dict = {}


def make_bed() -> None:
    """lakeside_river.json less its river: the sculpted bed and cleared scatter, no water in it yet."""
    scene = json.loads((SCENES / "lakeside_river.json").read_text(encoding="utf-8"))
    scene = ops.remove_river(scene, "brook")
    (SCENES / f"{BED}.json").write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    world = json.loads(WORLD.read_text(encoding="utf-8"))
    world["scenes"][BED] = {"label": "Lakeside Bed", "path": f"packs/core_regions/scenes/{BED}.json", "tags": []}
    WORLD.write_text(json.dumps(world, indent=2) + "\n", encoding="utf-8")


def open_bed() -> StudioDriver:
    d = StudioDriver(LAKESIDE)
    d.button("Rooms")
    d.button("Lakeside Bed", prefix=True)
    d.button("Terrain")
    d.button("River")
    v = d.studio.hd2d
    v.camera.target, v.camera.distance, v.camera.pitch = (30.2, 28.0, -0.3), 30.0, 48.0
    d.advance(3)
    return d


def ground(d: StudioDriver, px: float, py: float) -> tuple:
    return (px / 32, py / 32, d.renderer.terrain.surface_at(px, py)[0] / 32)


def post(d: StudioDriver, index: int) -> tuple:
    x, y, _w, level = ops.rivers(d.studio.project.scene())[0]["points"][index]
    return d.screen((x / 32, y / 32, level / 32))


def shot(d: StudioDriver, name: str) -> None:
    d.picture(OUT / f"{name}.png")
    report.setdefault("shots", []).append({"name": name, "message": d.studio.message,
                                           "rivers": ops.rivers(d.studio.project.scene())})


def lakeside() -> None:
    make_bed()
    d = open_bed()
    k, left = d.arcade.key, d.arcade.MOUSE_BUTTON_LEFT
    try:
        shot(d, "01_river_tool_on_the_bed")
        for i, (x, y) in enumerate(COURSE):
            d.click(*d.screen(ground(d, x, y)))
            if i == 3:
                shot(d, "02_drawing_4_points_preview")
        shot(d, "03_drawn_8_points_before_enter")
        d.key(k.ENTER)
        shot(d, "04_finished_one_undo_step")
        # a drag, caught mid-gesture, then let go
        start, end = post(d, 2), d.screen(ground(d, 904, 918))
        d.window.dispatch_event("on_mouse_press", *start, left, 0)
        for i in range(1, 9):
            p = (start[0] + (end[0] - start[0]) * i / 8, start[1] + (end[1] - start[1]) * i / 8)
            d.window.dispatch_event("on_mouse_drag", *p, 0, 0, left, 0)
            d.advance()
        shot(d, "05_dragging_point_3")
        d.window.dispatch_event("on_mouse_release", *end, left, 0)
        d.advance()
        shot(d, "06_dragged_saved")
        # a refused drag: point 3 over point 1 (the course would fold back on itself)
        d.window.dispatch_event("on_mouse_press", *post(d, 2), left, 0)
        bad = d.screen(ground(d, 760, 950))
        d.window.dispatch_event("on_mouse_drag", *bad, 0, 0, left, 0)
        d.advance(2)
        shot(d, "07_refused_mid_drag_last_valid_kept_red_post")
        d.window.dispatch_event("on_mouse_release", *bad, left, 0)
        d.advance()
        shot(d, "08_refused_on_release_unchanged")
        d.click(*post(d, 4))
        d.key(k.INSERT)
        shot(d, "09_inserted_after_point_5")
        d.key(k.DELETE)
        d.key(k.Z, k.MOD_CTRL)
        shot(d, "10_undo_brings_the_inserted_point_back")
        d.key(k.Y, k.MOD_CTRL)
        shot(d, "11_redo_removes_it_again")
        d.key(k.S, k.MOD_CTRL)
        report["saved"] = ops.rivers(d.studio.project.scene())
    finally:
        d.close()
    reopened = Project(LAKESIDE, "packs/core_regions/worlds/main.json")
    report["reopened_from_disk_same"] = ops.rivers(reopened.scene(BED)) == report["saved"]
    d = open_bed()
    try:
        shot(d, "12_reopened_in_a_new_studio")
        report["reopened_shown_same"] = [[list(p) for p in r.points] for r in d.renderer.settings.rivers] == \
            [r["points"] for r in report["saved"]]
        d.key(d.arcade.key.F4)
        d.advance(30)
        game = d.window.hd2d_renderer
        player = d.game.player()  # stood beside the footbridge: the gameplay camera follows the player
        player.center_x, player.center_y = 990.0, 800.0
        d.advance(30)
        shot(d, "13_play_the_saved_river")
        report["play_rivers_same"] = [[list(p) for p in r.points] for r in game.settings.rivers] == \
            [r["points"] for r in report["saved"]]
        report["play_water_time_s"] = round(d.window.water_time, 3)
        d.key(d.arcade.key.F4)
    finally:
        d.close()


def drag_cost(d: StudioDriver, name: str, index: int, dx: float) -> dict:
    """Drag point ``index`` ``dx`` px east in 30 moves, a frame each: what it costs."""
    tool, left = d.studio.hd2d.river, d.arcade.MOUSE_BUTTON_LEFT
    pts = ops.rivers(d.studio.project.scene())[0]["points"]
    lo, hi, bottom, top = d.studio.hd2d._rect()
    centre = ((lo + hi) / 2, (bottom + top) / 2)
    if index < 0:  # the point nearest the middle of the view
        index = min(range(len(pts)), key=lambda i: sum((a - b) ** 2 for a, b in zip(
            d.screen((pts[i][0] / 32, pts[i][1] / 32, pts[i][3] / 32)), centre)))
    x, y, _w, level = pts[index]
    start = d.screen((x / 32, y / 32, level / 32))
    end = d.screen(ground(d, x + dx, y))
    water = d.renderer.water
    before = {"allocations": water.river_allocations, "programs": d.gl_counts()["program"]}
    tool.timings["check_ms"].clear()
    frames = []
    d.window.dispatch_event("on_mouse_press", *start, left, 0)
    assert tool.gesture is not None, (name, index, start, d.studio.message)
    for i in range(1, 31):
        p = (start[0] + (end[0] - start[0]) * i / 30, start[1] + (end[1] - start[1]) * i / 30)
        t = time.perf_counter()
        d.window.dispatch_event("on_mouse_drag", *p, 0, 0, left, 0)
        d.advance()
        frames.append((time.perf_counter() - t) * 1000)
    t = time.perf_counter()
    d.window.dispatch_event("on_mouse_release", *end, left, 0)
    d.advance()
    release = (time.perf_counter() - t) * 1000
    idle = []
    for _ in range(30):
        t = time.perf_counter()
        d.advance()
        idle.append((time.perf_counter() - t) * 1000)
    checks = tool.timings["check_ms"]
    from engine.hd2d.river import parse_rivers, ribbon

    length = ribbon(parse_rivers(ops.rivers(d.studio.project.scene()))[0]).length_m
    return {"river_m": round(length, 1), "moves": 30, "checks": len(checks),
            "check_ms_median": round(statistics.median(checks), 2), "check_ms_max": round(max(checks), 2),
            "drag_frame_ms_median": round(statistics.median(frames), 2), "drag_frame_ms_max": round(max(frames), 2),
            "release_commit_frame_ms": round(release, 1),
            "of_which_checked_edit_ms": round(tool.timings["commit_ms"][-1], 1), "idle_frame_ms_median": round(statistics.median(idle), 2),
            "river_buffers_made_during_drag": water.river_allocations - before["allocations"],
            "shader_programs_before_after": [before["programs"], d.gl_counts()["program"]],
            "saved_moved": ops.rivers(d.studio.project.scene())[0]["points"][index][0] != x}


def cost() -> None:
    d = open_bed()
    try:
        d.click(*d.screen(ground(d, *COURSE[0])))
        for x, y in COURSE[1:]:
            d.click(*d.screen(ground(d, x, y)))
        d.key(d.arcade.key.ENTER)
        report["cost_short_lakeside"] = drag_cost(d, "short", 2, 20)
    finally:
        d.close()
    project = r1.make_project(OUT, "long", rivers=False)
    path = project / "packs" / "core_regions" / "scenes" / "start.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    import math

    # a river snaking across the whole village and back, five runs of 28 m joined by 4 m-radius turns: ~200 m
    metres = []
    for row in range(5):
        y = 4 + 8 * row
        xs = [5 + 4 * i for i in range(8)]
        metres += [(x, y) for x in (xs if row % 2 == 0 else xs[::-1])]
        if row < 4:
            cx, sign = (33, 1) if row % 2 == 0 else (5, -1)
            metres += [(cx + sign * 4 * math.cos(a), y + 4 + 4 * math.sin(a)) for a in (-0.785, 0.0, 0.785)]
    points = [[x * 32, y * 32, 64, 8 - i * 0.1] for i, (x, y) in enumerate(metres)]
    scene = ops.add_river(scene, "long", points)
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    d = StudioDriver(project)
    try:
        d.button("Terrain")
        d.button("River")
        v = d.studio.hd2d
        v.camera.target, v.camera.distance = (20.0, 19.0, 0.0), 60.0
        d.advance(2)
        report["cost_long_village"] = drag_cost(d, "long", -1, 20)
        d.picture(OUT / "14_long_river_dragged.png")
    finally:
        d.close()


if '--cost-only' not in sys.argv:
    lakeside()
else:
    report.update(json.loads((OUT / 'report.json').read_text(encoding='utf-8')))
cost()
(OUT / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
print(json.dumps({k: v for k, v in report.items() if k not in ("shots", "saved")}, indent=1))
for s in report["shots"]:
    print(s["name"], "|", s["message"][:110])
