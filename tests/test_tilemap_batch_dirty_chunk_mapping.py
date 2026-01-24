from __future__ import annotations

from engine.tilemap_batch import TilemapBatchState


def test_tilemap_batch_dirty_chunk_mapping() -> None:
    state = TilemapBatchState(map_width=64, map_height=64, tile_width=16, tile_height=16, chunk_size_tiles=16)
    state.mark_tile_dirty("layer", 0, 0)
    state.mark_tile_dirty("layer", 17, 2)
    state.mark_tile_dirty("layer", 31, 31)
    assert state.dirty_chunks["layer"] == {(0, 0), (1, 0), (1, 1)}
