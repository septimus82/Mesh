from __future__ import annotations


def resize_grid(
    old_tiles: list[int],
    *,
    old_w: int,
    old_h: int,
    new_w: int,
    new_h: int,
    anchor: str = "tl",
    fill_tile: int = 0,
) -> list[int]:
    """Resize a flattened row-major tile grid, preserving content by anchor.

    Anchors:
    - tl: top-left
    - tr: top-right
    - bl: bottom-left
    - br: bottom-right
    """
    if old_w <= 0 or old_h <= 0:
        raise ValueError("old_w/old_h must be > 0")
    if new_w <= 0 or new_h <= 0:
        raise ValueError("new_w/new_h must be > 0")
    if len(old_tiles) != old_w * old_h:
        raise ValueError(f"old_tiles length mismatch: expected {old_w * old_h}, got {len(old_tiles)}")

    anchor_norm = str(anchor or "").strip().lower()
    if anchor_norm not in {"tl", "tr", "bl", "br"}:
        raise ValueError(f"invalid anchor: {anchor}")

    offset_x = 0
    offset_y = 0
    if anchor_norm in {"tr", "br"}:
        offset_x = int(new_w) - int(old_w)
    if anchor_norm in {"bl", "br"}:
        offset_y = int(new_h) - int(old_h)

    desired = int(fill_tile)
    new_tiles: list[int] = [desired] * (int(new_w) * int(new_h))

    for ny in range(int(new_h)):
        oy = ny - offset_y
        if oy < 0 or oy >= int(old_h):
            continue
        for nx in range(int(new_w)):
            ox = nx - offset_x
            if ox < 0 or ox >= int(old_w):
                continue
            new_tiles[ny * int(new_w) + nx] = old_tiles[oy * int(old_w) + ox]

    return new_tiles

