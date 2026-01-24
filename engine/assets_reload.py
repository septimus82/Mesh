from __future__ import annotations

from typing import Any


def reload_render_assets(window: Any) -> dict[str, int]:
    counts: dict[str, int] = {
        "asset_textures_cleared": 0,
        "render_queue_textures_cleared": 0,
        "render_queue_sprites_cleared": 0,
        "particle_textures_cleared": 0,
        "particle_sprites_cleared": 0,
        "tilemap_textures_cleared": 0,
        "tilemap_images_cleared": 0,
        "tilemap_batches_invalidated": 0,
        "fx_presets_reloaded": 0,
    }

    assets = getattr(window, "assets", None)
    if assets is not None:
        get_size = getattr(assets, "get_cache_size", None)
        clear = getattr(assets, "clear", None)
        if callable(get_size) and callable(clear):
            counts["asset_textures_cleared"] = int(get_size())
            clear()

    render_queue = getattr(window, "render_queue", None)
    renderer = getattr(render_queue, "renderer", None) if render_queue is not None else None
    if renderer is not None:
        clear_tex = getattr(renderer, "clear_texture_cache", None)
        if callable(clear_tex):
            counts["render_queue_textures_cleared"] = int(clear_tex())
        clear_sprites = getattr(renderer, "clear_sprite_cache", None)
        if callable(clear_sprites):
            counts["render_queue_sprites_cleared"] = int(clear_sprites())

    particle_manager = getattr(window, "particle_manager", None)
    if particle_manager is not None:
        clear_particles = getattr(particle_manager, "clear_render_cache", None)
        if callable(clear_particles):
            result = clear_particles()
            if isinstance(result, dict):
                for key, value in result.items():
                    try:
                        counts[str(key)] = int(value)
                    except Exception:
                        pass

    tilemap_manager = getattr(window, "tilemap_manager", None)
    if tilemap_manager is not None:
        clear_tex = getattr(tilemap_manager, "clear_texture_cache", None)
        if callable(clear_tex):
            counts["tilemap_textures_cleared"] = int(clear_tex())
        clear_imgs = getattr(tilemap_manager, "clear_tileset_images", None)
        if callable(clear_imgs):
            counts["tilemap_images_cleared"] = int(clear_imgs())

    scene_controller = getattr(window, "scene_controller", None)
    if scene_controller is not None:
        invalidate = getattr(scene_controller, "invalidate_tilemap_batches", None)
        if callable(invalidate):
            counts["tilemap_batches_invalidated"] = int(invalidate())

    if getattr(window, "fx_presets", None) is not None:
        try:
            from engine.fx_presets import build_fx_preset_registry  # noqa: PLC0415

            window.fx_presets = build_fx_preset_registry()
            counts["fx_presets_reloaded"] = 1
        except Exception:
            counts["fx_presets_reloaded"] = 0

    return counts
