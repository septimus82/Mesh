"""Shadow bench: the engine's real LightManager on a small Arcade window, with exact pixels and timings.

Each scene is a flat grey floor (so a pixel's value is a measure of the light reaching it), dark wall
rectangles, point lights and a room light. A scene is drawn through ``LightManager.begin()/end()`` (what
the game and Mesh Studio call) and the window's pixels are read back before the frame is shown.

Used by the Milestone 12 GPU tests (tests/test_shadow_compositing_gpu.py) and on its own:

    py -3.13 tooling/shadow_bench.py [--renderer new|legacy] [--frames N] [--out report.json]

which renders the named example scenes and the benchmark scenes and prints pixels and frame times.
``--renderer legacy`` selects the pre-Milestone-12 shadow overlay (MESH_SHADOWS_RENDERER=legacy).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

FLOOR = (160, 160, 160)
WALL = (70, 60, 60)
SIZE = (640, 480)


@dataclass
class Scene:
    """What to draw: world units, y up, the camera's bottom-left at ``camera`` (zoom ``zoom``)."""

    ambient: tuple[int, int, int] = (40, 40, 60)
    lights: list[dict[str, Any]] = field(default_factory=list)  # scene "lights" entries
    walls: list[tuple[float, float, float, float]] = field(default_factory=list)  # x, y, w, h (rect occluders)
    polys: list[list[tuple[float, float]]] = field(default_factory=list)  # polygon occluders
    shadows: str = "hard"
    camera: tuple[float, float] = (0.0, 0.0)
    zoom: float = 1.0
    settings: dict[str, Any] = field(default_factory=dict)  # room settings (e.g. lighting_shadow_softness)
    # Characters: (x, y of the sprite's centre, frame of the starter hero sheet (row * 4 + column), entity data).
    characters: list[tuple[float, float, int, dict[str, Any]]] = field(default_factory=list)


class _CameraController:
    def __init__(self, window: Any) -> None:
        self.window = window

    def use_gui_camera(self) -> None:
        self.window.gui_camera.use()


class Bench:
    """One hidden-from-the-player window, reused for every scene."""

    def __init__(self, size: tuple[int, int] = SIZE, *, visible: bool = False) -> None:
        import engine.optional_arcade as optional_arcade  # first: DPI-unaware, as the engine runs (1 px = 1 px)
        from engine.lighting import LightManager

        arcade = optional_arcade.arcade

        self.arcade = arcade
        self.window = arcade.Window(size[0], size[1], "Mesh shadow bench", visible=visible)
        self.window.camera = arcade.Camera2D()
        self.window.gui_camera = arcade.Camera2D()
        self.window.camera_controller = _CameraController(self.window)
        self.window.scene_controller = None
        self.sprites = arcade.SpriteList()
        sheet = arcade.load_spritesheet(str(REPO / "assets/sprites/starter_hero.png"))
        self.hero_frames = sheet.get_texture_grid(size=(32, 48), columns=4, count=16)
        self.window.engine_config = None
        self.window.show_debug = False
        self.size = size
        self.manager = LightManager(self.window, enabled=True, shadows_mode="hard")
        self.scene = Scene()

    def close(self) -> None:
        self.window.close()

    def load(self, scene: Scene) -> None:
        """Configure the manager as the scene loader does: settings, lights, occluders."""
        from engine.scene_lifecycle_controller import apply_shadow_look  # noqa: PLC0415

        self.scene = scene
        m = self.manager
        m._last_lighting_stats = {}
        m.set_shadows_mode(scene.shadows)
        m.ambient_color = (*scene.ambient, 255)
        apply_shadow_look(m, scene.settings)  # as the scene loader does
        occluders = [{"id": f"w{i}", "type": "rect", "x": x, "y": y, "width": w, "height": h}
                     for i, (x, y, w, h) in enumerate(scene.walls)]
        occluders += [{"id": f"p{i}", "type": "poly", "points": [list(p) for p in poly]} for i, poly in enumerate(scene.polys)]
        m.configure_scene_occluders(occluders)
        m.configure_scene_lights(scene.lights)
        self.sprites.clear()
        for x, y, frame, data in scene.characters:
            sprite = self.arcade.Sprite(self.hero_frames[frame], scale=float(data.get("scale", 1.0)), center_x=x, center_y=y)
            sprite.mesh_entity_data = {"tag": "player", **data}
            sprite.sync_hit_box_to_texture()
            self.sprites.append(sprite)
        from types import SimpleNamespace

        self.window.scene_controller = SimpleNamespace(all_sprites=self.sprites) if scene.characters else None

    def _place_camera(self) -> None:
        cam = self.window.camera
        cam.zoom = self.scene.zoom
        w, h = self.size
        cam.position = (self.scene.camera[0] + w / 2 / self.scene.zoom, self.scene.camera[1] + h / 2 / self.scene.zoom)

    def draw(self) -> None:
        """One frame, as the game draws it (tick.on_draw)."""
        a = self.arcade
        self.window.clear()
        self._place_camera()
        self.window.camera.use()
        with self.manager.begin():
            a.draw_lrbt_rectangle_filled(-4000, 4000, -4000, 4000, FLOOR)
            for x, y, w, h in self.scene.walls:
                a.draw_lrbt_rectangle_filled(x, x + w, y, y + h, WALL)
            for poly in self.scene.polys:
                a.draw_polygon_filled(poly, WALL)
            self.sprites.draw(pixelated=True)
        self.window.camera_controller.use_gui_camera()
        self.manager.end()

    def frame(self) -> Any:
        """Draw and return the window's pixels (a PIL image, y down)."""
        self.draw()
        image = self.arcade.get_image(0, 0, *self.size)
        self.window.flip()
        return image

    def screen(self, world: tuple[float, float]) -> tuple[int, int]:
        """A world point's pixel in the returned image (x right, y down)."""
        z = self.scene.zoom
        sx = (world[0] - self.scene.camera[0]) * z
        sy = (world[1] - self.scene.camera[1]) * z
        return int(sx), int(self.size[1] - 1 - sy)

    def pixel(self, image: Any, world: tuple[float, float]) -> tuple[int, int, int]:
        r, g, b = image.getpixel(self.screen(world))[:3]
        return int(r), int(g), int(b)

    def time_frames(self, frames: int) -> dict[str, Any]:
        """Lighting-pass CPU/GPU time (the manager's own profile) and whole-frame time over ``frames`` frames."""
        os.environ["MESH_LIGHTING_PROFILE"] = "1"
        self.manager._profile.clear()
        ctx = self.window.ctx
        started = time.perf_counter()
        for _ in range(frames):
            self.manager.update(1 / 60)  # flicker moves, as in the game
            self.draw()
            ctx.finish()
            self.window.flip()
        total = (time.perf_counter() - started) * 1000.0 / frames
        os.environ.pop("MESH_LIGHTING_PROFILE", None)
        profile = self.manager.lighting_profile() or {}
        return {"frame_ms": round(total, 3), **profile, "stats": dict(self.manager._last_lighting_stats)}


def light(x: float, y: float, radius: float = 200.0, color: str = "#ffffff", **extra: Any) -> dict[str, Any]:
    return {"x": x, "y": y, "radius": radius, "color": color, "mode": "soft", **extra}


# ---------------------------------------------------------------------------------------- scenes
def example_scenes() -> dict[str, Scene]:
    """The brief's examples A-D and the no-occluder reference."""
    wall = (300.0, 140.0, 24.0, 200.0)  # a wall in the middle of the view
    return {
        "open": Scene(lights=[light(200, 240)]),
        "A_one_lantern_one_wall": Scene(lights=[light(200, 240)], walls=[wall]),
        "B_two_lanterns": Scene(lights=[light(200, 240), light(420, 420, color="#88bbff")], walls=[wall]),
        "B_only_lantern_b": Scene(lights=[light(420, 420, color="#88bbff")], walls=[wall]),
        "C_no_lights": Scene(lights=[], walls=[wall]),
        "C_no_lights_shadows_off": Scene(lights=[], walls=[wall], shadows="none"),
        "D_daylight": Scene(ambient=(200, 200, 190), lights=[light(200, 240)], walls=[wall]),
        "D_daylight_no_lamp": Scene(ambient=(200, 200, 190), lights=[], walls=[wall]),
        "A_shadows_off": Scene(lights=[light(200, 240)], walls=[wall], shadows="none"),
    }


def bench_scenes() -> dict[str, Scene]:
    """The benchmark rooms (Phase 6): one light and a few walls up to a crowded room."""
    few = [(300.0, 140.0, 24.0, 200.0), (420.0, 60.0, 120.0, 24.0), (80.0, 360.0, 24.0, 90.0)]
    grid = [(60.0 + 90 * c, 40.0 + 80 * r, 26.0, 26.0) for c in range(7) for r in range(6)]  # 42 pillars
    lights_many = [light(80 + 120 * i, 120 + 160 * (i % 2), 180, ["#ffcc88", "#88bbff", "#ff5555", "#66ff77"][i % 4])
                   for i in range(5)]
    lights_crowd = [light(40 + 70 * i, 60 + 90 * (i % 5), 160, "#ffcc88") for i in range(10)]
    two = [light(200, 240, 260), light(460, 300, 260, "#ffcc88")]

    def hero(x: float, y: float, frame: int = 0) -> tuple[float, float, int, dict[str, Any]]:
        return (x, y, frame, {"tag": "npc"})

    crowd = [hero(120 + 80 * i, 160 + 70 * (i % 2), (i * 5) % 16) for i in range(6)]
    return {
        "one_light_few_walls": Scene(lights=[light(200, 240)], walls=few),
        "five_lights_overlapping": Scene(lights=lights_many, walls=few),
        "crowded_10_lights_42_pillars": Scene(lights=lights_crowd, walls=grid),
        "crowded_zoom_2": Scene(lights=lights_crowd, walls=grid, zoom=2.0, camera=(100.0, 80.0)),
        "five_lights_no_shadows": Scene(lights=lights_many, walls=few, shadows="none"),
        "crowded_soft": Scene(lights=lights_crowd, walls=grid, settings={"lighting_shadow_softness": "soft"}),
        "crowded_softer": Scene(lights=lights_crowd, walls=grid, settings={"lighting_shadow_softness": "softer"}),
        # Milestone 12.1: characters casting shadows, flickering lamps.
        "two_lights_1_character": Scene(lights=two, walls=few, characters=[hero(320, 240)]),
        "two_lights_6_characters": Scene(lights=two, walls=few, characters=crowd),
        "two_lights_6_characters_soft": Scene(lights=two, walls=few, characters=crowd, settings={"lighting_shadow_softness": "soft"}),
        "two_lights_6_characters_softer": Scene(lights=two, walls=few, characters=crowd,
                                                settings={"lighting_shadow_softness": "softer"}),
        "two_lights_6_characters_softer_high": Scene(lights=two, walls=few, characters=crowd,
                                                     settings={"lighting_shadow_softness": "softer", "lighting_shadow_quality": "high"}),
        "two_lights_6_characters_zoom_2": Scene(lights=two, walls=few, characters=crowd, zoom=2.0, camera=(160.0, 120.0)),
        "two_torches_6_characters": Scene(lights=[{**lamp, "flicker_enabled": True, "flicker_preset": "torch"} for lamp in two],
                                          walls=few, characters=crowd),
        "two_lights_6_characters_no_character_shadows": Scene(lights=two, walls=few, characters=crowd,
                                                              settings={"lighting_character_shadows": False}),
    }


def run(renderer: str, frames: int) -> dict[str, Any]:
    if renderer == "legacy":
        os.environ["MESH_SHADOWS_RENDERER"] = "legacy"
    else:
        os.environ.pop("MESH_SHADOWS_RENDERER", None)
    bench = Bench()
    out: dict[str, Any] = {"renderer": renderer, "examples": {}, "bench": {}}
    probes = {"lit_open": (240, 240), "behind_wall": (380, 240), "far_dark": (600, 40), "between": (260, 240)}
    try:
        info = bench.window.ctx.info
        out["gl"] = {"version": bench.window.ctx.gl_version, "renderer": info.RENDERER}
        for name, scene in example_scenes().items():
            bench.load(scene)
            image = bench.frame()
            out["examples"][name] = {k: bench.pixel(image, p) for k, p in probes.items()}
        for name, scene in bench_scenes().items():
            bench.load(scene)
            bench.frame()  # warm up: programs, buffers
            out["bench"][name] = bench.time_frames(frames)
    finally:
        bench.close()
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--renderer", choices=("new", "legacy"), default="new")
    parser.add_argument("--frames", type=int, default=240)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run(args.renderer, args.frames)
    text = json.dumps(report, indent=1, default=str)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)
