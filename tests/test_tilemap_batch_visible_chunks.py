from __future__ import annotations

from engine.tilemap_batch import TileChunkKey, TilemapBatchState


def test_tilemap_batch_visible_chunks() -> None:
    state = TilemapBatchState(map_width=32, map_height=32, tile_width=16, tile_height=16, chunk_size_tiles=8)
    rect = (0.0, 0.0, 64.0, 64.0)
    keys = state.compute_visible_chunks("layer", rect)
    assert keys == [TileChunkKey(layer_id="layer", chunk_x=0, chunk_y=3)]

    outside = state.compute_visible_chunks("layer", (600.0, 600.0, 700.0, 700.0))
    assert outside == []
