from __future__ import annotations


def test_line_of_sight_clear_blocked_mid_tile() -> None:
    from engine.pathfinding import NavGrid, line_of_sight_clear

    width, height = 5, 1
    blocked = {0 * width + 2}
    grid = NavGrid(width=width, height=height, tile_w=16, tile_h=16, blocked=frozenset(blocked))

    assert line_of_sight_clear((0, 0), (1, 0), grid) is True
    assert line_of_sight_clear((0, 0), (4, 0), grid) is False

