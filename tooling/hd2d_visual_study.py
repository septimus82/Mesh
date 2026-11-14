"""Milestone 16 HD-2D visual direction: the starter village under several gameplay cameras, and two character
styles, in a hidden window, for side-by-side comparison. Nothing is shown on screen.

    py -3.13 tooling/hd2d_visual_study.py cameras OUT        # every camera treatment, the same walk and spots
    py -3.13 tooling/hd2d_visual_study.py sprites OUT --camera ortho   # placeholder vs improved characters

``cameras`` creates a project from the developer-only ``hd2d_rpg`` template in OUT/project, then for each treatment
rewrites only ``settings.hd2d.camera`` in both rooms and walks the same route with key events (the camera never turns,
so every treatment visits exactly the same positions). At each spot it saves a picture and measures: how much of the
picture is empty background, the player's height on screen and how much of it is hidden, and the camera. It records a
short movement clip (stairs and bridge) and the frame cost split into game update, drawing, GPU and read-back. Then it
puts the treatments side by side (OUT/compare_*.png, OUT/walk.webp) and writes OUT/study.json.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
import review_media  # noqa: E402
from hd2d_demo import SCENES, HiddenGame, _total_pixels  # noqa: E402  # the Stage 2 hidden-window harness
from hd2d_floors_demo import _feet, hold_key  # noqa: E402

SIZE = (1280, 720)
SKY = (118, 160, 214)  # the renderer's default background
VIEW_M = 11.25  # m of the world visible top to bottom at the player: 64 px per m at 720 px, 96 at 1080 (2x / 3x)

# Every treatment shows the same height of world at the player (VIEW_M) so they differ only in angle and projection;
# "current" is the Stage 6A template's camera, for reference.
TREATMENTS: dict[str, dict[str, Any]] = {
    "current": {"pitch": 34.0, "fov": 30.0, "distance": 15.0, "ortho": False},
    "ortho": {"pitch": 30.0, "fov": 30.0, "ortho": True},
    "narrow": {"pitch": 30.0, "fov": 12.0, "ortho": False},
    "low": {"pitch": 18.0, "fov": 30.0, "ortho": False},
}
LABELS = {"current": "Stage 6A camera (34 deg, 30 deg FOV, 15 m)", "ortho": "1. Angled orthographic (30 deg)",
          "narrow": "2. Narrow-FOV perspective (30 deg, 12 deg FOV)", "low": "3. Low perspective (18 deg, 30 deg FOV)"}
SHOTS = ("establishing", "stairs", "bridge", "npc", "under_bridge", "cottage", "behind_cottage", "inside",
         "inside_east")


def camera_settings(name: str) -> dict[str, Any]:
    """The ``settings.hd2d.camera`` of a treatment: its distance chosen so VIEW_M of world shows at the player."""
    t = dict(TREATMENTS[name])
    if "distance" not in t:
        t["distance"] = round(VIEW_M / 2 / math.tan(math.radians(t["fov"]) / 2), 3)
    return {**t, "follow": "player"}


def _rooms(project: Path) -> list[Path]:
    return [project / SCENES / "start.json", project / SCENES / "cottage.json"]


def set_camera(project: Path, camera: dict[str, Any]) -> None:
    for path in _rooms(project):
        scene = json.loads(path.read_text(encoding="utf-8"))
        scene["settings"]["hd2d"]["camera"] = dict(camera)
        path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")


def _bbox_rows(data: bytes, width: int) -> tuple[int, int] | None:
    """The first and last row (from the bottom) holding a solid-red pixel, in RGB bytes read back from GL."""
    rows = [i // (width * 3) for i in range(0, len(data), 3) if data[i] > 200 and data[i + 1] < 60]
    return (min(rows), max(rows)) if rows else None


def distortion(camera: dict[str, Any], aspect: float) -> float:
    """How much larger a character at the bottom edge of the picture looks than one at the top edge (1 = none):
    the ratio of their depths along the view, for characters standing on the player's floor."""
    from engine.hd2d.renderer import Camera

    if camera["ortho"]:
        return 1.0
    cam = Camera(camera["pitch"], camera["fov"], camera["distance"], False)
    eye = cam.eye()
    fwd = [cam.target[i] - eye[i] for i in range(3)]
    n = math.sqrt(sum(v * v for v in fwd))
    fwd = [v / n for v in fwd]
    depths = []
    for ndc_y in (-1.0, 1.0):
        origin, d = cam.ray(0.0, ndc_y, aspect)
        if d[2] >= -1e-6:
            return float("inf")  # the top edge sees the horizon
        t = -origin[2] / d[2]
        p = [origin[i] + d[i] * t for i in range(3)]
        depths.append(sum((p[i] - eye[i]) * fwd[i] for i in range(3)))
    return round(depths[1] / depths[0], 2)


def horizon_visible(camera: dict[str, Any]) -> bool:
    return not camera["ortho"] and camera["pitch"] < camera["fov"] / 2


class Walk:
    """The study's route through the village with key events, stopping at each spot of SHOTS."""

    def __init__(self, game: HiddenGame, out: Path, prefix: str) -> None:
        self.game, self.out, self.prefix = game, out, prefix
        self.keys = game.arcade.key
        self.spots: dict[str, dict[str, Any]] = {}
        self.clip: list[Any] = []
        self.track: list[dict[str, Any]] = []

    @property
    def player(self) -> Any:
        return self.game.player()

    def go(self, key: str, axis: int, target: float, *, film: bool = False) -> bool:
        each = self._film if film else None
        return bool(hold_key(self.game, self.player, getattr(self.keys, key), axis, target, 900, each_frame=each))

    def _film(self) -> None:
        hd = self.game.window.hd2d_renderer
        player = self.player
        fx, fy = _feet(player)
        z = hd.elevation_of(player) / 32
        self.track.append({"feet_y": fy, "z": z, "target_z": hd.camera.target[2], "screen": self._screen(fx, fy, z)})
        if len(self.track) % 4 == 1:  # 15 pictures a second
            self.clip.append(self.game.draw().convert("RGB").resize((SIZE[0] // 2, SIZE[1] // 2)))

    def _screen(self, x: float, y: float, z: float) -> list[float]:
        """Where a world point (m) appears, in pixels from the picture's bottom-left (the last frame's camera)."""
        hd = self.game.window.hd2d_renderer
        vp = hd.camera.view_projection(SIZE[0] / SIZE[1])
        c = [sum(vp[r][k] * v for k, v in enumerate((x, y, z, 1.0))) for r in range(4)]
        return [round((c[0] / c[3] * 0.5 + 0.5) * SIZE[0], 1), round((c[1] / c[3] * 0.5 + 0.5) * SIZE[1], 1)]

    def shot(self, name: str) -> None:
        game, hd, player = self.game, self.game.window.hd2d_renderer, self.player
        game.step(45)  # let the camera settle
        image = game.draw().convert("RGB")
        image.save(self.out / f"{self.prefix}_{name}.png")
        pixels = image.getdata()
        background = sum(1 for p in pixels if p == SKY) / len(pixels)
        visible = hd.visible_pixels(player)
        total = _total_pixels(hd, player)
        static, ground = hd.static, hd.ground
        hd.static, hd.ground = [], None
        try:
            rows = _bbox_rows(hd.draw(solid=player, read=True), SIZE[0])
        finally:
            hd.static, hd.ground = static, ground
        fx, fy = _feet(player)
        self.spots[name] = {
            "feet_m": [round(fx, 2), round(fy, 2)], "elevation_m": round(hd.elevation_of(player) / 32, 2),
            "floor": getattr(player, "mesh_hd2d_floor", None),
            "room": Path(str(game.window.scene_controller.current_scene_path)).name,
            "background_pct": round(100 * background, 1),
            "player_height_px": None if rows is None else rows[1] - rows[0] + 1,
            "player_visible_pct": round(100 * visible / total, 1) if total else None,
            "player_screen_px": self._screen(fx, fy, hd.elevation_of(player) / 32),
            "camera_target_m": [round(v, 2) for v in hd.camera.target]}

    def run(self) -> None:
        go, shot = self.go, self.shot
        go("UP", 1, 15.0)
        shot("establishing")
        go("LEFT", 0, 15.0, film=True)
        go("UP", 1, 19.6, film=True)
        shot("stairs")
        go("UP", 1, 24.0, film=True)
        go("RIGHT", 0, 20.0, film=True)
        shot("bridge")
        go("RIGHT", 0, 26.8, film=True)
        shot("npc")
        go("UP", 1, 25.2)
        go("RIGHT", 0, 30.0)
        go("DOWN", 1, 14.5)
        go("LEFT", 0, 20.0)
        go("UP", 1, 24.0)
        shot("under_bridge")
        go("DOWN", 1, 8.5)
        go("LEFT", 0, 11.5)
        shot("cottage")
        go("RIGHT", 0, 13.5)
        go("UP", 1, 14.8)
        go("LEFT", 0, 10.0)
        shot("behind_cottage")
        go("RIGHT", 0, 13.5)
        go("DOWN", 1, 6.5)  # the door's trigger reaches 1-2 m out (2 m before the M17 door fix): approach from the south, not along its front
        go("LEFT", 0, 10.0)
        self.enter("UP")
        shot("inside")
        go("RIGHT", 0, 9.0)
        shot("inside_east")

    def enter(self, key: str) -> None:
        """Walk through a door: hold the key only until the room changes (held longer, the player would walk on)."""
        window = self.game.window
        before = window.scene_controller.current_scene_path
        window.dispatch_event("on_key_press", getattr(self.keys, key), 0)
        for _ in range(300):
            self.game.step(1)
            if window.scene_controller.current_scene_path != before:
                break
        window.dispatch_event("on_key_release", getattr(self.keys, key), 0)
        self.game.step(60)


def frame_cost(game: HiddenGame, frames: int = 120) -> dict[str, Any]:
    """One game frame split up: the game's update (movement, behaviours, UI), drawing (CPU: the HD-2D renderer and
    the 2D interface over it), waiting for the GPU, and reading the picture back (only the harness does that)."""
    window, ctx, hd = game.window, game.window.ctx, game.window.hd2d_renderer
    spent: list[float] = []
    original = hd.draw

    def timed(*args: Any, **kwargs: Any) -> Any:
        t = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            spent.append((time.perf_counter() - t) * 1000)

    hd.draw = timed
    update, draw, gpu = [], [], []
    try:
        for _ in range(frames):
            t0 = time.perf_counter()
            window.dispatch_event("on_update", 1 / 60)
            t1 = time.perf_counter()
            window.dispatch_event("on_draw")
            t2 = time.perf_counter()
            ctx.finish()
            t3 = time.perf_counter()
            update.append((t1 - t0) * 1000)
            draw.append((t2 - t1) * 1000)
            gpu.append((t3 - t2) * 1000)
    finally:
        del hd.draw
    readback = []
    for _ in range(10):
        t = time.perf_counter()
        game.arcade.get_image(0, 0, *window.get_framebuffer_size())
        readback.append((time.perf_counter() - t) * 1000)
    med = statistics.median
    return {"update_ms": round(med(update), 2), "draw_cpu_ms": round(med(draw), 2),
            "hd2d_renderer_cpu_ms": round(med(spent), 2) if spent else None, "gpu_wait_ms": round(med(gpu), 2),
            "frame_ms": round(med(u + d + g for u, d, g in zip(update, draw, gpu)), 2),
            "frame_ms_p95": round(sorted(u + d + g for u, d, g in zip(update, draw, gpu))[int(frames * 0.95)], 2),
            "readback_ms": round(med(readback), 2)}


# The improved, original character style (tooling/make_starter_art.py) in place of the starter characters.
SPRITE_SWAP = {"starter_hero.png": "hd2d_hero.png", "starter_villager.png": "hd2d_villager.png",
               "starter_merchant.png": "hd2d_merchant.png"}
DEFAULT_SUN = [-0.45, -0.55, 0.70]  # the engine's default: high, from the south-west (behind the camera, left)
PREFERRED = "narrow"


STAGE_6A_SUN = [0.35, 0.5, 0.79]  # the Stage 6A template's: high, from the north-east (behind the scene)
STAGE_6A_INDOOR = {"pitch": 55.0, "fov": 30.0, "distance": 10.0, "ortho": False, "follow": "player"}


def new_project(out: Path, name: str, *, stage6a: bool = True) -> Path:
    """A project from the ``hd2d_rpg`` template. ``stage6a``: as Stage 6A made it (its cameras, sun and starter
    characters), the fixed starting point of every comparison; otherwise exactly as the template makes it now."""
    from engine.project_scaffold import create_project

    project = out / name
    if project.exists():  # only ever a project this study made in its own output folder
        shutil.rmtree(project)
    create_project(project, "Visual Study", "hd2d_rpg")
    if stage6a:
        set_camera(project, camera_settings("current"))
        set_hd2d(project, "cottage.json", camera=dict(STAGE_6A_INDOOR))
        path = project / SCENES / "start.json"
        scene = json.loads(path.read_text(encoding="utf-8"))
        scene["settings"]["hd2d"]["sun"]["direction"] = STAGE_6A_SUN
        scene["settings"]["hd2d"]["ground"]["to"] = [40 * 32, 32 * 32]  # its village ended 8 m north of the hills
        path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
        path = project / SCENES / "cottage.json"  # and its door, arrival and start inside (px, sprite centres)
        scene = json.loads(path.read_text(encoding="utf-8"))
        where = {"door": (204.8, 243.2), "spawn_point": (204.8, 147.2), "player": (256.0, 162.0)}
        for entity in scene["entities"]:
            tag = "player" if entity.get("prefab_id") == "player" else entity.get("tag")
            if tag in where:
                entity["x"], entity["y"] = where[tag]
        path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
        swap_sprites(project, {new: old for old, new in SPRITE_SWAP.items()})
    return project


def swap_sprites(project: Path, swap: dict[str, str]) -> None:
    """Every character sheet ``old`` named in the project replaced by ``new`` (copied in from the engine)."""
    for new in swap.values():
        shutil.copyfile(REPO / "assets" / "sprites" / new, project / "assets" / "sprites" / new)
    for path in project.rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        changed = text
        for old, new in swap.items():
            changed = changed.replace(f"assets/sprites/{old}", f"assets/sprites/{new}")
        if changed != text:
            path.write_text(changed, encoding="utf-8")


def use_hd2d_sprites(project: Path) -> None:
    swap_sprites(project, SPRITE_SWAP)


def set_hd2d(project: Path, room: str, **keys: Any) -> None:
    path = project / SCENES / room
    scene = json.loads(path.read_text(encoding="utf-8"))
    scene["settings"]["hd2d"].update(keys)
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")


def session(project: Path, out: Path, prefix: str, *, measure: bool = True) -> dict[str, Any]:
    """One hidden game: the walk (pictures and facts at every spot) and, at the village's centre, the frame cost."""
    game = HiddenGame(project, size=SIZE)
    result: dict[str, Any] = {}
    try:
        game.load(f"{SCENES}/start.json")
        game.step(90)  # past the room's fade-in
        walk = Walk(game, out, prefix)
        if measure:
            walk.go("UP", 1, 15.0)
            result["frame"] = frame_cost(game)
            stats = game.window.hd2d_renderer.stats()
            result["renderer"] = {k: stats[k] for k in ("draw_calls", "triangles", "shadow_draws")}
        walk.run()
    finally:
        game.close()
    screen_y = [t["screen"][1] for t in walk.track]
    rise = max(t["target_z"] for t in walk.track) - min(t["target_z"] for t in walk.track) if walk.track else None
    result.update({"spots": walk.spots, "_clip": walk.clip,
                   "walk": {"frames": len(walk.track), "camera_rise_m": None if rise is None else round(rise, 2),
                            "player_screen_y_range_px": [min(screen_y), max(screen_y)] if screen_y else None}})
    return result


def run_treatment(project: Path, out: Path, name: str) -> dict[str, Any]:
    camera = camera_settings(name)
    set_camera(project, camera)
    result = session(project, out, name)
    view = VIEW_M if name != "current" else round(2 * camera["distance"] * math.tan(math.radians(camera["fov"]) / 2), 2)
    return {"camera": camera, "label": LABELS[name], "view_m_at_player": view,
            "distortion_bottom_vs_top": distortion(camera, SIZE[0] / SIZE[1]),
            "horizon_in_view": horizon_visible(camera), **result}


def _label(image: Any, text: str) -> Any:
    from PIL import ImageDraw, ImageFont

    d = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=max(14, image.height // 22))
    box = d.textbbox((10, 8), text, font=font)
    d.rectangle((box[0] - 6, box[1] - 4, box[2] + 6, box[3] + 4), fill=(20, 22, 28))
    d.text((10, 8), text, fill=(240, 240, 240), font=font)
    return image


def grid(images: list[Any], labels: list[str], cell: tuple[int, int]) -> Any:
    """Pictures two to a row, each scaled to ``cell`` and labelled."""
    from PIL import Image

    cols = 2
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cell[0] * cols, cell[1] * rows), (20, 22, 28))
    for i, (image, text) in enumerate(zip(images, labels)):
        enlarge = cell[0] > image.width  # pixels stay square blocks; a reduction is filtered
        sheet.paste(_label(image.resize(cell, Image.Resampling.NEAREST if enlarge else Image.Resampling.LANCZOS), text),
                    ((i % cols) * cell[0], (i // cols) * cell[1]))
    return sheet


def pair(out: Path, left: str, right: str, labels: tuple[str, str], shots: tuple[str, ...], name: str) -> None:
    from PIL import Image

    for shot in shots:
        grid([Image.open(out / f"{left}_{shot}.png"), Image.open(out / f"{right}_{shot}.png")], list(labels),
             (SIZE[0] // 2, SIZE[1] // 2)).save(out / f"{name}_{shot}.png")


def close_up(out: Path, prefixes: list[str], labels: list[str], shot: str, name: str,
             half: tuple[int, int] = (150, 90)) -> None:
    """The picture around the player at 2x (nearest), side by side: pixel density, outlines, contact, lighting."""
    from PIL import Image

    pictures = []
    for prefix in prefixes:
        image = Image.open(out / f"{prefix}_{shot}.png")
        spot = json.loads((out / f"{prefix}.spots.json").read_text(encoding="utf-8"))[shot]["player_screen_px"]
        cx, cy = int(spot[0]), SIZE[1] - int(spot[1]) - 40  # a little above the feet
        pictures.append(image.crop((cx - half[0], cy - half[1], cx + half[0], cy + half[1])))
    grid(pictures, labels, (half[0] * 4, half[1] * 4)).save(out / f"{name}.png")


def cameras(out: Path) -> dict[str, Any]:
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    project = new_project(out, "project")
    results = {name: run_treatment(project, out, name) for name in TREATMENTS}
    names = list(TREATMENTS)
    for shot in SHOTS:
        grid([Image.open(out / f"{n}_{shot}.png") for n in names], [LABELS[n] for n in names],
             (SIZE[0] // 2, SIZE[1] // 2)).save(out / f"compare_{shot}.png")
    clips = [results[n].pop("_clip") for n in names]
    length = min(len(c) for c in clips)
    frames = [grid([c[i] for c in clips], [LABELS[n] for n in names], (SIZE[0] // 4, SIZE[1] // 4))
              for i in range(length)]
    review_media.save_clip(frames, out / "walk.webp", duration=67, quality=80)
    return {"size": list(SIZE), "view_m": VIEW_M, "treatments": results}


def _keep_spots(out: Path, prefix: str, result: dict[str, Any]) -> dict[str, Any]:
    (out / f"{prefix}.spots.json").write_text(json.dumps(result["spots"], indent=2) + "\n", encoding="utf-8")
    result.pop("_clip", None)
    return result


def sprites(out: Path, camera: str) -> dict[str, Any]:
    """The starter characters and the improved style, under one camera, with the Stage 6A lighting."""
    out.mkdir(parents=True, exist_ok=True)
    project = new_project(out, "project_sprites")
    set_camera(project, camera_settings(camera))
    before = _keep_spots(out, "sprite_old", session(project, out, "sprite_old", measure=False))
    use_hd2d_sprites(project)
    after = _keep_spots(out, "sprite_new", session(project, out, "sprite_new", measure=False))
    labels = ("Starter characters (Stage 6A)", "Improved HD-2D style")
    pair(out, "sprite_old", "sprite_new", labels, ("establishing", "npc", "cottage", "stairs", "inside"), "sprites")
    close_up(out, ["sprite_old", "sprite_new"], list(labels), "npc", "sprites_close_npc")
    close_up(out, ["sprite_old", "sprite_new"], list(labels), "cottage", "sprites_close_cottage")
    return {"camera": camera_settings(camera), "old": before, "new": after}


def _probe(game: HiddenGame) -> dict[str, float]:
    """Brightness (mean of r, g, b) of the light arriving at a character, a wall facing the camera, and the ground,
    in the open at the village's centre; and at the cottage's front wall beside its door."""
    hd = game.window.hd2d_renderer
    game.draw()
    spots = {"character_in_the_open": (20.0, 15.0, 0.9, 0.0, -1.0, 0.0, True),
             "wall_facing_camera_in_the_open": (20.0, 15.0, 0.9, 0.0, -1.0, 0.0, False),
             "ground_in_the_open": (20.0, 15.0, 0.01, 0.0, 0.0, 1.0, False),
             "cottage_front_wall": (11.5, 9.95, 1.5, 0.0, -1.0, 0.0, False),
             "character_at_cottage_front": (11.5, 9.4, 0.9, 0.0, -1.0, 0.0, True)}
    light = hd.lighting.probe(list(spots.values()))
    return {k: round(sum(v) / 3, 3) for k, v in zip(spots, light)}


def lighting(out: Path, camera: str) -> dict[str, Any]:
    """The Stage 6A sun (high, from the north-east) and the engine's default (from the south-west), with the
    improved characters under one camera: how characters and the walls facing the camera are lit."""
    out.mkdir(parents=True, exist_ok=True)
    project = new_project(out, "project_lighting")
    set_camera(project, camera_settings(camera))
    use_hd2d_sprites(project)
    result: dict[str, Any] = {}
    for prefix, sun in (("sun_6a", None), ("sun_default", DEFAULT_SUN)):
        if sun is not None:
            path = project / SCENES / "start.json"
            scene = json.loads(path.read_text(encoding="utf-8"))
            scene["settings"]["hd2d"]["sun"]["direction"] = sun
            path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
        game = HiddenGame(project, size=SIZE)
        try:
            game.load(f"{SCENES}/start.json")
            game.step(90)
            probe = _probe(game)
        finally:
            game.close()
        walked = _keep_spots(out, prefix, session(project, out, prefix, measure=False))
        sun_now = json.loads((project / SCENES / "start.json").read_text(encoding="utf-8"))["settings"]["hd2d"]["sun"]
        result[prefix] = {"sun": sun_now, "probe": probe, **walked}
    labels = ("Stage 6A sun (north-east)", "Engine default sun (south-west)")
    pair(out, "sun_6a", "sun_default", labels, ("establishing", "npc", "cottage"), "lighting")
    close_up(out, ["sun_6a", "sun_default"], list(labels), "cottage", "lighting_close_cottage")
    return result


INDOOR = {  # name: (label, camera); bounds: the cottage's inside, 6 x 5 m about (8, 6) m, with room to spare
    "in_6a": ("Stage 6A indoor (55 deg, 30 deg FOV, 10 m, follows)",
              {"pitch": 55.0, "fov": 30.0, "distance": 10.0, "ortho": False}),
    "in_45": ("Narrow FOV 45 deg, 11.25 m, bounds", {"pitch": 45.0, "fov": 12.0, "ortho": False}),
    "in_55": ("Narrow FOV 55 deg, 11.25 m, bounds", {"pitch": 55.0, "fov": 12.0, "ortho": False}),
    "in_55_close": ("Narrow FOV 55 deg, 7.5 m (3x), bounds", {"pitch": 55.0, "fov": 12.0, "ortho": False, "view": 7.5}),
}
COTTAGE_BOUNDS = [4.5 * 32, 3.0 * 32, 11.5 * 32, 9.0 * 32]


def indoor(out: Path) -> dict[str, Any]:
    """The cottage's inside under several indoor cameras: the player by the door, then 1.6 m east and 1.5 m north."""
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    project = new_project(out, "project_indoor")
    use_hd2d_sprites(project)
    result: dict[str, Any] = {}
    for name, (label, settings) in INDOOR.items():
        cam: dict[str, Any] = dict(settings)
        view = cam.pop("view", VIEW_M)
        if "distance" not in cam:
            cam["distance"] = round(view / 2 / math.tan(math.radians(cam["fov"]) / 2), 3)
            cam["bounds"] = COTTAGE_BOUNDS
        set_hd2d(project, "cottage.json", camera={**cam, "follow": "player"})
        game = HiddenGame(project, size=SIZE)
        try:
            game.load(f"{SCENES}/cottage.json")
            game.step(90)
            walk = Walk(game, out, name)
            walk.shot("door")
            walk.go("RIGHT", 0, 8.0)
            walk.go("UP", 1, 6.5)
            walk.shot("east")
            result[name] = {"label": label, "camera": cam, "spots": walk.spots}
        finally:
            game.close()
    names = list(INDOOR)
    for shot in ("door", "east"):
        grid([Image.open(out / f"{n}_{shot}.png") for n in names], [INDOOR[n][0] for n in names],
             (SIZE[0] // 2, SIZE[1] // 2)).save(out / f"indoor_{shot}.png")
    return result


def cost(out: Path, rounds: int = 3) -> dict[str, Any]:
    """Each camera's frame cost (with Stage 6A's look), and the template as it now is ("recommended"), measured in
    turn ``rounds`` times (a slow moment of the machine then shows as spread, not as one of them being slower)."""
    out.mkdir(parents=True, exist_ok=True)
    project = new_project(out, "project_cost")
    template = new_project(out, "project_cost_template", stage6a=False)
    samples: dict[str, list[dict[str, Any]]] = {n: [] for n in [*TREATMENTS, "recommended"]}
    for _ in range(rounds):
        for name in samples:
            if name != "recommended":
                set_camera(project, camera_settings(name))
            game = HiddenGame(template if name == "recommended" else project, size=SIZE)
            try:
                game.load(f"{SCENES}/start.json")
                game.step(90)
                hold_key(game, game.player(), game.arcade.key.UP, 1, 15.0)
                samples[name].append(frame_cost(game, 240))
            finally:
                game.close()
    return {name: {key: [r[key] for r in runs] for key in runs[0]} for name, runs in samples.items()}


def play_cost(out: Path) -> dict[str, Any]:
    """Stage 6A's "game frame" (21 ms) taken apart. tooling/hd2d_starter_demo.py timed StudioDriver.frame() in Mesh
    Studio's Play mode: the game's update and drawing, Mesh Studio's own interface over it, and the harness reading
    the whole picture back into a PIL image. Here: that same timing, then the same frame split up."""
    from hd2d_studio_demo import StudioDriver

    out.mkdir(parents=True, exist_ok=True)
    project = new_project(out, "project_play")
    d = StudioDriver(project)
    try:
        d.advance(10)
        d.key(d.arcade.key.F4)  # Play
        d.advance(30)
        def driver_frames() -> float:
            whole = []
            for _ in range(60):
                t = time.perf_counter()
                d.frame()  # (timed: the frame as it was measured, read-back included)
                whole.append((time.perf_counter() - t) * 1000)
            return round(statistics.median(whole), 2)

        plain = driver_frames()
        tracemalloc.start()  # as tooling/hd2d_starter_demo.py had it while timing (it measured Python's peak memory)
        traced = driver_frames()
        tracemalloc.stop()
        split = frame_cost(d.game, 120)
    finally:
        d.close()
    return {"studio_driver_frame_ms_median": plain, "studio_driver_frame_ms_median_with_tracemalloc": traced,
            "split_in_studio_play": split}


def profile(out: Path, frames: int = 240) -> dict[str, Any]:
    """Where a game frame's CPU time goes (cProfile over ``frames`` frames of the game alone, at the village's
    centre): the functions with the most time of their own."""
    import cProfile
    import io
    import pstats

    out.mkdir(parents=True, exist_ok=True)
    project = new_project(out, "project_profile", stage6a=False)
    set_camera(project, camera_settings(PREFERRED))
    game = HiddenGame(project, size=SIZE)
    try:
        game.load(f"{SCENES}/start.json")
        game.step(90)
        hold_key(game, game.player(), game.arcade.key.UP, 1, 15.0)
        profiler = cProfile.Profile()
        profiler.enable()
        for _ in range(frames):
            game.window.dispatch_event("on_update", 1 / 60)
            game.window.dispatch_event("on_draw")
            game.window.ctx.finish()
        profiler.disable()
    finally:
        game.close()
    text = io.StringIO()
    pstats.Stats(profiler, stream=text).sort_stats("tottime").print_stats(25)
    (out / "profile.txt").write_text(text.getvalue(), encoding="utf-8")
    stats = getattr(pstats.Stats(profiler), "stats")  # noqa: B009  # undeclared in the stubs
    rows = sorted(((v[2], f"{Path(k[0]).name}:{k[1]} {k[2]}") for k, v in stats.items()), reverse=True)[:25]
    return {"frames": frames, "own_ms_per_frame": [[round(t * 1000 / frames, 3), name] for t, name in rows]}


def recommended(out: Path) -> dict[str, Any]:
    """The template exactly as it is now (the recommended camera, bounds, sun and characters) beside Stage 6A's,
    at every spot of the walk, with a movement clip of each and the frame cost."""
    out.mkdir(parents=True, exist_ok=True)
    before = _keep_spots(out, "before", session(new_project(out, "project_before"), out, "before"))
    after = session(new_project(out, "project_after", stage6a=False), out, "after")
    clip = after.pop("_clip")
    review_media.save_clip(clip, out / "after_walk.webp", duration=67, quality=80)
    _keep_spots(out, "after", after)
    labels = ("Stage 6A template", "Recommended HD-2D standard")
    pair(out, "before", "after", labels, SHOTS, "recommended")
    close_up(out, ["before", "after"], list(labels), "npc", "recommended_close_npc")
    camera = json.loads((out / "project_after" / SCENES / "start.json").read_text(encoding="utf-8"))
    return {"before": before, "after": after, "after_camera": camera["settings"]["hd2d"]["camera"]}


COMMANDS: dict[str, Callable[..., dict[str, Any]]] = {
    "recommended": recommended, "cameras": cameras, "sprites": sprites, "lighting": lighting, "indoor": indoor,
    "cost": cost, "play_cost": play_cost, "profile": profile}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=list(COMMANDS))
    parser.add_argument("out", type=Path)
    parser.add_argument("--camera", default=PREFERRED, choices=list(TREATMENTS))
    args = parser.parse_args()
    if args.command in ("sprites", "lighting"):
        report = COMMANDS[args.command](args.out, args.camera)
    else:
        report = COMMANDS[args.command](args.out)
    (args.out / f"{args.command}.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, default=str)[:6000])


if __name__ == "__main__":
    main()
