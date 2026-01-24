from __future__ import annotations

from engine.assets_reload import reload_render_assets


class _StubAssets:
    def __init__(self) -> None:
        self.cleared = False

    def get_cache_size(self) -> int:
        return 3

    def clear(self) -> None:
        self.cleared = True


class _StubRenderer:
    def clear_texture_cache(self) -> int:
        return 5

    def clear_sprite_cache(self) -> int:
        return 7


class _StubRenderQueue:
    def __init__(self) -> None:
        self.renderer = _StubRenderer()


class _StubParticleManager:
    def clear_render_cache(self) -> dict[str, int]:
        return {"particle_textures_cleared": 11, "particle_sprites_cleared": 13}


class _StubTilemapManager:
    def clear_texture_cache(self) -> int:
        return 17

    def clear_tileset_images(self) -> int:
        return 19


class _StubSceneController:
    def invalidate_tilemap_batches(self) -> int:
        return 23


class _StubWindow:
    def __init__(self) -> None:
        self.assets = _StubAssets()
        self.render_queue = _StubRenderQueue()
        self.particle_manager = _StubParticleManager()
        self.tilemap_manager = _StubTilemapManager()
        self.scene_controller = _StubSceneController()


def test_assets_reload_clears_caches() -> None:
    window = _StubWindow()
    counts = reload_render_assets(window)
    assert counts["asset_textures_cleared"] == 3
    assert counts["render_queue_textures_cleared"] == 5
    assert counts["render_queue_sprites_cleared"] == 7
    assert counts["particle_textures_cleared"] == 11
    assert counts["particle_sprites_cleared"] == 13
    assert counts["tilemap_textures_cleared"] == 17
    assert counts["tilemap_images_cleared"] == 19
    assert counts["tilemap_batches_invalidated"] == 23
    assert window.assets.cleared is True
