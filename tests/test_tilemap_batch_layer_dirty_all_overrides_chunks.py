from __future__ import annotations

from engine.tilemap_batch import TilemapBatchState


def test_tilemap_batch_layer_dirty_all_overrides_chunks() -> None:
    state = TilemapBatchState(map_width=32, map_height=32, tile_width=16, tile_height=16, chunk_size_tiles=8)
    state.mark_layer_dirty_all("layer")
    state.mark_chunk_dirty("layer", 1, 1)

    assert state.consume_dirty_flag("layer", 0, 0) is True
    state.mark_chunk_built("layer", 0, 0)
    assert state.consume_dirty_flag("layer", 0, 0) is False

    assert state.consume_dirty_flag("layer", 1, 1) is True
    state.mark_chunk_built("layer", 1, 1)
    assert state.consume_dirty_flag("layer", 1, 1) is False
