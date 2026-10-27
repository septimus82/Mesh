"""Setting up and releasing a scene's HD-2D renderer (``window.hd2d_renderer``) on scene load and window close; the
game loop (``engine.game_runtime.tick``) updates and draws it. A scene without ``settings.hd2d`` never gets a
renderer, so 2D games are untouched. A scene whose structures carry collision (``engine.hd2d.glb``) also gets
``window.hd2d_world``: height-aware movement over its floors (``engine.hd2d.world``).

A scene whose HD-2D settings or models are broken still loads (drawn 2D) and the reason is logged and kept on
``window.hd2d_error``, so a bad .glb never takes the game down.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from engine.logging_tools import get_logger

logger = get_logger(__name__)


def release(window: Any) -> None:
    renderer = getattr(window, "hd2d_renderer", None)
    if renderer is not None:
        renderer.release()
    window.hd2d_renderer = None
    window.hd2d_world = None


def _contained(resolve: Any) -> Any:
    """``resolve`` (engine.paths.resolve_path), refusing a file that, links followed, lies outside every content
    root: a scene can name only the project's own assets."""
    from pathlib import Path  # noqa: PLC0415

    from engine.hd2d.settings import Hd2dSettingsError  # noqa: PLC0415
    from engine.paths import is_path_under_content_roots  # noqa: PLC0415

    def resolve_inside(rel: str) -> Path:
        path = Path(resolve(rel))
        if not is_path_under_content_roots(path):  # links followed
            raise Hd2dSettingsError(f"'{rel}' lies outside the project's content (a link out of it?)")
        return path

    return resolve_inside


def configure_scene(window: Any, settings: Any, scene: Any = None) -> None:
    """Called while a scene loads: drop the previous scene's renderer, make this one's if it asks for HD-2D."""
    release(window)
    window.hd2d_error = None
    window.hd2d_terrain_error = None
    window.hd2d_scatter_error = None
    window.hd2d_motion_error = None
    raw = settings.get("hd2d") if isinstance(settings, dict) else None
    if raw is None:
        return
    from engine.hd2d.glb import GlbError  # noqa: PLC0415  # only HD-2D scenes load the 3D code
    from engine.hd2d.renderer import Hd2dRenderer  # noqa: PLC0415
    from engine.hd2d.settings import Hd2dSettingsError, parse_hd2d, parse_scene_lights  # noqa: PLC0415
    from engine.paths import resolve_path  # noqa: PLC0415

    world = (settings.get("world_width"), settings.get("world_height"))
    map_size = (float(world[0]), float(world[1])) if all(isinstance(v, (int, float)) for v in world) else None
    try:
        hd2d = parse_hd2d(raw, map_size_px=map_size, lenient=True)
        if hd2d.terrain_error:  # broken sculpted heights: the room plays on flat ground, the reason kept and logged
            window.hd2d_terrain_error = hd2d.terrain_error
            logger.error("[Mesh][HD-2D] this room's ground is drawn %s: %s", "unpainted"
                         if hd2d.terrain_error.startswith("its paint") else "flat", hd2d.terrain_error)
        if hd2d.scatter_error:  # broken scatter: none drawn, the rest of the room stands; the reason logged and shown
            window.hd2d_scatter_error = hd2d.scatter_error
            logger.error("[Mesh][HD-2D] this room's scattered decoration is set aside: %s", hd2d.scatter_error)
        lights = scene.get("lights") if isinstance(scene, dict) else None
        hd2d = dataclasses.replace(hd2d, **parse_scene_lights(lights, settings))  # the room's own lights
        from engine.wind import WindError, parse_wind  # noqa: PLC0415

        if hd2d.motion_error:  # (its motion settings set aside: its decoration stands still)
            window.hd2d_motion_error = hd2d.motion_error
            logger.error("[Mesh][HD-2D] this room's decoration stands still: %s", hd2d.motion_error)
        try:  # the room's wind (Milestone 20E): its plants sway in it, as its rain falls in it
            hd2d = dataclasses.replace(hd2d, wind=parse_wind(settings.get("wind")))
        except WindError as exc:  # (still air, the reason kept: the room stands, its decoration flutters as in calm)
            window.hd2d_motion_error = window.hd2d_motion_error or f"its wind is set aside (still air): {exc}"
            logger.error("[Mesh][HD-2D] this room's wind is set aside (still air): %s", exc)
        window.hd2d_renderer = Hd2dRenderer(window, hd2d, _contained(resolve_path))
        models = window.hd2d_renderer.models
        sculpted = hd2d.ground is not None and hd2d.ground.terrain is not None  # Milestone 20A
        if sculpted or any(model.colliders for model in models.values()):  # floors and walls authored in the GLBs
            from engine.hd2d.world import World  # noqa: PLC0415

            window.hd2d_world = World(hd2d, models)
            if window.hd2d_renderer.terrain is not None:  # one set of heights: what is drawn is what is walked on
                window.hd2d_world.update_terrain(window.hd2d_renderer.terrain)
    except (Hd2dSettingsError, GlbError) as exc:
        window.hd2d_error = str(exc)
        logger.error("[Mesh][HD-2D] this scene is drawn 2D: %s", exc)
    except Exception as exc:  # noqa: BLE001  # REASON: a room's 3D build failing (a texture missing, the driver refusing) plays it 2D, said and logged, never takes the game or Studio down
        window.hd2d_renderer = window.hd2d_world = None
        window.hd2d_error = f"{type(exc).__name__}: {exc}"
        logger.error("[Mesh][HD-2D] this scene is drawn 2D: %s", window.hd2d_error, exc_info=True)

