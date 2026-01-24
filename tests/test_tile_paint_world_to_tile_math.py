from __future__ import annotations


def test_world_to_tile_math_y_is_top_row() -> None:
    from engine.tile_paint_mode import world_to_tile

    # 10x10 tiles, 16px each.
    # Tile coords are (x, y) where y=0 is the top row.
    assert world_to_tile(map_width=10, map_height=10, tile_width=16, tile_height=16, world_x=0, world_y=0) == (0, 9)
    assert world_to_tile(map_width=10, map_height=10, tile_width=16, tile_height=16, world_x=15.9, world_y=0) == (0, 9)
    assert world_to_tile(map_width=10, map_height=10, tile_width=16, tile_height=16, world_x=16, world_y=0) == (1, 9)

    assert world_to_tile(map_width=10, map_height=10, tile_width=16, tile_height=16, world_x=0, world_y=16) == (0, 8)
    assert world_to_tile(map_width=10, map_height=10, tile_width=16, tile_height=16, world_x=0, world_y=159.9) == (0, 0)

    assert world_to_tile(map_width=10, map_height=10, tile_width=16, tile_height=16, world_x=-1, world_y=0) is None
    assert world_to_tile(map_width=10, map_height=10, tile_width=16, tile_height=16, world_x=0, world_y=-1) is None
    assert world_to_tile(map_width=10, map_height=10, tile_width=16, tile_height=16, world_x=0, world_y=160) is None

