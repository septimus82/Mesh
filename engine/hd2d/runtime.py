"""Setting up and releasing a scene's HD-2D renderer (``window.hd2d_renderer``) on scene load and window close; the
game loop (``engine.game_runtime.tick``) updates and draws it. A scene without ``settings.hd2d`` never gets a
renderer, so 2D games are untouched. A scene whose structures carry collision (``engine.hd2d.glb``) also gets
``window.hd2d_world``: height-aware movement over its floors (``engine.hd2d.world``).

A scene whose HD-2D settings or models are broken still loads (drawn 2D) and the reason is logged and kept on
``window.hd2d_error``, so a bad .glb never takes the game down.
"""

from __future__ import annotations

from typing import Any

from engine.logging_tools import get_logger

logger = get_logger(__name__)


def release(window: Any) -> None:
    renderer = getattr(window, "hd2d_renderer", None)
    if renderer is not None:
        renderer.release()
    window.hd2d_renderer = None
    window.hd2d_world = None


def configure_scene(window: Any, settings: Any) -> None:
    """Called while a scene loads: drop the previous scene's renderer, make this one's if it asks for HD-2D."""
    release(window)
    window.hd2d_error = None
    raw = settings.get("hd2d") if isinstance(settings, dict) else None
    if raw is None:
        return
    from engine.hd2d.glb import GlbError  # noqa: PLC0415  # only HD-2D scenes load the 3D code
    from engine.hd2d.renderer import Hd2dRenderer  # noqa: PLC0415
    from engine.hd2d.settings import Hd2dSettingsError, parse_hd2d  # noqa: PLC0415
    from engine.paths import resolve_path  # noqa: PLC0415

    world = (settings.get("world_width"), settings.get("world_height"))
    map_size = (float(world[0]), float(world[1])) if all(isinstance(v, (int, float)) for v in world) else None
    try:
        hd2d = parse_hd2d(raw, map_size_px=map_size)
        window.hd2d_renderer = Hd2dRenderer(window, hd2d, resolve_path)
        models = window.hd2d_renderer.models
        if any(model.colliders for model in models.values()):  # floors and walls authored in the GLBs
            from engine.hd2d.world import World  # noqa: PLC0415

            window.hd2d_world = World(hd2d, models)
    except (Hd2dSettingsError, GlbError) as exc:
        window.hd2d_error = str(exc)
        logger.error("[Mesh][HD-2D] this scene is drawn 2D: %s", exc)

