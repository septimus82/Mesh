from __future__ import annotations

from engine.tilemap_batch import TilemapBatchState


def test_tilemap_batch_dirty_chunk_consumption_ordered() -> None:
    state = TilemapBatchState(map_width=32, map_height=32, tile_width=16, tile_height=16, chunk_size_tiles=8)
    state.mark_chunk_dirty("layer", 1, 0)
    state.mark_chunk_dirty("layer", 0, 1)
    assert sorted(state.dirty_chunks["layer"]) == [(0, 1), (1, 0)]

    assert state.consume_dirty_flag("layer", 1, 0) is True
    assert state.consume_dirty_flag("layer", 1, 0) is False
    assert state.consume_dirty_flag("layer", 0, 1) is True
    assert state.consume_dirty_flag("layer", 0, 1) is False
    assert "layer" not in state.dirty_chunks
