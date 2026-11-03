"""R3 evidence (scratch only): real 1280x720 hidden-window frames of carving, clearing, wading and deep water.

A. The R3 study village (tooling/r3_river_bed_study.py) in Mesh Studio: the stream before its bed is carved (its
   water under the ground), after Carve the bed, after Clear plants (Studio's own buttons).
B. Play there: the player halfway across the ford (wading), stopped at the deep stretch's edge, on the bridge's
   deck over the deep water.
C. Lakeside (scratch copy): R1's brook course on the room's own ground, its water under it; carved and cleared with
   the ops; Studio before/after and a gameplay frame by the footbridge.
D. Cost: carve and clear (ms), and the play frame while walking with and without the river's water underfoot.
"""
import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO = Path(r"D:\Games\Mesh-rivers")
M17 = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\D--Games-Mesh\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\m17")
OUT = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\D--Games-Mesh\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\river\r3_evidence")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scratch_guard import inside_scratch  # noqa: E402

OUT, M17 = inside_scratch(OUT), inside_scratch(M17)
OUT.mkdir(parents=True, exist_ok=True)
sys.path[:0] = [str(REPO), str(REPO / "tooling")]
os.environ.update({"MESH_USER_DIR": str(M17 / "user"), "MESH_PROJECTS_DIR": str(M17 / "userprojects"),
                   "APPDATA": str(M17 / "appdata"), "XDG_DATA_HOME": str(M17 / "xdg"), "MESH_STUDIO_NO_AI_BRIDGE": "1"})
import r3_river_bed_study as study  # noqa: E402
from hd2d_demo import SCENES, HiddenGame  # noqa: E402
from hd2d_studio_demo import StudioDriver  # noqa: E402

from engine import project_ops as ops  # noqa: E402

report: dict = {}


def shot_studio(d: StudioDriver, name: str) -> None:
    d.picture(OUT / f"{name}.png")
    report.setdefault("studio", {})[name] = d.studio.message


def village_studio() -> None:
    d = StudioDriver(study.make_project(OUT, "village"))
    try:
        d.button("Terrain")
        d.button("River")
        d.button("Select 'brook'")
        v = d.studio.hd2d
        v.camera.target, v.camera.distance = (20.0, 19.0, 0.0), 24.0
        d.advance(2)
        shot_studio(d, "A1_studio_before_carving_water_under_the_ground")
        t = time.perf_counter()
        d.button("Carve the bed")
        report["carve_click_to_reloaded_ms"] = round((time.perf_counter() - t) * 1000, 1)
        v.camera.target, v.camera.distance = (20.0, 19.0, 0.0), 24.0
        d.advance(2)
        shot_studio(d, "A2_studio_bed_carved")
        d.button("Clear plants")
        v.camera.target, v.camera.distance = (20.0, 19.0, 0.0), 24.0
        d.advance(2)
        shot_studio(d, "A3_studio_plants_cleared")
    finally:
        d.close()


def drawn_then_carved() -> None:
    """Studio's own flow: a river drawn by clicking flat ground (its water 0.25 m over the ground clicked, shown at
    once), then Carve the bed: the water lowered to just under the ground beside it, lying in its channel."""
    import r1_river_study as r1  # noqa: PLC0415

    project = r1.study.new_project(OUT, "drawn", stage6a=False)
    d = StudioDriver(project)
    try:
        d.button("Terrain")
        d.button("River")
        v = d.studio.hd2d
        v.camera.target, v.camera.distance = (11.0, 3.5, 0.0), 18.0
        d.advance(2)
        for x, y in ((5.0, 3.2), (8.5, 2.4), (12.0, 3.4), (16.0, 2.8)):
            d.click(*d.screen((x, y, 0.0)))
        d.key(d.arcade.key.ENTER)
        d.advance(2)
        shot_studio(d, "A4_studio_drawn_over_the_ground")
        report["drawn_levels_px"] = [p[3] for p in ops.rivers(d.studio.project.scene())[0]["points"]]
        d.button("Carve the bed")
        v.camera.target, v.camera.distance = (11.0, 3.5, 0.0), 18.0
        d.advance(2)
        shot_studio(d, "A5_studio_drawn_river_carved_lies_in_its_bed")
        report["carved_levels_px"] = [p[3] for p in ops.rivers(d.studio.project.scene())[0]["points"]]
    finally:
        d.close()


def village_play() -> None:
    game = HiddenGame(study.make_project(OUT, "play", carved=True), size=(1280, 720))
    left = game.arcade.key.A
    try:
        game.load(f"{SCENES}/start.json")
        game.step(3)
        frames = {"ford": (study.EAST_BANK_X, study.FORD_Y, 0.0), "deep": (study.EAST_BANK_X, study.DEEP_Y, 0.0),
                  "bridge": study.DECK}
        for name, start in frames.items():
            result = study.walk(game, start, left, 150)
            report.setdefault("walks", {})[name] = result
        # the pictures: halfway across the ford, at the deep edge, on the deck
        for name, start, n in (("B1_play_wading_the_ford", frames["ford"], 32),
                               ("B2_play_stopped_at_deep_water", frames["deep"], 150),
                               ("B3_play_on_the_bridge_over_deep_water", frames["bridge"], 40)):
            player = game.player()
            player.center_x = start[0]
            player.center_y = start[1] + (player.center_y - player.bottom)
            player.mesh_entity_data["elevation"] = start[2] * 32
            game.step(2)
            game.window.dispatch_event("on_key_press", left, 0)
            game.step(n)
            game.window.dispatch_event("on_key_release", left, 0)
            game.step(1)
            game.draw().convert("RGB").save(OUT / f"{name}.png")
            report.setdefault("pictures", {})[name] = {
                "x": round(player.center_x, 1), "elevation_m": round(player.mesh_entity_data["elevation"] / 32, 3),
                "wading": getattr(player, "mesh_hd2d_wading", None)}
        # cost: walking frames, through the river's water underfoot
        player = game.player()
        player.center_x, player.mesh_entity_data["elevation"] = study.EAST_BANK_X, 0.0
        times = []
        game.window.dispatch_event("on_key_press", game.arcade.key.W, 0)
        for _ in range(120):
            t = time.perf_counter()
            game.step(1)
            game.draw()
            times.append((time.perf_counter() - t) * 1000)
        game.window.dispatch_event("on_key_release", game.arcade.key.W, 0)
        report["play_frame_ms_with_river"] = round(statistics.median(times), 2)
    finally:
        game.close()


def lakeside() -> None:
    project = M17 / "projects" / "lakeside"
    scenes = project / "packs" / "core_regions" / "scenes"
    world_path = project / "packs" / "core_regions" / "worlds" / "main.json"
    scene = json.loads((scenes / "lakeside.json").read_text(encoding="utf-8"))
    arm = next(e for e in scene["entities"] if e.get("name") == "Puddle 2")
    scene = ops.remove_entity(scene, arm["id"])
    points = [[700, 960, 56, -4.0], [800, 930, 60, -5.0], [900, 905, 64, -6.0], [990, 870, 66, -7.5],
              [1060, 852, 68, -9.0], [1130, 860, 70, -10.5], [1190, 890, 74, -12.0], [1250, 935, 84, -13.25]]
    scene = ops.add_river(scene, "brook", points)
    before = scene
    t = time.perf_counter()
    carved = ops.carve_river_bed(before, "brook")
    report["lakeside_carve_ms"] = round((time.perf_counter() - t) * 1000, 1)
    t = time.perf_counter()
    try:
        cleared = ops.clear_scatter_in_rivers(carved, "brook")
    except ops.OpError as err:
        cleared, report["lakeside_clear"] = carved, str(err)
    report["lakeside_clear_ms"] = round((time.perf_counter() - t) * 1000, 1)
    for name, sc in (("lakeside_r3_before", before), ("lakeside_r3_carved", cleared)):
        (scenes / f"{name}.json").write_text(json.dumps(sc, indent=2) + "\n", encoding="utf-8")
    world = json.loads(world_path.read_text(encoding="utf-8"))
    for name, label in (("lakeside_r3_before", "Lakeside R3 Before"), ("lakeside_r3_carved", "Lakeside R3 Carved")):
        world["scenes"][name] = {"label": label, "path": f"packs/core_regions/scenes/{name}.json", "tags": []}
    world_path.write_text(json.dumps(world, indent=2) + "\n", encoding="utf-8")
    for name, label in (("C1_lakeside_studio_before_carving", "Lakeside R3 Before"),
                        ("C2_lakeside_studio_carved_and_cleared", "Lakeside R3 Carved")):
        d = StudioDriver(project)
        try:
            d.button("Rooms")
            d.button(label, prefix=True)
            v = d.studio.hd2d
            v.camera.target, v.camera.distance, v.camera.pitch = (30.2, 28.0, -0.3), 30.0, 48.0
            d.advance(3)
            d.picture(OUT / f"{name}.png")
        finally:
            d.close()
    game = HiddenGame(project, size=(1280, 720))
    try:
        game.load("packs/core_regions/scenes/lakeside_r3_carved.json")
        game.step(3)
        player = game.player()
        player.center_x, player.center_y = 990.0, 800.0
        game.step(30)
        game.draw().convert("RGB").save(OUT / "C3_lakeside_play_by_the_bridge.png")
        # wading in the brook's shallows near its bank, then trying its middle
        result = study.walk(game, (900.0, 870.0, 0.0), game.arcade.key.W, 60)
        report["lakeside_walk_north_into_the_brook"] = result
        game.draw().convert("RGB").save(OUT / "C4_lakeside_play_wading_the_brook.png")
    finally:
        game.close()


village_studio()
drawn_then_carved()
village_play()
lakeside()
(OUT / "report.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
print(json.dumps(report, indent=1, default=str))
