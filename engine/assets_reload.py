from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.logging_tools import get_logger


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)

logger = get_logger(__name__)

_SHADER_EXTENSIONS: tuple[str, ...] = (".glsl", ".vert", ".frag")
_IMAGE_EXTENSIONS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp")
_AUDIO_EXTENSIONS: tuple[str, ...] = (".wav", ".ogg", ".mp3")


def _has_shader_changes(changed_paths: tuple[str, ...] | None) -> bool:
    if changed_paths is None:
        return True
    for path in changed_paths:
        suffix = Path(str(path)).suffix.lower()
        if suffix in _SHADER_EXTENSIONS:
            return True
    return False


def _iter_changed_image_paths(changed_paths: tuple[str, ...] | None) -> tuple[str, ...]:
    if changed_paths is None:
        return ()
    image_paths: set[str] = set()
    for path in changed_paths:
        normalized = str(path or "").strip()
        if not normalized:
            continue
        suffix = Path(normalized).suffix.lower()
        if suffix in _IMAGE_EXTENSIONS:
            image_paths.add(normalized)
    return tuple(sorted(image_paths))


def _iter_changed_audio_paths(changed_paths: tuple[str, ...] | None) -> tuple[str, ...]:
    if changed_paths is None:
        return ()
    audio_paths: set[str] = set()
    for path in changed_paths:
        normalized = str(path or "").strip()
        if not normalized:
            continue
        suffix = Path(normalized).suffix.lower()
        if suffix in _AUDIO_EXTENSIONS:
            audio_paths.add(normalized)
    return tuple(sorted(audio_paths))


def _reload_changed_asset_textures(window: Any, image_paths: tuple[str, ...]) -> tuple[int, int]:
    if not image_paths:
        return (0, 0)

    assets = getattr(window, "assets", None)
    if assets is None:
        return (0, 0)

    cache = getattr(assets, "_textures", None)
    resolver = getattr(assets, "_resolve_path", None)
    loader = getattr(assets, "_load_texture_internal", None)
    if not isinstance(cache, dict) or not callable(resolver) or not callable(loader):
        return (0, 0)

    reloaded = 0
    failed = 0
    for image_path in image_paths:
        try:
            cache_key = str(resolver(image_path))
        except Exception:
            _log_swallow("ASSE-002", "texture cache key resolve fallback", once=True)
            cache_key = str(image_path)

        had_previous = cache_key in cache
        previous_texture = cache.get(cache_key)
        try:
            texture = loader(cache_key)
        except Exception as exc:  # noqa: BLE001
            _log_swallow("ASSE-003", "texture reload fallback", once=True)
            logger.warning("[Mesh][HotReload] texture reload failed for '%s': %s", image_path, exc)
            texture = None
        if texture is None:
            failed += 1
            if had_previous:
                cache[cache_key] = previous_texture
            continue
        cache[cache_key] = texture
        reloaded += 1
    return (reloaded, failed)


def reload_render_assets(
    window: Any,
    *,
    changed_paths: tuple[str, ...] | None = None,
) -> dict[str, int]:
    counts: dict[str, int] = {
        "asset_textures_cleared": 0,
        "asset_textures_reloaded": 0,
        "asset_textures_failed": 0,
        "audio_reloaded": 0,
        "audio_failed": 0,
        "render_queue_textures_cleared": 0,
        "render_queue_sprites_cleared": 0,
        "particle_textures_cleared": 0,
        "particle_sprites_cleared": 0,
        "tilemap_textures_cleared": 0,
        "tilemap_images_cleared": 0,
        "tilemap_batches_invalidated": 0,
        "fx_presets_reloaded": 0,
        "shader_programs_reloaded": 0,
        "shader_programs_failed": 0,
    }

    image_changed_paths = _iter_changed_image_paths(changed_paths)
    audio_changed_paths = _iter_changed_audio_paths(changed_paths)
    texture_reloaded = 0
    texture_failed = 0
    used_safe_texture_reload = False
    if image_changed_paths:
        texture_reloaded, texture_failed = _reload_changed_asset_textures(window, image_changed_paths)
        used_safe_texture_reload = bool(texture_reloaded or texture_failed)
        counts["asset_textures_reloaded"] = int(texture_reloaded)
        counts["asset_textures_failed"] = int(texture_failed)

    if audio_changed_paths:
        audio_manager = getattr(window, "audio", None)
        invalidate_muffled_variant_cache = getattr(audio_manager, "invalidate_muffled_variant_cache_for_path", None)
        if callable(invalidate_muffled_variant_cache):
            for audio_path in audio_changed_paths:
                try:
                    invalidate_muffled_variant_cache(audio_path)
                except Exception as exc:  # noqa: BLE001
                    _log_swallow("ASSE-004", "audio muffled variant cache invalidate fallback", once=True)
                    logger.warning("[Mesh][HotReload] muffled variant cache invalidate failed: %s", exc)
        reload_cached_sounds = getattr(audio_manager, "reload_cached_sounds", None)
        if callable(reload_cached_sounds):
            try:
                audio_reloaded, audio_failed = reload_cached_sounds(audio_changed_paths)
            except Exception as exc:  # noqa: BLE001
                _log_swallow("ASSE-005", "audio reload fallback", once=True)
                logger.warning("[Mesh][HotReload] audio reload failed: %s", exc)
                audio_reloaded, audio_failed = 0, 0
            counts["audio_reloaded"] = int(audio_reloaded or 0)
            counts["audio_failed"] = int(audio_failed or 0)

    assets = getattr(window, "assets", None)
    if assets is not None and not used_safe_texture_reload:
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
                        _log_swallow("ASSE-001", "engine/assets_reload.py pass-only blanket swallow")
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
            _log_swallow("ASSE-006", "fx presets rebuild fallback", once=True)
            counts["fx_presets_reloaded"] = 0

    if _has_shader_changes(changed_paths):
        post_process_pipeline = getattr(window, "post_process_pipeline", None)
        reload_shaders = getattr(post_process_pipeline, "reload_shaders", None)
        if callable(reload_shaders):
            try:
                shader_counts = reload_shaders(window, changed_paths=changed_paths)
            except Exception as exc:  # noqa: BLE001
                _log_swallow("ASSE-007", "shader reload fallback", once=True)
                logger.warning("[Mesh][HotReload] shader reload failed: %s", exc)
            else:
                if isinstance(shader_counts, dict):
                    for key in ("shader_programs_reloaded", "shader_programs_failed"):
                        value = shader_counts.get(key)
                        if value is None:
                            continue
                        try:
                            counts[key] = int(value)
                        except (TypeError, ValueError):
                            continue

    setattr(
        window,
        "_last_hot_reload_stats",
        {
            "shader_reloaded": int(counts.get("shader_programs_reloaded", 0) or 0),
            "shader_failed": int(counts.get("shader_programs_failed", 0) or 0),
            "textures_reloaded": int(counts.get("asset_textures_reloaded", 0) or 0),
            "textures_failed": int(counts.get("asset_textures_failed", 0) or 0),
            "audio_reloaded": int(counts.get("audio_reloaded", 0) or 0),
            "audio_failed": int(counts.get("audio_failed", 0) or 0),
        },
    )

    return counts
