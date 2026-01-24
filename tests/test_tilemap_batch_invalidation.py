from __future__ import annotations

from engine.tilemap_batch import TilemapBatchState


def test_tilemap_batch_invalidation() -> None:
    state = TilemapBatchState(map_width=8, map_height=8, tile_width=16, tile_height=16, chunk_size_tiles=4)
    version = state.mark_layer_dirty("floor")
    assert version == 1
    assert state.layer_versions["floor"] == 1
    assert "floor" in state.dirty_all_layers

    version = state.mark_layer_dirty("floor")
    assert version == 2
    assert state.layer_versions["floor"] == 2

    state.clear()
    assert state.layer_versions == {}
    assert state.dirty_all_layers == set()
