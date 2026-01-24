from __future__ import annotations


def test_layer_cycle_is_sorted_and_wraps() -> None:
    from engine.tile_paint_mode import cycle_layer_id

    tile_layers = [{"id": "Walls"}, {"id": "Ground"}, {"id": "Deco"}]
    assert cycle_layer_id(tile_layers=tile_layers, current="", direction=1) == "Deco"
    assert cycle_layer_id(tile_layers=tile_layers, current="Deco", direction=1) == "Ground"
    assert cycle_layer_id(tile_layers=tile_layers, current="Walls", direction=1) == "Deco"
    assert cycle_layer_id(tile_layers=tile_layers, current="Deco", direction=-1) == "Walls"

