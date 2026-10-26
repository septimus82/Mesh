"""Milestone 19B evidence: water that belongs to its place, in the HD-2D starter village (hidden windows only).

    py -3.13 tooling/m19b_water_study.py proof OUT     # comparisons, acceptance renders, places, gameplay, Studio
    py -3.13 tooling/m19b_water_study.py perf OUT      # GPU cost at 720p / 1080p / 4K per reflection setting; lifecycle

Pictures are the game's own camera at its own window size (1280 x 720), cropped 1:1 (never scaled), so what is judged
is what a player sees. The village is a project from the HD-2D RPG template, with water placed through the same checked
operations Studio and AI use (``project_ops.place_blank`` and ``set_water``), at ``PLACES`` (m).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
import hd2d_visual_study as study  # noqa: E402
import m19_water_study as m19  # noqa: E402
from hd2d_demo import SCENES, HiddenGame, _gl_counts  # noqa: E402

PX = 32.0
RAIN = m19.RAIN
# name: (preset, x m, y m, settings); the elevation (px) is the water's level
PLACES: dict[str, tuple[str, float, float, dict[str, Any]]] = {
    # where Stage 19A's pond stood, by the bridge, the shop's roof in front of it: Stage 19A's, or the natural pond
    "classic_pond": ("pond", 24.5, 18.5, {"width": 224, "height": 150}),
    "natural_pond": ("natural_pond", 24.5, 18.5, {}),
    # a second natural pond west of the north path, in the same picture as the classic one
    "west_pond": ("natural_pond", 14.8, 13.6, {"width": 160, "height": 96, "seed": 11}),
    # against the west plateau's cliff (it rises from y 22 m): its far side runs into the terrain's edge
    "cliff_pond": ("natural_pond", 10.5, 20.9, {"width": 192, "height": 112, "seed": 4}),
    # on the east-west path, and one half off it (turned)
    "path_puddle": ("muddy_puddle", 14.5, 7.1, {}),
    "edge_puddle": ("muddy_puddle", 17.2, 6.4, {"width": 60, "height": 36, "seed": 8, "rotation": 20}),
    "classic_puddle": ("puddle", 14.5, 7.1, {"width": 72, "height": 44}),
    # between the cottage and the north path
    "stone_pool": ("stone_pool", 15.5, 13.0, {"width": 144, "height": 112}),
    # under the bridge's deck (sheltered), and up on the east plateau (2 m up, its top)
    "under_bridge": ("muddy_puddle", 20.0, 23.4, {"width": 48, "height": 40}),
    "plateau_puddle": ("muddy_puddle", 28.5, 24.5, {"elevation": 64.0}),
}


def make_village(out: Path, name: str, waters: list[str], *, rain: bool = True, reflections: str | None = None,
                 extra: dict[str, dict[str, Any]] | None = None) -> Path:
    """The village with these of ``PLACES``' water (``extra`` changing some of their settings), and rain."""
    from engine import project_ops as ops

    project: Path = study.new_project(out, name, stage6a=False)
    path = project / SCENES / "start.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    for key in waters:
        preset, x, y, settings = PLACES[key]
        settings = {**settings, **(extra or {}).get(key, {})}
        elevation = settings.pop("elevation", None)
        scene, eid = ops.place_blank(scene, "start", key.replace("_", " ").title(), x * PX, y * PX)
        scene = ops.set_water(scene, eid, preset=preset, **settings)
        if elevation is not None:
            scene = ops.set_entity_fields(scene, eid, elevation=elevation)
    if rain:
        scene = ops.set_particles(scene, RAIN)
    if reflections:
        scene = ops.set_water_reflections(scene, reflections)
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    return project


def _open(out: Path, name: str, waters: list[str], size: tuple[int, int] = study.SIZE, **kw: Any) -> HiddenGame:
    game = HiddenGame(make_village(out, name, waters, **kw), size=size)
    game.load(f"{SCENES}/start.json")
    game.step(30)
    return game


def at_moment(game: HiddenGame, t: float) -> None:
    """Water and rain at moment ``t`` s (pictures to compare are of the same moment)."""
    game.window.water_time = t
    hd = game.window.hd2d_renderer
    if hd.particles is not None:
        hd.particles.time = t


def shot_at(game: HiddenGame, x: float, y: float, z: float = 0.0) -> Any:
    """The game's own camera, as it follows a player standing at (x, y) m."""
    return m19.shot(game, (x, y - 0.8, z + 0.8))


def _spot(key: str) -> tuple[float, float, float]:
    _preset, x, y, settings = PLACES[key]
    return x, y, float(settings.get("elevation", 0.0)) / PX


def _without_water(game: HiddenGame, x: float, y: float, z: float = 0.0, only: str | None = None) -> Any:
    """The same picture without the water (``only``: without that one, by name)."""
    bodies = game.window.water_bodies
    game.window.water_bodies = [b for b in bodies if only is not None
                                and str(getattr(b.entity, "mesh_name", "")).lower() != only]
    try:
        return shot_at(game, x, y, z)
    finally:
        game.window.water_bodies = bodies


def _texel_px(game: HiddenGame, x: float, y: float) -> float:
    """How many screen pixels one of the art's texels (1/32 m) spans at (x, y), the game's camera on it."""
    hd = game.window.hd2d_renderer
    hd.camera.target = (x, y - 0.8, 0.8)
    vp = hd.camera.view_projection(study.SIZE[0] / study.SIZE[1])

    def screen(px: float) -> float:
        c = [sum(vp[r][k] * (px, y, 0.0, 1.0)[k] for k in range(4)) for r in (0, 3)]
        return float(c[0] / c[1] * 0.5 * study.SIZE[0])

    return float(round((screen(x + 1.0) - screen(x)) / 32.0, 3))


# --- 1. the problems, side by side: Stage 19A against Stage 19B, the same place, camera and moment ---------------

PAIRS = {"pond": (["classic_pond"], ["natural_pond"], (24.5, 18.5)),
         "puddle": (["classic_puddle"], ["path_puddle", "edge_puddle"], (15.5, 7.0)),
         "stone_pool": ([], ["stone_pool"], (15.5, 13.0))}


def comparisons(out: Path) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for rain in (False, True):
        for name, (before, after, (x, y)) in PAIRS.items():
            pictures = []
            for i, waters in enumerate((before, after)):
                game = _open(out, f"cmp_{name}_{i}_{rain}", waters, rain=rain)
                try:
                    at_moment(game, 3.0)
                    pictures.append(shot_at(game, x, y))
                    if name == "pond" and not rain:
                        report.setdefault("texel_px", _texel_px(game, x, y))
                        report.setdefault("reflection", {})["19a" if i == 0 else "19b"] = _reflection_share(game, x, y)
                finally:
                    game.close()
            m19.m18_pair(pictures, ["Stage 19A" if before else "no water", "Stage 19B"],
                         out / f"compare_{name}_{'rain' if rain else 'dry'}.png")
    return report


def _reflection_share(game: HiddenGame, x: float, y: float) -> dict[str, float]:
    """How much the mirror changes the water: the same frame with the water's reflection set to 0, over the water's
    pixels (mean change per channel, 0-255, and the share of its pixels changed by more than 24)."""
    import numpy as np

    wet, dry = shot_at(game, x, y), _without_water(game, x, y)
    bodies = game.window.water_bodies
    kept = [b.water for b in bodies]
    for b in bodies:
        b.water = replace(b.water, reflection=0.0)
    try:
        flat = shot_at(game, x, y)
    finally:
        for b, w in zip(bodies, kept):
            b.water = w
    mask = m19._mask(wet, dry)
    diff = np.abs(np.asarray(wet, dtype=np.int16) - np.asarray(flat, dtype=np.int16))[mask]
    return {"water_pixels": int(mask.sum()), "mean_change": round(float(diff.mean()), 2),
            "share_changed_over_24": round(float((diff.max(axis=1) > 24).mean()), 3)}


# --- 6. acceptance renders -------------------------------------------------------------------------------------

def renders(out: Path) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for rain in (False, True):
        tag = "rain" if rain else "dry"
        game = _open(out, f"both_{tag}", ["classic_pond", "west_pond"], rain=rain)
        try:  # 1: Stage 19A's pond (east of the path) and a natural pond (west of it) in one picture
            at_moment(game, 3.0)
            shot_at(game, 19.6, 16.0).save(out / f"both_ponds_{tag}.png")
        finally:
            game.close()
        game = _open(out, f"village_{tag}", ["natural_pond", "path_puddle", "edge_puddle", "stone_pool"], rain=rain)
        try:  # 2-4: the muddy puddles on the path, the stone pool, the natural pond
            at_moment(game, 3.0)
            for name, (x, y) in (("puddles", (15.5, 7.0)), ("stone_pool", (15.5, 13.0)), ("natural_pond", (24.5, 18.5))):
                shot_at(game, x, y).save(out / f"{name}_{tag}.png")
            report[f"water_surfaces_{tag}"] = game.window.hd2d_renderer.stats()["water_surfaces"]
        finally:
            game.close()
    report["reflection_and_pan"] = pan(out)
    return report


def pan(out: Path) -> dict[str, Any]:
    """5: the camera moving over the natural pond with the player standing on its far bank (mirrored in it) and the
    plateau's cliff behind; the water's own clock running. A 1:1 clip, and the mirror on against off."""
    import m18_particles_study as m18

    game = _open(out, "pan", ["natural_pond"], rain=False)
    report: dict[str, Any] = {}
    try:
        player = game.player()
        player.center_x = 24.0 * PX
        player.center_y += 21.1 * PX - player.bottom
        game.step(2)
        frames = []
        for i in range(48):
            at_moment(game, 2.0 + i / 15)
            x = 22.5 + 4.0 * i / 47
            frames.append(m18.crop_at(shot_at(game, x, 18.6), study.SIZE[0] / 2, study.SIZE[1] / 2, (640, 360)))
        frames[0].save(out / "pond_pan.webp", save_all=True, append_images=frames[1:], duration=66, loop=0,
                       quality=88, method=6)
        at_moment(game, 3.0)
        bodies = game.window.water_bodies
        kept = [b.water for b in bodies]
        pictures = {}
        for value in (0.0, 0.3, 0.8):  # the creator's Reflection setting: none, the preset's, strong
            for b, w in zip(bodies, kept):
                b.water = replace(w, reflection=value)
            pictures[value] = shot_at(game, 24.5, 18.6)
        for b, w in zip(bodies, kept):
            b.water = w
        m19.m18_pair(list(pictures.values()), ["reflection 0", "reflection 0.3 (the natural pond's)", "reflection 0.8"],
                     out / "reflection.png")
        report = {"clip_frames": len(frames),
                  "mirrored_pixels": {str(v): int(m19._mask(pictures[v], pictures[0.0]).sum()) for v in (0.3, 0.8)}}
    finally:
        game.close()
    return report


# --- 5. places: roofs, under the bridge, an elevated floor, a terrain edge --------------------------------------

def _hidden(game: HiddenGame, key: str) -> tuple[int, int, Any, Any, Any]:
    """One water's pixels drawn, and those hidden by what stands in front (counted with the depth test off)."""
    hd = game.window.hd2d_renderer
    x, y, z = _spot(key)
    z = float(m19._body(game, key.replace("_", " ")).entity.mesh_entity_data.get("elevation", 0.0)) / PX
    wet, dry = shot_at(game, x, y, z), _without_water(game, x, y, z, only=key.replace("_", " "))
    hd.water.depth_test = False
    try:
        seen = shot_at(game, x, y, z)
    finally:
        hd.water.depth_test = True
    drawn, unhidden = m19._mask(wet, dry), m19._mask(seen, dry)
    return int(drawn.sum()), int((unhidden & ~drawn).sum()), dry, wet, seen


def places(out: Path) -> dict[str, Any]:
    report: dict[str, Any] = {}
    game = _open(out, "places", ["natural_pond", "cliff_pond", "plateau_puddle"], rain=False)
    try:
        at_moment(game, 3.0)
        for key, label in (("natural_pond", "roof"), ("cliff_pond", "cliff")):
            drawn, hidden, dry, wet, seen = _hidden(game, key)
            report[label] = {"water": key, "pixels_drawn": drawn, "pixels_hidden_by_what_stands_in_front": hidden}
            m19.m18_pair([wet, seen], [f"{key} (depth-tested)", f"{key}, depth test off"], out / f"place_{label}.png")
        # an elevated floor: the puddle at the plateau's top (2 m) is drawn; the same puddle at 0 m is inside the
        # plateau and hidden (the level is the water's elevation, as for any object)
        drawn_up, hidden_up, _dry, wet_up, _seen = _hidden(game, "plateau_puddle")
        body = m19._body(game, "plateau puddle")
        body.entity.mesh_entity_data["elevation"] = 0.0
        drawn_down, hidden_down, _dry2, _wet2, _seen2 = _hidden(game, "plateau_puddle")
        body.entity.mesh_entity_data["elevation"] = 64.0
        report["elevated_floor"] = {"at_2m_drawn": drawn_up, "at_2m_hidden": hidden_up, "at_0m_drawn": drawn_down,
                                    "at_0m_hidden": hidden_down}
        m19.m18_pair([_dry, wet_up], ["the east plateau (2 m up)", "a muddy puddle on it"], out / "place_plateau.png")
    finally:
        game.close()
    report["bridge"] = sheltered(out)
    return report


def sheltered(out: Path) -> dict[str, Any]:
    """Rain rings open water and not water under the bridge's deck (Stage 18B's map), for the 19B material: ripple
    pixels with the rings on against off, judged with the depth test off (the deck hides the puddle anyway), and the
    negative control with its shelter switched off."""
    game = _open(out, "bridge", ["under_bridge", "path_puddle"], rain=True)
    report: dict[str, Any] = {}
    try:
        hd = game.window.hd2d_renderer
        hd.draw(read=True)
        hd.water.depth_test = False
        for key, shelter in (("path_puddle", True), ("under_bridge", True), ("under_bridge", False)):
            hd.water.shelter = shelter
            name = key.replace("_", " ")
            x, y, z = _spot(key)
            counts = []
            for t in (3.0, 3.4, 3.8):
                at_moment(game, t)
                m19._with_ripples(game, True)
                on = shot_at(game, x, y, z)
                m19._with_ripples(game, False, only=name)
                off = shot_at(game, x, y, z)
                m19._with_ripples(game, True)
                counts.append(int(m19._mask(on, off).sum()))
            report[key if shelter else f"{key}_negative_control_shelter_off"] = counts
        hd.water.depth_test, hd.water.shelter = True, True
    finally:
        game.close()
    return report


# --- 5. gameplay kept: footsteps, blocking (a turned natural pond), ripple strength -----------------------------

def gameplay(out: Path) -> dict[str, Any]:
    from hd2d_floors_demo import _feet, hold_key

    report: dict[str, Any] = {}
    game = _open(out, "steps", ["path_puddle"], rain=False)
    try:  # the player walks east-west along the path through the muddy puddle
        player = game.player()
        x, y, _z = _spot("path_puddle")
        keys = game.arcade.key
        player.center_x = (x + 3.0) * PX
        player.center_y += y * PX - player.bottom
        game.step(10)
        behaviour = next(b for b in m19._body(game, "path puddle").entity.mesh_behaviours_runtime
                         if type(b).__name__ == "WaterSurface")
        before = behaviour.steps
        hold_key(game, player, keys.LEFT, 0, x - 3.0, 400)
        bus = getattr(game.window, "event_bus", None)
        names = bus.get_recent_event_names(200) if bus is not None and hasattr(bus, "get_recent_event_names") else []
        report["steps"] = {"through_the_muddy_puddle": behaviour.steps - before,
                           "water_step_events": sum(1 for n in names if n == "water_step")}
    finally:
        game.close()
    for walkable in (True, False):  # a natural pond turned 30 degrees: waded, or blocking at the box round it
        game = _open(out, f"block_{walkable}", ["natural_pond"], rain=False,
                     extra={"natural_pond": {"rotation": 30, "walkable": walkable}})
        try:
            from engine import water as water_mod

            x, y, _z = _spot("natural_pond")
            w = m19._body(game, "natural pond").water
            half_h = water_mod.extent(w)[1] / PX / 2
            player = game.player()
            player.center_x = x * PX
            player.center_y += (y - half_h - 1.5) * PX - player.bottom
            game.step(5)
            hold_key(game, player, game.arcade.key.UP, 1, y, 240)
            report["walkable" if walkable else "blocking"] = {"box_south_edge_m": round(y - half_h, 2),
                                                              "centre_m": y, "feet_reached_m": round(_feet(player)[1], 2)}
        finally:
            game.close()
    game = _open(out, "ripple_strength", ["natural_pond"], rain=True)
    try:  # how much rain's rings change the natural pond at ripple strength 1, 0.5 and 0 (summed per channel)
        import numpy as np

        x, y, _z = _spot("natural_pond")
        body = m19._body(game, "natural pond")
        kept = body.water
        at_moment(game, 3.0)
        body.water = replace(kept, rain_ripples=False)
        calm = np.asarray(shot_at(game, x, y), dtype=np.int32)
        strength = {}
        for value in (1.0, 0.5, 0.0):
            body.water = replace(kept, ripples=value)
            strength[str(value)] = int(np.abs(np.asarray(shot_at(game, x, y), dtype=np.int32) - calm).sum())
        body.water = kept
        report["ripple_change_by_strength"] = strength
    finally:
        game.close()
    return report


# --- 6. Studio: placing and adjusting water through its own buttons, fields and keys -----------------------------

def studio_workflow(out: Path) -> dict[str, Any]:
    import os

    import hd2d_studio_demo

    from engine import project_ops as ops

    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    project = make_village(out, "studio", [], rain=True)
    report: dict[str, Any] = {}
    d = hd2d_studio_demo.StudioDriver(project)
    try:
        studio, k = d.studio, d.arcade.key
        spot = (24.5, 18.5, 0.0)
        d.button("Water")
        at = d.screen(spot)
        d.window.dispatch_event("on_mouse_motion", *at, 0, 0)
        d.frame()
        d.click(*at)
        wid = studio.selected

        def now() -> dict[str, Any]:
            found = ops.water_of(ops.find_entity(studio.project.scene(), wid))
            assert found is not None, "it is water"
            return found

        report["placed"] = {k2: now()[k2] for k2 in ("preset", "shape", "shore")}
        d.frame(2).convert("RGB").save(out / "studio_1_placed.png")
        d.button("Natural pond")
        d.type_into("water_w", "200")
        d.type_into("water_h", "128")
        d.button("+15")
        d.button("+15")
        d.button("New natural outline")
        report["adjusted"] = {k2: now()[k2] for k2 in ("preset", "width", "height", "rotation", "seed", "shore")}
        d.button("Stone")
        d.type_into("water_depth", "0.8")
        d.type_into("water_deep", "#16324a")
        report["stone_bank"] = {k2: now()[k2] for k2 in ("shore", "depth", "deep_colour")}
        d.button("Half size")
        report["room_reflections"] = (studio.project.scene()["settings"]["hd2d"]).get("water_reflections")
        frames = [d.frame(2).convert("RGB") for _ in range(2)]
        frames[-1].save(out / "studio_2_adjusted.png")
        report["drawn_and_moving"] = int(m19._mask(*frames).sum())
        d.key(k.Z, k.MOD_CTRL)
        undone = (studio.project.scene()["settings"]["hd2d"]).get("water_reflections", "full")
        d.key(k.Z, k.MOD_CTRL)
        report["undo"] = {"reflections": undone, "deep_colour": now()["deep_colour"]}
        d.key(k.Y, k.MOD_CTRL)
        d.key(k.Y, k.MOD_CTRL)
        report["redo"] = {"reflections": (studio.project.scene()["settings"]["hd2d"]).get("water_reflections"),
                          "deep_colour": now()["deep_colour"]}
        studio.select(None)
        d.click(*d.screen(spot))
        report["clicked_in_3d_selects_it"] = studio.selected == wid
        d.key(k.S, k.MOD_CTRL)
        report["saved_dirty_after"] = studio.project.is_dirty
        report["expected"] = now()
    finally:
        d.close()
    d = hd2d_studio_demo.StudioDriver(project)
    try:
        report["reopened_same"] = ops.water_of(ops.find_entity(d.studio.project.scene(), wid)) == report["expected"]
        d.key(d.arcade.key.F4)
        d.frame(20)
        report["in_play"] = {"mode": d.studio.mode, "water_surfaces": len(getattr(d.window, "water_bodies", [])),
                             "reflections": d.renderer.settings.water_reflections if d.renderer else None}
        d.key(d.arcade.key.F4)
        d.frame(3)
        report["after_stop_mode"] = d.studio.mode
    finally:
        d.close()
    return report


def two_d(out: Path) -> dict[str, Any]:
    """The new presets in an ordinary 2D room (the blank template), in rain: drawn under the player, banks and all."""
    from engine import project_ops as ops
    from engine.project_scaffold import create_project

    project = out / "Plain2D"
    create_project(project, "Plain2D", template_id="blank")
    path = project / "packs" / "core_regions" / "scenes" / "start.json"
    scene = json.loads(path.read_text(encoding="utf-8"))
    player = next(e for e in scene["entities"] if e.get("tag") == "player" or e.get("prefab_id") == "player")
    px, py = float(player["x"]), float(player["y"])
    for name, preset, dx, dy in (("Puddle", "muddy_puddle", 0, -10), ("Pond", "natural_pond", 40, 230),
                                 ("Pool", "stone_pool", 250, 70)):
        scene, wid = ops.place_blank(scene, "start", name, px + dx, py + dy)
        scene = ops.set_water(scene, wid, preset=preset, width=88 if preset == "muddy_puddle" else 200,
                              height=56 if preset == "muddy_puddle" else 128)
    scene = ops.set_particles(scene, RAIN)
    path.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    game = HiddenGame(project, size=(960, 540))
    report: dict[str, Any] = {}
    try:
        game.load("packs/core_regions/scenes/start.json")
        game.step(60)
        wet = game.draw().convert("RGB")
        bodies = game.window.water_bodies
        game.window.water_bodies = []
        dry = game.draw().convert("RGB")
        game.window.water_bodies = bodies
        mask = m19._mask(wet, dry)
        p = game.player()
        box = (int(p.left), int(540 - p.top), int(p.right), int(540 - p.bottom))
        report = {"water_pixels": int(mask.sum()), "player_pixels_changed_by_water": int(mask[box[1]:box[3], box[0]:box[2]].sum()),
                  "error": getattr(game.window, "scene_water_error", None)}
        from PIL import Image

        sheet = Image.new("RGB", (1920, 540))
        sheet.paste(dry, (0, 0))
        sheet.paste(wet, (960, 0))
        sheet.save(out / "two_d_water.png")
    finally:
        game.close()
    return report


def proof(out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    for name, step in (("comparisons", comparisons), ("renders", renders), ("places", places),
                       ("gameplay", gameplay), ("two_d", two_d), ("studio", studio_workflow)):
        report[name] = step(out)
        print(name, json.dumps(report[name]), flush=True)
    (out / "proof.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


# --- performance: 720p / 1080p / 4K, each reflection setting; GPU objects over loads, edits, Play/Stop ------------

SIZES = {"720p": (1280, 720), "1080p": (1920, 1080), "4k": (3840, 2160)}


def perf(out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"method": "per resolution one game: the village in rain (4,000 drops) with the natural pond, "
                                        "the stone pool and two muddy puddles, the camera on the natural pond; after "
                                        "300 drawn warm-up frames, 5 rounds, each measuring every reflection setting in "
                                        "turn (so all three see the same GPU clocks): the water pass's GPU time by a "
                                        "timer query round it (its frame copy included), the whole frame's GPU time "
                                        "with and without the water, and the water step's CPU time; medians",
                              "cases": {}}
    waters = ["natural_pond", "stone_pool", "path_puddle", "edge_puddle"]
    modes = ("full", "half", "sky")
    for size_name, size in SIZES.items():
        game = _open(out, f"perf_{size_name}", waters, size=size)
        try:
            ctx = game.window.ctx
            report.setdefault("gpu", {"renderer": ctx.info.RENDERER, "gl_version": list(ctx.gl_version)})
            player = game.player()  # the camera follows the player: put them by the natural pond
            player.center_x = 24.5 * PX
            player.center_y += 16.0 * PX - player.bottom
            for _ in range(300):  # warm-up, drawn (step alone doesn't draw): the GPU at its working clocks
                game.window.dispatch_event("on_update", 1 / 60)
                game.window.dispatch_event("on_draw")
            hd = game.window.hd2d_renderer
            bodies = list(game.window.water_bodies)
            rows: dict[str, dict[str, list[float]]] = {m: {"pass": [], "cpu": [], "with": [], "without": []} for m in modes}
            for _round in range(5):
                for mode in modes:
                    hd.settings = replace(hd.settings, water_reflections=mode)
                    for _ in range(10):
                        game.window.dispatch_event("on_update", 1 / 60)
                        game.window.dispatch_event("on_draw")
                    rows[mode]["pass"].append(m19._water_gpu_ms(game, 20))
                    rows[mode]["cpu"].append(m19._water_cpu_ms(game, 20))
                    rows[mode]["with"].append(m19._frame_gpu_ms(game, 20))
                    game.window.water_bodies = []
                    rows[mode]["without"].append(m19._frame_gpu_ms(game, 20))
                    game.window.water_bodies = bodies
            for mode in modes:
                hd.settings = replace(hd.settings, water_reflections=mode)
                game.window.dispatch_event("on_draw")
                stats = hd.stats()
                med = statistics.median
                r = rows[mode]
                case = {"water_surfaces": len(bodies), "draw_calls": stats["draw_calls"], "water_bytes": stats["water_bytes"],
                        "water_pass_gpu_ms": round(med(r["pass"]), 3), "water_draw_cpu_ms": round(med(r["cpu"]), 3),
                        "frame_gpu_ms_with": round(med(r["with"]), 3), "frame_gpu_ms_without": round(med(r["without"]), 3),
                        "water_pass_gpu_ms_rounds": [round(v, 3) for v in r["pass"]]}
                report["cases"][f"{size_name}_{mode}"] = case
                print(size_name, mode, case, flush=True)
        finally:
            game.close()
    report["lifecycle"] = lifecycle(out)
    (out / "perf.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def lifecycle(out: Path) -> dict[str, Any]:
    """GPU objects (after ``ctx.gc()``) over 10 room changes, over the reflection settings switched back and forth
    (each a room reload; sky frees the frame copy), and in Studio over 10 water edits and 5 Play/Stop."""
    import os

    import hd2d_studio_demo

    from engine import project_ops as ops

    report: dict[str, Any] = {}
    game = _open(out, "life", ["natural_pond", "stone_pool", "path_puddle"])
    try:
        ctx = game.window.ctx
        game.window.dispatch_event("on_draw")
        ctx.gc()
        before = _gl_counts(ctx)
        for _ in range(10):
            game.load(f"{SCENES}/cottage.json")
            game.step(3)
            game.window.dispatch_event("on_draw")
            game.load(f"{SCENES}/start.json")
            game.step(3)
            game.window.dispatch_event("on_draw")
        ctx.gc()
        report["room_changes_10"] = {"before": before, "after": _gl_counts(ctx)}
        layer = game.window.hd2d_renderer.water
        sizes = {}
        for _round in range(3):
            for mode in ("full", "half", "sky"):
                game.window.hd2d_renderer.settings = replace(game.window.hd2d_renderer.settings, water_reflections=mode)
                game.window.dispatch_event("on_draw")
                sizes[mode] = layer.memory_bytes()
        game.window.hd2d_renderer.settings = replace(game.window.hd2d_renderer.settings, water_reflections="full")
        game.window.dispatch_event("on_draw")
        ctx.gc()
        report["reflection_settings_switched_9"] = {"after": _gl_counts(ctx), "water_bytes": sizes}
    finally:
        game.close()
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    driver = hd2d_studio_demo.StudioDriver(make_village(out, "life_studio", ["natural_pond", "stone_pool"]))
    try:
        rows = {"start": driver.gl_counts()}
        pond = next(e["id"] for e in ops.entities(driver.studio.project.scene()) if e.get("name") == "Natural Pond")
        for i in range(10):
            driver.studio._edit(lambda s, i=i: ops.set_water(s, pond, rotation=10 * i, seed=i + 1), "")
            driver.frame(2)
        rows["after_10_edits"] = driver.gl_counts()
        for mode in ("half", "sky", "full"):
            driver.studio._edit(lambda s, mode=mode: ops.set_water_reflections(s, mode), "")
            driver.frame(2)
        rows["after_3_reflection_changes"] = driver.gl_counts()
        f4 = driver.arcade.key.F4
        for cycles in (5, 5):  # the first Play makes the game's own objects once (as in Stage 19A): then level
            for _ in range(cycles):
                driver.key(f4)
                driver.frame(10)
                driver.key(f4)
                driver.frame(3)
            rows["after_5_play_stop" if "after_5_play_stop" not in rows else "after_10_play_stop"] = driver.gl_counts()
        report["studio"] = rows
    finally:
        driver.close()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["proof", "perf", "comparisons", "renders", "places", "gameplay", "two_d",
                                            "studio"])
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    steps = {"proof": proof, "perf": perf, "comparisons": comparisons, "renders": renders, "places": places,
             "gameplay": gameplay, "two_d": two_d, "studio": studio_workflow}
    result = steps[args.command](args.out)
    if args.command not in ("proof", "perf"):
        print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
