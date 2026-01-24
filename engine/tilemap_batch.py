from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TileChunkKey:
    layer_id: str
    chunk_x: int
    chunk_y: int


@dataclass(slots=True)
class TilemapBatchStats:
    chunks_drawn: int = 0
    sprites_drawn: int = 0
    draw_calls: int = 0

    def add(self, other: "TilemapBatchStats") -> None:
        self.chunks_drawn += int(other.chunks_drawn)
        self.sprites_drawn += int(other.sprites_drawn)
        self.draw_calls += int(other.draw_calls)


@dataclass(slots=True)
class TilemapBatchState:
    map_width: int
    map_height: int
    tile_width: int
    tile_height: int
    chunk_size_tiles: int = 16
    layer_versions: dict[str, int] = field(default_factory=dict)
    dirty_all_layers: set[str] = field(default_factory=set)
    dirty_chunks: dict[str, set[tuple[int, int]]] = field(default_factory=dict)
    chunk_versions: dict[str, dict[tuple[int, int], int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.map_width = int(self.map_width)
        self.map_height = int(self.map_height)
        self.tile_width = int(self.tile_width)
        self.tile_height = int(self.tile_height)
        if int(self.chunk_size_tiles) <= 0:
            self.chunk_size_tiles = 16
        else:
            self.chunk_size_tiles = int(self.chunk_size_tiles)

    @property
    def map_pixel_height(self) -> int:
        return int(self.map_height * self.tile_height)

    @property
    def map_pixel_width(self) -> int:
        return int(self.map_width * self.tile_width)

    def mark_layer_dirty(self, layer_id: str) -> int:
        return self.mark_layer_dirty_all(layer_id)

    def mark_layer_dirty_all(self, layer_id: str) -> int:
        key = str(layer_id)
        version = int(self.layer_versions.get(key, 0)) + 1
        self.layer_versions[key] = version
        self.dirty_all_layers.add(key)
        self.dirty_chunks.pop(key, None)
        return version

    def mark_chunk_dirty(self, layer_id: str, chunk_x: int, chunk_y: int) -> None:
        if self.map_width <= 0 or self.map_height <= 0:
            return
        chunk_x = int(chunk_x)
        chunk_y = int(chunk_y)
        if chunk_x < 0 or chunk_y < 0:
            return
        max_chunk_x = max(0, (self.map_width - 1) // self.chunk_size_tiles)
        max_chunk_y = max(0, (self.map_height - 1) // self.chunk_size_tiles)
        if chunk_x > max_chunk_x or chunk_y > max_chunk_y:
            return
        key = str(layer_id)
        self.dirty_chunks.setdefault(key, set()).add((chunk_x, chunk_y))

    def mark_tile_dirty(self, layer_id: str, tile_x: int, tile_y: int) -> None:
        if self.map_width <= 0 or self.map_height <= 0:
            return
        tile_x = int(tile_x)
        tile_y = int(tile_y)
        if tile_x < 0 or tile_y < 0:
            return
        if tile_x >= self.map_width or tile_y >= self.map_height:
            return
        chunk_x = tile_x // self.chunk_size_tiles
        chunk_y = tile_y // self.chunk_size_tiles
        self.mark_chunk_dirty(layer_id, chunk_x, chunk_y)

    def mark_chunk_built(self, layer_id: str, chunk_x: int, chunk_y: int) -> None:
        key = str(layer_id)
        version = int(self.layer_versions.get(key, 0))
        chunk_map = self.chunk_versions.setdefault(key, {})
        chunk_map[(int(chunk_x), int(chunk_y))] = version

    def consume_dirty_flag(self, layer_id: str, chunk_x: int, chunk_y: int) -> bool:
        key = str(layer_id)
        chunk_key = (int(chunk_x), int(chunk_y))
        dirty_set = self.dirty_chunks.get(key)
        if dirty_set and chunk_key in dirty_set:
            dirty_set.discard(chunk_key)
            if not dirty_set:
                self.dirty_chunks.pop(key, None)
            return True
        if key in self.dirty_all_layers:
            version = int(self.layer_versions.get(key, 0))
            built = self.chunk_versions.get(key, {}).get(chunk_key, -1)
            return built < version
        return False

    def clear(self) -> None:
        self.layer_versions.clear()
        self.dirty_all_layers.clear()
        self.dirty_chunks.clear()
        self.chunk_versions.clear()

    def compute_visible_chunks(
        self,
        layer_id: str,
        rect: tuple[float, float, float, float],
        *,
        offset: tuple[float, float] = (0.0, 0.0),
    ) -> list[TileChunkKey]:
        if self.map_width <= 0 or self.map_height <= 0:
            return []
        if self.tile_width <= 0 or self.tile_height <= 0:
            return []

        left, bottom, right, top = (float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))
        if right < left:
            left, right = right, left
        if top < bottom:
            bottom, top = top, bottom

        offset_x, offset_y = float(offset[0]), float(offset[1])
        map_left = offset_x
        map_right = offset_x + self.map_pixel_width
        map_bottom = offset_y
        map_top = offset_y + self.map_pixel_height
        if right < map_left or left > map_right or top < map_bottom or bottom > map_top:
            return []

        col_min = int(math.floor((left - offset_x) / self.tile_width))
        col_max = int(math.floor((right - offset_x) / self.tile_width))
        row_min = int(math.floor((self.map_pixel_height + offset_y - top) / self.tile_height))
        row_max = int(math.floor((self.map_pixel_height + offset_y - bottom) / self.tile_height))

        col_min = max(0, min(self.map_width - 1, col_min))
        col_max = max(0, min(self.map_width - 1, col_max))
        row_min = max(0, min(self.map_height - 1, row_min))
        row_max = max(0, min(self.map_height - 1, row_max))
        if col_max < col_min or row_max < row_min:
            return []

        chunk_size = self.chunk_size_tiles
        chunk_x_min = col_min // chunk_size
        chunk_x_max = col_max // chunk_size
        chunk_y_min = row_min // chunk_size
        chunk_y_max = row_max // chunk_size

        keys: list[TileChunkKey] = []
        for chunk_y in range(chunk_y_min, chunk_y_max + 1):
            for chunk_x in range(chunk_x_min, chunk_x_max + 1):
                keys.append(
                    TileChunkKey(layer_id=str(layer_id), chunk_x=int(chunk_x), chunk_y=int(chunk_y))
                )
        return keys
