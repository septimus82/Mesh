from engine.tilemap_resize import resize_grid


def test_tilemap_resize_expand_anchor_tl():
    # old 2x2:
    # 1 2
    # 3 4
    old = [1, 2, 3, 4]
    new = resize_grid(old, old_w=2, old_h=2, new_w=3, new_h=3, anchor="tl", fill_tile=9)
    # Expect top-left preserved:
    # 1 2 9
    # 3 4 9
    # 9 9 9
    assert new == [1, 2, 9, 3, 4, 9, 9, 9, 9]


def test_tilemap_resize_shrink_anchor_br():
    # old 3x3:
    # 1 2 3
    # 4 5 6
    # 7 8 9
    old = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    new = resize_grid(old, old_w=3, old_h=3, new_w=2, new_h=2, anchor="br", fill_tile=0)
    # Keep bottom-right quadrant:
    # 5 6
    # 8 9
    assert new == [5, 6, 8, 9]

