from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade
from engine.tilemap_batch import TilemapBatchState, TilemapBatchStats
from engine.swallowed_exceptions import _log_swallow


class TilemapBatcher:
    def __init__(self, window: Any, state: TilemapBatchState) -> None:
        self.window = window
        self.state = state
        self.available = optional_arcade.arcade is not None
        self._layer_chunks: dict[str, dict[tuple[int, int], Any]] = {}

    def clear(self) -> None:
        if self._layer_chunks:
            for chunks in self._layer_chunks.values():
                for sprite_list in chunks.values():
                    try:
                        sprite_list.clear()
                    except Exception:
                        _log_swallow("TILE-001", "engine/tilemap_batch_arcade.py pass-only blanket swallow")
                        pass
        self._layer_chunks.clear()

    def invalidate_batches(self) -> int:
        layer_ids = list(self.state.layer_versions.keys())
        self.clear()
        for layer_id in layer_ids:
            self.state.mark_layer_dirty_all(layer_id)
        return len(layer_ids)

    def draw_layer(
        self,
        *,
        layer_id: str,
        sprites: Any,
        rect: tuple[float, float, float, float],
        offset: tuple[float, float] = (0.0, 0.0),
    ) -> TilemapBatchStats:
        stats = TilemapBatchStats()
        if not self.available or optional_arcade.arcade is None:
            return stats

        layer_id = str(layer_id)
        chunks = self._layer_chunks.setdefault(layer_id, {})
        visible = self.state.compute_visible_chunks(layer_id, rect, offset=offset)
        if not visible:
            return stats

        for key in visible:
            chunk_key = (key.chunk_x, key.chunk_y)
            sprite_list = chunks.get(chunk_key)
            if sprite_list is None or self.state.consume_dirty_flag(layer_id, key.chunk_x, key.chunk_y):
                sprite_list = self._build_chunk(
                    layer_id=layer_id,
                    sprites=sprites,
                    chunk_x=key.chunk_x,
                    chunk_y=key.chunk_y,
                    offset=offset,
                )
                chunks[chunk_key] = sprite_list
                self.state.mark_chunk_built(layer_id, key.chunk_x, key.chunk_y)
            if sprite_list is None or len(sprite_list) == 0:
                continue
            sprite_list.draw()
            stats.chunks_drawn += 1
            stats.draw_calls += 1
            stats.sprites_drawn += len(sprite_list)
        return stats

    def _build_chunk(
        self,
        *,
        layer_id: str,
        sprites: Any,
        chunk_x: int,
        chunk_y: int,
        offset: tuple[float, float],
    ) -> Any:
        sprite_list = optional_arcade.arcade.SpriteList()
        if sprites is None:
            return sprite_list

        tile_w = self.state.tile_width
        tile_h = self.state.tile_height
        map_w = self.state.map_width
        map_h = self.state.map_height
        if tile_w <= 0 or tile_h <= 0 or map_w <= 0 or map_h <= 0:
            return sprite_list

        chunk_size = max(1, int(self.state.chunk_size_tiles))
        col_start = int(chunk_x * chunk_size)
        row_start = int(chunk_y * chunk_size)
        col_end = min(map_w, col_start + chunk_size)
        row_end = min(map_h, row_start + chunk_size)

        offset_x, offset_y = float(offset[0]), float(offset[1])
        map_pixel_height = self.state.map_pixel_height
        left = offset_x + col_start * tile_w
        right = offset_x + col_end * tile_w
        top = map_pixel_height - row_start * tile_h + offset_y
        bottom = map_pixel_height - row_end * tile_h + offset_y

        min_x = min(left, right)
        max_x = max(left, right)
        min_y = min(bottom, top)
        max_y = max(bottom, top)

        for sprite in sprites:
            center_x = float(getattr(sprite, "center_x", 0.0))
            center_y = float(getattr(sprite, "center_y", 0.0))
            if center_x < min_x or center_x > max_x:
                continue
            if center_y < min_y or center_y > max_y:
                continue
            sprite_list.append(sprite)
        return sprite_list
