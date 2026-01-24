from __future__ import annotations

from engine.tilemap_batch import TileChunkKey, TilemapBatchState


def test_tilemap_batch_ordering() -> None:
    state = TilemapBatchState(map_width=16, map_height=16, tile_width=10, tile_height=10, chunk_size_tiles=4)
    rect = (0.0, 81.0, 79.0, 160.0)
    keys = state.compute_visible_chunks("fg", rect)
    assert keys == [
        TileChunkKey(layer_id="fg", chunk_x=0, chunk_y=0),
        TileChunkKey(layer_id="fg", chunk_x=1, chunk_y=0),
        TileChunkKey(layer_id="fg", chunk_x=0, chunk_y=1),
        TileChunkKey(layer_id="fg", chunk_x=1, chunk_y=1),
    ]
