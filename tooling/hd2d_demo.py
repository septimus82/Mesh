"""The developer-only HD-2D test scene (Milestone 16 Stage 2), and its checks, in a hidden window.

    py -3.13 tooling/hd2d_demo.py build PROJECT_DIR        # a blank-template project with the HD-2D rooms
    py -3.13 tooling/hd2d_demo.py check PROJECT_DIR OUT_DIR  # walk the player with real key events; pictures + JSON
    py -3.13 tooling/hd2d_demo.py bench PROJECT_DIR OUT_DIR  # the village: batched vs unbatched

``build`` makes an ordinary Mesh project (the blank template: its player, animation and controls) and turns its start
room into an HD-2D one: the Stage 1 stone outpost (a GLB) on pixel-textured grass, a person standing on the raised
platform, and wall tiles under the building so the ordinary 2D movement collision walks the player around it. It
also adds ``village.json``: the outpost repeated as separate buildings, for the batching benchmark. Not a template.

``check`` and ``bench`` never show a window or touch the mouse or keyboard: the game's window is created hidden and
key presses are dispatched to it as events. Set MESH_USER_DIR / MESH_PROJECTS_DIR to keep runs out of the owner's
recent-projects list.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
LAB = REPO / "tooling" / "hd2d_lab" / "assets"
SCENES = "packs/core_regions/scenes"
OUTPOST = (384.0, 256.0)  # the outpost's centre on the 24 x 16 map (px)
TILE = 32
# The outpost's pieces in its own space (metres, from tooling/hd2d_lab/blender_build.py): the platform and the
# steps are what the player walks around (no height physics in Stage 2: the steps are not climbable).
SOLID_BOXES_M = [(-2.0, -1.0, 2.0, 2.0), (-0.6, -2.2, 0.6, -1.0)]
PLATFORM_TOP_PX = 32.0  # 1 m


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _paint_walls(scene: dict, centres: list[tuple[float, float]]) -> None:
    tm = scene["tilemap"]
    width, height = tm["width"], tm["height"]
    walls = next(layer for layer in tm["tile_layers"] if layer["id"] == tm["collision_layer_id"])
    for cx, cy in centres:
        for x0, y0, x1, y1 in SOLID_BOXES_M:
            for col in range(width):
                for row in range(height):
                    tx, ty = col * TILE + TILE / 2, (height - 1 - row) * TILE + TILE / 2  # row 0 is the top
                    if cx + x0 * TILE <= tx <= cx + x1 * TILE and cy + y0 * TILE <= ty <= cy + y1 * TILE:
                        walls["tiles"][row * width + col] = 1


def build(project: Path) -> Path:
    from engine.project_scaffold import create_project

    if project.exists():
        raise SystemExit(f"{project} exists; pick a new folder (this never overwrites)")
    create_project(project, "HD-2D test", "blank")
    (project / "assets/models").mkdir(parents=True)
    (project / "assets/textures").mkdir(parents=True)
    shutil.copy2(LAB / "stone_outpost.glb", project / "assets/models/stone_outpost.glb")
    shutil.copy2(LAB / "grass.png", project / "assets/textures/grass.png")
    start = project / SCENES / "start.json"
    scene = json.loads(start.read_text(encoding="utf-8"))
    hd2d = {
        "structures": [{"model": "assets/models/stone_outpost.glb", "x": OUTPOST[0], "y": OUTPOST[1]}],
        "ground": {"texture": "assets/textures/grass.png", "from": [0, 0], "to": [768, 512]},
        "camera": {"pitch": 32, "fov": 30, "distance": 15, "follow": "player"},
    }
    scene["name"] = "HD-2D Outpost"
    scene.setdefault("settings", {})["hd2d"] = hd2d
    _paint_walls(scene, [OUTPOST])
    scene["entities"] = [
        {"id": "start_player_128_128_0_0", "prefab_id": "player", "x": 384.0, "y": 120.0},
        # On the platform, in front of the hut: 1 m up, feet 0.5 m south of the platform's middle.
        {"id": "outpost_keeper", "prefab_id": "person", "mesh_name": "Keeper", "x": OUTPOST[0] + 42.0,
         "y": OUTPOST[1] - 16.0 + 24.0, "elevation": PLATFORM_TOP_PX},
    ]
    _write(start, scene)
    # The village: the same building, separately placed, on a bigger map (for the batching benchmark).
    village = json.loads(json.dumps(scene))
    village["name"] = "HD-2D Village"
    tm = village["tilemap"]
    tm["width"], tm["height"] = 48, 32
    for layer in tm["tile_layers"]:
        layer["tiles"] = [1 if layer["id"] == "ground" else 0] * (48 * 32)
    centres = [(160.0 + 320.0 * i, 128.0 + 256.0 * j) for i in range(5) for j in range(4)]  # 20 buildings
    village["settings"]["hd2d"] = dict(hd2d, structures=[{"model": "assets/models/stone_outpost.glb", "x": x, "y": y,
                                                         "rotation": 90.0 * ((k * 7) % 4)}
                                                        for k, (x, y) in enumerate(centres)],
                                       ground={"texture": "assets/textures/grass.png", "from": [0, 0], "to": [1536, 1024]})
    village["settings"]["world_width"], village["settings"]["world_height"] = 1536, 1024
    _paint_walls(village, [])
    village["entities"] = [{"id": "village_player", "prefab_id": "player", "x": 320.0, "y": 64.0}]
    _write(project / SCENES / "village.json", village)
    world_path = project / "packs/core_regions/worlds/main.json"
    world = json.loads(world_path.read_text(encoding="utf-8"))
    world["scenes"]["village"] = {"label": "Village", "path": f"{SCENES}/village.json", "tags": []}
    _write(world_path, world)
    return project


# ---------------------------------------------------------------------- the hidden game window
class HiddenGame:
    def __init__(self, project: Path, size: tuple[int, int] = (960, 540)) -> None:
        import engine.optional_arcade as optional_arcade  # first: DPI-unaware, as the engine runs

        self.arcade = arcade = optional_arcade.arcade
        self._original_init = arcade.Window.__init__
        original = self._original_init

        def hidden_init(window: Any, *args: Any, **kwargs: Any) -> None:
            kwargs["visible"] = False  # never shown: nothing on the owner's screen, no focus taken
            original(window, *args, **kwargs)

        arcade.Window.__init__ = hidden_init
        self._cwd = os.getcwd()
        os.chdir(project)
        from engine.config import load_config
        from engine.game import GameWindow

        config = load_config(str(project / "config.json"))
        self.window = GameWindow(width=size[0], height=size[1], title="Mesh HD-2D check", vsync=False, config=config,
                                 config_path=str(project / "config.json"))
        self.window._allow_dispatch_event = True

    def load(self, scene: str) -> None:
        self.window.load_scene(scene)

    def step(self, frames: int = 1) -> None:
        for _ in range(frames):
            self.window.dispatch_event("on_update", 1 / 60)

    def hold(self, key: int, frames: int) -> None:
        """The player holds a key for ``frames`` frames: the same key events the OS would send."""
        self.window.dispatch_event("on_key_press", key, 0)
        self.step(frames)
        self.window.dispatch_event("on_key_release", key, 0)
        self.step(2)

    def draw(self) -> Any:
        self.window.dispatch_event("on_draw")
        return self.arcade.get_image(0, 0, *self.window.get_framebuffer_size())

    def player(self) -> Any:
        return next(s for s in self.window.scene_controller.all_sprites if getattr(s, "mesh_tag", None) == "player")

    def sprite(self, name: str) -> Any:
        return next(s for s in self.window.scene_controller.all_sprites if getattr(s, "mesh_name", None) == name)

    def close(self) -> None:
        try:
            self.window.close()
        finally:
            self.arcade.Window.__init__ = self._original_init
            os.chdir(self._cwd)


def _gl_counts(ctx: Any) -> dict[str, int]:
    """Live GL objects of each kind (created minus freed)."""
    return {k: getattr(ctx.stats, k)[0] - getattr(ctx.stats, k)[1] for k in ("buffer", "texture", "framebuffer", "program")}


def check(project: Path, out: Path) -> dict[str, Any]:
    """Walk the player with key events and record what happened (positions, animation, camera, occlusion)."""
    out.mkdir(parents=True, exist_ok=True)
    game = HiddenGame(project)
    keys = game.arcade.key
    report: dict[str, Any] = {}
    try:
        ctx = game.window.ctx
        _write_2d_room(project)
        game.load(f"{SCENES}/plain_2d.json")  # the same room without HD-2D: the GL baseline
        game.step(30)
        game.draw()
        ctx.gc()
        before = _gl_counts(ctx)
        game.load(f"{SCENES}/start.json")
        hd = game.window.hd2d_renderer
        report["hd2d_active"] = hd is not None
        report["error"] = getattr(game.window, "hd2d_error", None)
        game.step(90)  # past the room's fade-in
        player, keeper = game.player(), game.sprite("Keeper")
        report["keeper_elevation_px"] = hd.elevation_of(keeper)
        game.draw().convert("RGB").save(out / "01_start.png")
        walk: list[dict[str, Any]] = []

        def note(label: str) -> None:
            walk.append({"after": label, "player": [round(player.center_x, 1), round(player.center_y, 1)],
                         "animation": _animation_state(player),
                         "camera_target_m": [round(v, 2) for v in hd.camera.target],
                         "visible_px": hd.visible_pixels(player), "total_px": _total_pixels(hd, player)})

        note("start")
        frames_seen: set[Any] = set()
        game.window.dispatch_event("on_key_press", keys.RIGHT, 0)
        for _ in range(40):
            game.step(1)
            frames_seen.add(id(player.texture))
        game.window.dispatch_event("on_key_release", keys.RIGHT, 0)
        game.step(2)
        report["walk_right_distinct_frames"] = len(frames_seen)
        note("right x40")
        game.hold(keys.UP, 50)
        note("up x50 (beside the platform, east)")
        game.draw().convert("RGB").save(out / "02_beside.png")
        game.hold(keys.UP, 46)
        game.hold(keys.LEFT, 40)
        note("up x46, left x40 (north of it: behind the building)")
        game.draw().convert("RGB").save(out / "03_behind.png")
        game.hold(keys.DOWN, 20)
        note("down x20 (against its north wall)")
        game.draw().convert("RGB").save(out / "04_against.png")
        game.hold(keys.LEFT, 120)
        game.hold(keys.DOWN, 120)
        game.hold(keys.RIGHT, 60)
        note("round the west side, back in front")
        report["walk"] = walk
        # Save and load in the HD-2D room: the ordinary save system; loading rebuilds the room and its renderer
        saves = game.window.save_manager
        saved_at = [round(player.center_x, 1), round(player.center_y, 1)]
        report["saved"] = saves.save_game("hd2d_check")
        game.hold(keys.RIGHT, 30)
        report["loaded"] = saves.load_game("hd2d_check")
        game.step(30)
        player, keeper = game.player(), game.sprite("Keeper")
        hd = game.window.hd2d_renderer
        report["save_load"] = {"saved_at": saved_at, "after_load": [round(player.center_x, 1), round(player.center_y, 1)],
                               "renderer_rebuilt": hd is not None, "keeper_elevation_px": hd.elevation_of(keeper)}
        game.draw().convert("RGB").save(out / "06a_after_load.png")
        hd.camera.ortho = True  # the orthographic option: same scene, parallel projection
        game.draw().convert("RGB").save(out / "07_ortho.png")
        report["ortho_player_visible_px"] = hd.visible_pixels(player)
        hd.camera.ortho = False
        report["keeper_visible_px"] = hd.visible_pixels(keeper)
        report["keeper_total_px"] = _total_pixels(hd, keeper)
        # Resize: the off-screen target follows the window
        game.window.set_size(1280, 720)
        game.window.dispatch_event("on_resize", 1280, 720)
        game.step(2)
        game.draw().convert("RGB").save(out / "05_resized.png")
        report["target_after_resize"] = list(hd._fbo.size)
        report["stats"] = hd.stats()
        # Scene change: back to the 2D room releases every GPU object the HD-2D room made
        ctx.gc()
        loaded = _gl_counts(ctx)
        game.load(f"{SCENES}/plain_2d.json")
        game.step(30)
        game.draw()
        ctx.gc()
        after = _gl_counts(ctx)
        game.load(f"{SCENES}/plain_2d.json")  # and once more 2D -> 2D: what a plain room change costs anyway
        game.step(30)
        game.draw()
        ctx.gc()
        report["gl_objects"] = {"before": before, "hd2d_loaded": loaded, "after_2d_room": after,
                                "after_another_2d_load": _gl_counts(ctx)}
        report["renderer_after_2d_room"] = game.window.hd2d_renderer
        game.draw().convert("RGB").save(out / "06_plain_2d.png")
    finally:
        game.close()
    _write(out / "check.json", report)
    return report


def _animation_state(sprite: Any) -> Any:
    clips = [getattr(b, "_current_clip_name", None) for b in getattr(sprite, "mesh_behaviours_runtime", None) or []]
    return next((c for c in clips if c), None)


def _total_pixels(hd: Any, sprite: Any) -> int:
    """The sprite's pixels with the structures removed (what visible_pixels would count unoccluded)."""
    static, ground = hd.static, hd.ground
    hd.static, hd.ground = [], None
    try:
        return int(hd.visible_pixels(sprite))
    finally:
        hd.static, hd.ground = static, ground


def _write_2d_room(project: Path) -> None:
    room = project / SCENES / "plain_2d.json"
    if not room.exists():
        scene = json.loads((project / SCENES / "start.json").read_text(encoding="utf-8"))
        scene["settings"].pop("hd2d")
        scene["name"] = "Plain 2D"
        for layer in scene["tilemap"]["tile_layers"]:
            if layer["id"] == "walls":
                layer["tiles"] = [0] * len(layer["tiles"])
        _write(room, scene)


def bench(project: Path, out: Path, frames: int = 300) -> dict[str, Any]:
    """The village (20 separate buildings) drawn batched and unbatched: draw calls, CPU and GPU time, memory."""
    from engine.hd2d.renderer import Hd2dRenderer
    from engine.hd2d.settings import parse_hd2d
    from engine.paths import resolve_path

    out.mkdir(parents=True, exist_ok=True)
    game = HiddenGame(project, size=(1280, 720))
    result: dict[str, Any] = {}
    try:
        game.load(f"{SCENES}/village.json")
        game.step(90)
        scene_settings = game.window.scene_controller.scene_settings
        settings = parse_hd2d(scene_settings["hd2d"], map_size_px=(1536, 1024))
        ctx = game.window.ctx
        game.window.hd2d_renderer.release()
        for batched in (True, False):
            tracemalloc.start()
            t0 = time.perf_counter()
            renderer = Hd2dRenderer(game.window, settings, resolve_path, batched=batched)
            build_ms = (time.perf_counter() - t0) * 1000
            build_peak = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
            game.window.hd2d_renderer = renderer
            renderer.camera.distance = 40.0  # the whole village in view: the worst case for draw calls
            for _ in range(30):
                game.window.dispatch_event("on_draw")
            ctx.finish()
            cpu, gpu = [], []
            query = ctx.query(time=True, samples=False, primitives=False)
            for _ in range(frames):
                t0 = time.perf_counter()
                with query:
                    renderer.draw()
                cpu.append((time.perf_counter() - t0) * 1000)  # submitting the frame (Python + driver)
                gpu.append(query.time_elapsed / 1e6)  # the GPU executing it
            game.window.dispatch_event("on_draw")
            ctx.finish()
            game.arcade.get_image(0, 0, 1280, 720).convert("RGB").save(out / f"village_{'batched' if batched else 'unbatched'}.png")
            result["batched" if batched else "unbatched"] = {
                "build_ms": round(build_ms, 1), "build_python_peak_kib": round(build_peak / 1024, 1),
                "cpu_ms_median": round(statistics.median(cpu), 3), "cpu_ms_p95": round(sorted(cpu)[int(frames * 0.95)], 3),
                "gpu_ms_median": round(statistics.median(gpu), 3), **renderer.stats()}
            renderer.release()
            game.window.hd2d_renderer = None
            ctx.gc()
        result["structures"] = len(settings.structures)
        result["frames"] = frames
        result["gl"] = {"renderer": ctx.info.RENDERER, "version": ctx.gl_version}
    finally:
        game.close()
    _write(out / "bench.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["build", "check", "bench"])
    parser.add_argument("project", type=Path)
    parser.add_argument("out", type=Path, nargs="?")
    args = parser.parse_args()
    if args.command == "build":
        print(build(args.project.resolve()))
    else:
        if args.out is None:
            parser.error(f"{args.command} needs OUT_DIR")
        run = check if args.command == "check" else bench
        print(json.dumps(run(args.project.resolve(), args.out.resolve()), indent=1, default=str))
