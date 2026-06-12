# mypy: ignore-errors
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, cast

import engine.optional_arcade as optional_arcade
from engine.tilemap import TilemapInstance
from engine.tilemap_batch import TilemapBatchState
from engine.tilemap_batch_arcade import TilemapBatcher


def _clear_tilemap_batching(self) -> None:
    import engine.scene_controller as scene_controller_module

    batcher = self._tilemap_batcher
    if batcher is not None:
        try:
            batcher.clear()
        except Exception:
            scene_controller_module.logger.debug("Tilemap batcher clear failed", exc_info=True)
    self._tilemap_batcher = None
    self._tilemap_batch_state = None


def _clear_tilemap_layers(self) -> None:
    import engine.scene_controller as scene_controller_module

    self._clear_tilemap_batching()
    for sprite_list in self._tilemap_background_layers:
        sprite_list.clear()
    for sprite_list in self._tilemap_foreground_layers:
        sprite_list.clear()
    if self.tilemap_instance and self.tilemap_instance.collision_sprites:
        self.tilemap_instance.collision_sprites.clear()
    self._tilemap_background_layers = []
    self._tilemap_foreground_layers = []
    self._tilemap_draw_layers = []
    self._background_layers = []
    self.tilemap_instance = None
    self.navigation.invalidate()
    try:
        from engine.lighting.occluders import OCCLUDER_CACHE  # noqa: PLC0415

        OCCLUDER_CACHE.invalidate()
    except Exception:  # noqa: BLE001  # REASON: occluder cache invalidation failures should not block tilemap teardown
        scene_controller_module.logger.debug("Occluder cache invalidation failed", exc_info=True)


def _load_tilemap_layers(self, scene: Dict[str, Any], scene_dir: Path) -> None:
    import engine.scene_controller as scene_controller_module

    scene_controller_module._scene_load_apply_runtime.load_tilemap_layers(
        self,
        scene,
        scene_dir,
        load_tilemap_func=lambda *args, **kwargs: self.window.tilemap_manager.load_map(*args, **kwargs),
    )


def _init_tilemap_batching(self, instance: TilemapInstance) -> None:
    map_w, map_h = instance.map_size
    tile_w, tile_h = instance.tile_size
    if map_w <= 0 or map_h <= 0 or tile_w <= 0 or tile_h <= 0:
        self._clear_tilemap_batching()
        return
    chunk_size = int(getattr(self.window, "tilemap_chunk_size", 16) or 16)
    if chunk_size <= 0:
        chunk_size = 16
    state = TilemapBatchState(
        map_width=map_w,
        map_height=map_h,
        tile_width=tile_w,
        tile_height=tile_h,
        chunk_size_tiles=chunk_size,
    )
    for layer_id in instance.layer_data.keys():
        state.mark_layer_dirty(layer_id)
    self._tilemap_batch_state = state
    self._tilemap_batcher = TilemapBatcher(self.window, state)


def _apply_tilemap_world_bounds(self, instance: TilemapInstance) -> None:
    if instance is None:
        return
    map_w, map_h = instance.map_size
    tile_w, tile_h = instance.tile_size
    if map_w <= 0 or map_h <= 0 or tile_w <= 0 or tile_h <= 0:
        return
    width_px = int(map_w * tile_w)
    height_px = int(map_h * tile_h)

    if self.window.world_width is None or self.window.world_width <= 0:
        self.window.world_width = width_px
    if self.window.world_height is None or self.window.world_height <= 0:
        self.window.world_height = height_px

    if self.window.camera_controller.bounds is None and width_px > 0 and height_px > 0:
        self.window.camera_controller.bounds = (0.0, 0.0, float(width_px), float(height_px))


def _mark_tilemap_layer_dirty(self, layer_id: str) -> None:
    import engine.scene_controller as scene_controller_module

    state = self._tilemap_batch_state
    if state is None:
        return
    try:
        state.mark_layer_dirty_all(str(layer_id))
    except Exception:
        scene_controller_module.logger.debug("mark_tilemap_layer_dirty failed for %r", layer_id, exc_info=True)
        return


def invalidate_tilemap_batches(self) -> int:
    import engine.scene_controller as scene_controller_module

    count = 0
    if self._tilemap_batcher is not None:
        try:
            count = int(self._tilemap_batcher.invalidate_batches())
        except Exception:
            scene_controller_module.logger.debug("invalidate_tilemap_batches failed", exc_info=True)
            count = 0
    state = self._tilemap_batch_state
    if state is not None and count == 0:
        layer_ids = list(state.layer_versions.keys())
        for layer_id in layer_ids:
            state.mark_layer_dirty_all(layer_id)
        count = len(layer_ids)
    return count


def _mark_tilemap_tile_dirty(self, layer_id: str, col: int, row: int) -> None:
    import engine.scene_controller as scene_controller_module

    state = self._tilemap_batch_state
    if state is None:
        return
    try:
        state.mark_tile_dirty(str(layer_id), int(col), int(row))
    except Exception:
        scene_controller_module.logger.debug("mark_tilemap_tile_dirty failed layer=%r", layer_id, exc_info=True)
        return


def set_tile(self, layer_name: str, col: int, row: int, gid: int) -> tuple[int, int] | None:
    if not self.tilemap_instance:
        return None
    data = self.tilemap_instance.layer_data.get(layer_name)
    if data is None:
        return None
    width, height = self.tilemap_instance.layer_dimensions or (0, 0)
    if width <= 0 or height <= 0:
        return None
    if not (0 <= col < width and 0 <= row < height):
        return None
    index = row * width + col
    old_gid = int(data[index] if index < len(data) else 0)
    if gid == old_gid:
        return None
    if index >= len(data):
        return None
    data[index] = int(gid)
    sprites = self.tilemap_instance.layer_lookup.get(layer_name)
    tile_w, tile_h = self.tilemap_instance.tile_size
    offset = self.tilemap_instance.layer_offsets.get(layer_name, (0.0, 0.0))
    map_pixel_height = height * tile_h
    center_x = (col + 0.5) * tile_w + offset[0]
    center_y = map_pixel_height - ((row + 0.5) * tile_h) + offset[1]
    if sprites:
        for sprite in list(sprites):
            if abs(sprite.center_x - center_x) < 0.1 and abs(sprite.center_y - center_y) < 0.1:
                sprites.remove(sprite)
    if gid != 0 and sprites is not None:
        tileset = None
        for ts in self.tilemap_instance.tilesets:
            if ts.contains(gid):
                tileset = ts
                break
        if tileset:
            local_id = gid - tileset.first_gid
            tilemap_manager = cast(Any, self.window.tilemap_manager)
            texture = tilemap_manager._get_tile_texture(tileset, local_id)
            if texture:
                sprite = optional_arcade.arcade.Sprite()
                sprite.texture = texture
                sprite.center_x = center_x
                sprite.center_y = center_y
                sprite.scale = 1.0
                sprites.append(sprite)
    self._mark_tilemap_tile_dirty(layer_name, col, row)
    return (old_gid, gid)


def bind_tilemap_state_methods(cls) -> None:
    cls._load_tilemap_layers = _load_tilemap_layers
    cls._init_tilemap_batching = _init_tilemap_batching
    cls._apply_tilemap_world_bounds = _apply_tilemap_world_bounds
    cls._mark_tilemap_layer_dirty = _mark_tilemap_layer_dirty
    cls.invalidate_tilemap_batches = invalidate_tilemap_batches
    cls._mark_tilemap_tile_dirty = _mark_tilemap_tile_dirty
    cls.set_tile = set_tile
    cls._clear_tilemap_batching = _clear_tilemap_batching
    cls._clear_tilemap_layers = _clear_tilemap_layers
