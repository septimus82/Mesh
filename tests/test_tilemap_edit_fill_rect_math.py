from engine.tilemap_edit import TilemapDims, clear_rect, fill_rect


def test_tilemap_edit_fill_rect_inclusive_math():
    dims = TilemapDims(width=4, height=3)
    tiles = [0] * (dims.width * dims.height)

    changed = fill_rect(tiles, dims=dims, x0=1, y0=1, x1=2, y1=2, tile=5)
    assert changed is True

    # Expected filled coords: (1,1),(2,1),(1,2),(2,2)
    def idx(x: int, y: int) -> int:
        return y * dims.width + x

    for x, y in [(1, 1), (2, 1), (1, 2), (2, 2)]:
        assert tiles[idx(x, y)] == 5
    assert sum(1 for v in tiles if v == 5) == 4

    cleared = clear_rect(tiles, dims=dims, x0=2, y0=2, x1=2, y1=2)
    assert cleared is True
    assert tiles[idx(2, 2)] == 0

